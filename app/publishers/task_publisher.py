import asyncio
import logging

from celery import Celery
from celery.result import AsyncResult

logger = logging.getLogger(__name__)


class TaskPublisher:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, celery_app: Celery) -> None:
        if not hasattr(self, "celery_app"):
            self.celery_app = celery_app

    async def _publish_task(
        self,
        queue: str,
        task_name: str,
        args: list | None = None,
        kwargs: dict | None = None,
    ) -> AsyncResult:
        try:
            return await asyncio.to_thread(
                self.celery_app.send_task,
                task_name,
                args=args or [],
                kwargs=kwargs or {},
                queue=queue,
            )
        except Exception:
            logger.exception(
                "Failed to publish Celery task: %s to queue: %s",
                task_name,
                queue,
            )
            raise
