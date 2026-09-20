import logging

from fastapi_users import (
    models,
)
from fastapi_users.authentication import (
    JWTStrategy,
    Strategy,
)
from fastapi_users.jwt import generate_jwt

from app.db.database import AsyncSessionLocal
from app.db.refresh_token_database import SQLAlchemyRefreshTokenDatabase
from config import settings

logger = logging.getLogger("jwt.servises")


SECRET = settings.jwt_secret


class JWTStrategyCustom(JWTStrategy):
    """Переопределяет payload JWT"""

    async def write_token(self, user: models.UP) -> str:
        data = {
            "sub": str(user.id),
            "is_active": bool(user.is_verified),
            "is_superuser": bool(user.is_superuser),
            "aud": settings.gateway_name,
        }
        return generate_jwt(
            data, self.encode_key, self.lifetime_seconds, algorithm=self.algorithm
        )

    async def destroy_token(self, token: str, user: models.UP) -> None:
        async with AsyncSessionLocal() as session, session.begin():
            token_db = SQLAlchemyRefreshTokenDatabase(session)
            if token:
                await token_db.delete_by_token(token)

    async def destroy_tokens_by_user(self, user: models.UP) -> None:
        async with AsyncSessionLocal() as session:
            if user:
                async with session.begin():
                    token_db = SQLAlchemyRefreshTokenDatabase(session)
                    await token_db.delete_by_user_id(user.id)


def get_strategy() -> Strategy[models.UP, models.ID]:
    return JWTStrategyCustom(
        secret=SECRET,
        lifetime_seconds=settings.access_token_expire_sec,
        token_audience=settings.gateway_name,
    )
