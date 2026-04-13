"""Тесты новых user-flows: смена пароля и запрос смены email."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException
from fastapi_users.manager import VERIFY_USER_TOKEN_AUDIENCE

from app.schemas.users import UserUpdateEmail, UserUpdatePassword
from app.services.users import UserManager
from config import settings


def _get_route(app, name: str):
    return next(route for route in app.routes if getattr(route, "name", None) == name)


@pytest.mark.asyncio
async def test_user_manager_update_uses_new_password(mock_user_db):
    """UserManager.update должен прокидывать в БД только новый пароль."""
    manager = UserManager(mock_user_db)
    user = SimpleNamespace(
        id=1,
        email="user@example.com",
        hashed_password="old-hash",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    update = UserUpdatePassword(
        current_password="oldpassword123",
        new_password="newpassword123",
    )

    updated_user = await manager.update(update, user, safe=True)

    assert updated_user is user
    assert mock_user_db.update_called
    assert mock_user_db.update_call_data is not None
    assert "hashed_password" in mock_user_db.update_call_data
    assert mock_user_db.update_call_data["hashed_password"] != "newpassword123"
    assert "password" not in mock_user_db.update_call_data
    assert "current_password" not in mock_user_db.update_call_data
    assert "new_password" not in mock_user_db.update_call_data


@pytest.mark.asyncio
async def test_change_password_success(app):
    """Смена пароля должна обновить пароль, разлогинить и отправить уведомление."""
    route = _get_route(app, "users:patch_pass_current_user")
    user = SimpleNamespace(
        id=10,
        email="user@example.com",
        hashed_password="old-hash",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    user_update = UserUpdatePassword(
        current_password="oldpassword123",
        new_password="newpassword123",
    )
    request = SimpleNamespace(cookies={settings.refresh_token_name: "refresh-token"})
    user_manager = UserManager(SimpleNamespace())
    strategy = SimpleNamespace(destroy_tokens_by_user=AsyncMock())

    with (
        patch.object(
            user_manager.password_helper,
            "verify_and_update",
            new=MagicMock(return_value=(True, None)),
        ) as verify_password_mock,
        patch.object(user_manager, "update", new=AsyncMock(return_value=user)) as update_mock,
        patch.object(user_manager, "on_after_reset_password", new=AsyncMock()) as on_after_reset_password_mock,
        patch("app.services.users.auth_backend.logout", new_callable=AsyncMock) as logout_mock,
    ):
        response = await route.endpoint(
            request=request,
            user_update_pass_schema=user_update,
            user=user,
            user_manager=user_manager,
            strategy=strategy,
        )

    assert response == {"status": "Пароль обновлен, нужна повторная авторизация"}
    verify_password_mock.assert_called_once_with(
        user_update.current_password, user.hashed_password
    )
    update_mock.assert_awaited_once_with(user_update, user)
    on_after_reset_password_mock.assert_awaited_once_with(user, request)
    logout_mock.assert_awaited_once()
    assert logout_mock.await_args.args[0] is strategy
    assert logout_mock.await_args.args[1] is user
    assert logout_mock.await_args.args[2] == "refresh-token"
    strategy.destroy_tokens_by_user.assert_awaited_once_with(user)


@pytest.mark.asyncio
async def test_change_password_rejects_bad_current_password(app):
    """Неверный current_password должен вернуть 400."""
    route = _get_route(app, "users:patch_pass_current_user")
    user = SimpleNamespace(
        id=10,
        email="user@example.com",
        hashed_password="old-hash",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    user_update = UserUpdatePassword(
        current_password="wrongpassword",
        new_password="newpassword123",
    )
    request = SimpleNamespace(cookies={settings.refresh_token_name: "refresh-token"})
    user_manager = UserManager(SimpleNamespace())
    strategy = SimpleNamespace(destroy_tokens_by_user=AsyncMock())

    with (
        patch.object(
            user_manager.password_helper,
            "verify_and_update",
            new=MagicMock(return_value=(False, None)),
        ) as verify_password_mock,
        patch.object(user_manager, "update", new=AsyncMock()) as update_mock,
        patch.object(user_manager, "on_after_reset_password", new=AsyncMock()) as on_after_reset_password_mock,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await route.endpoint(
                request=request,
                user_update_pass_schema=user_update,
                user=user,
                user_manager=user_manager,
                strategy=strategy,
            )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "UPDATE_USER_INVALID_PASSWORD"
    verify_password_mock.assert_called_once_with(
        user_update.current_password, user.hashed_password
    )
    update_mock.assert_not_awaited()
    on_after_reset_password_mock.assert_not_awaited()
    strategy.destroy_tokens_by_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_request_change_email_sends_verification_link(app, mock_user_db):
    """Запрос смены email должен отправить письмо с токеном подтверждения."""
    route = _get_route(app, "users:patch_email_current_user")
    user = SimpleNamespace(
        id=7,
        email="current@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    user_update = UserUpdateEmail(
        current_email="current@example.com",
        new_email="new@example.com",
        password="currentpassword123",
    )
    user_manager = UserManager(mock_user_db)

    with (
        patch.object(
            user_manager.password_helper,
            "verify_and_update",
            new=MagicMock(return_value=(True, None)),
        ) as verify_password_mock,
        patch.object(
            mock_user_db, "get_by_email", new=AsyncMock(wraps=mock_user_db.get_by_email)
        ) as get_by_email_mock,
        patch("app.routes.users.send_email", new_callable=AsyncMock) as send_email_mock,
    ):
        response = await route.endpoint(
            request=SimpleNamespace(),
            user_update_email_schema=user_update,
            user=user,
            user_manager=user_manager,
        )

    assert response == {
        "status": "Подтвержение смены email отправлено, тербуется подтверждение."
    }
    verify_password_mock.assert_called_once_with(user_update.password, user.hashed_password)
    get_by_email_mock.assert_awaited_once_with(user_update.new_email)
    send_email_mock.assert_awaited_once()
    recipient, subject, body = send_email_mock.call_args.args
    assert recipient == user.email
    assert subject == "Подтвержжение смены адреса электроного ящика"
    token = body.split("verify_token=", 1)[1].strip()
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=["HS256"],
        audience=VERIFY_USER_TOKEN_AUDIENCE,
    )
    assert payload["sub"] == str(user.id)
    assert payload["current_email"] == user_update.current_email
    assert payload["new_email"] == user_update.new_email
    assert payload["type"] == "change_email"
    assert payload["aud"] == VERIFY_USER_TOKEN_AUDIENCE


@pytest.mark.asyncio
async def test_request_change_email_rejects_wrong_current_email(app, mock_user_db):
    """Если current_email не совпадает с почтой пользователя, запрос отклоняется."""
    route = _get_route(app, "users:patch_email_current_user")
    user = SimpleNamespace(
        id=7,
        email="current@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    user_update = UserUpdateEmail(
        current_email="wrong@example.com",
        new_email="new@example.com",
        password="currentpassword123",
    )
    user_manager = UserManager(mock_user_db)

    with (
        patch.object(
            user_manager.password_helper,
            "verify_and_update",
            new=MagicMock(return_value=(True, None)),
        ) as verify_password_mock,
        patch.object(
            mock_user_db, "get_by_email", new=AsyncMock(wraps=mock_user_db.get_by_email)
        ) as get_by_email_mock,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await route.endpoint(
                request=SimpleNamespace(),
                user_update_email_schema=user_update,
                user=user,
                user_manager=user_manager,
            )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "LOGIN_BAD_CREDENTIALS"
    verify_password_mock.assert_called_once_with(user_update.password, user.hashed_password)
    get_by_email_mock.assert_not_awaited()
