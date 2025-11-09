from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from config import settings

db_url = URL.create(
    drivername=settings.db_driver,
    username=settings.db_user,
    password=settings.db_pass,
    host=settings.db_host,
    port=settings.db_port,
    database=settings.db_name,
)

engine = create_async_engine(db_url)
AsyncSessionLocal = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
