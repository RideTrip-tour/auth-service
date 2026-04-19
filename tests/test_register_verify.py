"""Тесты регистрации и подтверждения (register / verify)."""

import os
import sys
from unittest.mock import AsyncMock, patch
from fastapi_users.jwt import generate_jwt
import jwt
import pytest
from fastapi_users.manager import VERIFY_USER_TOKEN_AUDIENCE
from datetime import datetime, timedelta, timezone
from app.utils.token_crypto import encrypt_token

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi_users.router.common import ErrorCode  # noqa: E402

from config import settings  # noqa: E402

# --- Register ---


@pytest.mark.asyncio
async def test_register_success(client, mock_user_db):
    """Успешный запрос регистрации."""
    mock_user_db.get_by_email_result = None

    created_user = type(
        "User",
        (),
        {
            "id": 1,
            "email": "newuser@example.com",
            "is_active": True,
            "is_superuser": False,
            "is_verified": False,
        },
    )()
    mock_user_db.create_result = created_user

    with patch(
        "app.services.users.UserManager.on_after_register",
        new_callable=AsyncMock,
    ) as on_after_register_mock:
        response = await client.post(
            "/api/auth/register",
            json={"email": "newuser@example.com", "password": "securepassword123"},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@example.com"

    on_after_register_mock.assert_called_once()


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
    payload = {
        "email": email,
        "hashed_password": hashed_password,
        "aud": VERIFY_USER_TOKEN_AUDIENCE,
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
    }
    return encrypt_token(payload, settings.jwt_secret)


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

    response = await client.post("/api/auth/verify", json={"token": token})

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == existing_user.id
    assert data["email"] == new_email
    assert mock_user_db.update_called
    assert mock_user_db.update_call_user is existing_user
    assert mock_user_db.update_call_data == {"email": new_email}
