from app.celery.base_task import AsyncDatabaseTask
from app.celery.celery_app import celery_app


class SoftDeleteAccountTask(AsyncDatabaseTask):
    name = "auth.soft_delete_account"

    max_retries = 5
    retry_backoff = 5
    retry_backoff_max = 300
    retry_jitter = True

    async def run_async(self, user_id: int) -> None:
        user = await self.user_manager.get(user_id)

        if user is None or user.deleted_at is not None:
            return

        await self.user_manager.delete_account(user)


celery_app.register_task(SoftDeleteAccountTask())
