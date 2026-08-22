from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi_users.openapi import OpenAPIResponseType
from fastapi_users.router.common import ErrorCode, ErrorModel

import app.services.audit as audit_service
from app.db.refresh_token_database import (
    SQLAlchemyRefreshTokenDatabase,
    get_refresh_token_db,
)
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
    refresh_token_db: SQLAlchemyRefreshTokenDatabase = Depends(get_refresh_token_db),
):
    refresh_token = request.cookies.get(settings.refresh_token_name)

    if not refresh_token:
        await audit_service.log_event(
            audit_service.AuditEventType.SESSION_ROTATE_FAILED,
            request=request,
            success=False,
            reason="missing_refresh_token",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing token or inactive user.",
        )

    async with refresh_token_db.session.begin():
        db_token = await refresh_token_db.get(
            refresh_token,
            with_user=True,
            with_for_update=True,
        )

        if not db_token:
            await audit_service.log_event(
                audit_service.AuditEventType.SESSION_ROTATE_FAILED,
                request=request,
                success=False,
                reason="invalid_or_expired_refresh_token",
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )

        await refresh_token_db.delete(db_token)
        new_refresh_token = await refresh_token_db.create(db_token.user_id)

    access_token = await get_strategy().write_token(db_token.user)
    await audit_service.log_event(
        audit_service.AuditEventType.SESSION_ROTATED,
        request=request,
        user_id=db_token.user_id,
        details={"refresh_token_id": getattr(new_refresh_token, "id", None)},
    )

    return await cookie_transport.get_login_response(
        access_token, new_refresh_token.token
    )
