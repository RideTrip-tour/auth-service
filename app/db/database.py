from typing import Annotated

from fastapi import Depends
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import OAuthAccount, User
from app.db.user_db import UserDatabase
from config import settings

db_url = URL.create(
    drivername=settings.db_driver,
    username=settings.db_user,
    password=settings.db_pass,
    host=settings.db_host,
    port=settings.db_port,
    database=settings.db_name,
)

engine = create_async_engine(
    db_url,
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


async def get_async_session():
    async with AsyncSessionLocal() as session:
        yield session


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield UserDatabase(session, User, OAuthAccount)


UserDatabaseDep = Annotated[UserDatabase, Depends(get_user_db)]
