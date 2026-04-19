"""Тесты логики refresh-token: login, destroy_token и logout."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

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


@pytest.mark.asyncio
async def test_login_creates_refresh_token_without_deleting_existing_ones():
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


@pytest.mark.asyncio
async def test_destroy_token_deletes_only_current_token():
    """destroy_token должен удалять только токен, который ему передали."""
    user = SimpleNamespace(id=10, is_verified=True, is_superuser=False)
    fake_token_db = SimpleNamespace(delete_by_token=AsyncMock())

    with patch("app.services.users.SQLAlchemyRefreshTokenDatabase", return_value=fake_token_db), patch(
        "app.services.users.AsyncSessionLocal", new=_FakeSessionFactory()
    ):
        strategy = get_strategy()
        await strategy.destroy_token("current.refresh.token", user)

    fake_token_db.delete_by_token.assert_awaited_once_with("current.refresh.token")


@pytest.mark.asyncio
async def test_logout_uses_refresh_cookie_for_token_deletion(app):
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
