from pydantic import BaseModel, ConfigDict
from typing import Optional
from decimal import Decimal
from datetime import datetime
import uuid
from app.models.company import PipelineStage, OwnershipType


class CompanyCreate(BaseModel):
    name: str
    website: Optional[str] = None
    hq_location: Optional[str] = None
    employee_count: Optional[int] = None
    sector: str = "Other"
    ownership_type: OwnershipType = OwnershipType.Unknown
    revenue_low: Optional[Decimal] = None
    revenue_high: Optional[Decimal] = None
    ebitda_low: Optional[Decimal] = None
    ebitda_high: Optional[Decimal] = None
    stage: PipelineStage = PipelineStage.Identified
    ai_fit_score: Optional[int] = None
    source: Optional[str] = None
    notes: Optional[str] = None


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    website: Optional[str] = None
    hq_location: Optional[str] = None
    employee_count: Optional[int] = None
    sector: Optional[str] = None
    ownership_type: Optional[OwnershipType] = None
    revenue_low: Optional[Decimal] = None
    revenue_high: Optional[Decimal] = None
    ebitda_low: Optional[Decimal] = None
    ebitda_high: Optional[Decimal] = None
    stage: Optional[PipelineStage] = None
    ai_fit_score: Optional[int] = None
    source: Optional[str] = None
    notes: Optional[str] = None


class CompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    website: Optional[str]
    hq_location: Optional[str]
    employee_count: Optional[int]
    sector: str
    ownership_type: OwnershipType
    revenue_low: Optional[Decimal]
    revenue_high: Optional[Decimal]
    ebitda_low: Optional[Decimal]
    ebitda_high: Optional[Decimal]
    stage: PipelineStage
    ai_fit_score: Optional[int]
    source: Optional[str]
    notes: Optional[str]
    added_by: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime
