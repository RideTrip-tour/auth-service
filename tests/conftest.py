import os
import sys
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Делаем так, чтобы в тестах корректно импортировался пакет `app` и `config`
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import settings  # noqa: E402


@pytest.fixture(autouse=True)
def reset_email_settings() -> Generator[None, None, None]:
    """
    Авто-фикстура для изоляции настроек email между тестами.

    Сохраняет исходные значения и восстанавливает их после каждого теста.
    """
    original = {
        "debug": settings.debug,
        "mail_server": settings.mail_server,
        "mail_from": settings.mail_from,
        "mail_username": settings.mail_username,
        "mail_password": settings.mail_password,
    }

    try:
        yield
    finally:
        settings.debug = original["debug"]
        settings.mail_server = original["mail_server"]
        settings.mail_from = original["mail_from"]
        settings.mail_username = original["mail_username"]
        settings.mail_password = original["mail_password"]


class MockUserDb:
    """Мок БД пользователей без MagicMock, чтобы не путать с UserManager.get_by_email."""

    def __init__(self):
        self.get_by_email_result = None
        self.create_result = MagicMock(
            id=1,
            email="user@example.com",
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )
        self.create_called = False
        self.create_call_data = None

    async def get_by_email(self, email: str):
        return self.get_by_email_result

    async def create(self, data: dict):
        self.create_called = True
        self.create_call_data = data
        return self.create_result


@pytest.fixture
def mock_user_db() -> MockUserDb:
    """Мок БД пользователей: get_by_email и create."""
    return MockUserDb()


@pytest.fixture
def app():
    """Приложение FastAPI для тестов."""
    from main import app as fastapi_app

    return fastapi_app


@pytest_asyncio.fixture
async def auth_app(app, mock_user_db):
    """Приложение с подменённым get_user_db на mock_user_db (адаптер БД)."""
    from app.db.database import get_user_db

    async def override_get_user_db() -> AsyncGenerator:
        yield mock_user_db

    # Подменяем get_user_db: get_user_manager получит mock_user_db и создаст UserManager(mock_user_db)
    app.dependency_overrides[get_user_db] = override_get_user_db
    try:
        yield app
    finally:
        app.dependency_overrides.pop(get_user_db, None)


@pytest_asyncio.fixture
async def client(auth_app):
    """Async HTTP-клиент для вызова API аутентификации."""
    async with AsyncClient(
        transport=ASGITransport(app=auth_app),
        base_url="http://test",
    ) as ac:
        yield ac
