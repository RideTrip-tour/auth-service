from dataclasses import dataclass
from enum import StrEnum

from fastapi_users import models
from pydantic import BaseModel

from app.utils.validators import EmailValidator, PasswordValidator


class ResetPass(BaseModel, PasswordValidator):
    password: str
    token: str


class EmailForgotPass(BaseModel, EmailValidator):
    email: str


class VerifyOperation(StrEnum):
    REGISTER = "register"
    CHANGE_EMAIL = "change_email"


@dataclass
class VerifyResult:
    user: models.UP
    operation: VerifyOperation
