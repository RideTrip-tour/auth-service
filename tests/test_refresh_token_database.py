from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.models import RefreshToken
from app.db.refresh_token_database import (
    SQLAlchemyRefreshTokenDatabase,
    get_refresh_token_db,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("with_user", "with_for_update"),
    [
        (False, False),
        (True, False),
        (False, True),
        (True, True),
    ],
)
async def test_get(refresh_token_db, with_user, with_for_update):
    db, session = refresh_token_db

    token = SimpleNamespace(token="test-token")
    result = MagicMock()
    result.scalars.return_value.first.return_value = token
    session.execute.return_value = result

    actual = await db.get(
        "test-token",
        with_user=with_user,
        with_for_update=with_for_update,
    )

    assert actual is token
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_create(refresh_token_db, mocker):
    db, session = refresh_token_db

    refresh_token = MagicMock()
    create_mock = mocker.patch.object(
        RefreshToken,
        "create",
        return_value=refresh_token,
    )

    result = await db.create(
        user_id=42,
        expires_days=10,
    )

    assert result is refresh_token
    create_mock.assert_called_once_with(42, expires_days=10)
    session.add.assert_called_once_with(refresh_token)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete(refresh_token_db):
    db, session = refresh_token_db

    refresh_token = MagicMock()

    await db.delete(refresh_token)

    session.delete.assert_awaited_once_with(refresh_token)


@pytest.mark.asyncio
async def test_delete_by_user_id(refresh_token_db):
    db, session = refresh_token_db

    result = MagicMock()
    result.rowcount = 3
    session.execute.return_value = result

    deleted = await db.delete_by_user_id(42)

    assert deleted == 3
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_by_token(refresh_token_db):
    db, session = refresh_token_db
    result = MagicMock()
    result.rowcount = 1
    session.execute.return_value = result
    deleted = await db.delete_by_token("refresh-token")

    assert deleted == 1
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_refresh_token_db():
    session = AsyncMock()
    generator = get_refresh_token_db(session)
    db = await anext(generator)

    assert isinstance(db, SQLAlchemyRefreshTokenDatabase)
    assert db.session is session
