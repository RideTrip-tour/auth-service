import logging
import secrets
from datetime import datetime
from textwrap import dedent
from typing import Annotated
from urllib.parse import urlencode

import jwt
from fastapi import Depends, HTTPException, Request, Response
from fastapi_users import (
    BaseUserManager,
    IntegerIDMixin,
    exceptions,
    models,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.jwt import decode_jwt, generate_jwt
from httpx_oauth.clients.google import GoogleOAuth2
from pydantic import EmailStr, TypeAdapter
from sqlalchemy import update as sqlalchemy_update

import app.services.audit as audit_service
from app.clients.gateway_client import GatewayClient
from app.db.database import get_user_db
from app.db.email_change_request_database import SQLAlchemyEmailChangeRequestDatabase
from app.db.models import User
from app.dependencies.cache import get_cache_manager
from app.schemas.reset_pass import VerifyOperation, VerifyResult
from app.services.cache import CacheManager
from app.services.email import send_email
from app.utils.registration_token import (
    InvalidRegistrationToken,
    decrypt_registration_token,
    encrypt_registration_token,
)
from config import settings

logger = logging.getLogger("users.servises")
email_adapter = TypeAdapter(EmailStr)


SECRET = settings.jwt_secret

google_oauth_client = GoogleOAuth2(
    settings.google_oauth_client_id,
    settings.google_oauth_client_secret,
)


class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    reset_password_token_secret = SECRET
    reset_password_token_lifetime_seconds = (
        settings.reset_password_token_lifetime_seconds
    )
    verification_token_secret = SECRET
    verification_token_lifetime_seconds = settings.verification_token_lifetime_seconds
    change_email_token_lifetime_seconds = settings.change_email_token_lifetime_seconds
    chage_eamil_token_audience = "fastapi-users:change_email"

    def __init__(self, user_db: SQLAlchemyUserDatabase, cache_manager: CacheManager):
        super().__init__(user_db)
        self.cache_manager = cache_manager
        self.gateway_client = GatewayClient()

    @staticmethod
    def _build_password_recovery_link(token: str) -> str:
        recovery_url = (
            f"{settings.origin.rstrip('/')}/"
            f"{settings.password_recovery_path.lstrip('/')}"
        )
        return (
            f"{recovery_url}{'&' if '?' in recovery_url else '?'}"
            f"{urlencode({'token': token})}"
        )

    @staticmethod
    def _mask_email(email: str) -> str:
        local_part, separator, domain = email.partition("@")
        if not separator:
            return email
        visible_local_part = local_part[:1] or "*"
        return f"{visible_local_part}***@{domain}"

    @staticmethod
    def _format_lifetime(seconds: int) -> str:
        if seconds % 3600 == 0:
            hours = seconds // 3600
            if hours % 10 == 1 and hours % 100 != 11:
                unit = "час"
            elif 2 <= hours % 10 <= 4 and not 12 <= hours % 100 <= 14:
                unit = "часа"
            else:
                unit = "часов"
            return f"{hours} {unit}"

        if seconds % 60 == 0:
            minutes = seconds // 60
            if minutes % 10 == 1 and minutes % 100 != 11:
                unit = "минуту"
            elif 2 <= minutes % 10 <= 4 and not 12 <= minutes % 100 <= 14:
                unit = "минуты"
            else:
                unit = "минут"
            return f"{minutes} {unit}"

        return f"{seconds} секунд"

    def _generate_password_recovery_token(self, user: models.UP) -> str:
        return generate_jwt(
            {
                "sub": str(user.id),
                "password_fgpt": self.password_helper.hash(user.hashed_password),
                "aud": self.reset_password_token_audience,
            },
            self.reset_password_token_secret,
            self.reset_password_token_lifetime_seconds,
        )

    async def on_after_register(self, user: User, request: Request | None = None):
        logger.info(f"Пользователь {user.id} Зарегистрировался.")
        await audit_service.log_event(
            audit_service.AuditEventType.REGISTERED,
            request=request,
            user_id=user.id,
        )

    async def on_after_forgot_password(
        self, user: User, token: str, request: Request | None = None
    ):
        recovery_link = self._build_password_recovery_link(token)
        recovery_link_lifetime = self._format_lifetime(
            self.reset_password_token_lifetime_seconds
        )
        await send_email(
            user.email,
            "Восстановление доступа",
            dedent(
                f"""
                Здравствуйте!

                Вы запросили восстановление доступа к аккаунту в сервисе «3шагадо».

                Чтобы установить новый пароль, перейдите по ссылке:

                {recovery_link}

                Ссылка действует {recovery_link_lifetime}.

                Если вы не запрашивали восстановление доступа, просто проигнорируйте это письмо.

                Если у вас возникли вопросы, напишите нам: {settings.support_email}

                — Команда «3шагадо»
                """
            ).strip(),
            html=False,
        )
        logger.info(
            "Пользователь %s запросил сброс пароля.",
            user.id,
        )
        await audit_service.log_event(
            audit_service.AuditEventType.PASSWORD_RESET_REQUESTED,
            request=request,
            user_id=user.id,
            details={"token_length": len(token)},
        )

    async def on_after_request_verify(
        self, user: User, token: str, request: Request | None = None
    ):
        logger.info(
            f"Пользователь {user.id} запросил активацию аккаунта. Токен: {token}"
        )
        await audit_service.log_event(
            audit_service.AuditEventType.VERIFICATION_REQUESTED,
            request=request,
            user_id=user.id,
            details={"token_length": len(token)},
        )

    async def on_before_register(self, user_dict: dict, request: Request | None = None):
        """
        Отправляем cсылку для подтверждения регистрации пользователю.

        В cсылку включаем зашифрованный токен, в котором лежит необходимая
        информация для регистрации пользователя.
        """
        user_dict["aud"] = self.verification_token_audience
        user_dict["type"] = "register"
        signed_token = generate_jwt(
            user_dict,
            self.verification_token_secret,
            self.verification_token_lifetime_seconds,
        )
        verify_token = encrypt_registration_token(signed_token)
        link = (
            f"{settings.origin.rstrip('/')}/auth/verify"
            f"?{urlencode({'verify_token': verify_token})}"
        )
        link_lifetime = self._format_lifetime(self.verification_token_lifetime_seconds)
        await send_email(
            user_dict["email"],
            "Подтвердите email - и поехали 🏔️",
            f"""
            <html>
                <body>
                    <p>Привет!</p>

                    <p>
                        Мы рады, что вы решили присоединиться к «3шагадо». Осталось совсем немного - подтвердите адрес электронной почты, чтобы завершить регистрацию.<br>
                        <a href="{link}">Подтвердить email</a><br>
                        Ссылка действует {link_lifetime}. Если она истечёт, новую можно будет запросить при следующем входе.<br>
                        Если вы не регистрировались в «3шагадо», просто проигнорируйте это письмо. Ничего не произойдёт.<br>
                        А если что-то пошло не так - напишите нам: support@3shagado.ru<br>
                        <br>
                        <br>
                        Команда «3шагадо»
                    </p>
                </body>
            </html>
            """,
        )
        logger.info(
            "Пользователь запросил регистрацию, отправлено письмо на почту %s.",
            user_dict["email"],
        )

    @staticmethod
    def _get_register_notice_key(email: str) -> str:
        normalized_email = email.strip().lower()
        return f"auth:register_notice:{normalized_email}"

    async def send_existing_email_notice(
        self,
        email: str,
    ) -> None:
        """Уведомляем о попытке регистрации на существующий email."""

        if not await self.cache_manager.acquire_cooldown(
            self._get_register_notice_key(email=email), ttl=300
        ):
            logger.info(
                "Уведомление о повторной регистрации пропущено: достигнут лимит отправки."
            )
            return
        await send_email(
            email,
            "Попытка регистрации — 3шагадо",
            """
            <html>
                <body>
                    <p>
                        Кто-то пытался зарегистрироваться с вашим email.
                        Если это были вы — войдите в аккаунт или сбросьте пароль.
                        Если нет — проигнорируйте это письмо.
                        <br>
                        <br>
                        Команда «3шагадо»
                    </p>
                </body>
            </html>
            """,
        )
        logger.info(
            "Отправлено уведомление о попытке регистрации на существующий email."
        )

    async def on_after_verify(
        self, user: models.UP, request: Request | None = None
    ) -> None:
        link = f"{settings.origin.rstrip('/')}/profile"
        await send_email(
            user.email,
            "Добро пожаловать в «3шагадо» 🏔️",
            f"""
            <html>
                <body>
                    <p>Привет!</p>

                    <p>
                        Регистрация подтверждена — теперь вы с нами.<br>
                        Собрать поездку, пройти тест на уровень, сохранить варианты в избранное — всё это уже можно сделать на сайте.<br>
                        Сейчас в «3шагадо» только горнолыжные курорты. Но мы уже работаем над новыми горизонтами.<br>
                        Переходите по <a href="{link}">по ссылке</a> и планируйте в удовольствие! 🏔️<br>
                        <br>
                        <br>
                        Команда «3шагадо»
                    </p>
                </body>
            </html>
            """,
        )

    async def create_change_email_verification_token(
        self,
        *,
        user: models.UP,
        current_email: str,
        new_email: str,
    ) -> str:
        data = {
            "sub": str(user.id),
            "new_email": new_email,
            "current_email": current_email,
            "type": "change_email",
            "aud": self.verification_token_audience,
            "jti": secrets.token_urlsafe(16),
        }
        token = generate_jwt(
            data,
            self.verification_token_secret,
            self.change_email_token_lifetime_seconds,
        )

        session = getattr(self.user_db, "session", None)
        if session is not None:
            token_db = SQLAlchemyEmailChangeRequestDatabase(session)
            await token_db.replace_for_user(
                user_id=user.id,
                current_email=current_email,
                new_email=new_email,
                token=token,
                lifetime_seconds=self.change_email_token_lifetime_seconds,
            )

        return token

    async def _validate_change_email_request(self, token: str, data: dict) -> None:
        session = getattr(self.user_db, "session", None)
        if session is None:
            return

        token_db = SQLAlchemyEmailChangeRequestDatabase(session)
        request = await token_db.get_valid(token)
        if request is None:
            raise exceptions.InvalidVerifyToken()
        try:
            user_id = int(data["sub"])
        except (KeyError, TypeError, ValueError):
            raise exceptions.InvalidVerifyToken()
        current_email = data.get("current_email")
        new_email = data.get("new_email")
        if (
            request.user_id != user_id
            or request.current_email != current_email
            or request.new_email != new_email
        ):
            raise exceptions.InvalidVerifyToken()

    async def _delete_change_email_request(self, token: str) -> None:
        session = getattr(self.user_db, "session", None)
        if session is None:
            return

        token_db = SQLAlchemyEmailChangeRequestDatabase(session)
        await token_db.delete_by_token(token)

    async def verify(  # type: ignore[override]
        self, token: str, request: Request | None = None
    ) -> VerifyResult[User]:
        """Проверяем токен на валидность и создаем пользователя"""
        decoded_token = token
        try:
            decoded_token = decrypt_registration_token(token)
        except InvalidRegistrationToken:
            pass

        try:
            data = decode_jwt(
                decoded_token,
                self.verification_token_secret,
                [self.verification_token_audience],
            )
        except jwt.PyJWTError:
            raise exceptions.InvalidVerifyToken()

        try:
            aud = data.pop("aud")
            type_operation = data.pop("type")
            data.pop("exp")
        except KeyError:
            raise exceptions.InvalidVerifyToken()

        if aud != self.verification_token_audience:
            raise exceptions.InvalidVerifyToken()

        if type_operation == VerifyOperation.REGISTER:
            created_user = await self.register_user(data)
            try:
                await self.gateway_client.create_profile(created_user)
            except Exception as exc:
                logger.exception(
                    "Не удалось создать профиль для пользователя user_id=%s. "
                    "Выполняется удаление пользователя.",
                    created_user.id,
                )
                await audit_service.log_event(
                    audit_service.AuditEventType.VERIFY_SUCCES,
                    details={"verify_fail": getattr(created_user, "email", None)},
                )
                await self.user_db.delete(created_user)
                raise HTTPException(
                    status_code=400, detail="Fail create profile"
                ) from exc
            await audit_service.log_event(
                audit_service.AuditEventType.VERIFY_SUCCES,
                user_id=created_user.id,
                details={"verify_account": getattr(created_user, "id", None)},
            )
            return VerifyResult(user=created_user, operation=VerifyOperation.REGISTER)

        if type_operation == VerifyOperation.CHANGE_EMAIL:
            data["token"] = token
            await self._validate_change_email_request(token, data)
            user = await self.change_email(data)
            await self.on_after_change_email(
                user,
                current_email=data["current_email"],
                new_email=data["new_email"],
                request=request,
            )
            user_id = data.get("sub")
            await audit_service.log_event(
                audit_service.AuditEventType.CHANGE_COMPLETED,
                request=request,
                user_id=int(user_id) if user_id is not None else None,
                details={
                    "change_type": "email",
                    "current_email": data.get("current_email"),
                    "new_email": data.get("new_email"),
                },
            )
            return VerifyResult(user=user, operation=VerifyOperation.CHANGE_EMAIL)
        raise exceptions.InvalidVerifyToken()

    async def register_user(self, data: dict) -> User:
        email = data["email"]
        existing_user = await self.user_db.get_by_email(email)
        if existing_user is not None:
            raise exceptions.UserAlreadyExists()

        data["is_verified"] = True

        created_user = await self.user_db.create(data)
        return created_user

    async def change_email(self, data: dict):
        new_email = data["new_email"]
        current_email = data["current_email"]
        token = data.get("token")
        user = await self.user_db.get_by_email(current_email)
        if user is None:
            raise exceptions.UserNotExists()
        existing_user = await self.user_db.get_by_email(new_email)
        if existing_user is not None:
            raise exceptions.UserAlreadyExists()

        updated_user = await self.user_db.update(user, {"email": new_email})
        if token:
            await self._delete_change_email_request(token)
        return updated_user

    async def on_after_change_email(
        self,
        user: models.UP,
        *,
        current_email: str,
        new_email: str,
        request: Request | None = None,
    ) -> None:
        changed_at = datetime.now().astimezone().strftime("%d.%m.%Y %H:%M %Z")
        password_recovery_link = self._build_password_recovery_link(
            self._generate_password_recovery_token(user)
        )
        password_recovery_link_lifetime = self._format_lifetime(
            self.reset_password_token_lifetime_seconds
        )
        await send_email(
            current_email,
            "Email аккаунта изменен",
            dedent(
                f"""
                Здравствуйте!

                Адрес электронной почты, привязанный к вашему аккаунту в сервисе «3шагадо», был успешно изменён.

                Дата и время изменения: {changed_at}

                Предыдущий адрес: {self._mask_email(current_email)}
                Новый адрес: {self._mask_email(new_email)}

                Если это были вы — никаких дополнительных действий не требуется.

                Если вы не меняли адрес электронной почты, рекомендуем как можно скорее сменить пароль от аккаунта и обратиться в поддержку для проверки безопасности аккаунта.

                Сменить пароль: {password_recovery_link}

                Ссылка для смены пароля действует {password_recovery_link_lifetime}.

                Если у вас остались вопросы, напишите нам:

                {settings.support_email}

                Мы поможем проверить безопасность аккаунта и восстановить доступ при необходимости.

                Команда «3шагадо»
                """
            ).strip(),
            html=False,
        )
        await send_email(
            new_email,
            "Email аккаунта изменен",
            dedent(
                f"""
                Здравствуйте!

                Этот адрес электронной почты был указан как новый адрес для аккаунта в сервисе «3шагадо».

                Дата и время изменения: {changed_at}

                Если это были вы — никаких дополнительных действий не требуется.

                Если вы не запрашивали это изменение, напишите нам:

                {settings.support_email}

                Команда «3шагадо»
                """
            ).strip(),
            html=False,
        )
        logger.info(
            "Пользователь %s сменил email с %s на %s.",
            user.id,
            current_email,
            new_email,
        )

    async def on_after_login(
        self,
        user: models.UP,
        request: Request | None = None,
        response: Response | None = None,
    ) -> None:
        await audit_service.log_event(
            audit_service.AuditEventType.LOGIN_SUCCESS,
            request=request,
            user_id=user.id,
        )

    async def create(self, user_create, safe=False, request=None):
        user_create.is_superuser = False
        return await super().create(user_create, safe, request)

    async def update(self, user_update, user, safe=False, request=None):
        if hasattr(user_update, "is_superuser"):
            user_update.is_superuser = False
        return await super().update(user_update, user, safe, request)

    async def change_password(
        self,
        user: User,
        current_password: str,
        new_password: str,
        request: Request | None = None,
    ) -> User | None:
        valid_password, _ = self.password_helper.verify_and_update(
            current_password,
            user.hashed_password,
        )
        if not valid_password:
            return None

        await self.validate_password(new_password, user)
        new_hashed_password = self.password_helper.hash(new_password)

        session = getattr(self.user_db, "session", None)
        user_table = getattr(self.user_db, "user_table", None)
        if session is None or user_table is None:
            raise RuntimeError("Atomic password update requires SQLAlchemy user DB")

        result = await session.execute(
            sqlalchemy_update(user_table)
            .where(user_table.id == user.id)
            .where(user_table.hashed_password == user.hashed_password)
            .values(hashed_password=new_hashed_password)
        )
        if result.rowcount != 1:
            await session.rollback()
            return None

        await session.commit()
        await session.refresh(user)
        await self.on_after_update(
            user,
            {"hashed_password": new_hashed_password},
            request,
        )
        return user

    async def on_after_reset_password(
        self, user: models.UP, request: Request | None = None
    ) -> None:
        current_user = await self.get(user.id) if hasattr(self.user_db, "get") else user
        recovery_token = self._generate_password_recovery_token(current_user)
        changed_at = datetime.now().astimezone().strftime("%d.%m.%Y %H:%M %Z")
        recovery_link = self._build_password_recovery_link(recovery_token)
        recovery_link_lifetime = self._format_lifetime(
            self.reset_password_token_lifetime_seconds
        )
        await send_email(
            user.email,
            "Пароль успешно изменен",
            dedent(
                f"""
                Здравствуйте!

                Пароль от вашего аккаунта в сервисе «3шагадо» был успешно изменён.

                Дата и время изменения: {changed_at}

                Если это были вы — никаких дополнительных действий не требуется.

                Если вы не меняли пароль, рекомендуем как можно скорее восстановить доступ к аккаунту и установить новый пароль:

                Восстановить доступ: {recovery_link}

                Ссылка для восстановления действует {recovery_link_lifetime}.

                Также рекомендуем:
                • проверить безопасность вашей электронной почты;
                • завершить активные сессии на других устройствах в настройках аккаунта.

                Если у вас возникли вопросы, напишите нам: {settings.support_email}

                — Команда «3шагадо»
                """
            ).strip(),
            html=False,
        )
        logger.info("Пользователь %s обновил пароль.", user.id)
        await audit_service.log_event(
            audit_service.AuditEventType.CHANGE_COMPLETED,
            request=request,
            user_id=user.id,
            details={"change_type": "password"},
        )


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
    cache_manager: CacheManager = Depends(get_cache_manager),
):
    yield UserManager(user_db, cache_manager=cache_manager)


UserManagerDep = Annotated[UserManager, Depends(get_user_manager)]
