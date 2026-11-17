from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.tasks import account_tasks


@pytest.mark.asyncio
async def test_soft_delete_account_success(
    monkeypatch,
    user_manager,
    celery_session,
):
    user = SimpleNamespace(deleted_at=None)

    user_manager.get = AsyncMock(return_value=user)
    user_manager.delete_account = AsyncMock()

    monkeypatch.setattr(
        account_tasks,
        "UserManager",
        lambda user_db: user_manager,
    )

    await account_tasks._soft_delete_account(user_id=123)

    user_manager.get.assert_awaited_once_with(123)
    user_manager.delete_account.assert_awaited_once_with(user)


@pytest.mark.asyncio
async def test_soft_delete_account_user_not_found(
    monkeypatch,
    user_manager,
    celery_session,
):
    user_manager.get = AsyncMock(return_value=None)
    user_manager.delete_account = AsyncMock()

    monkeypatch.setattr(
        account_tasks,
        "UserManager",
        lambda user_db: user_manager,
    )

    await account_tasks._soft_delete_account(user_id=123)

    user_manager.get.assert_awaited_once_with(123)
    user_manager.delete_account.assert_not_awaited()


@pytest.mark.asyncio
async def test_soft_delete_account_already_deleted(
    monkeypatch,
    user_manager,
    celery_session,
):
    user = SimpleNamespace(deleted_at=MagicMock())

    user_manager.get = AsyncMock(return_value=user)
    user_manager.delete_account = AsyncMock()

    monkeypatch.setattr(
        account_tasks,
        "UserManager",
        lambda user_db: user_manager,
    )

    await account_tasks._soft_delete_account(user_id=123)

    user_manager.get.assert_awaited_once_with(123)
    user_manager.delete_account.assert_not_awaited()


def test_soft_delete_account_task(monkeypatch):
    soft_delete_mock = AsyncMock()

    monkeypatch.setattr(
        account_tasks,
        "_soft_delete_account",
        soft_delete_mock,
    )

    account_tasks.soft_delete_account.run(user_id=123)

    soft_delete_mock.assert_awaited_once_with(123)
