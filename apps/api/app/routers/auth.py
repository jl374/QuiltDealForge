from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from app.database import AsyncSessionLocal
from app.models.user import User, UserRole
from app.dependencies import verify_internal_key, get_db, get_current_user, CurrentUser
import uuid

router = APIRouter()


class UpsertUserRequest(BaseModel):
    google_id: str
    email: str
    name: Optional[str] = None
    avatar_url: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    email: str
    name: Optional[str]
    avatar_url: Optional[str]
    role: str

    class Config:
        from_attributes = True


@router.post("/upsert-user", response_model=UserResponse)
async def upsert_user(
    payload: UpsertUserRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal_key),
):
    result = await db.execute(
        select(User).where(User.google_id == payload.google_id)
    )
    user = result.scalar_one_or_none()

    if user:
        user.name = payload.name
        user.avatar_url = payload.avatar_url
        await db.commit()
        await db.refresh(user)
    else:
        # First user automatically gets GP role
        result_count = await db.execute(select(User))
        existing = result_count.scalars().all()
        role = UserRole.GP if len(existing) == 0 else UserRole.Analyst

        user = User(
            google_id=payload.google_id,
            email=payload.email,
            name=payload.name,
            avatar_url=payload.avatar_url,
            role=role,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url,
        role=user.role.value,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        user_id = uuid.UUID(current_user.id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid user ID")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url,
        role=user.role.value,
    )


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UpdateProfileRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        user_id = uuid.UUID(current_user.id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid user ID — sign out and back in to refresh your session")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.name is not None:
        user.name = payload.name
    await db.commit()
    await db.refresh(user)
    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url,
        role=user.role.value,
    )
