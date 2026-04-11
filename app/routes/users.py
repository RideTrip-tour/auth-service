from fastapi import APIRouter, Depends, Response, status, Request,HTTPException
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
    

    try:
        updated_user = await user_manager.update(
            user_update,
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


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    request: Request,
    user=Depends(current_active_user),
    user_manager=Depends(get_user_manager),
):
    await user_manager.delete(user, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
