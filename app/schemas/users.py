import re

from fastapi_users import schemas
from pydantic import EmailStr, field_validator, TypeAdapter,BaseModel
from typing import Optional

email_adapter = TypeAdapter(EmailStr)

class UserRead(schemas.BaseUser[int]):
    pass


class UserCreate(schemas.BaseUserCreate):
    @field_validator("email", mode="after")
    @classmethod
    def validate_email(cls, email: str) -> str:
        if not email.isascii():
            raise ValueError("Email должен содержать только латинские символы")
        if any(ch.isspace() for ch in email):
            raise ValueError("Email не должен содержать пробелы")
        if len(email) > 255:
            raise ValueError("Email должен содержать не более 255 символов.")
        local_part = email.split("@", 1)[0]
        if len(local_part) > 64:
            raise ValueError(
                "Локальная часть email должна содержать не более 64 символов."
            )

        normalized_email = str(email_adapter.validate_python(email))
        domain = normalized_email.rsplit("@", 1)[1]
        if re.search(r"[А-Яа-яЁё]", domain):
            raise ValueError("Доменная часть email не должна содержать кириллицу.")
        
        return email

    @field_validator("password", mode="after")
    @classmethod
    def validate_password(cls, password: str) -> str:
        if any(ch.isspace() for ch in password):
            raise ValueError("Пароль не должен содержать пробелы")
        if 8 > len(password) or len(password) > 100:
            raise ValueError("Пароль должен быть более 8 и менее 100 символов")
        return password


class UserUpdate(schemas.BaseUserUpdate):
    pass


class UserBeforeVerify(UserRead):
    is_verified: bool = True

class UserMeUpdate(schemas.CreateUpdateDictModel):
    password: Optional[str] = None

class ResetPasswordRequest(BaseModel):
    token: str
    password: str

    @field_validator("password", mode="after")
    @classmethod
    def validate_password(cls, password: str) -> str:
        if any(ch.isspace() for ch in password):
            raise ValueError("Пароль не должен содержать пробелы")
        if 8 > len(password) or len(password) > 100:
            raise ValueError("Пароль должен быть более 8 и менее 100 символов")
        return password

