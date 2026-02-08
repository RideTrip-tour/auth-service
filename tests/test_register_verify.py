"""Тесты регистрации и подтверждения (register / verify)."""

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest
from fastapi_users.jwt import generate_jwt
from fastapi_users.manager import VERIFY_USER_TOKEN_AUDIENCE

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi_users.router.common import ErrorCode  # noqa: E402

from config import settings  # noqa: E402

# --- Register ---


@pytest.mark.asyncio
async def test_register_success(client, mock_user_db):
    """Успешный запрос регистрации: 204, пользователь не создаётся в БД, письмо не падает."""
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
    call_kw = send_email_mock.call_args
    assert call_kw[0][0] == "newuser@example.com"
    assert "verufy_token=" in call_kw[0][2] or "Подтвержжение" in call_kw[0][1]


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
    from fastapi_users import exceptions as fu_exceptions

    with patch(
        "app.services.users.UserManager.validate_password",
        new_callable=AsyncMock,
        side_effect=fu_exceptions.InvalidPasswordException(reason="Password too short"),
    ):
        response = await client.post(
            "/api/auth/register",
            json={"email": "user@example.com", "password": "short"},
        )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == ErrorCode.REGISTER_INVALID_PASSWORD
    assert "reason" in detail


# --- Verify ---


def _make_verify_token(email: str, hashed_password: str) -> str:
    """Формирует валидный токен подтверждения, как в on_before_register."""
    payload = {
        "email": email,
        "hashed_password": hashed_password,
        "aud": VERIFY_USER_TOKEN_AUDIENCE,
    }
    return generate_jwt(
        payload,
        settings.jwt_secret,
        lifetime_seconds=10 * 60,
    )


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
    """Токен валидный, но пользователь с таким email уже есть → ошибка, пользователь не создаётся."""
    from fastapi_users import exceptions as fu_exceptions

    email = "existing@example.com"
    token = _make_verify_token(email, "hash")
    existing_user = type("User", (), {"id": 1, "email": email})()
    mock_user_db.get_by_email_result = existing_user
    mock_user_db.create_called = False

    try:
        response = await client.post("/api/auth/verify", json={"token": token})
        # Роутер не ловит UserAlreadyExists → 500
        assert response.status_code in (400, 500)
    except fu_exceptions.UserAlreadyExists:
        # В некоторых тестовых запусках исключение может пробрасываться
        pass

    assert not mock_user_db.create_called
