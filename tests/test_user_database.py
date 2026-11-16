from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.models import User
from app.db.user_db import UserDatabase


@pytest.fixture
def user_db():
    db = UserDatabase.__new__(UserDatabase)
    db.user_table = User
    db.session = MagicMock()
    db.session.execute = AsyncMock()
    db.session.refresh = AsyncMock()
    db.session.commit = AsyncMock()
    db.session.rollback = AsyncMock()
    return db


@pytest.fixture
def user():
    user = MagicMock()
    user.id = 1
    user.is_active = False
    return user


@pytest.mark.asyncio
async def test_compare_and_update_success(user_db, user):
    user_db.session.execute.return_value = MagicMock(rowcount=1)

    result = await user_db.compare_and_update(
        user,
        {"is_active": True},
        ("is_active",),
    )

    assert result is user
    user_db.session.execute.assert_awaited_once()
    user_db.session.refresh.assert_awaited_once_with(user)
    user_db.session.commit.assert_not_awaited()
    user_db.session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_compare_and_update_not_found(user_db, user):
    user_db.session.execute.return_value = MagicMock(rowcount=0)

    result = await user_db.compare_and_update(
        user,
        {"is_active": True},
        ("is_active",),
    )

    assert result is None
    user_db.session.refresh.assert_not_awaited()
    user_db.session.commit.assert_not_awaited()
    user_db.session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_compare_and_update_committed_success(user_db, user):
    user_db.compare_and_update = AsyncMock(return_value=user)

    result = await user_db.compare_and_update_committed(
        user,
        {"is_active": True},
        ("is_active",),
    )

    assert result is user
    user_db.session.commit.assert_awaited_once()
    user_db.session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_compare_and_update_committed_not_found(user_db, user):
    user_db.compare_and_update = AsyncMock(return_value=None)

    result = await user_db.compare_and_update_committed(
        user,
        {"is_active": True},
        ("is_active",),
    )

    assert result is None
    user_db.session.rollback.assert_awaited_once()
    user_db.session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_compare_and_update_committed_error(user_db, user):
    user_db.compare_and_update = AsyncMock(side_effect=RuntimeError("Database error"))

    with pytest.raises(RuntimeError, match="Database error"):
        await user_db.compare_and_update_committed(
            user,
            {"is_active": True},
            ("is_active",),
        )

    user_db.session.rollback.assert_awaited_once()
    user_db.session.commit.assert_not_awaited()
