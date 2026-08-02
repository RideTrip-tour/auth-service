from typing import ClassVar
from fastapi_users import schemas
from pydantic import BaseModel, Field, model_validator
from typing import Annotated

from app.utils.validators import EmailValidator, PasswordValidator


class UserRead(schemas.BaseUser[int]):
    id: Annotated[int, Field(gt=0, le=2147483647)]


class UserCreate(schemas.BaseUserCreate, EmailValidator, PasswordValidator):
    is_superuser: bool = False


class UserUpdatePassword(schemas.CreateUpdateDictModel, PasswordValidator):
    password_fields: ClassVar[tuple[str, ...]] = ("new_password", "current_password")
    current_password: str
    new_password: str

    @model_validator(mode="after")
    def passwords_must_differ(self):
        if self.current_password == self.new_password:
            raise ValueError("Новый пароль не должен совпадать с текущим")
        return self
    
    def create_update_dict(self):
        return {'password': self.new_password}
    
    def create_update_dict_superuser(self):
        return self.create_update_dict()

class UserUpdateEmail(schemas.CreateUpdateDictModel, PasswordValidator, EmailValidator):
    email_fields: ClassVar[tuple[str, ...]] = ("new_email", 'current_email')
    current_email: str
    new_email: str
    password: str

    @model_validator(mode="after")
    def passwords_must_differ(self):
        if self.current_email == self.new_email:
            raise ValueError("Новый email не должен совпадать с текущим")
        return self


class UserBeforeVerify(UserRead):
    is_verified: bool = True


class StatusResponse(BaseModel):
    status: str
