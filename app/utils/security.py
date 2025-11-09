from passlib.context import CryptContext
from jose import jwt
import datetime as dt
from datetime import datetime, timedelta
from fastapi import HTTPException, status
from app.schemas.user import UserCreate, UserLogin, UserData, UserResponse
from config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password, hashed_password) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    user_obj: UserData,
    expires_delta: timedelta = timedelta(minutes=settings.access_token_expire_min),
) -> str:
    to_encode = user_obj.model_dump()
    expire = datetime.now(dt.UTC) + expires_delta
    to_encode.update({"exp": expire.timestamp()})
    print(to_encode)
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def validate_token(token: str):
    """Валидирует токен при неудаче выбрасывает исключение"""
    payload = jwt.decode(token, settings.jwt_secret)
    sub = payload.get("sub", None)
    exp = payload.get("exp", None)
    if exp < datetime.now(dt.UTC).timestamp():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="The token has expired"
        )
