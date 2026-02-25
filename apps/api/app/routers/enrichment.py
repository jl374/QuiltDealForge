"""
Enrichment Router
Endpoints for enriching companies with principal owner information.
"""
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select

from app.dependencies import get_db, get_current_user, CurrentUser
from app.models.contact import Contact
from app.services.enrichment_service import enrich_company, enrich_project, get_enrichment_status

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/company/{company_id}")
async def enrich_single_company(
    company_id: uuid.UUID,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Enrich a single company — find its principal owner via web research + Apollo."""
    try:
        result = await enrich_company(db, str(company_id))
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[Enrichment] Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Enrichment failed")


@router.post("/project/{project_id}")
async def enrich_project_companies(
    project_id: uuid.UUID,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Bulk enrich all companies in a project that haven't been enriched yet."""
    try:
        result = await enrich_project(db, str(project_id))
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[Enrichment] Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Bulk enrichment failed")


@router.get("/company/{company_id}/status")
async def get_company_enrichment_status(
    company_id: uuid.UUID,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Check the enrichment status for a company's principal owner."""
    return await get_enrichment_status(db, str(company_id))
