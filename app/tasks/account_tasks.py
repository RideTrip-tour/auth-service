import logging

from sqlalchemy.exc import OperationalError, TimeoutError

from app.celery.base_task import AsyncDatabaseTask
from app.celery.celery_app import celery_app
from app.exceptions.users import UserUpdateFailed
from app.services.user_manager import UserManager

logger = logging.getLogger(__name__)


class SoftDeleteAccountTask(AsyncDatabaseTask):
    name = "auth.soft_delete_account"

    autoretry_for = (
        OperationalError,
        TimeoutError,
        UserUpdateFailed,
    )

    max_retries = 5
    retry_backoff = 5
    retry_backoff_max = 300
    retry_jitter = True

    async def run_async(self, user_manager: UserManager, user_id: int) -> None:
        user = await user_manager.get(user_id)

        if user is None or user.deleted_at is not None:
            return

        await user_manager.delete_account(user)
        logger.info(
            "Account %s soft-deleted successfully",
            user_id,
        )


celery_app.register_task(SoftDeleteAccountTask())
