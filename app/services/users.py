import logging
from typing import Generic, Optional

from fastapi import APIRouter, Depends, Response, Request, status,HTTPException
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
from fastapi_users.jwt import generate_jwt
from httpx_oauth.clients.google import GoogleOAuth2
from datetime import datetime, timedelta, timezone
from app.utils.token_crypto import encrypt_token
from cryptography.fernet import InvalidToken
from app.utils.token_crypto import decrypt_token
from pydantic import EmailStr, TypeAdapter

from app.db.database import AsyncSessionLocal, get_user_db
from app.db.models import User
from app.db.refresh_token_database import SQLAlchemyRefreshTokenDatabase
from app.routes.auth import get_auth_router
from app.routes.register import get_register_router, get_verify_router
from app.routes.users import get_users_router
from app.services.email import send_email
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

    async def destroy_token(
        self, token: str, user: models.UP
    ) -> None:
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
    
class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET
    verification_token_lifetime_seconds = 60 * 60  #  Токен живет 1 час.
    chage_eamil_token_audience = 'fastapi-users:change_email'

    async def on_after_register(self, user: User, request: Request | None = None):
        logger.info(f"Пользователь {user.id} Зарегистрировался.")

    async def on_after_forgot_password(
        self,
        user: User,
        token: str,
        request: Optional[Request] = None,
    ) -> None:
        reset_link = f"{settings.frontend_url}/reset-password?token={token}"

        await send_email(
            user.email,
            "Восстановление пароля",
            f"Перейдите по ссылке: {reset_link}",
        )


    async def validate_password(
        self,
        password: str,
        user: User | None = None,
    ) -> None:
        if len(password) < 8:
            raise ValueError("Пароль должен содержать минимум 8 символов")

    async def on_after_request_verify(
        self, user: User, token: str, request: Request | None = None
    ):
        logger.info(
            f"Пользователь {user.id} запросил активацию аккаунта. Токен: {token}"
        )

    async def on_before_register(self, user_dict: dict, request: Request | None = None):
        payload = {
            **user_dict,
            "aud": self.verification_token_audience,
            "exp": int(
                (
                    datetime.now(timezone.utc)
                    + timedelta(seconds=self.verification_token_lifetime_seconds)
                ).timestamp()
            ),
        }

        verify_token = encrypt_token(payload, settings.jwt_secret)

        link = f"{settings.origin}/{settings.lk_path}?verify_token={verify_token}"

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

    async def verify(self, token: str, request: Request | None = None) -> models.UP:
        try:
            data = decrypt_token(token, settings.jwt_secret)
            logger.info(f"Данные из токена: {data}")
        except InvalidToken:
            raise exceptions.InvalidVerifyToken()

        try:
            aud = data.pop("aud")
            email = data["email"]
            exp = data.pop("exp")
        except KeyError:
            raise exceptions.InvalidVerifyToken()

        if aud != self.verification_token_audience:
            raise exceptions.InvalidVerifyToken()

        now_ts = int(datetime.now(timezone.utc).timestamp())
        if exp < now_ts:
            raise exceptions.InvalidVerifyToken()

        existing_user = await self.user_db.get_by_email(email)
        if existing_user is not None:
            raise exceptions.UserAlreadyExists()

        data["is_verified"] = True
        created_user = await self.user_db.create(data)
        return created_user
    
    async def change_email(self, data: dict):
        new_email = data["new_email"]
        current_email = data["current_email"]
        user = await self.user_db.get_by_email(current_email)
        if user is None:
            raise exceptions.UserNotExists()
        existing_user = await self.user_db.get_by_email(new_email)
        if existing_user is not None:
            raise exceptions.UserAlreadyExists()
        
        updated_user = await self.user_db.update(user, {'email': new_email})
        return updated_user
        
    async def create(self, user_create, safe=False, request=None):
        user_create.is_superuser = False
        return await super().create(user_create, safe, request)
    
    async def update(self, user_update, user, safe=False, request=None):
        if hasattr(user_update, "is_superuser"):
            user_update.is_superuser = False
        return await super().update(user_update, user, safe, request)

    async def on_after_reset_password(
        self, user: models.UP, request: Request | None = None
    ) -> None:
        await send_email(
            user.email,
            "Пароль успешно изменен.",
            """
            Доброго времени суток!

            Ваш пароль успешно изменен
            """,
        )
        logger.info(
            f"Пользователь {user.id} обновbл пароль."
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
