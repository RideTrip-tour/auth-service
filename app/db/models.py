from datetime import datetime, timezone
from fastapi_users.db import (SQLAlchemyBaseOAuthAccountTable,
                              SQLAlchemyBaseUserTable)
from sqlalchemy import Boolean, DateTime, ForeignKey, func, Integer
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from app.db.base import Base

class AuditMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    def soft_delete(self) -> None:
        now = datetime.now(timezone.utc)
        self.deleted_at = now
        self.updated_at = now

    def restore(self) -> None:
        self.deleted_at = None
        self.updated_at = datetime.now(timezone.utc)

class OAuthAccount(AuditMixin, SQLAlchemyBaseOAuthAccountTable[int], Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    user: Mapped["User"] = relationship(
        "User",
        back_populates="oauth_accounts",
    )

    @declared_attr
    def user_id(cls) -> Mapped[int]:
        return mapped_column(
            Integer, ForeignKey("user.id", ondelete="cascade"), nullable=False
        )


class User(AuditMixin, SQLAlchemyBaseUserTable[int], Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    oauth_accounts: Mapped[list[OAuthAccount]] = relationship(
        "OAuthAccount",
        back_populates="user",
        passive_deletes=True,
    )
