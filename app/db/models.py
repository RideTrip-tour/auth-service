from fastapi_users.db import (SQLAlchemyBaseOAuthAccountTable,
                              SQLAlchemyBaseUserTable)
from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from app.db.base import Base


class OAuthAccount(SQLAlchemyBaseOAuthAccountTable[int], Base):
    id: Mapped[int] = mapped_column(primary_key=True)

    @declared_attr
    def user_id(cls) -> Mapped[int]:
        return mapped_column(
            Integer, ForeignKey("user.id", ondelete="cascade"), nullable=False
        )


class User(SQLAlchemyBaseUserTable[int], Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    oauth_accounts: Mapped[list[OAuthAccount]] = relationship(
        "OAuthAccount", lazy="joined"
    )
