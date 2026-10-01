import logging

from fastapi import APIRouter, HTTPException, Response, status
from fastapi_users import (
    BaseUserManager,
    FastAPIUsers,
    models,
    schemas,
)
from fastapi_users.authentication import (
    AuthenticationBackend,
    Authenticator,
    CookieTransport,
    Strategy,
)
from httpx_oauth.clients.google import GoogleOAuth2
from pydantic import EmailStr, TypeAdapter

import app.services.audit as audit_service
from app.db.database import AsyncSessionLocal
from app.db.models import User
from app.db.refresh_token_database import SQLAlchemyRefreshTokenDatabase
from app.routes.auth import get_auth_router
from app.routes.register import get_register_router, get_verify_router
from app.routes.reset_pass import get_reset_password_router
from app.routes.users import get_users_router
from app.schemas.users import UserUpdateEmail, UserUpdatePassword
from app.services.jwt import get_strategy
from app.services.user_manager import get_user_manager
from config import settings

logger = logging.getLogger("users.servises")
email_adapter = TypeAdapter(EmailStr)


SECRET = settings.jwt_secret

google_oauth_client = GoogleOAuth2(
    settings.google_oauth_client_id,
    settings.google_oauth_client_secret,
)


class FastAPIUsersCustom(FastAPIUsers[User, int]):
    """Переопределенный FastAPIUsers"""

    def __init__(self, get_user_manager, auth_backends):
        super().__init__(get_user_manager, auth_backends)
        self.authenticator = CustomAuthenticator(auth_backends, get_user_manager)  # type: ignore[assignment]
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

    def get_verify_router(  # type: ignore[override]
        self,
        backend: AuthenticationBackend[User, int],
        user_schema: type[schemas.U],
    ) -> APIRouter:
        """
        Return a router with e-mail verification routes.

        :param user_schema: Pydantic schema of a public user.
        """
        return get_verify_router(self.get_user_manager, backend, user_schema)

    def get_auth_router(  # type: ignore[override]
        self,
        backend: AuthenticationBackend[User, int],
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

    def get_users_router(  # type: ignore[override]
        self,
        backend: AuthenticationBackend[User, int],
        user_schema: type[schemas.U],
        user_update_pass_schema: type[UserUpdatePassword],
        user_update_email_schema: type[UserUpdateEmail],
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

    def get_reset_password_router(self) -> APIRouter:
        """Return a reset password process router."""
        return get_reset_password_router(self.get_user_manager)


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
        user_manager: BaseUserManager[User, int],
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
    transport: CookieTransportCustom

    def __init__(self, *args, session_factory, **kwargs):
        super().__init__(*args, **kwargs)
        self.session_factory = session_factory

    async def login(
        self,
        strategy: Strategy[models.UP, models.ID],
        user: models.UP,
    ) -> Response:
        access_token = await strategy.write_token(user)

        async with self.session_factory() as session, session.begin():
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


cookie_transport = CookieTransportCustom(
    cookie_name="access_token",
    cookie_max_age=settings.access_token_expire_sec,
)

auth_backend = AuthenticationBackendCustom(
    name="cookie",
    transport=cookie_transport,
    get_strategy=get_strategy,
    session_factory=AsyncSessionLocal,
)

fastapi_users = FastAPIUsersCustom(get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)
