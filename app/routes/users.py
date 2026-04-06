from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.users import UserMeUpdate, UserRead
from app.services.users import fastapi_users, get_user_manager
from fastapi_users import BaseUserManager
from fastapi_users.exceptions import InvalidPasswordException

router = APIRouter(prefix="/api/users", tags=["users"])

current_active_user = fastapi_users.current_user(active=True)


@router.get("/me", response_model=UserRead)
async def get_me(user=Depends(current_active_user)):
    return user


@router.patch("/me", response_model=UserRead)
async def update_me(
    user_update: UserMeUpdate,
    user=Depends(current_active_user),
    user_manager: BaseUserManager = Depends(get_user_manager),
):
    update_dict = user_update.create_update_dict()

    # Дополнительная защита:
    # даже если кто-то попытается руками подсунуть email/is_verified,
    # мы их выкинем.
    update_dict.pop("email", None)
    update_dict.pop("is_verified", None)
    update_dict.pop("is_superuser", None)
    update_dict.pop("is_active", None)

    try:
        updated_user = await user_manager.update(
            update_dict,
            user,
            safe=True,
            request=None,
        )
    except InvalidPasswordException:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid password",
        )

    return updated_user