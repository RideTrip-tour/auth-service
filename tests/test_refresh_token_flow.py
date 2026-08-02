"""Тесты логики refresh-token: login, destroy_token и logout."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.services.users import auth_backend, get_strategy


class _AsyncContextManager:
    def __init__(self, value=None):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def begin(self):
        return _AsyncContextManager()


class _FakeSessionFactory:
    def __call__(self):
        return _AsyncContextManager(_FakeSession())


class _FakeRefreshTokenSession:
    def begin(self):
        return _AsyncContextManager()


class _FakeRefreshTokenDb:
    def __init__(self, token_record, new_token):
        self.session = _FakeRefreshTokenSession()
        self.token_record = token_record
        self.get = AsyncMock(return_value=token_record)
        self.delete = AsyncMock()
        self.create = AsyncMock(return_value=new_token)


def _get_route(app, name: str):
    return next(route for route in app.routes if getattr(route, "name", None) == name)


@pytest.mark.asyncio
async def test_login_creates_refresh_token_without_deleting_existing_ones(mock_audit_log):
    """Login должен создавать новый refresh token, но не удалять старые."""
    user = SimpleNamespace(id=10, is_verified=True, is_superuser=False)
    strategy = get_strategy()
    fake_refresh_token = SimpleNamespace(token="new.refresh.token")
    fake_token_db = SimpleNamespace(
        create=AsyncMock(return_value=fake_refresh_token),
        delete_by_user_id=AsyncMock(),
    )

    with patch(
        "app.services.users.SQLAlchemyRefreshTokenDatabase",
        return_value=fake_token_db,
    ), patch("app.services.users.auth_backend.session_factory", new=_FakeSessionFactory()):
        response = await auth_backend.login(strategy, user)

    assert response.status_code == 204
    fake_token_db.create.assert_awaited_once_with(user.id)
    fake_token_db.delete_by_user_id.assert_not_called()
    mock_audit_log.assert_awaited_once()
    assert mock_audit_log.await_args.args[0] == "session_created"
    assert mock_audit_log.await_args.kwargs["user_id"] == user.id


@pytest.mark.asyncio
async def test_destroy_token_deletes_only_current_token(mock_audit_log):
    """destroy_token должен удалять только токен, который ему передали."""
    user = SimpleNamespace(id=10, is_verified=True, is_superuser=False)
    fake_token_db = SimpleNamespace(delete_by_token=AsyncMock())

    with patch("app.services.users.SQLAlchemyRefreshTokenDatabase", return_value=fake_token_db), patch(
        "app.services.users.AsyncSessionLocal", new=_FakeSessionFactory()
    ):
        strategy = get_strategy()
        await strategy.destroy_token("current.refresh.token", user)

    fake_token_db.delete_by_token.assert_awaited_once_with("current.refresh.token")
    mock_audit_log.assert_not_awaited()


@pytest.mark.asyncio
async def test_logout_uses_refresh_cookie_for_token_deletion(app, mock_audit_log):
    """Logout должен брать refresh token из cookie и передавать его в backend.logout."""
    user = SimpleNamespace(
        id=11,
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    strategy = get_strategy()
    access_token = await strategy.write_token(user)
    request = SimpleNamespace(
        cookies={
            "access_token": access_token,
            "refresh_token": "logout.refresh.token",
        }
    )

    with patch(
        "app.services.users.auth_backend.logout",
        new=AsyncMock(return_value=SimpleNamespace(status_code=204)),
    ) as logout_mock:
        logout_route = next(
            route for route in app.routes if getattr(route, "name", None) == "auth:cookie.logout"
        )
        response = await logout_route.endpoint(
            request=request,
            user_token=(user, access_token),
            strategy=strategy,
        )

    assert response.status_code == 204
    logout_mock.assert_awaited_once()
    assert logout_mock.await_args.args[2] == "logout.refresh.token"
    assert logout_mock.await_args.args[1] == user
    mock_audit_log.assert_awaited_once()
    assert mock_audit_log.await_args.args[0] == "logout"
    assert mock_audit_log.await_args.kwargs["user_id"] == user.id


@pytest.mark.asyncio
async def test_login_route_logs_failed_auth_attempt(app, mock_audit_log):
    """Неудачный логин должен писать audit-событие с причиной."""
    route = _get_route(app, "auth:cookie.login")
    request = SimpleNamespace()
    user_manager = SimpleNamespace(authenticate=AsyncMock(return_value=None))
    strategy = get_strategy()

    with pytest.raises(HTTPException) as exc_info:
        await route.endpoint(
            request=request,
            credentials=SimpleNamespace(username="user@example.com"),
            user_manager=user_manager,
            strategy=strategy,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "LOGIN_BAD_CREDENTIALS"
    mock_audit_log.assert_awaited_once()
    assert mock_audit_log.await_args.args[0] == "login_failed"
    assert mock_audit_log.await_args.kwargs["success"] is False


@pytest.mark.asyncio
async def test_login_rejects_oversized_form_before_auth(client, mock_user_db):
    """Большой form-urlencoded login body должен отклоняться до парсинга формы."""
    response = await client.post(
        "/api/auth/login",
        content=f"username=user@example.com&password={'x' * 9000}",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Login form body too large"
    assert mock_user_db.get_by_email_calls == []


@pytest.mark.asyncio
async def test_refresh_route_logs_session_rotation(app, mock_audit_log):
    """Успешный refresh должен писать событие rotation новой активной сессии."""
    route = _get_route(app, "token:refresh_token")
    user = SimpleNamespace(id=12, is_verified=True, is_superuser=False)
    db_token = SimpleNamespace(user_id=user.id, user=user)
    new_token = SimpleNamespace(id=99, token="new.refresh.token")
    fake_db = _FakeRefreshTokenDb(db_token, new_token)
    request = SimpleNamespace(cookies={"refresh_token": "current.refresh.token"})

    response = await route.endpoint(request=request, refresh_token_db=fake_db)

    assert response.status_code == 204
    fake_db.get.assert_awaited_once()
    fake_db.delete.assert_awaited_once_with(db_token)
    fake_db.create.assert_awaited_once_with(user.id)
    mock_audit_log.assert_awaited_once()
    assert mock_audit_log.await_args.args[0] == "session_rotated"
    assert mock_audit_log.await_args.kwargs["user_id"] == user.id


@pytest.mark.asyncio
async def test_refresh_route_logs_failed_rotation_without_cookie(app, mock_audit_log):
    """Если refresh cookie отсутствует, это тоже должно попасть в audit."""
    route = _get_route(app, "token:refresh_token")

    with pytest.raises(HTTPException) as exc_info:
        await route.endpoint(
            request=SimpleNamespace(cookies={}),
            refresh_token_db=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 401
    mock_audit_log.assert_awaited_once()
    assert mock_audit_log.await_args.args[0] == "session_rotate_failed"
    assert mock_audit_log.await_args.kwargs["success"] is False
