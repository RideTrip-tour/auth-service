import logging
from collections.abc import Iterable
from typing import cast

from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy import CursorResult
from sqlalchemy import update as sqlalchemy_update

from app.db.models import User

logger = logging.getLogger(__name__)


class UserDatabase(SQLAlchemyUserDatabase):
    async def compare_and_update(
        self,
        user: User,
        values: dict,
        fields: Iterable[str],
    ) -> User | None:
        """
        Атомарно обновляет поля пользователя при неизменённых исходных значениях.

        Изменения применяются только в рамках текущей транзакции сессии.
        Не вызывает session.commit(). Закоммитить их должен вызывающий код.
        """
        if self.session is None or self.user_table is None:
            raise RuntimeError("Atomic user update requires SQLAlchemy user DB")

        query = sqlalchemy_update(self.user_table).where(self.user_table.id == user.id)

        for field in fields:
            query = query.where(getattr(self.user_table, field) == getattr(user, field))

        result = cast(
            CursorResult,
            await self.session.execute(query.values(**values)),
        )

        if result.rowcount != 1:
            return None

        await self.session.refresh(user)

        return user

    async def compare_and_update_committed(
        self,
        user: User,
        values: dict,
        fields: Iterable[str],
    ) -> User | None:
        try:
            updated_user = await self.compare_and_update(user, values, fields)

            if updated_user is None:
                await self.rollback()
                return None

            await self.commit()
            return updated_user

        except Exception:
            logger.exception("Error while updating user: %s", user.id)
            await self.rollback()
            raise

    async def restore_user(
        self,
        user: User,
        hashed_password: str,
    ) -> User | None:
        async with self.session.begin_nested():
            updated_user = await self.compare_and_update(
                user,
                {
                    "hashed_password": hashed_password,
                    "is_active": True,
                    "deleted_at": None,
                },
                ("hashed_password", "deleted_at", "is_active"),
            )

            return updated_user

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
