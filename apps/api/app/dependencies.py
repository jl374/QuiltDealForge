from fastapi import Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from app.database import AsyncSessionLocal
from app.config import settings
import uuid


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


class CurrentUser:
    def __init__(self, user_id: str, role: str):
        self.id = user_id
        self.role = role


def get_current_user(
    x_user_id: Optional[str] = Header(default=None),
    x_user_role: Optional[str] = Header(default=None),
) -> CurrentUser:
    # Require at least a role header; user_id may be a google ID during initial setup
    if not x_user_role:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return CurrentUser(user_id=x_user_id or "", role=x_user_role)


def require_role(allowed_roles: List[str]):
    def dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{current_user.role}' is not authorized for this action.",
            )
        return current_user

    return dependency


def verify_internal_key(x_internal_key: Optional[str] = Header(default=None)):
    if x_internal_key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid internal API key")
