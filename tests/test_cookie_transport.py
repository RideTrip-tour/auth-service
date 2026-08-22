"""Тесты CookieTransportCustom: установка и удаление access/refresh cookies при логине, логауте и refresh."""

import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.services.users import (
    CookieTransportCustom,
    UserManager,
    get_strategy,
)
from config import settings


def _parse_set_cookie_headers(response):
    """Извлекает все Set-Cookie из ответа как список (name, value_part, full_string)."""
    raw = getattr(response, "raw_headers", None)
    if raw is None:
        raw = getattr(response.headers, "raw", [])
    cookies = []
    for key, value in raw:
        if (
            key.decode("latin-1").lower() if isinstance(key, bytes) else key.lower()
        ) == "set-cookie":
            val = value.decode("latin-1") if isinstance(value, bytes) else value
            part = val.split(";")[0].strip()
            if "=" in part:
                name, value_part = part.split("=", 1)
                cookies.append((name.strip(), value_part.strip(), val))
    return cookies


def _cookie_by_name(cookies, name):
    """Возвращает полную строку Set-Cookie для cookie с именем name."""
    for n, v, full in cookies:
        if n == name:
            return full
    return None


def _get_route(app, name: str):
    for route in app.routes:
        if getattr(route, "name", None) == name:
            return route
    raise AssertionError(f"Route {name!r} not found")


@pytest.fixture
def transport():
    """Экземпляр CookieTransportCustom с настройками из config."""
    return CookieTransportCustom(
        cookie_name="access_token",
        cookie_max_age=settings.access_token_expire_sec,
    )


@pytest.mark.asyncio
async def test_get_login_response_sets_access_and_refresh_cookies(transport):
    """При авторизации (get_login_response с access и refresh) выставляются оба cookie."""
    access = "access.jwt.token"
    refresh = "refresh.jwt.token"
    response = await transport.get_login_response(access, refresh)

    assert response.status_code == 204
    cookies = _parse_set_cookie_headers(response)
    names = [n for n, _, _ in cookies]
    assert "access_token" in names
    assert "refresh_token" in names

    access_header = _cookie_by_name(cookies, "access_token")
    refresh_header = _cookie_by_name(cookies, "refresh_token")
    assert access in (access_header or "")
    assert refresh in (refresh_header or "")
    assert "max-age=" in (access_header or "").lower()
    assert "max-age=" in (refresh_header or "").lower()


@pytest.mark.asyncio
async def test_get_login_response_without_refresh_sets_only_access(transport):
    """При get_login_response без refresh_token выставляется только access cookie."""
    access = "only.access.token"
    response = await transport.get_login_response(access, None)

    assert response.status_code == 204
    cookies = _parse_set_cookie_headers(response)
    names = [n for n, _, _ in cookies]
    assert "access_token" in names
    assert "refresh_token" not in names

    access_header = _cookie_by_name(cookies, "access_token")
    assert access in (access_header or "")


@pytest.mark.asyncio
async def test_get_logout_response_clears_access_and_refresh(transport):
    """При логауте (get_logout_response) оба cookie удаляются (max-age=0 или пустое значение)."""
    response = await transport.get_logout_response()

    assert response.status_code == 204
    cookies = _parse_set_cookie_headers(response)
    names = [n for n, _, _ in cookies]
    assert "access_token" in names
    assert "refresh_token" in names

    access_header = _cookie_by_name(cookies, "access_token")
    refresh_header = _cookie_by_name(cookies, "refresh_token")
    assert "max-age=0" in (access_header or "").lower()
    assert "max-age=0" in (refresh_header or "").lower()
    # Значение для удаления — пустая строка (формат SimpleCookie: "name=; Max-Age=0; ...")
    assert access_header and (
        "access_token=;" in access_header or 'access_token="";' in access_header
    )
    assert refresh_header and (
        "refresh_token=;" in refresh_header or 'refresh_token="";' in refresh_header
    )


@pytest.mark.asyncio
async def test_refresh_sets_new_access_and_refresh_cookies(transport):
    """При refresh вызывается get_login_response — выставляются новые access и refresh (как при авторизации)."""
    new_access = "new.access.after.refresh"
    new_refresh = "new.refresh.after.refresh"
    response = await transport.get_login_response(new_access, new_refresh)

    assert response.status_code == 204
    cookies = _parse_set_cookie_headers(response)
    names = [n for n, _, _ in cookies]
    assert "access_token" in names
    assert "refresh_token" in names

    access_header = _cookie_by_name(cookies, "access_token")
    refresh_header = _cookie_by_name(cookies, "refresh_token")
    assert new_access in (access_header or "")
    assert new_refresh in (refresh_header or "")


@pytest.mark.asyncio
async def test_login_sets_cookies(app, mock_user_db, transport, mock_audit_log):
    existing = type(
        "User",
        (),
        {
            "id": 1,
            "email": "user@example.com",
            "hashed_password": "",
            "is_active": True,
            "is_verified": True,
        },
    )()
    mock_user_db.get_by_email_result = existing

    async def _fake_login(*_args, **_kwargs):
        return await transport.get_login_response(
            "access.jwt.token", "refresh.jwt.token"
        )

    route = _get_route(app, "auth:cookie.login")
    user_manager = UserManager(mock_user_db)

    with (
        patch(
            "app.services.users.UserManager.authenticate",
            new=AsyncMock(return_value=existing),
        ),
        patch(
            "app.services.users.auth_backend.login",
            new=AsyncMock(side_effect=_fake_login),
        ),
    ):
        response = await route.endpoint(
            request=SimpleNamespace(),
            credentials=SimpleNamespace(username="user@example.com"),
            user_manager=user_manager,
            strategy=get_strategy(),
        )

    assert response.status_code == 204

    cookies = _parse_set_cookie_headers(response)
    names = [name for name, _, _ in cookies]

    assert "access_token" in names
    assert "refresh_token" in names
    mock_audit_log.assert_awaited_once()
    assert mock_audit_log.await_args.args[0] == "login_success"
