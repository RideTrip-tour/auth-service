from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi_users.openapi import OpenAPIResponseType
from fastapi_users.router.common import ErrorCode, ErrorModel
from app.db.database import get_async_session
from app.db.models import RefreshToken
from app.services.users import (
    auth_backend,
    cookie_transport,
    get_strategy,
    get_user_manager,
)
from config import settings
from datetime import datetime, timedelta, timezone
from app.utils.token_crypto import encrypt_token
from app.services.email import send_email
from app.utils.token_crypto import decrypt_token
from cryptography.fernet import InvalidToken
from app.schemas.users import ResetPasswordRequest
from fastapi_users.password import PasswordHelper

token_router = APIRouter()
password_helper = PasswordHelper()

refresh_responses: OpenAPIResponseType = {
    status.HTTP_400_BAD_REQUEST: {
        "model": ErrorModel,
        "content": {
            "application/json": {
                "examples": {
                    ErrorCode.LOGIN_BAD_CREDENTIALS: {
                        "summary": "Bad credentials or the user is inactive.",
                        "value": {"detail": ErrorCode.LOGIN_BAD_CREDENTIALS},
                    },
                    ErrorCode.LOGIN_USER_NOT_VERIFIED: {
                        "summary": "The user is not verified.",
                        "value": {"detail": ErrorCode.LOGIN_USER_NOT_VERIFIED},
                    },
                }
            }
        },
    },
    status.HTTP_401_UNAUTHORIZED: {"description": "Missing token or inactive user."},
    **auth_backend.transport.get_openapi_login_responses_success(),
}


@token_router.post(
    "/refresh",
    name="token:refresh_token",
    responses=refresh_responses,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def refresh_token(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    refresh_token = request.cookies.get(settings.refresh_token_name)

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing token or inactive user.",
        )

    async with session.begin():
        result = await session.execute(
            select(RefreshToken)
            .options(selectinload(RefreshToken.user))
            .where(
                RefreshToken.token == refresh_token,
                RefreshToken.expires_at > datetime.now(timezone.utc),
            )
            .with_for_update()
        )

        db_token = result.scalars().first()

        if not db_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )

        await session.delete(db_token)

        new_refresh_token = RefreshToken.create(db_token.user_id)
        session.add(new_refresh_token)

    access_token = await get_strategy().write_token(db_token.user)

    return await cookie_transport.get_login_response(
        access_token, new_refresh_token.token
    )


@token_router.post("/forgot-password")
async def forgot_password(email: str):
    user = await get_user_manager.get_by_email(email)

    if not user:
        return {"message": "If user exists, email was sent"}  # не палим

    payload = {
        "user_id": str(user.id),
        "email": user.email,
        "type": "reset_password",
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=30)).timestamp()),
    }

    token = encrypt_token(payload, settings.secret_key)

    link = f"{settings.frontend_url}/reset-password?token={token}"

    await send_email(
        user.email,
        "Восстановление пароля",
        f"Перейдите по ссылке: {link}",
    )

    return {"message": "If user exists, email was sent"}


@token_router.post("/reset-password")
async def reset_password(data: ResetPasswordRequest, new_password: str):
    password = data.password
    token = data.token
    try:
        data = decrypt_token(token, settings.secret_key)
    except InvalidToken:
        raise HTTPException(status_code=400, detail="Invalid token")

    # проверка структуры
    if data.get("type") != "reset_password":
        raise HTTPException(status_code=400, detail="Invalid token")

    # проверка exp
    if data["exp"] < int(datetime.now(timezone.utc).timestamp()):
        raise HTTPException(status_code=400, detail="Token expired")

    user = await get_user_manager.get_by_email(data["email"])
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    hashed_password = password_helper.hash(new_password)

    user.hashed_password = hashed_password
    await get_user_manager.update(user)

    await send_email(
        user.email,
        "Пароль изменён",
        "Ваш пароль был успешно изменён",
    )

    return {"message": "Password updated"}
