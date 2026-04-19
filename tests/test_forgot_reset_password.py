"""Тесты восстановления пароля (forgot-password / reset-password)."""

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest
from fastapi_users.router.common import ErrorCode

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


@pytest.mark.asyncio
async def test_forgot_password_success(client, mock_user_db):
    """
    Если пользователь существует, endpoint должен вернуть успешный ответ
    и вызвать отправку письма.
    """
    user = type(
        "User",
        (),
        {
            "id": 1,
            "email": "user@example.com",
            "is_active": True,
            "is_verified": True,
            "hashed_password": "hashed_password_value",
        },
    )()
    mock_user_db.get_by_email_result = user

    with patch(
        "app.services.users.send_email",
        new_callable=AsyncMock,
    ) as send_email_mock:
        response = await client.post(
            "/api/auth/forgot-password",
            json={"email": "user@example.com"},
        )

    assert response.status_code in (200, 202)
    data = response.json()
    assert "message" in data
    send_email_mock.assert_called_once()

    call_args = send_email_mock.call_args[0]
    assert call_args[0] == "user@example.com"
    assert "Восстановление" in call_args[1] or "reset" in call_args[1].lower()
    assert "reset-password" in call_args[2] or "token=" in call_args[2]


@pytest.mark.asyncio
async def test_forgot_password_user_not_found(client, mock_user_db):
    """
    Если пользователя нет, endpoint всё равно должен вернуть успешный ответ,
    но письмо не должно отправляться.
    """
    mock_user_db.get_by_email_result = None

    with patch(
        "app.services.users.send_email",
        new_callable=AsyncMock,
    ) as send_email_mock:
        response = await client.post(
            "/api/auth/forgot-password",
            json={"email": "missing@example.com"},
        )

    assert response.status_code in (200, 202)
    data = response.json()
    assert "message" in data
    send_email_mock.assert_not_called()


@pytest.mark.asyncio
async def test_reset_password_success(client, mock_user_db):
    """
    Успешный reset пароля по валидному токену.
    """
    user = type(
        "User",
        (),
        {
            "id": 1,
            "email": "user@example.com",
            "is_active": True,
            "is_verified": True,
            "hashed_password": "old_hash",
        },
    )()
    mock_user_db.get_by_email_result = user
    mock_user_db.update_result = user

    fake_token = "valid-reset-token"

    with (
        patch(
            "app.services.users.send_email",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.users.UserManager.reset_password",
            new_callable=AsyncMock,
        ) as reset_password_mock,
    ):
        response = await client.post(
            "/api/auth/reset-password",
            json={
                "token": fake_token,
                "password": "newsecurepassword123",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert "message" in data

    reset_password_mock.assert_called_once()
    args = reset_password_mock.call_args[0]
    assert fake_token in args
    assert "newsecurepassword123" in args


@pytest.mark.asyncio
async def test_reset_password_bad_token(client, mock_user_db):
    """
    Невалидный токен должен вернуть ошибку 400.
    """
    with patch(
        "app.services.users.UserManager.reset_password",
        new_callable=AsyncMock,
        side_effect=Exception("bad token"),
    ):
        response = await client.post(
            "/api/auth/reset-password",
            json={
                "token": "bad-token",
                "password": "newsecurepassword123",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == ErrorCode.RESET_PASSWORD_BAD_TOKEN


@pytest.mark.asyncio
async def test_reset_password_invalid_password_validation(client, mock_user_db):
    """
    Слишком короткий пароль должен упасть на валидации схемы.
    """
    response = await client.post(
        "/api/auth/reset-password",
        json={
            "token": "some-token",
            "password": "short",
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert "msg" in detail
