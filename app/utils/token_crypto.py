import base64
import hashlib
import json
from cryptography.fernet import Fernet, InvalidToken


def _build_fernet(secret_key: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode()).digest())
    return Fernet(key)


def encrypt_token(data: dict, secret_key: str) -> str:
    fernet = _build_fernet(secret_key)
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return fernet.encrypt(raw).decode("utf-8")


def decrypt_token(token: str, secret_key: str) -> dict:
    fernet = _build_fernet(secret_key)
    raw = fernet.decrypt(token.encode("utf-8"))
    return json.loads(raw.decode("utf-8"))