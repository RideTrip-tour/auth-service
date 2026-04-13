from fastapi_users import schemas
from pydantic import field_validator, Field


class UserRead(schemas.BaseUser[int]):
    pass


class UserCreate(schemas.BaseUserCreate):
    password: str = Field(min_length=8, max_length=100)

    @field_validator("email", mode="after")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if not value.isascii():
            raise ValueError("Email address must contain only Latin (ASCII) characters")

        parts = value.rsplit("@", 1)
        if len(parts) != 2:
            raise ValueError("Invalid email format")

        local_part, domain_part = parts

        if len(domain_part) > 189:
            raise ValueError("Domain part of email must not exceed 189 characters")

        if domain_part.startswith(".") or domain_part.endswith("."):
            raise ValueError("Invalid domain part")

        labels = domain_part.split(".")
        if any(not label for label in labels):
            raise ValueError("Invalid domain part")

        if any(len(label) > 63 for label in labels):
            raise ValueError("Each domain label must not exceed 63 characters")

        return value

    @field_validator("password", mode="after")
    @classmethod
    def validate_password_spaces(cls, value: str) -> str:
        if value.startswith(" ") or value.endswith(" "):
            raise ValueError("Password cannot start or end with spaces")
        return value


class UserUpdate(schemas.BaseUserUpdate):
    pass

class UserBeforeVerify(UserRead):
    is_verified: bool = True