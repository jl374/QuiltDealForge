from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import uuid
from app.dependencies import get_db, require_role
from app.schemas.contact import ContactCreate, ContactUpdate, ContactResponse
from app.models.contact import Contact

router = APIRouter()


@router.get("/", response_model=list[ContactResponse])
async def list_contacts(
    company_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["GP", "Analyst", "Admin"])),
):
    result = await db.execute(
        select(Contact)
        .where(Contact.company_id == company_id)
        .order_by(Contact.created_at.asc())
    )
    return list(result.scalars().all())


@router.post("/", response_model=ContactResponse, status_code=201)
async def create_contact(
    payload: ContactCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["GP", "Analyst", "Admin"])),
):
    contact = Contact(**payload.model_dump())
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


@router.patch("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: uuid.UUID,
    payload: ContactUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["GP", "Admin"])),
):
    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    await db.commit()
    await db.refresh(contact)
    return contact
