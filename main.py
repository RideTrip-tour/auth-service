import logging.config

from fastapi import FastAPI

from app.routes.token import token_router
from app.schemas.users import UserBeforeVerify, UserCreate, UserRead
from app.services.users import auth_backend, fastapi_users, google_oauth_client
from app.utils.logging import LOGGING_CONFIG
from app.routes.users import router as users_router
from config import settings

logging.config.dictConfig(LOGGING_CONFIG)

app = FastAPI(
    docs_url="/api/auth/docs",
    redoc_url="/api/auth/redoc",
    openapi_url="/api/auth/openapi.json",
)

app.include_router(
    fastapi_users.get_auth_router(auth_backend), prefix="/api/auth", tags=["auth"]
)
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/api/auth",
    tags=["auth"],
)
app.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="/api/auth",
    tags=["auth"],
)
app.include_router(
    fastapi_users.get_verify_router(UserBeforeVerify),
    prefix="/api/auth",
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

app.include_router(users_router)


app.include_router(token_router, prefix="/api/auth", tags=["auth"])
