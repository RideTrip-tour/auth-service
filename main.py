import logging.config

from fastapi import FastAPI

from app.routes.token import token_router
from app.routes.users import get_users_router
from app.schemas.users import (
    UserBeforeVerify,
    UserCreate,
    UserRead,
    UserUpdateEmail,
    UserUpdatePassword,
)
from app.services.fastapi_users_instance import fastapi_users
from app.services.users import auth_backend, get_user_manager, google_oauth_client
from app.utils.logging import LOGGING_CONFIG
from config import settings

logging.config.dictConfig(LOGGING_CONFIG)

app = FastAPI(
    docs_url=f"/api/{settings.app_name.split('-')[0]}/docs",
    redoc_url=f"/api/{settings.app_name.split('-')[0]}/redoc",
    openapi_url=f"/api/{settings.app_name.split('-')[0]}/openapi.json",
)

app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/api/auth",
    tags=["auth"],
)

app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix=f"/api/{settings.app_name.split('-')[0]}",
    tags=["auth"],
)

app.include_router(
    fastapi_users.get_reset_password_router(),
    prefix=f"/api/{settings.app_name.split('-')[0]}",
    tags=["auth"],
)

app.include_router(
    fastapi_users.get_verify_router(UserBeforeVerify),
    prefix=f"/api/{settings.app_name.split('-')[0]}",
    tags=["auth"],
)

app.include_router(
    fastapi_users.get_oauth_router(
        google_oauth_client,
        auth_backend,
        settings.jwt_secret,
        associate_by_email=True,
        is_verified_by_default=True,
    ),
    prefix="/api/auth/google",
    tags=["auth"],
)

app.include_router(
    get_users_router(
        backend=auth_backend,
        get_user_manager=get_user_manager,
        user_schema=UserRead,
        user_update_pass_schema=UserUpdatePassword,
        user_update_email_schema=UserUpdateEmail,
        authenticator=fastapi_users.authenticator,
    ),
    prefix="/api/users",
    tags=["users"],
)

app.include_router(token_router, prefix="/api/auth", tags=["auth"])


@app.get(f"/api/{settings.app_name.split('-')[0]}/health")
async def health_check():
    return {"status": "ok"}