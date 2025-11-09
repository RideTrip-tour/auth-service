from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import User
from app.utils.security import hash_password


async def get_user_by_email(db: AsyncSession, email: str):
    stmt = select(User).filter_by(email=email)
    result = await db.execute(stmt)
    return result.scalars().first()


async def create_user(db: AsyncSession, email: str, password: str):
    hashed_pw = hash_password(password)
    user = User(email=email, hashed_password=hashed_pw)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
