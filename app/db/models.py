from datetime import datetime, timedelta, timezone
from fastapi_users.db import SQLAlchemyBaseOAuthAccountTable, SQLAlchemyBaseUserTable
import secrets
from sqlalchemy import DateTime, ForeignKey, JSON, func, Integer, String
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from app.db.base import Base


USER_ID_FK = "user.id"


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
            Integer, ForeignKey(USER_ID_FK, ondelete="cascade"), nullable=False
        )


class User(AuditMixin, SQLAlchemyBaseUserTable[int], Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    oauth_accounts: Mapped[list[OAuthAccount]] = relationship(
        "OAuthAccount",
        back_populates="user",
        passive_deletes=True,
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        passive_deletes=True,
        cascade="all, delete-orphan",
    )
    email_change_request: Mapped["EmailChangeRequest | None"] = relationship(
        "EmailChangeRequest",
        back_populates="user",
        passive_deletes=True,
        cascade="all, delete-orphan",
    )


class RefreshToken(AuditMixin, Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey(USER_ID_FK, ondelete="CASCADE"), nullable=False
    )
    user: Mapped["User"] = relationship(back_populates="refresh_tokens")
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    @staticmethod
    def create(user_id: int, expires_days: int = 7) -> "RefreshToken":
        """Создаёт новый refresh token"""
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)
        return RefreshToken(user_id=user_id, token=token, expires_at=expires_at)


class EmailChangeRequest(AuditMixin, Base):
    __tablename__ = "email_change_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey(USER_ID_FK, ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    current_email: Mapped[str] = mapped_column(String(320), nullable=False)
    new_email: Mapped[str] = mapped_column(String(320), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    user: Mapped["User"] = relationship(back_populates="email_change_request")

    @staticmethod
    def create(
        *,
        user_id: int,
        token: str,
        current_email: str,
        new_email: str,
        lifetime_seconds: int,
    ) -> "EmailChangeRequest":
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=lifetime_seconds)
        return EmailChangeRequest(
            user_id=user_id,
            token=token,
            current_email=current_email,
            new_email=new_email,
            expires_at=expires_at,
        )


class UserActionLog(Base):
    __tablename__ = "user_action_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey(USER_ID_FK, ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    success: Mapped[bool] = mapped_column(nullable=False, default=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
