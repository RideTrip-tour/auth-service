from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.celery.base_task import AsyncDatabaseTask


class DummyTask(AsyncDatabaseTask):
    async def run_async(self, user_id: int):
        return user_id


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
        patch("app.celery.base_task.UserDatabase"),
        patch("app.celery.base_task.UserManager"),
    ):
        yield


def test_task_success(session_context, task_patches):
    task = DummyTask()

    result = task(user_id=123)

    assert result == 123
    assert not hasattr(task, "user_manager")
    session_context.__aenter__.assert_awaited_once()
    session_context.__aexit__.assert_awaited_once()


def test_task_error(session_context, task_patches):
    task = DummyTask()
    task.run_async = AsyncMock(side_effect=ValueError("Test error"))

    with pytest.raises(ValueError, match="Test error"):
        task(user_id=123)

    assert not hasattr(task, "user_manager")
    session_context.__aexit__.assert_awaited_once()
