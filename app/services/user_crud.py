from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.models import User
from app.schemas import UserCreate
from .auth import get_password_hash, verify_password

async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    res = await db.execute(select(User).where(User.email == email))
    return res.scalar_one_or_none()

async def create_user(db: AsyncSession, payload: UserCreate) -> User:
    existing = await get_user_by_email(db, payload.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered.")
    user = User(email=payload.email, hashed_password=get_password_hash(payload.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(db, email)
    if not user or not verify_password(password, str(user.hashed_password)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password.")
    return user
