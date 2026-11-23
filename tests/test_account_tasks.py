from unittest.mock import AsyncMock, MagicMock

import pytest
from celery.exceptions import Retry
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from app.tasks.account_tasks import SoftDeleteAccountTask
from app.celery.celery_app import celery_app


@pytest.fixture
def soft_delete_account_task():
    return SoftDeleteAccountTask()


@pytest.fixture
def task():
    return celery_app.register_task(SoftDeleteAccountTask())


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


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("SELECT 1", {}, Exception("Database connection error")),
        SQLAlchemyTimeoutError("Connection pool timeout"),
    ],
)
def test_task_retries_on_database_errors(task, error):
    task._execute = AsyncMock(side_effect=error)

    retry_mock = MagicMock(side_effect=Retry())
    task.retry = retry_mock

    with pytest.raises(Retry):
        task.run(user_id=123)

    retry_mock.assert_called_once()

    retry_kwargs = retry_mock.call_args.kwargs

    assert retry_kwargs["exc"] is error
    assert "countdown" in retry_kwargs
    assert task.max_retries == 5


def test_task_does_not_retry_on_unexpected_error(task):
    error = ValueError("Unexpected error")
    task._execute = AsyncMock(side_effect=error)

    retry_mock = MagicMock()
    task.retry = retry_mock

    with pytest.raises(ValueError, match="Unexpected error"):
        task.run(user_id=123)

    retry_mock.assert_not_called()
