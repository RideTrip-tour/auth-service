import asyncio

from app.celery.celery_app import celery_app
from app.db.database import AsyncSessionLocal
from app.db.models import OAuthAccount, User
from app.db.user_db import UserDatabase
from app.services.user_manager import UserManager


@celery_app.task(name="auth.soft_delete_account")
def soft_delete_account(user_id: int) -> None:
    asyncio.run(_soft_delete_account(user_id))


async def _soft_delete_account(user_id: int) -> None:
    async with AsyncSessionLocal() as session:
        manager = UserManager(
            user_db=UserDatabase(session, User, OAuthAccount),
        )
        user = await manager.get(user_id)

        if user is None or user.deleted_at is not None:
            return

        await manager.delete_account(user)
