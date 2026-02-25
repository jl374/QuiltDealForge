from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime, date
import uuid


class ContactCreate(BaseModel):
    company_id: uuid.UUID
    name: str
    title: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    notes: Optional[str] = None


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    facebook_url: Optional[str] = None
    is_principal_owner: Optional[bool] = None
    enrichment_status: Optional[str] = None
    enrichment_source: Optional[str] = None
    last_contact_date: Optional[date] = None
    notes: Optional[str] = None


class ContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    title: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    linkedin_url: Optional[str]
    relationship_owner: Optional[uuid.UUID]
    last_contact_date: Optional[date]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
