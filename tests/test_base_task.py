from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.celery.base_task import AsyncDatabaseTask
from app.celery.celery_app import celery_app


class DummyTask(AsyncDatabaseTask):
    name = "test.dummy_task"

    async def run_async(self, user_manager, user_id: int):
        return user_id


@pytest.fixture
def task():
    return celery_app.register_task(DummyTask())


@pytest.fixture
def session_context():
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=MagicMock())
    context.__aexit__ = AsyncMock(return_value=False)
    return context


@pytest.fixture
def task_patches(session_context):
    with (
        patch(
            "app.celery.base_task.AsyncSessionLocalCelery",
            return_value=session_context,
        ),
        patch("app.celery.base_task.UserDatabase") as user_database_mock,
        patch("app.celery.base_task.UserManager") as user_manager_mock,
    ):
        yield {
            "user_database": user_database_mock,
            "user_manager": user_manager_mock,
        }


def test_task_success(task, session_context, task_patches):
    task.run_async = AsyncMock(return_value=123)

    result = task(user_id=123)

    assert result == 123

    task_patches["user_database"].assert_called_once()
    task_patches["user_manager"].assert_called_once()

    task.run_async.assert_awaited_once_with(
        task_patches["user_manager"].return_value,
        user_id=123,
    )

    session_context.__aenter__.assert_awaited_once()
    session_context.__aexit__.assert_awaited_once()


def test_task_error(task, session_context, task_patches):
    task.run_async = AsyncMock(
        side_effect=ValueError("Test error"),
    )

    with pytest.raises(ValueError, match="Test error"):
        task(user_id=123)

    task.run_async.assert_awaited_once()
    session_context.__aexit__.assert_awaited_once()
