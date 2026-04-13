from typing import Any

from fastapi_users import exceptions


class InvalidEmailException(exceptions.FastAPIUsersException):
    def __init__(self, reason: Any) -> None:
        self.reason = reason
