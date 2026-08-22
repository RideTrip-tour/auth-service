"""Тесты новых user-flows: смена пароля и запрос смены email."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi_users.manager import VERIFY_USER_TOKEN_AUDIENCE

from app.db.models import User
from app.schemas.users import UserUpdateEmail, UserUpdatePassword
from app.services.users import UserManager
from config import settings
from main import request_validation_exception_handler


def _get_route(app, name: str):
    return next(route for route in app.routes if getattr(route, "name", None) == name)


def test_user_manager_token_lifetime_defaults():
    assert settings.reset_password_token_lifetime_seconds == 60 * 60
    assert settings.verification_token_lifetime_seconds == 60 * 60
    assert settings.change_email_token_lifetime_seconds == 60 * 60
    assert UserManager.reset_password_token_lifetime_seconds == 60 * 60
    assert UserManager.verification_token_lifetime_seconds == 60 * 60
    assert UserManager.change_email_token_lifetime_seconds == 60 * 60


@pytest.mark.asyncio
async def test_forgot_password_sends_recovery_link(mock_audit_log):
    """Запрос восстановления пароля должен отправить ссылку с reset-token."""
    user = SimpleNamespace(
        id=11,
        email="user@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    manager = UserManager(SimpleNamespace())
    token = "reset.token.value"

    with patch(
        "app.services.users.send_email", new_callable=AsyncMock
    ) as send_email_mock:
        await manager.on_after_forgot_password(user, token, SimpleNamespace())

    send_email_mock.assert_awaited_once()
    recipient, subject, body = send_email_mock.await_args.args
    assert recipient == user.email
    assert subject == "Восстановление доступа"

    recovery_url = urlparse(body.split("http://trip.com", 1)[1].splitlines()[0])
    assert recovery_url.path == settings.password_recovery_path
    assert parse_qs(recovery_url.query)["token"] == [token]
    assert "Ссылка действует 1 час." in body

    mock_audit_log.assert_awaited_once()
    assert mock_audit_log.await_args.args[0] == "password_reset_requested"
    assert mock_audit_log.await_args.kwargs["user_id"] == user.id
    assert mock_audit_log.await_args.kwargs["details"] == {"token_length": len(token)}


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
async def test_user_manager_change_password_returns_none_on_stale_hash():
    """Если hash в БД уже изменился, смена пароля должна считаться неуспешной."""
    execute_result = SimpleNamespace(rowcount=0)
    session = SimpleNamespace(
        execute=AsyncMock(return_value=execute_result),
        rollback=AsyncMock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )
    user_db = SimpleNamespace(session=session, user_table=User)
    manager = UserManager(user_db)
    user = SimpleNamespace(
        id=1,
        email="user@example.com",
        hashed_password="old-hash",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )

    with (
        patch.object(
            manager.password_helper,
            "verify_and_update",
            new=MagicMock(return_value=(True, None)),
        ),
        patch.object(
            manager.password_helper, "hash", new=MagicMock(return_value="new-hash")
        ),
        patch.object(manager, "validate_password", new=AsyncMock()),
    ):
        result = await manager.change_password(
            user,
            "oldpassword123",
            "newpassword123",
        )

    assert result is None
    session.execute.assert_awaited_once()
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
    session.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_change_password_success(app, mock_audit_log):
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
            user_manager,
            "change_password",
            new=AsyncMock(return_value=user),
        ) as change_password_mock,
        patch(
            "app.services.users.send_email", new_callable=AsyncMock
        ) as send_email_mock,
        patch(
            "app.services.users.auth_backend.logout", new_callable=AsyncMock
        ) as logout_mock,
    ):
        response = await route.endpoint(
            request=request,
            user_update_pass_schema=user_update,
            user=user,
            user_manager=user_manager,
            strategy=strategy,
        )

    assert response == {"status": "Пароль обновлен, нужна повторная авторизация"}
    change_password_mock.assert_awaited_once_with(
        user,
        user_update.current_password,
        user_update.new_password,
        request,
    )
    send_email_mock.assert_awaited_once()
    logout_mock.assert_awaited_once()
    assert logout_mock.await_args.args[0] is strategy
    assert logout_mock.await_args.args[1] is user
    assert logout_mock.await_args.args[2] == "refresh-token"
    strategy.destroy_tokens_by_user.assert_awaited_once_with(user)
    assert mock_audit_log.await_count == 2
    assert mock_audit_log.await_args_list[0].args[0] == "change_completed"
    assert mock_audit_log.await_args_list[0].kwargs["user_id"] == user.id
    assert (
        mock_audit_log.await_args_list[0].kwargs["details"]["change_type"] == "password"
    )
    assert mock_audit_log.await_args_list[1].args[0] == "logout"
    assert mock_audit_log.await_args_list[1].kwargs["user_id"] == user.id


@pytest.mark.asyncio
async def test_change_password_rejects_bad_current_password(app, mock_audit_log):
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
            user_manager,
            "change_password",
            new=AsyncMock(return_value=None),
        ) as change_password_mock,
        patch.object(
            user_manager, "on_after_reset_password", new=AsyncMock()
        ) as on_after_reset_password_mock,
        pytest.raises(HTTPException) as exc_info,
    ):
        await route.endpoint(
            request=request,
            user_update_pass_schema=user_update,
            user=user,
            user_manager=user_manager,
            strategy=strategy,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "UPDATE_USER_INVALID_PASSWORD"
    change_password_mock.assert_awaited_once_with(
        user,
        user_update.current_password,
        user_update.new_password,
        request,
    )
    on_after_reset_password_mock.assert_not_awaited()
    strategy.destroy_tokens_by_user.assert_not_awaited()
    mock_audit_log.assert_awaited_once()
    assert mock_audit_log.await_args.args[0] == "change_failed"
    assert mock_audit_log.await_args.kwargs["user_id"] == user.id
    assert mock_audit_log.await_args.kwargs["details"]["change_type"] == "password"


@pytest.mark.asyncio
async def test_request_change_email_sends_verification_link(
    app, mock_user_db, mock_audit_log
):
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
        "status": "Подтвержение смены email отправлено, требуется подтверждение."
    }
    verify_password_mock.assert_called_once_with(
        user_update.password, user.hashed_password
    )
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
    assert "jti" in payload
    mock_audit_log.assert_awaited_once()
    assert mock_audit_log.await_args.args[0] == "change_requested"
    assert mock_audit_log.await_args.kwargs["user_id"] == user.id
    assert mock_audit_log.await_args.kwargs["details"]["change_type"] == "email"


@pytest.mark.asyncio
async def test_request_change_email_lowercases_emails(
    app, mock_user_db, mock_audit_log
):
    """Email при запросе смены приводится к нижнему регистру до lookup и токена."""
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
        current_email="Current@Example.COM",
        new_email="New@Example.COM",
        password="currentpassword123",
    )
    user_manager = UserManager(mock_user_db)

    with (
        patch.object(
            user_manager.password_helper,
            "verify_and_update",
            new=MagicMock(return_value=(True, None)),
        ),
        patch.object(
            mock_user_db, "get_by_email", new=AsyncMock(wraps=mock_user_db.get_by_email)
        ) as get_by_email_mock,
        patch("app.routes.users.send_email", new_callable=AsyncMock) as send_email_mock,
    ):
        await route.endpoint(
            request=SimpleNamespace(),
            user_update_email_schema=user_update,
            user=user,
            user_manager=user_manager,
        )

    assert user_update.current_email == "current@example.com"
    assert user_update.new_email == "new@example.com"
    get_by_email_mock.assert_awaited_once_with("new@example.com")
    _, _, body = send_email_mock.call_args.args
    token = body.split("verify_token=", 1)[1].strip()
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=["HS256"],
        audience=VERIFY_USER_TOKEN_AUDIENCE,
    )
    assert payload["current_email"] == "current@example.com"
    assert payload["new_email"] == "new@example.com"
    assert "jti" in payload
    assert (
        mock_audit_log.await_args.kwargs["details"]["current_email"]
        == "current@example.com"
    )
    assert mock_audit_log.await_args.kwargs["details"]["new_email"] == "new@example.com"


@pytest.mark.asyncio
async def test_change_email_token_is_stored_and_replaces_previous_request():
    """При наличии SQLAlchemy session pending-токен смены email сохраняется в БД."""
    session = SimpleNamespace()
    user_db = SimpleNamespace(session=session)
    manager = UserManager(user_db)
    user = SimpleNamespace(id=7)
    token_db = SimpleNamespace(replace_for_user=AsyncMock())

    with patch(
        "app.services.users.SQLAlchemyEmailChangeRequestDatabase",
        return_value=token_db,
    ) as token_db_class:
        token = await manager.create_change_email_verification_token(
            user=user,
            current_email="current@example.com",
            new_email="new@example.com",
        )

    token_db_class.assert_called_once_with(session)
    token_db.replace_for_user.assert_awaited_once_with(
        user_id=user.id,
        current_email="current@example.com",
        new_email="new@example.com",
        token=token,
        lifetime_seconds=60 * 60,
    )


@pytest.mark.asyncio
async def test_request_validation_error_hides_input():
    """Ошибки валидации не должны отражать пользовательские данные в ответе."""
    body = (
        '{"current_email":"current@example.com",'
        '"new_email":"new@example.com",'
        '"password":"currentpassword123"}'
    )
    exc = RequestValidationError(
        [
            {
                "type": "model_attributes_type",
                "loc": ("body",),
                "msg": "Input should be a valid dictionary or object",
                "input": body,
            }
        ]
    )
    response = await request_validation_exception_handler(None, exc)

    assert response.status_code == 422
    response_text = response.body.decode()
    assert '"input"' not in response_text
    assert "current@example.com" not in response_text
    assert "new@example.com" not in response_text
    assert "currentpassword123" not in response_text


@pytest.mark.asyncio
async def test_request_change_email_rejects_wrong_current_email(
    app, mock_user_db, mock_audit_log
):
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
        pytest.raises(HTTPException) as exc_info,
    ):
        await route.endpoint(
            request=SimpleNamespace(),
            user_update_email_schema=user_update,
            user=user,
            user_manager=user_manager,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "LOGIN_BAD_CREDENTIALS"
    verify_password_mock.assert_called_once_with(
        user_update.password, user.hashed_password
    )
    get_by_email_mock.assert_not_awaited()
    mock_audit_log.assert_awaited_once()
    assert mock_audit_log.await_args.args[0] == "change_failed"
    assert mock_audit_log.await_args.kwargs["details"]["change_type"] == "email"
    assert mock_audit_log.await_args.kwargs["user_id"] == user.id


@pytest.mark.asyncio
async def test_reset_password_bad_pass(
    client,
):
    """Проверка валидации пароля при сбросе пароля."""
    response = await client.post(
        "api/auth/reset-password",
        json={
            "token": "token",
            "password": " ",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_reset_password_bad_email(
    client,
):
    """Проверка валидации email при сбросе пароля."""
    response = await client.post(
        "api/auth/forgot-password",
        json={
            "email": "кирилица@mail.ru",
        },
    )

    assert response.status_code == 422
