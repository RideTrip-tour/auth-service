"""Тесты регистрации и подтверждения (register / verify)."""

import os
import re
import sys
from urllib.parse import unquote
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi_users.jwt import generate_jwt
from fastapi_users.manager import VERIFY_USER_TOKEN_AUDIENCE

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi_users.router.common import ErrorCode  # noqa: E402

from config import settings  # noqa: E402
from app.utils.registration_token import (  # noqa: E402
    decrypt_registration_token,
    encrypt_registration_token,
)

# --- Register ---


@pytest.mark.asyncio
async def test_register_success(client, mock_user_db):
    """Успешный запрос регистрации: 204, письмо содержит токен подтверждения."""
    mock_user_db.get_by_email_result = None
    with patch(
        "app.services.users.send_email", new_callable=AsyncMock
    ) as send_email_mock:
        response = await client.post(
            "/api/auth/register",
            json={"email": "newuser@example.com", "password": "securepassword123"},
        )
    assert response.status_code == 204
    assert response.content == b""
    send_email_mock.assert_called_once()
    recipient, subject, body = send_email_mock.call_args.args
    assert recipient == "newuser@example.com"
    assert subject == "Подтверждение регистрации"

    match = re.search(r"verify_token=([^\s]+)", body)
    assert match is not None
    encrypted_token = unquote(match.group(1))
    with pytest.raises(jwt.DecodeError):
        jwt.decode(
            encrypted_token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience=VERIFY_USER_TOKEN_AUDIENCE,
        )

    payload = jwt.decode(
        decrypt_registration_token(encrypted_token),
        settings.jwt_secret,
        algorithms=["HS256"],
        audience=VERIFY_USER_TOKEN_AUDIENCE,
    )
    assert payload["email"] == "newuser@example.com"
    assert payload["type"] == "register"
    assert payload["aud"] == VERIFY_USER_TOKEN_AUDIENCE
    assert "hashed_password" in payload


@pytest.mark.asyncio
async def test_register_lowercases_email(client, mock_user_db):
    """Email при регистрации приводится к нижнему регистру до lookup и токена."""
    mock_user_db.get_by_email_result = None
    with patch(
        "app.services.users.send_email", new_callable=AsyncMock
    ) as send_email_mock:
        response = await client.post(
            "/api/auth/register",
            json={"email": "NewUser@Example.COM", "password": "securepassword123"},
        )

    assert response.status_code == 204
    assert mock_user_db.get_by_email_calls == ["newuser@example.com"]
    recipient, _, body = send_email_mock.call_args.args
    assert recipient == "newuser@example.com"

    match = re.search(r"verify_token=([^\s]+)", body)
    assert match is not None
    payload = jwt.decode(
        decrypt_registration_token(unquote(match.group(1))),
        settings.jwt_secret,
        algorithms=["HS256"],
        audience=VERIFY_USER_TOKEN_AUDIENCE,
    )
    assert payload["email"] == "newuser@example.com"


@pytest.mark.asyncio
async def test_register_user_already_exists(client, mock_user_db):
    """Регистрация с уже существующим email возвращает 400."""
    existing = type("User", (), {"id": 1, "email": "taken@example.com"})()
    mock_user_db.get_by_email_result = existing
    response = await client.post(
        "/api/auth/register",
        json={"email": "taken@example.com", "password": "password123"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == ErrorCode.REGISTER_USER_ALREADY_EXISTS


@pytest.mark.asyncio
async def test_register_invalid_password(client, mock_user_db):
    """При ошибке валидации пароля (InvalidPasswordException) возвращается 400."""
    mock_user_db.get_by_email_result = None
    response = await client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "short"},
    )
    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert "msg" in detail
    assert "Пароль должен быть более 8 и менее 100 символов" in detail["msg"]


@pytest.mark.asyncio
async def test_register_password_with_cyrillic_rejected(client, mock_user_db):
    """Пароль с кириллицей должен отклоняться на уровне схемы."""
    mock_user_db.get_by_email_result = None
    response = await client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "passwordпароль123"},
    )
    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert "msg" in detail
    assert "Пароль не должен содержать кириллицу" in detail["msg"]


# --- Verify ---


def _make_verify_token(email: str, hashed_password: str) -> str:
    """Формирует валидный токен подтверждения, как в on_before_register."""
    payload = {
        "email": email,
        "hashed_password": hashed_password,
        "aud": VERIFY_USER_TOKEN_AUDIENCE,
        "type": "register",
    }
    signed_token = generate_jwt(
        payload,
        settings.jwt_secret,
        lifetime_seconds=10 * 60,
    )
    return encrypt_registration_token(signed_token)


