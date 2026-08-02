import logging
import secrets
from datetime import datetime
from textwrap import dedent
from typing import Generic
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from fastapi_users import (
    BaseUserManager,
    FastAPIUsers,
    IntegerIDMixin,
    exceptions,
    models,
    schemas,
)
from fastapi_users.authentication import (
    AuthenticationBackend,
    Authenticator,
    CookieTransport,
    JWTStrategy,
    Strategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.jwt import decode_jwt, generate_jwt
from httpx_oauth.clients.google import GoogleOAuth2
from pydantic import EmailStr, TypeAdapter
from sqlalchemy import update as sqlalchemy_update

from app.db.database import AsyncSessionLocal, get_user_db
from app.db.email_change_request_database import SQLAlchemyEmailChangeRequestDatabase
from app.db.models import User
from app.db.refresh_token_database import SQLAlchemyRefreshTokenDatabase
from app.routes.auth import get_auth_router
from app.routes.register import get_register_router, get_verify_router
from app.routes.reset_pass import get_reset_password_router
from app.routes.users import get_users_router
import app.services.audit as audit_service
from app.services.email import send_email
from app.schemas.reset_pass import ResetPass
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


class JWTStrategyCustom(JWTStrategy):
    """Переопределяет payload JWT"""

    async def write_token(self, user: models.UP) -> str:
        data = {
            "sub": str(user.id),
            "is_active": bool(user.is_verified),
            "is_superuser": bool(user.is_superuser),
            "aud": settings.gateway_name,
        }
        return generate_jwt(
            data, self.encode_key, self.lifetime_seconds, algorithm=self.algorithm
        )

    async def destroy_token(self, token: str, user: models.UP) -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                token_db = SQLAlchemyRefreshTokenDatabase(session)
                if token:
                    await token_db.delete_by_token(token)

    async def destroy_tokens_by_user(self, user: models.UP) -> None:
        async with AsyncSessionLocal() as session:
            if user:
                async with session.begin():
                    token_db = SQLAlchemyRefreshTokenDatabase(session)
                    await token_db.delete_by_user_id(user.id)


class FastAPIUsersCustom(
    FastAPIUsers[models.UP, models.ID], Generic[models.UP, models.ID]
):
    """Переопределенный FastAPIUsers"""

    def __init__(self, get_user_manager, auth_backends):
        super().__init__(get_user_manager, auth_backends)
        self.authenticator = CustomAuthenticator(auth_backends, get_user_manager)
        self.current_user = self.authenticator.current_user

    def get_register_router(
        self, user_schema: type[schemas.U], user_create_schema: type[schemas.UC]
    ) -> APIRouter:
        """
        Return a router with a register route.

        :param user_schema: Pydantic schema of a public user.
        :param user_create_schema: Pydantic schema for creating a user.
        """
        return get_register_router(
            self.get_user_manager, user_schema, user_create_schema
        )

    def get_verify_router(self, user_schema: type[schemas.U]) -> APIRouter:
        """
        Return a router with e-mail verification routes.

        :param user_schema: Pydantic schema of a public user.
        """
        return get_verify_router(self.get_user_manager, user_schema)

    def get_auth_router(
        self,
        backend: AuthenticationBackend[models.UP, models.ID],
        requires_verification: bool = False,
    ) -> APIRouter:
        """
        Return an auth router for a given authentication backend.

        :param backend: The authentication backend instance.
        :param requires_verification: Whether the authentication
        require the user to be verified or not. Defaults to False.
        """
        return get_auth_router(
            backend,
            self.get_user_manager,
            self.authenticator,
            requires_verification,
        )

    def get_users_router(
        self,
        backend: AuthenticationBackend[models.UP, models.ID],
        user_schema: type[schemas.U],
        user_update_pass_schema: type[schemas.CreateUpdateDictModel],
        user_update_email_schema: type[schemas.CreateUpdateDictModel],
        requires_verification: bool = False,
    ) -> APIRouter:
        """
        Return a router with routes to manage users.

        :param user_schema: Pydantic schema of a public user.
        :param user_update_schema: Pydantic schema for updating a user.
        :param requires_verification: Whether the endpoints
        require the users to be verified or not. Defaults to False.
        """
        return get_users_router(
            backend,
            self.get_user_manager,
            user_schema,
            user_update_pass_schema,
            user_update_email_schema,
            self.authenticator,
            requires_verification,
        )

    def get_reset_password_router(self, reset_pass_schema: ResetPass) -> APIRouter:
        """Return a reset password process router."""
        return get_reset_password_router(self.get_user_manager, reset_pass_schema)
    
class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    reset_password_token_secret = SECRET
    reset_password_token_lifetime_seconds = (
        settings.reset_password_token_lifetime_seconds
    )
    verification_token_secret = SECRET
    verification_token_lifetime_seconds = settings.verification_token_lifetime_seconds
    change_email_token_lifetime_seconds = settings.change_email_token_lifetime_seconds
    chage_eamil_token_audience = "fastapi-users:change_email"

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
            f"{settings.origin.rstrip('/')}/{settings.lk_path.lstrip('/')}"
            f"?{urlencode({'verify_token': verify_token})}"
        )
        await send_email(
            user_dict["email"],
            "Подтверждение регистрации",
            f"""
            Доброго времени суток!

            Для подтверждения регистрации перейдите по ссылке: {link}
            """,
        )
        logger.info(
            "Пользователь запросил регистрацию, отправлено письмо на почту %s.",
            user_dict["email"],
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

    async def verify(self, token: str, request: Request | None = None) -> models.UP:
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

        if type_operation == "register":
            created_user = await self.register_user(data)
            return created_user

        if type_operation == "change_email":
            data["token"] = token
            await self._validate_change_email_request(token, data)
            response = await self.change_email(data)
            await self.on_after_change_email(
                response,
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
            return response
        raise exceptions.InvalidVerifyToken()

    async def register_user(self, data: dict) -> models.UP:
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
        return


class CookieTransportCustom(CookieTransport):
    refresh_token_name = settings.refresh_token_name
    access_cookie_max_age = settings.access_token_expire_sec
    refresh_cookie_max_age = settings.refresh_token_expire_sec
    refresh_cookie_path = settings.refresh_token_path
    access_cookie_path = "/"

    async def get_login_response(
        self,
        access_token: str,
        refresh_token: str | None = None,
    ) -> Response:
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        response = self._set_access_cookie(response, access_token)
        if refresh_token:
            response = self._set_refresh_cookie(response, refresh_token)
        else:
            logger.warning("Refresh token не установлен!")
        return response

    async def get_logout_response(self) -> Response:
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        self._clear_access_cookie(response)
        self._clear_refresh_cookie(response)
        return response

    def _set_refresh_cookie(self, response, refresh_token):
        logger.info(
            f"Установка {self.refresh_token_name} cookie: path={self.refresh_cookie_path}"
        )
        response.set_cookie(
            key=self.refresh_token_name,
            value=refresh_token,
            httponly=True,
            secure=not settings.debug,
            samesite="lax",
            max_age=self.refresh_cookie_max_age,
            path=self.refresh_cookie_path,
        )
        logger.info("Установлен refresh token")
        return response

    def _set_access_cookie(self, response: Response, token: str) -> Response:
        logger.info(
            f"Установка {self.cookie_name} cookie: path={self.access_cookie_path}"
        )
        response.set_cookie(
            key=self.cookie_name,
            value=token,
            max_age=self.access_cookie_max_age,
            path=self.access_cookie_path,
            secure=not settings.debug,
            httponly=True,
            samesite=self.cookie_samesite,
        )
        return response

    def _clear_access_cookie(self, response: Response) -> None:
        response.set_cookie(
            key=self.cookie_name,
            value="",
            max_age=0,
            path=self.access_cookie_path,
            domain=self.cookie_domain,
            secure=not settings.debug,
            httponly=True,
            samesite=self.cookie_samesite,
        )

    def _clear_refresh_cookie(self, response: Response) -> None:
        response.set_cookie(
            key=self.refresh_token_name,
            value="",
            httponly=True,
            secure=not settings.debug,
            samesite="lax",
            max_age=0,
            path=self.refresh_cookie_path,
        )


class CustomAuthenticator(Authenticator[User, int]):
    async def _authenticate(
        self,
        *args,
        user_manager: UserManager,
        optional: bool = False,
        active: bool = False,
        verified: bool = False,
        superuser: bool = False,
        **kwargs,
    ):
        if superuser:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        return await super()._authenticate(
            *args,
            user_manager=user_manager,
            optional=optional,
            active=active,
            verified=verified,
            superuser=superuser,
            **kwargs,
        )


class AuthenticationBackendCustom(AuthenticationBackend[User, int]):
    def __init__(self, *args, session_factory, **kwargs):
        super().__init__(*args, **kwargs)
        self.session_factory = session_factory

    async def login(
        self,
        strategy: Strategy[models.UP, models.ID],
        user: models.UP,
    ) -> Response:
        access_token = await strategy.write_token(user)

        async with self.session_factory() as session:
            async with session.begin():
                token_db = SQLAlchemyRefreshTokenDatabase(session)
                refresh_token = await token_db.create(user.id)
        await audit_service.log_event(
            audit_service.AuditEventType.SESSION_CREATED,
            user_id=user.id,
            details={"refresh_token_id": getattr(refresh_token, "id", None)},
        )
        return await self.transport.get_login_response(
            access_token, refresh_token.token
        )


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    yield UserManager(user_db)


cookie_transport = CookieTransportCustom(
    cookie_name="access_token",
    cookie_max_age=settings.access_token_expire_sec,
)


def get_strategy() -> Strategy[models.UP, models.ID]:
    return JWTStrategyCustom(
        secret=SECRET,
        lifetime_seconds=settings.access_token_expire_sec,
        token_audience=settings.gateway_name,
    )


auth_backend = AuthenticationBackendCustom(
    name="cookie",
    transport=cookie_transport,
    get_strategy=get_strategy,
    session_factory=AsyncSessionLocal,
)

fastapi_users = FastAPIUsersCustom[User, int](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)
