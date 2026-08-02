from pydantic import BaseModel

from app.utils.validators import PasswordValidator


class ResetPass(BaseModel, PasswordValidator):
    password: str
    token: str