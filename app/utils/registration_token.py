import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from config import settings


class InvalidRegistrationToken(ValueError):
    pass


def _get_registration_token_secret() -> str:
    return settings.registration_token_encryption_secret or settings.jwt_secret


def _get_fernet() -> Fernet:
    secret = _get_registration_token_secret()
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_registration_token(token: str) -> str:
    return _get_fernet().encrypt(token.encode("utf-8")).decode("ascii")


def decrypt_registration_token(token: str) -> str:
    try:
        return _get_fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeEncodeError) as exc:
        raise InvalidRegistrationToken() from exc
