from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi_users.openapi import OpenAPIResponseType
from fastapi_users.router.common import ErrorCode, ErrorModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_async_session
from app.db.models import RefreshToken
from app.services.users import auth_backend, cookie_transport, get_strategy
from config import settings

token_router = APIRouter()

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

    access_token = get_strategy().write_token(db_token.user)

    return await cookie_transport.get_login_response(
        access_token, new_refresh_token.token
    )
