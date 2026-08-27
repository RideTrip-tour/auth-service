from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EmailChangeRequest


class SQLAlchemyEmailChangeRequestDatabase:
    """Адаптер для pending-запросов смены email."""

    session: AsyncSession
    token_table: type[EmailChangeRequest]

    def __init__(
        self,
        session: AsyncSession,
        token_table: type[EmailChangeRequest] = EmailChangeRequest,
    ):
        self.session = session
        self.token_table = token_table

    async def get_valid(self, token: str) -> EmailChangeRequest | None:
        statement = select(self.token_table).where(
            self.token_table.token == token,
            self.token_table.expires_at > datetime.now(UTC),
        )
        result = await self.session.execute(statement)
        return result.scalars().first()

    async def replace_for_user(
        self,
        *,
        user_id: int,
        current_email: str,
        new_email: str,
        token: str,
        lifetime_seconds: int,
    ) -> EmailChangeRequest:
        await self.session.execute(
            delete(self.token_table).where(self.token_table.user_id == user_id)
        )
        request = EmailChangeRequest.create(
            user_id=user_id,
            token=token,
            current_email=current_email,
            new_email=new_email,
            lifetime_seconds=lifetime_seconds,
        )
        self.session.add(request)
        await self.session.commit()
        await self.session.refresh(request)
        return request

    async def delete_by_token(self, token: str) -> int | None:
        result = await self.session.execute(
            delete(self.token_table).where(self.token_table.token == token)
        )
        await self.session.commit()
        return result.rowcount
