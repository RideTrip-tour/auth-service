from pydantic import BaseModel

from app.utils.validators import EmailValidator, PasswordValidator


class ResetPass(BaseModel, PasswordValidator):
    password: str
    token: str


class EmailForgotPass(BaseModel, EmailValidator):
    email: str
