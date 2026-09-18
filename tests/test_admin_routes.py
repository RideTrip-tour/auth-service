# Тесты для админки
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi_users import exceptions

from app.db.database import get_async_session
from app.db.models import User
from app.routes.admin import admin_routes
from app.services.users import get_user_manager


@pytest.fixture
def override_admin(app):
    async def mock_admin_user():
        return User(id=1, email="admin@test.com", is_superuser=True)

    app.dependency_overrides[admin_routes.dependencies[0].dependency] = mock_admin_user

    yield

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_user(client, app, override_admin):
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [
        User(
            id=1,
            email="admin@test.com",
            is_superuser=True,
            is_active=True,
            is_verified=False,
        )
    ]
    mock_db.execute.return_value = mock_result

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_async_session] = mock_get_db
    response = await client.get("/api/admin/?id=1&email=admin@test.com")
    data = response.json()
    assert response.status_code == 200
    assert len(data) == 1


@pytest.mark.asyncio
async def test_delete_user(client, app, override_admin):
    mock_user_manager = AsyncMock()
    mock_user_manager.get.return_value = User(
        id=1,
        email="test@test.com",
        is_active=True,
        is_verified=False,
        is_superuser=False,
    )

    async def mock_get_user_manager():
        yield mock_user_manager

    app.dependency_overrides[get_user_manager] = mock_get_user_manager
    response = await client.delete("/api/admin/1")
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_user_not_found(client, app, override_admin):
    mock_user_manager = AsyncMock()
    mock_user_manager.get.side_effect = exceptions.UserNotExists()

    async def mock_get_user_manager():
        yield mock_user_manager

    app.dependency_overrides[get_user_manager] = mock_get_user_manager
    response = await client.delete("/api/admin/1")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_user(client, app, override_admin):
    mock_user_manager = AsyncMock()
    mock_user_manager.get.return_value = User(
        id=1,
        email="test@test.com",
        is_active=False,
        is_superuser=True,
        is_verified=False,
    )
    mock_user_manager.update.return_value = User(
        id=1,
        email="test@test.com",
        is_active=False,
        is_superuser=True,
        is_verified=False,
    )

    async def mock_get_user_manager():
        yield mock_user_manager

    app.dependency_overrides[get_user_manager] = mock_get_user_manager

    response = await client.patch("/api/admin/1", json={"is_active": False})
    assert response.status_code == 200
    assert response.json()["is_active"] == False


@pytest.mark.asyncio
async def test_create_user(client, app, override_admin):
    mock_user_manager = AsyncMock()
    mock_user_manager.create.return_value = User(
        id=1,
        email="test@test.com",
        is_active=False,
        is_superuser=True,
        is_verified=False,
    )

    async def mock_get_user_manager():
        yield mock_user_manager

    app.dependency_overrides[get_user_manager] = mock_get_user_manager

    response = await client.post(
        "/api/admin/", json={"id": 1, "email": "test@test.com", "password": "123456789"}
    )
    assert response.status_code == 201
    assert response.json()["email"] == "test@test.com"


@pytest.mark.asyncio
async def test_create_user_already_exist(client, app, override_admin):
    mock_user_manager = AsyncMock()
    mock_user_manager.create.side_effect = exceptions.UserAlreadyExists()

    async def mock_get_user_manager():
        yield mock_user_manager

    app.dependency_overrides[get_user_manager] = mock_get_user_manager

    response = await client.post(
        "/api/admin/", json={"id": 1, "email": "test@test.com", "password": "123456789"}
    )
    assert response.status_code == 400
