import re

from typing import ClassVar
from pydantic import EmailStr, model_validator, TypeAdapter


email_adapter = TypeAdapter(EmailStr)


class PasswordValidator:
    password_fields: ClassVar[tuple[str, ...]] = ("password",)

    @model_validator(mode="after")
    def validate_password(self):
        for field in self.password_fields:
            password: str = getattr(self, field, None)
            if any(ch.isspace() for ch in password):
                raise ValueError("Пароль не должен содержать пробелы")
            if re.search(r"[А-Яа-яЁё]", password):
                raise ValueError("Пароль не должен содержать кириллицу")
            if 8 > len(password) or len(password) > 100:
                raise ValueError("Пароль должен быть более 8 и менее 100 символов")
        return self


class EmailValidator:
    email_fields: ClassVar[tuple[str, ...]] = ("email",)

    @model_validator(mode="before")
    @classmethod
    def normalize_email(cls, data):
        if not isinstance(data, dict):
            return data

        for field in cls.email_fields:
            email = data.get(field)
            if isinstance(email, str):
                data[field] = email.lower()
        return data

    @model_validator(mode="after")
    def validate_email(self):
        for field in self.email_fields:
            email: str = getattr(self, field, None)
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
            
            if len(domain) > 189:
                raise ValueError(
                    "Доменная часть email должна содержать не более 189 символов."
                )
        
        return self