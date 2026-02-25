from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import uuid
from app.dependencies import get_db, require_role
from app.schemas.company import CompanyCreate, CompanyUpdate, CompanyResponse
from app.services.company_service import CompanyService
from app.models.company import PipelineStage

router = APIRouter()


@router.get("/", response_model=list[CompanyResponse])
async def list_companies(
    sector: Optional[str] = Query(None),
    stage: Optional[PipelineStage] = Query(None),
    search: Optional[str] = Query(None, max_length=200),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["GP", "Analyst", "Admin"])),
):
    svc = CompanyService(db)
    return await svc.list_companies(
        sector=sector, stage=stage, search=search, limit=limit, offset=offset
    )


@router.post("/", response_model=CompanyResponse, status_code=201)
async def create_company(
    payload: CompanyCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["GP", "Admin"])),
):
    svc = CompanyService(db)
    return await svc.create_company(payload, added_by=current_user.id)


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["GP", "Analyst", "Admin"])),
):
    svc = CompanyService(db)
    company = await svc.get_by_id(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.patch("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: uuid.UUID,
    payload: CompanyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["GP", "Admin"])),
):
    svc = CompanyService(db)
    return await svc.update_company(company_id, payload)


@router.delete("/{company_id}", status_code=204)
async def delete_company(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["Admin"])),
):
    svc = CompanyService(db)
    await svc.delete_company(company_id)
