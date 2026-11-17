import logging
from unittest.mock import MagicMock

import pytest


@pytest.mark.asyncio
async def test_publish_task_returns_async_result(task_publisher, celery_app):
    expected_result = MagicMock()

    celery_app.send_task.return_value = expected_result

    result = await task_publisher._publish_task(
        queue="auth",
        task_name="auth.soft_delete_account",
        args=[1],
        kwargs={"user_id": 1},
    )

    assert result is expected_result

    celery_app.send_task.assert_called_once_with(
        "auth.soft_delete_account",
        args=[1],
        kwargs={"user_id": 1},
        queue="auth",
    )


@pytest.mark.asyncio
async def test_publish_task_uses_empty_args_and_kwargs_by_default(
    task_publisher,
    celery_app,
):
    await task_publisher._publish_task(
        queue="auth",
        task_name="auth.soft_delete_account",
    )

    celery_app.send_task.assert_called_once_with(
        "auth.soft_delete_account",
        args=[],
        kwargs={},
        queue="auth",
    )


@pytest.mark.asyncio
async def test_publish_task_logs_and_reraises_exception(
    task_publisher,
    celery_app,
    caplog,
):
    error = ConnectionError("Redis connection failed")
    celery_app.send_task.side_effect = error

    with (
        caplog.at_level(logging.ERROR),
        pytest.raises(ConnectionError, match="Redis connection failed"),
    ):
        await task_publisher._publish_task(
            queue="auth",
            task_name="auth.soft_delete_account",
            kwargs={"user_id": 1},
        )

    celery_app.send_task.assert_called_once()

    assert (
        "Failed to publish Celery task: auth.soft_delete_account to queue: auth"
    ) in caplog.text
