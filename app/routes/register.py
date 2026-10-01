import logging
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from fastapi_users import exceptions, models, schemas
from fastapi_users.authentication import AuthenticationBackend, Strategy
from fastapi_users.manager import UserManagerDependency
from fastapi_users.password import PasswordHelper
from fastapi_users.router.common import ErrorCode, ErrorModel

from app.db.models import User
from app.schemas.reset_pass import VerifyOperation
from app.schemas.users import UserCreate
from app.services.user_manager import UserManagerDep

password_helper = PasswordHelper()
logger = logging.getLogger("users.register")


def get_register_router(
    get_user_manager: UserManagerDependency[models.UP, models.ID],
    user_schema: type[schemas.U],
    user_create_schema: type[schemas.UC],
) -> APIRouter:
    """Generate a router with the register route."""
    router = APIRouter()

    @router.post(
        "/register",
        status_code=status.HTTP_204_NO_CONTENT,
        name="register:register",
        responses={
            status.HTTP_400_BAD_REQUEST: {
                "model": ErrorModel,
                "content": {
                    "application/json": {
                        "examples": {
                            ErrorCode.REGISTER_USER_ALREADY_EXISTS: {
                                "summary": "A user with this email already exists.",
                                "value": {
                                    "detail": ErrorCode.REGISTER_USER_ALREADY_EXISTS
                                },
                            },
                            ErrorCode.REGISTER_INVALID_PASSWORD: {
                                "summary": "Password validation failed.",
                                "value": {
                                    "detail": {
                                        "code": ErrorCode.REGISTER_INVALID_PASSWORD,
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
    async def register(
        request: Request,
        user_create: UserCreate,
        user_manager: UserManagerDep,
    ):
        """
        Не регирируем пользователя сразу,
        создаем данные для регистрации и валидируем их
        """
        existing_user = await user_manager.user_db.get_by_email(user_create.email)
        if existing_user is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.REGISTER_USER_ALREADY_EXISTS,
            )
        try:
            await user_manager.validate_password(user_create.password, user_create)
        except exceptions.InvalidPasswordException as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": ErrorCode.REGISTER_INVALID_PASSWORD,
                    "reason": exc.reason,
                },
            ) from exc

        user_dict = user_create.create_update_dict()
        password = user_dict.pop("password")
        user_dict["hashed_password"] = password_helper.hash(password)

        await user_manager.on_before_register(user_dict, request)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


def get_verify_router(
    get_user_manager: UserManagerDependency[models.UP, models.ID],
    backend: AuthenticationBackend[User, int],
    user_schema: type[schemas.U],
):
    router = APIRouter()

    @router.post(
        "/verify",
        response_model=user_schema,
        name="verify:verify",
        responses={
            status.HTTP_400_BAD_REQUEST: {
                "model": ErrorModel,
                "content": {
                    "application/json": {
                        "examples": {
                            ErrorCode.VERIFY_USER_BAD_TOKEN: {
                                "summary": "Bad token, not existing user or"
                                "not the e-mail currently set for the user.",
                                "value": {"detail": ErrorCode.VERIFY_USER_BAD_TOKEN},
                            },
                            ErrorCode.VERIFY_USER_ALREADY_VERIFIED: {
                                "summary": "The user is already verified.",
                                "value": {
                                    "detail": ErrorCode.VERIFY_USER_ALREADY_VERIFIED
                                },
                            },
                        }
                    }
                },
            }
        },
    )
    async def verify(
        request: Request,
        token: Annotated[str, Body(..., embed=True)],
        user_manager: UserManagerDep,
        strategy: Annotated[Strategy[User, int], Depends(backend.get_strategy)],
    ):
        try:
            result = await user_manager.verify(token, request)
            if result.operation == VerifyOperation.REGISTER:
                return await backend.login(strategy, result.user)

            return user_schema.model_validate(result.user)
        except (exceptions.InvalidVerifyToken, exceptions.UserNotExists) as exc:
            logger.exception(ErrorCode.VERIFY_USER_BAD_TOKEN)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.VERIFY_USER_BAD_TOKEN,
            ) from exc
        except (exceptions.UserAlreadyVerified, exceptions.UserAlreadyExists) as exc:
            logger.exception(ErrorCode.VERIFY_USER_ALREADY_VERIFIED)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.VERIFY_USER_ALREADY_VERIFIED,
            ) from exc

    return router
