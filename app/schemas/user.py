from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    is_active: bool
    is_superuser: bool


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
