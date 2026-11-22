from unittest.mock import AsyncMock

import pytest

from app.tasks.account_tasks import SoftDeleteAccountTask


@pytest.fixture
def soft_delete_account_task():
    return SoftDeleteAccountTask()


@pytest.mark.asyncio
async def test_soft_delete_account_success(soft_delete_account_task, user):
    """Успешное удаление существующего пользователя."""
    soft_delete_account_task.user_manager = AsyncMock()
    soft_delete_account_task.user_manager.get.return_value = user

    await soft_delete_account_task.run_async(user_id=user.id)

    soft_delete_account_task.user_manager.get.assert_awaited_once_with(user.id)
    soft_delete_account_task.user_manager.delete_account.assert_awaited_once_with(user)


@pytest.mark.asyncio
async def test_soft_delete_account_user_not_found(soft_delete_account_task):
    """Пользователь не найден — удаление не выполняется."""
    soft_delete_account_task.user_manager = AsyncMock()
    soft_delete_account_task.user_manager.get.return_value = None

    await soft_delete_account_task.run_async(user_id=123)

    soft_delete_account_task.user_manager.get.assert_awaited_once_with(123)
    soft_delete_account_task.user_manager.delete_account.assert_not_awaited()


@pytest.mark.asyncio
async def test_soft_delete_account_already_deleted(soft_delete_account_task, user):
    """Повторное удаление уже удалённого пользователя."""
    user.deleted_at = object()

    soft_delete_account_task.user_manager = AsyncMock()
    soft_delete_account_task.user_manager.get.return_value = user

    await soft_delete_account_task.run_async(user_id=user.id)

    soft_delete_account_task.user_manager.get.assert_awaited_once_with(user.id)
    soft_delete_account_task.user_manager.delete_account.assert_not_awaited()