@pytest.mark.asyncio
async def test_verify_success(client, mock_user_db):
    """Успешное подтверждение: валидный токен → пользователь создаётся, возвращается UserRead."""
    mock_user_db.get_by_email_result = None
    email = "verified@example.com"
    hashed = "hashed_password_value"
    token = _make_verify_token(email, hashed)

    created_user = type(
        "User",
        (),
        {
            "id": 42,
            "email": email,
            "is_active": True,
            "is_superuser": False,
            "is_verified": True,
        },
    )()
    mock_user_db.create_result = created_user
    mock_user_db.create_called = False

    response = await client.post("/api/auth/verify", json={"token": token})

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == email
    assert data["id"] == 42
    assert data["is_verified"] is True
    assert mock_user_db.create_called
    assert mock_user_db.create_call_data["email"] == email
    assert mock_user_db.create_call_data["hashed_password"] == hashed
    assert mock_user_db.create_call_data.get("is_verified") is True
    assert "aud" not in mock_user_db.create_call_data
    assert "type" not in mock_user_db.create_call_data


@pytest.mark.asyncio
async def test_verify_bad_token(client, mock_user_db):
    """Невалидный токен → 400 VERIFY_USER_BAD_TOKEN."""
    response = await client.post(
        "/api/auth/verify",
        json={"token": "invalid.jwt.token"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == ErrorCode.VERIFY_USER_BAD_TOKEN
    assert not mock_user_db.create_called


@pytest.mark.asyncio
async def test_verify_expired_token(client, mock_user_db):
    """Истёкший токен → 400 VERIFY_USER_BAD_TOKEN."""
    from datetime import datetime, timedelta, timezone

    import jwt

    payload = {
        "email": "expired@example.com",
        "hashed_password": "hash",
        "aud": VERIFY_USER_TOKEN_AUDIENCE,
        "exp": datetime.now(timezone.utc) - timedelta(seconds=10),
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm="HS256",
    )
    response = await client.post("/api/auth/verify", json={"token": token})
    assert response.status_code == 400
    assert response.json()["detail"] == ErrorCode.VERIFY_USER_BAD_TOKEN
    assert not mock_user_db.create_called


@pytest.mark.asyncio
async def test_verify_user_already_exists(client, mock_user_db):
    """Если пользователь с email уже есть, verify возвращает 400 VERIFY_USER_ALREADY_VERIFIED."""
    email = "existing@example.com"
    token = _make_verify_token(email, "hash")
    existing_user = type("User", (), {"id": 1, "email": email})()
    mock_user_db.get_by_email_result = existing_user
    mock_user_db.create_called = False
    response = await client.post("/api/auth/verify", json={"token": token})
    assert response.status_code == 400
    assert response.json()["detail"] == ErrorCode.VERIFY_USER_ALREADY_VERIFIED
    assert not mock_user_db.create_called


def _make_change_email_token(
    user_id: int, current_email: str, new_email: str, *, secret: str
) -> str:
    payload = {
        "sub": str(user_id),
        "current_email": current_email,
        "new_email": new_email,
        "aud": VERIFY_USER_TOKEN_AUDIENCE,
        "type": "change_email",
    }
    return generate_jwt(payload, secret, lifetime_seconds=10 * 60)


@pytest.mark.asyncio
async def test_verify_change_email_success(client, mock_user_db):
    """Токен смены email должен обновить адрес пользователя."""
    current_email = "current@example.com"
    new_email = "new@example.com"
    existing_user = type(
        "User",
        (),
        {
            "id": 7,
            "email": current_email,
            "hashed_password": "hashed",
            "is_active": True,
            "is_superuser": False,
            "is_verified": True,
        },
    )()
    mock_user_db.get_by_email_map = {
        current_email: existing_user,
        new_email: None,
    }
    token = _make_change_email_token(
        existing_user.id,
        current_email,
        new_email,
        secret=settings.jwt_secret,
    )

    with patch("app.services.users.send_email", new_callable=AsyncMock) as send_email_mock:
        response = await client.post("/api/auth/verify", json={"token": token})

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == existing_user.id
    assert data["email"] == new_email
    assert mock_user_db.update_called
    assert mock_user_db.update_call_user is existing_user
    assert mock_user_db.update_call_data == {"email": new_email}
    assert send_email_mock.await_count == 2
    old_email_call, new_email_call = send_email_mock.await_args_list

    assert old_email_call.args[0] == current_email
    assert old_email_call.args[1] == "Email аккаунта изменен"
    assert "Предыдущий адрес: c***@example.com" in old_email_call.args[2]
    assert "Новый адрес: n***@example.com" in old_email_call.args[2]
    assert "Сменить пароль: http://trip.com/reset-password?token=" in old_email_call.args[2]

    assert new_email_call.args[0] == new_email
    assert new_email_call.args[1] == "Email аккаунта изменен"
    assert current_email not in new_email_call.args[2]
    assert "Предыдущий адрес" not in new_email_call.args[2]
    assert "Сменить пароль" not in new_email_call.args[2]
    assert "token=" not in new_email_call.args[2]
