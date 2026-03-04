from fastapi_users import schemas
from pydantic import field_validator,Field

class UserRead(schemas.BaseUser[int]):
    pass


class UserCreate(schemas.BaseUserCreate):
    password: str = Field(min_length=8, max_length=100)
    @field_validator("email", mode="after")
    @classmethod
    def validate_email_ascii(cls, value: str) -> str:
        if not value.isascii():
            raise ValueError("Email address must contain only Latin (ASCII) characters")
        return value

    @field_validator("password", mode="after")
    @classmethod
    def validate_password_spaces(cls, value: str) -> str:
        if value.startswith(" ") or value.endswith(" "):
            raise ValueError("Password cannot start or end with spaces")
        return value


class UserUpdate(schemas.BaseUserUpdate):
    pass
