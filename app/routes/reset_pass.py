from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi_limiter.depends import RateLimiter
from fastapi_users import exceptions, models
from fastapi_users.manager import BaseUserManager, UserManagerDependency
from fastapi_users.openapi import OpenAPIResponseType
from fastapi_users.router.common import ErrorCode, ErrorModel
from pyrate_limiter import Duration, Limiter, Rate

from app.dependencies.cache import get_cache_manager
from app.schemas.reset_pass import EmailForgotPass, ResetPass
from app.services.cache import CacheManager

RESET_PASSWORD_RESPONSES: OpenAPIResponseType = {
    status.HTTP_400_BAD_REQUEST: {
        "model": ErrorModel,
        "content": {
            "application/json": {
                "examples": {
                    ErrorCode.RESET_PASSWORD_BAD_TOKEN: {
                        "summary": "Bad or expired token.",
                        "value": {"detail": ErrorCode.RESET_PASSWORD_BAD_TOKEN},
                    },
                    ErrorCode.RESET_PASSWORD_INVALID_PASSWORD: {
                        "summary": "Password validation failed.",
                        "value": {
                            "detail": {
                                "code": ErrorCode.RESET_PASSWORD_INVALID_PASSWORD,
                                "reason": "Password should be at least 3 characters",
                            }
                        },
                    },
                }
            }
        },
    },
}


def get_reset_password_router(
    get_user_manager: UserManagerDependency[models.UP, models.ID],
) -> APIRouter:
    """Generate a router with the reset password routes."""
    router = APIRouter()

    @router.post(
        "/forgot-password",
        status_code=status.HTTP_202_ACCEPTED,
        name="reset:forgot_password",
        dependencies=[
            Depends(
                RateLimiter(
                    limiter=Limiter(
                        Rate(5, Duration.SECOND * 5)
                    )  # Пять запросов в 5 сек
                )
            )
        ],
    )
    async def forgot_password(
        request: Request,
        email_forgot_pass: EmailForgotPass,
        user_manager: BaseUserManager[models.UP, models.ID] = Depends(get_user_manager),
        cache: CacheManager = Depends(get_cache_manager),
    ):
        email = email_forgot_pass.email.strip().lower()
        cooldown_key = f"auth:service:forgot-password:cooldown:{email}"

        allowed = await cache.acquire_cooldown(
            cooldown_key,
        )

        if not allowed:
            return

        try:
            user = await user_manager.get_by_email(email_forgot_pass.email)
        except exceptions.UserNotExists:
            return

        try:
            await user_manager.forgot_password(user, request)
        except exceptions.UserInactive:
            pass

    @router.post(
        "/reset-password",
        name="reset:reset_password",
        responses=RESET_PASSWORD_RESPONSES,
        dependencies=[
            Depends(
                RateLimiter(
                    limiter=Limiter(
                        Rate(5, Duration.SECOND * 5)
                    )  # Пять запросов в 5 сек
                )
            )
        ],
    )
    async def reset_password(
        request: Request,
        reset_pass_schema: ResetPass,
        user_manager: BaseUserManager[models.UP, models.ID] = Depends(get_user_manager),
    ):
        try:
            await user_manager.reset_password(
                reset_pass_schema.token, reset_pass_schema.password, request
            )
        except (
            exceptions.InvalidResetPasswordToken,
            exceptions.UserNotExists,
            exceptions.UserInactive,
        ) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.RESET_PASSWORD_BAD_TOKEN,
            ) from exc
        except exceptions.InvalidPasswordException as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": ErrorCode.RESET_PASSWORD_INVALID_PASSWORD,
                    "reason": exc.reason,
                },
            ) from exc

    return router
