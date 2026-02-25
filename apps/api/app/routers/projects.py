"""
Projects Router
CRUD for named project folders + adding/removing companies from them.
"""
import uuid
from typing import Optional
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from app.dependencies import get_db, get_current_user, CurrentUser
from app.models.project import Project, ProjectCompany
from app.models.company import Company

logger = logging.getLogger(__name__)
router = APIRouter()


def _to_uuid(val: str | None) -> uuid.UUID | None:
    """Safely convert string to UUID, returning None if invalid."""
    if not val:
        return None
    try:
        return uuid.UUID(val)
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    color: str = Field(default="slate", pattern=r"^(slate|blue|green|amber|red|purple|pink|indigo|teal|orange)$")


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    color: Optional[str] = Field(default=None, pattern=r"^(slate|blue|green|amber|red|purple|pink|indigo|teal|orange)$")


class ProjectCompanyIn(BaseModel):
    company_id: uuid.UUID
    notes: Optional[str] = None


class ProjectCompanyOut(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    company_name: str
    company_sector: str
    company_stage: str
    company_location: Optional[str]
    notes: Optional[str]
    added_at: str

    class Config:
        from_attributes = True


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    color: str
    created_by: Optional[uuid.UUID]
    company_count: int
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class ProjectDetailOut(ProjectOut):
    companies: list[ProjectCompanyOut]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _project_out(p: Project) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "description": p.description,
        "color": p.color,
        "created_by": str(p.created_by) if p.created_by else None,
        "company_count": len(p.companies),
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


def _project_company_out(pc: ProjectCompany) -> dict:
    co: Company = pc.company
    return {
        "id": str(pc.id),
        "company_id": str(pc.company_id),
        "company_name": co.name,
        "company_sector": co.sector or "",
        "company_stage": co.stage or "",
        "company_location": co.hq_location,
        "notes": pc.notes,
        "added_at": pc.added_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_projects(
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all projects with company counts."""
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.companies))
        .order_by(Project.updated_at.desc())
    )
    projects = result.scalars().all()
    return [_project_out(p) for p in projects]


@router.post("", status_code=201)
async def create_project(
    payload: ProjectCreate,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new project folder."""
    project = Project(
        name=payload.name,
        description=payload.description,
        color=payload.color,
        created_by=_to_uuid(current_user.id),
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    # Reload with companies relationship
    result = await db.execute(
        select(Project).options(selectinload(Project.companies)).where(Project.id == project.id)
    )
    project = result.scalar_one()
    logger.info(f"[Projects] Created '{project.name}' (id={project.id}) by {current_user.id}")
    return _project_out(project)


@router.get("/{project_id}")
async def get_project(
    project_id: uuid.UUID,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get a single project with all its companies."""
    result = await db.execute(
        select(Project)
        .options(
            selectinload(Project.companies).selectinload(ProjectCompany.company)
        )
        .where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    out = _project_out(project)
    out["companies"] = [_project_company_out(pc) for pc in project.companies]
    return out


@router.patch("/{project_id}")
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Rename or update a project."""
    result = await db.execute(
        select(Project).options(selectinload(Project.companies)).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if payload.name is not None:
        project.name = payload.name
    if payload.description is not None:
        project.description = payload.description
    if payload.color is not None:
        project.color = payload.color

    await db.commit()
    await db.refresh(project)
    result = await db.execute(
        select(Project).options(selectinload(Project.companies)).where(Project.id == project_id)
    )
    project = result.scalar_one()
    return _project_out(project)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete a project (does NOT delete the companies themselves)."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.delete(project)
    await db.commit()


@router.post("/{project_id}/companies", status_code=201)
async def add_company_to_project(
    project_id: uuid.UUID,
    payload: ProjectCompanyIn,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Add a company to a project. Idempotent — returns existing link if already added."""
    # Verify project exists
    result = await db.execute(select(Project).where(Project.id == project_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    # Verify company exists
    result = await db.execute(select(Company).where(Company.id == payload.company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Check for existing link
    result = await db.execute(
        select(ProjectCompany).where(
            ProjectCompany.project_id == project_id,
            ProjectCompany.company_id == payload.company_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return {"id": str(existing.id), "already_member": True}

    pc = ProjectCompany(
        project_id=project_id,
        company_id=payload.company_id,
        notes=payload.notes,
        added_by=_to_uuid(current_user.id),
    )
    db.add(pc)
    await db.commit()
    await db.refresh(pc)
    logger.info(f"[Projects] Added company {payload.company_id} to project {project_id}")
    return {"id": str(pc.id), "already_member": False}


@router.delete("/{project_id}/companies/{company_id}", status_code=204)
async def remove_company_from_project(
    project_id: uuid.UUID,
    company_id: uuid.UUID,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Remove a company from a project."""
    await db.execute(
        delete(ProjectCompany).where(
            ProjectCompany.project_id == project_id,
            ProjectCompany.company_id == company_id,
        )
    )
    await db.commit()
