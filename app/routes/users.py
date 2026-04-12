import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi_users import exceptions, models, schemas
from fastapi_users.authentication import AuthenticationBackend, Authenticator, Strategy
from fastapi_users.jwt import generate_jwt
from fastapi_users.manager import BaseUserManager, UserManagerDependency
from fastapi_users.router.common import ErrorCode, ErrorModel

from app.schemas.users import StatusResponse
from app.services.email import send_email
from config import settings

logger = logging.getLogger("users.routes")

def get_users_router(
    backend: AuthenticationBackend[models.UP, models.ID],
    get_user_manager: UserManagerDependency[models.UP, models.ID],
    user_schema: type[schemas.U],
    user_update_pass_schema: type[schemas.CreateUpdateDictModel],
    user_update_email_schema: type[schemas.CreateUpdateDictModel],
    authenticator: Authenticator[models.UP, models.ID],
    requires_verification: bool = False,
) -> APIRouter:
    """Generate a router with the authentication routes."""
    router = APIRouter()

    get_current_active_user = authenticator.current_user(
        active=True, verified=requires_verification
    )

    async def get_user_or_404(
        id: str,
        user_manager: BaseUserManager[models.UP, models.ID] = Depends(get_user_manager),
    ) -> models.UP:
        try:
            parsed_id = user_manager.parse_id(id)
            return await user_manager.get(parsed_id)
        except (exceptions.UserNotExists, exceptions.InvalidID) as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from e

    @router.get(
        "/me",
        response_model=user_schema,
        name="users:current_user",
        responses={
            status.HTTP_401_UNAUTHORIZED: {
                "description": "Missing token or inactive user.",
            },
        },
    )
    async def me(
        user: models.UP = Depends(get_current_active_user),
    ):
        return user_schema.model_validate(user)

    @router.post(
        "/me/change-password",
        response_model=StatusResponse,
        dependencies=[Depends(get_current_active_user)],
        name="users:patch_pass_current_user",
        responses={
            status.HTTP_401_UNAUTHORIZED: {
                "description": "Missing token or inactive user.",
            },
            status.HTTP_400_BAD_REQUEST: {
                "model": ErrorModel,
                "content": {
                    "application/json": {
                        "examples": {
                            ErrorCode.UPDATE_USER_EMAIL_ALREADY_EXISTS: {
                                "summary": "A user with this email already exists.",
                                "value": {
                                    "detail": ErrorCode.UPDATE_USER_EMAIL_ALREADY_EXISTS
                                },
                            },
                            ErrorCode.UPDATE_USER_INVALID_PASSWORD: {
                                "summary": "Password validation failed.",
                                "value": {
                                    "detail": {
                                        "code": ErrorCode.UPDATE_USER_INVALID_PASSWORD,
                                        "reason": "Password should be"
                                        "at least 3 characters",
                                    }
                                },
                            },
                        }
                    }
                },
            },
        },
    )
    async def change_password(
        request: Request,
        user_update_pass_schema: user_update_pass_schema,  # type: ignore
        user: models.UP = Depends(get_current_active_user),
        user_manager: BaseUserManager[models.UP, models.ID] = Depends(get_user_manager),
        strategy: Strategy[models.UP, models.ID] = Depends(backend.get_strategy),
    ):
        if not await user_manager.verify_password(
            user_update_pass_schema.current_password, user.hashed_password
            ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.RESET_PASSWORD_INVALID_PASSWORD,
                )
        await user_manager.update(user_update_pass_schema, user)
        await user_manager.on_after_reset_password(user, request)
        refresh_token = request.cookies.get(settings.refresh_token_name)
        await backend.logout(strategy, user, refresh_token or "")
        await strategy.destroy_tokens_by_user(user)
        return {"status": "Пароль обновлен, нужна повторная авторизация"}
    
    @router.post(
        "/me/request-change-email",
        response_model=StatusResponse,
        dependencies=[Depends(get_current_active_user)],
        name="users:patch_email_current_user",
        responses={
            status.HTTP_401_UNAUTHORIZED: {
                "description": "Missing token or inactive user.",
            },
            status.HTTP_400_BAD_REQUEST: {
                "model": ErrorModel,
                "content": {
                    "application/json": {
                        "examples": {
                            ErrorCode.UPDATE_USER_EMAIL_ALREADY_EXISTS: {
                                "summary": "A user with this email already exists.",
                                "value": {
                                    "detail": ErrorCode.UPDATE_USER_EMAIL_ALREADY_EXISTS
                                },
                            },
                            ErrorCode.UPDATE_USER_INVALID_PASSWORD: {
                                "summary": "Password validation failed.",
                                "value": {
                                    "detail": {
                                        "code": ErrorCode.UPDATE_USER_INVALID_PASSWORD,
                                        "reason": "Password should be"
                                        "at least 3 characters",
                                    }
                                },
                            },
                        }
                    }
                },
            },
        },
    )
    async def request_change_email(
        request: Request,
        user_update_email_schema: user_update_email_schema,  # type: ignore
        user: models.UP = Depends(get_current_active_user),
        user_manager: BaseUserManager[models.UP, models.ID] = Depends(get_user_manager),
    ):
        if not await user_manager.verify_password(
            user_update_email_schema.password, user.hashed_password
            ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.LOGIN_BAD_CREDENTIALS,
                )
        if user.email != user_update_email_schema.current_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.LOGIN_BAD_CREDENTIALS,
                )
        if await user_manager.get_by_email(user_update_email_schema.new_email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.REGISTER_USER_ALREADY_EXISTS,
                )
        
        data = {
            'sub': str(user.id),
            'new_email': user_update_email_schema.new_email,
            'current_email': user_update_email_schema.current_email,
            'type': 'change_email',
            'aud': user_manager.verification_token_audience,
        }
        token = generate_jwt(
            data,
            user_manager.verification_token_secret,
            user_manager.verification_token_lifetime_seconds,
        )
        link = f"{settings.origin}/{settings.lk_path}?verify_token={token}"

        await send_email(
            user.email,
            "Подтвержжение смены адреса электроного ящика",
            f"""
            Доброго времени суток!

            Для подтверждения смены электроного ящика перейдите по ссылке: {link}
            """,
        )
        logger.info(
            "Пользователь запросил измнение email, отправлено письмо на почту %s.",
            user.email,
        )
        return {"status": "Подтвержение смены email отправлено, тербуется подтверждение."}
    return router
