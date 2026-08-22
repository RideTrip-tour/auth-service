from datetime import datetime

from fastapi import Depends
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_async_session
from app.db.models import RefreshToken


class SQLAlchemyRefreshTokenDatabase:
    """Адаптер для работы с refresh token в SQLAlchemy."""

    session: AsyncSession
    token_table: type[RefreshToken]

    def __init__(
        self,
        session: AsyncSession,
        token_table: type[RefreshToken] = RefreshToken,
    ):
        self.session = session
        self.token_table = token_table

    async def get(
        self,
        token: str,
        with_user: bool = False,
        with_for_update: bool = False,
    ) -> RefreshToken | None:
        statement = select(self.token_table).where(
            self.token_table.token == token,
            self.token_table.expires_at > datetime.now(datetime.UTC),
        )
        if with_user:
            statement = statement.options(selectinload(self.token_table.user))
        if with_for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalars().first()

    async def create(
        self,
        user_id: int,
        expires_days: int = 7,
    ) -> RefreshToken:
        refresh_token = RefreshToken.create(user_id, expires_days=expires_days)
        self.session.add(refresh_token)
        await self.session.flush()
        return refresh_token

    async def delete(self, refresh_token: RefreshToken) -> None:
        await self.session.delete(refresh_token)

    async def delete_by_user_id(self, user_id: int) -> int | None:
        result = await self.session.execute(
            delete(self.token_table).where(self.token_table.user_id == user_id)
        )
        return result.rowcount

    async def delete_by_token(self, token: str) -> int | None:
        result = await self.session.execute(
            delete(self.token_table).where(self.token_table.token == token)
        )
        return result.rowcount


async def get_refresh_token_db(
    session: AsyncSession = Depends(get_async_session),
):
    yield SQLAlchemyRefreshTokenDatabase(session)
