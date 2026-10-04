from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.email_change_request_database import (
    SQLAlchemyEmailChangeRequestDatabase,
)
from app.db.models import EmailChangeRequest


@pytest.mark.asyncio
async def test_get_valid_returns_request():
    request = SimpleNamespace(
        token="valid-token",
        expires_at=datetime.now(UTC),
    )

    scalars = MagicMock()
    scalars.first.return_value = request

    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                scalars=MagicMock(return_value=scalars),
            )
        )
    )

    db = SQLAlchemyEmailChangeRequestDatabase(session)

    result = await db.get_valid("valid-token")

    assert result is request
    session.execute.assert_awaited_once()
    scalars.first.assert_called_once()


@pytest.mark.asyncio
async def test_get_valid_returns_none_when_request_not_found():
    scalars = MagicMock()
    scalars.first.return_value = None

    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                scalars=MagicMock(return_value=scalars),
            )
        )
    )

    db = SQLAlchemyEmailChangeRequestDatabase(session)

    result = await db.get_valid("invalid-token")

    assert result is None
    session.execute.assert_awaited_once()
    scalars.first.assert_called_once()


@pytest.mark.asyncio
async def test_replace_for_user_deletes_old_and_creates_new():
    session = SimpleNamespace(
        execute=AsyncMock(),
        add=MagicMock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )

    db = SQLAlchemyEmailChangeRequestDatabase(session)

    result = await db.replace_for_user(
        user_id=7,
        current_email="old@example.com",
        new_email="new@example.com",
        token="new-token",
        lifetime_seconds=3600,
    )

    assert isinstance(result, EmailChangeRequest)
    assert result.user_id == 7
    assert result.token == "new-token"
    assert result.current_email == "old@example.com"
    assert result.new_email == "new@example.com"

    session.execute.assert_awaited_once()
    session.add.assert_called_once_with(result)
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_delete_by_token_returns_deleted_count():
    result = SimpleNamespace(rowcount=1)

    session = SimpleNamespace(
        execute=AsyncMock(return_value=result),
        commit=AsyncMock(),
    )

    db = SQLAlchemyEmailChangeRequestDatabase(session)

    deleted_count = await db.delete_by_token("token-to-delete")

    assert deleted_count == 1
    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()
