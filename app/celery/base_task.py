import asyncio
import logging

from celery import Task

from app.db.database import AsyncSessionLocalCelery
from app.db.models import OAuthAccount, User
from app.db.user_db import UserDatabase
from app.services.user_manager import UserManager

logger = logging.getLogger(__name__)


class AsyncDatabaseTask(Task):
    def run(self, *args, **kwargs):
        return asyncio.run(self._execute(*args, **kwargs))

    async def _execute(self, *args, **kwargs):
        async with AsyncSessionLocalCelery() as session:
            return await self.run_async(
                UserManager(
                    UserDatabase(
                        session,
                        User,
                        OAuthAccount,
                    ),
                ),
                *args,
                **kwargs,
            )

    async def run_async(self, user_manager, *args, **kwargs):
        raise NotImplementedError

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        logger.warning(
            "Task %s [%s] retrying. Attempt %s/%s. Error: %s",
            self.name,
            task_id,
            self.request.retries,
            self.max_retries,
            exc,
        )

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(
            "Task %s [%s] failed after %s retries. Error: %s",
            self.name,
            task_id,
            self.request.retries,
            exc,
            exc_info=(
                type(exc),
                exc,
                exc.__traceback__,
            ),
        )

    def on_success(self, retval, task_id, args, kwargs):
        logger.info(
            "Task %s [%s] completed successfully",
            self.name,
            task_id,
        )
