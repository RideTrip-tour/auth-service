import logging.config

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.middleware.login_form import limit_login_form_body
from app.routes.token import token_router
from app.schemas.users import (
    UserBeforeVerify,
    UserCreate,
    UserRead,
    UserUpdateEmail,
    UserUpdatePassword,
)
from app.services.users import auth_backend, fastapi_users
from app.utils.handler import remove_validation_input
from app.utils.logging import LOGGING_CONFIG
from config import settings

logging.config.dictConfig(LOGGING_CONFIG)

app = FastAPI(
    docs_url=f"/api/{settings.app_name.split('-')[0]}/docs",
    redoc_url=f"/api/{settings.app_name.split('-')[0]}/redoc",
    openapi_url=f"/api/{settings.app_name.split('-')[0]}/openapi.json",
)


app.middleware("http")(limit_login_form_body)


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(remove_validation_input(exc.errors()))},
    )


app.include_router(
    fastapi_users.get_auth_router(auth_backend), prefix="/api/auth", tags=["auth"]
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
    fastapi_users.get_users_router(
        backend=auth_backend,
        user_schema=UserRead,
        user_update_pass_schema=UserUpdatePassword,
        user_update_email_schema=UserUpdateEmail,
    ),
    prefix="/api/users",
    tags=["users"],
)

app.include_router(token_router, prefix="/api/auth", tags=["auth"])


@app.get(f"/api/{settings.app_name.split('-')[0]}/health")
async def health_check():
    return {"status": "ok"}
