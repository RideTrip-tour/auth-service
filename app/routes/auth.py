from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.schemas.user import UserCreate, UserLogin, UserData, UserResponse
from app.schemas.token import Token
from app.crud.user import create_user, get_user_by_email
from app.utils.security import verify_password, create_access_token
from app.db.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register user by email and pass."""
    if await get_user_by_email(db, user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )
    user = await create_user(db, user_data.email, user_data.password)
    return {"id": user.id}


@router.post("/login", response_model=Token)
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    """Login user by email and pass."""
    user = await get_user_by_email(db, user_data.email)
    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    user_data = UserData.model_validate(user)
    token = create_access_token(user_data)
    return {"access_token": token, "refresh_token": "_"}


@router.post("/auth", response_model=UserData)
async def auth(token: Token, db: Session = Depends(get_db)): ...
