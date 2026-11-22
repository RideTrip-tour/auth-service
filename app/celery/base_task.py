import asyncio

from celery import Task

from app.db.database import AsyncSessionLocalCelery
from app.db.models import OAuthAccount, User
from app.db.user_db import UserDatabase
from app.services.user_manager import UserManager


class AsyncDatabaseTask(Task):
    def __call__(self, *args, **kwargs):
        return asyncio.run(self._execute(*args, **kwargs))

    async def _execute(self, *args, **kwargs):
        async with AsyncSessionLocalCelery() as session:
            user_db = UserDatabase(session, User, OAuthAccount)

            self.user_manager = UserManager(user_db)

            try:
                return await self.run_async(*args, **kwargs)
            finally:
                del self.user_manager

    async def run_async(self, *args, **kwargs):
        raise NotImplementedError
