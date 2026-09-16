import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_users import exceptions
from fastapi_users.manager import BaseUserManager
from sqlalchemy import select

from app.db.database import get_async_session
from app.db.models import User
from app.schemas.users import UserCreate, UserUpdate
from app.services.users import fastapi_users, get_user_manager

logger = logging.getLogger("admin.routes")

admin_routes = APIRouter(dependencies=
[Depends(fastapi_users.current_user(active=True,superuser=True))])



@admin_routes.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,


 
)
async def user_delete(id: int,user_manager: BaseUserManager = Depends(get_user_manager)):
    try:
        user = await user_manager.get(id)
        await user_manager.delete(user)
        return 
    except exceptions.UserNotExists:
        raise HTTPException(status_code=404,detail="Пользователь не найден")

@admin_routes.patch(
    "/{id}",
    status_code=status.HTTP_200_OK,
    )
async def user_update(id: int,user_update: UserUpdate, user_manager: BaseUserManager = Depends(get_user_manager)):
    try:
        user = await user_manager.get(id)
        updated = await user_manager.update(user_update,user)
        return updated
    except exceptions.UserNotExists:
        raise HTTPException(status_code=404,detail="Пользователь не найден")
    
@admin_routes.post(
    "/",
    status_code = status.HTTP_201_CREATED
)
async def user_create(user: UserCreate,user_manager: BaseUserManager = Depends(get_user_manager)):
    try:
        new_user = await user_manager.create(user)
        return new_user

    except exceptions.UserAlreadyExists:
        raise HTTPException(status_code=400,detail="Не удалось создать пользователя")
    
@admin_routes.get(
    "/",
    status_code = status.HTTP_200_OK
)
async def get_user(id: int | None = None,email: str | None = None,session = Depends(get_async_session)):
    query = select(User)
    if id is not None:
        query = query.filter(User.id == id)
    if email is not None:
        query = query.filter(User.email == email)
    
    result = await session.execute(query)
    users = result.scalars().all()
    return users




