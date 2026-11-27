from unittest.mock import AsyncMock, MagicMock

import pytest
from celery.exceptions import Retry
from sqlalchemy.exc import OperationalError, TimeoutError

from app.celery.celery_app import celery_app
from app.exceptions.users import UserUpdateFailed
from app.tasks.account_tasks import SoftDeleteAccountTask


@pytest.fixture
def soft_delete_account_task():
    return SoftDeleteAccountTask()


@pytest.fixture
def task():
    return celery_app.register_task(SoftDeleteAccountTask())


@pytest.fixture
def user_manager():
    return AsyncMock()


@pytest.mark.asyncio
async def test_soft_delete_account_success(
    soft_delete_account_task,
    user_manager,
    user,
):
    """Успешное удаление существующего пользователя."""
    user_manager.get.return_value = user

    await soft_delete_account_task.run_async(
        user_manager=user_manager,
        user_id=user.id,
    )

    user_manager.get.assert_awaited_once_with(user.id)
    user_manager.delete_account.assert_awaited_once_with(user)


@pytest.mark.asyncio
async def test_soft_delete_account_user_not_found(
    soft_delete_account_task,
    user_manager,
):
    """Пользователь не найден — удаление не выполняется."""
    user_manager.get.return_value = None

    await soft_delete_account_task.run_async(
        user_manager=user_manager,
        user_id=123,
    )

    user_manager.get.assert_awaited_once_with(123)
    user_manager.delete_account.assert_not_awaited()


@pytest.mark.asyncio
async def test_soft_delete_account_already_deleted(
    soft_delete_account_task,
    user_manager,
    user,
):
    """Повторное удаление уже удалённого пользователя."""
    user.deleted_at = object()
    user_manager.get.return_value = user

    await soft_delete_account_task.run_async(
        user_manager=user_manager,
        user_id=user.id,
    )

    user_manager.get.assert_awaited_once_with(user.id)
    user_manager.delete_account.assert_not_awaited()


@pytest.mark.parametrize(
    "error",
    [
        OperationalError(
            "SELECT 1",
            {},
            Exception("Database connection error"),
        ),
        TimeoutError("Connection pool timeout"),
        UserUpdateFailed(),
    ],
)
def test_task_retries_on_database_errors(task, error):
    """Временные ошибки БД приводят к автоматическому повтору."""
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
    assert task.autoretry_for == (OperationalError, TimeoutError, UserUpdateFailed)
    assert task.retry_backoff == 5
    assert task.retry_backoff_max == 300
    assert task.retry_jitter is True


def test_task_does_not_retry_on_unexpected_error(task):
    """Неожиданные ошибки не приводят к повторному запуску."""
    error = ValueError("Unexpected error")
    task._execute = AsyncMock(side_effect=error)

    retry_mock = MagicMock()
    task.retry = retry_mock

    with pytest.raises(ValueError, match="Unexpected error"):
        task.run(user_id=123)

    retry_mock.assert_not_called()
