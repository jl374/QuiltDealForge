from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
from typing import Optional
import uuid
from app.models.company import Company, PipelineStage
from app.schemas.company import CompanyCreate, CompanyUpdate


class CompanyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_companies(
        self,
        sector: Optional[str] = None,
        stage: Optional[PipelineStage] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Company]:
        q = select(Company)

        if sector:
            q = q.where(Company.sector == sector)
        if stage:
            q = q.where(Company.stage == stage)
        if search:
            term = f"%{search}%"
            q = q.where(
                or_(
                    Company.name.ilike(term),
                    Company.notes.ilike(term),
                    Company.hq_location.ilike(term),
                )
            )

        q = q.order_by(Company.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def get_by_id(self, company_id: uuid.UUID) -> Optional[Company]:
        result = await self.db.execute(
            select(Company)
            .where(Company.id == company_id)
            .options(selectinload(Company.contacts))
        )
        return result.scalar_one_or_none()

    async def create_company(
        self, payload: CompanyCreate, added_by: Optional[str] = None
    ) -> Company:
        data = payload.model_dump()
        if added_by:
            try:
                data["added_by"] = uuid.UUID(added_by)
            except (ValueError, AttributeError):
                pass
        company = Company(**data)
        self.db.add(company)
        await self.db.commit()
        await self.db.refresh(company)
        return company

    async def update_company(
        self, company_id: uuid.UUID, payload: CompanyUpdate
    ) -> Company:
        company = await self.get_by_id(company_id)
        if not company:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Company not found")
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(company, field, value)
        await self.db.commit()
        await self.db.refresh(company)
        return company

    async def delete_company(self, company_id: uuid.UUID) -> None:
        company = await self.get_by_id(company_id)
        if not company:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Company not found")
        await self.db.delete(company)
        await self.db.commit()
