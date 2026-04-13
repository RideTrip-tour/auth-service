from typing import Generic

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi_users import FastAPIUsers, models
from fastapi_users.manager import BaseUserManager
from fastapi_users.router.common import ErrorCode

from app.schemas.password import ForgotPasswordRequest, ResetPasswordRequest


class FastAPIUsersCustomRegister(
    FastAPIUsers[models.UP, models.ID],
    Generic[models.UP, models.ID],
):
    def get_reset_password_router(self) -> APIRouter:
        router = APIRouter()

        @router.post(
            "/forgot-password",
            status_code=status.HTTP_202_ACCEPTED,
            summary="Request password reset",
        )
        async def forgot_password(
            request: Request,
            payload: ForgotPasswordRequest = Body(...),
            user_manager: BaseUserManager[models.UP, models.ID] = Depends(
                self.get_user_manager
            ),
        ) -> dict[str, str]:
            user = await user_manager.get_by_email(payload.email)

            if user is not None and user.is_active:
                await user_manager.forgot_password(user, request)

            return {
                "message": "If the email exists, reset instructions have been sent."
            }

        @router.post(
            "/reset-password",
            status_code=status.HTTP_200_OK,
            summary="Reset password",
        )
        async def reset_password(
            request: Request,
            payload: ResetPasswordRequest = Body(...),
            user_manager: BaseUserManager[models.UP, models.ID] = Depends(
                self.get_user_manager
            ),
        ) -> dict[str, str]:
            try:
                await user_manager.reset_password(
                    payload.token,
                    payload.password,
                    request,
                )
            except Exception as exc:
                # при желании можешь сузить до fastapi-users specific exceptions
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ErrorCode.RESET_PASSWORD_BAD_TOKEN,
                ) from exc

            return {"message": "Password updated successfully."}

        return router