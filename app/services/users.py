import logging
from typing import Generic

import jwt
from fastapi import APIRouter, Depends, Request
from fastapi_users import (BaseUserManager, FastAPIUsers, IntegerIDMixin,
                           exceptions, models, schemas)
from fastapi_users.authentication import (AuthenticationBackend,
                                          CookieTransport, JWTStrategy,
                                          Strategy)
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.jwt import decode_jwt, generate_jwt
from httpx_oauth.clients.google import GoogleOAuth2

from app.db.database import get_user_db
from app.db.models import User
from app.routes.register import get_register_router, get_verify_router
from app.services.email import send_email
from config import settings

logger = logging.getLogger("users")


SECRET = settings.jwt_secret

google_oauth_client = GoogleOAuth2(
    settings.google_oauth_client_id,
    settings.google_oauth_client_secret,
)


class JWTStrategyCustom(JWTStrategy):
    """Переопределяет payload JWT"""

    token_audience: list[str] = ([settings.gateway_name],)

    async def write_token(self, user: models.UP) -> str:
        data = {
            "sub": str(user.id),
            "is_active": bool(user.is_verified),
            "is_superuser": bool(user.is_superuser),
            "aud": self.token_audience,
        }
        return generate_jwt(
            data, self.encode_key, self.lifetime_seconds, algorithm=self.algorithm
        )


class FastAPIUsersCustomRegister(
    FastAPIUsers[models.UP, models.ID], Generic[models.UP, models.ID]
):
    """Переопределяет Регистрацию пользователя"""

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


class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET
    verification_token_lifetime_seconds = 10 * 60  #  Токен живет 10 минут.

    async def on_after_register(self, user: User, request: Request | None = None):
        logger.info(f"Пользователь {user.id} Зарегистрировался.")

    async def on_after_forgot_password(
        self, user: User, token: str, request: Request | None = None
    ):
        logger.info(
            f"Пользователь {user.id} Запросил сброс пользователя. Токен: {token}"
        )

    async def on_after_request_verify(
        self, user: User, token: str, request: Request | None = None
    ):
        logger.info(
            f"Пользователь {user.id} запросил активацию аккаунта. Токен: {token}"
        )

    async def on_before_register(self, user_dict: dict, request: Request | None = None):
        """
        Отправляем cсылку для подтверждения регистрации пользователю.

        В сылку включаем токен, в котором лежит необходимая информация
        для регистрации пользователя.
        """
        user_dict["aud"] = self.verification_token_audience
        verify_token = generate_jwt(
            user_dict,
            self.verification_token_secret,
            self.verification_token_lifetime_seconds,
        )
        link = f"{settings.origin}/{settings.lk_path}?verufy_token={verify_token}"
        await send_email(
            user_dict["email"],
            "Подтвержжение регистрации",
            f"""
            Доброго времени суток!

            Для подтверждения регистрации перейдите по ссылке: {link}
            """,
        )
        logger.info(
            "Пользователь запросил регистрацию, отправлено письмо на почту %s.",
            user_dict["email"],
        )

    async def verify(self, token: str, request: Request | None = None) -> models.UP:
        """Проверяем токен на валидность и создаем пользователя"""
        try:
            data = decode_jwt(
                token,
                self.verification_token_secret,
                [self.verification_token_audience],
            )
            logger.info(f"Данные из токена: {data}")
        except jwt.PyJWTError:
            raise exceptions.InvalidVerifyToken()

        try:
            aud = data.pop("aud")
            email = data["email"]
            data.pop("exp")
        except KeyError:
            raise exceptions.InvalidVerifyToken()

        if aud != self.verification_token_audience:
            raise exceptions.InvalidVerifyToken()

        existing_user = await self.user_db.get_by_email(email)
        if existing_user is not None:
            raise exceptions.UserAlreadyExists()

        data["is_verified"] = True

        created_user = await self.user_db.create(data)

        return created_user


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    yield UserManager(user_db)


cookie_transport = CookieTransport(
    cookie_name="access_token",
    cookie_max_age=settings.access_token_expire_sec,
)


def get_strategy() -> Strategy[models.UP, models.ID]:
    return JWTStrategyCustom(
        secret=SECRET, lifetime_seconds=settings.access_token_expire_sec
    )


auth_backend = AuthenticationBackend(
    name="cookie",
    transport=cookie_transport,
    get_strategy=get_strategy,
)

fastapi_users = FastAPIUsersCustomRegister[User, int](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)
