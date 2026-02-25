"""
Sourcing Router
Endpoints for searching external data sources for acquisition targets.
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional
import logging

from app.dependencies import get_current_user, CurrentUser
from app.services.sourcing_service import run_sourcing_search, score_company, SourcedCompany, _SEARCH_CACHE
from app.services.analysis_service import generate_fit_summary, generate_deep_dive

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class SourcingCriteria(BaseModel):
    sector: Optional[str] = None
    keywords: Optional[str] = None
    location: Optional[str] = None
    min_employees: Optional[int] = Field(default=None, ge=0)
    max_employees: Optional[int] = Field(default=None, ge=0)
    min_revenue: Optional[float] = Field(default=None, ge=0, description="Min revenue in dollars")
    max_revenue: Optional[float] = Field(default=None, ge=0, description="Max revenue in dollars")
    sources: Optional[list[str]] = Field(
        default=None,
        description="Which sources to search. Defaults to all.",
    )


class SourcingResultItem(BaseModel):
    name: str
    source: str
    source_url: str
    description: str
    sector: str
    location: str
    revenue: str
    employees: str
    asking_price: str
    website: str
    fit_score: Optional[int]
    fit_reasons: list[str]
    extra: dict


class SourcingResponse(BaseModel):
    results: list[SourcingResultItem]
    total: int
    criteria_used: dict
    cached: bool = False


class RescoreRequest(BaseModel):
    """Re-score a list of companies with updated criteria (no new searches)."""
    companies: list[dict]
    criteria: SourcingCriteria


class RescoreResponse(BaseModel):
    results: list[dict]


class AnalyzeRequest(BaseModel):
    """Request AI analysis of a single sourced company."""
    company: dict
    criteria: SourcingCriteria
    mode: str = Field(default="summary", description="'summary' for card blurb, 'deep_dive' for full profile")


class AnalyzeResponse(BaseModel):
    mode: str
    # Summary mode
    fit_summary: Optional[str] = None
    # Deep dive mode
    business_summary: Optional[str] = None
    service_lines: Optional[str] = None
    leadership: Optional[str] = None
    contact: Optional[str] = None
    fit_rationale: Optional[str] = None
    research_sources: Optional[list[str]] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/search", response_model=SourcingResponse)
async def search_companies(
    criteria: SourcingCriteria,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Search multiple data sources for acquisition targets.
    Returns deduplicated, scored results.
    """
    criteria_dict = criteria.model_dump(exclude_none=True)

    # Validate at least one criterion is set
    if not any([
        criteria.sector,
        criteria.keywords,
        criteria.location,
    ]):
        raise HTTPException(
            status_code=422,
            detail="At least one of sector, keywords, or location must be provided.",
        )

    from app.services.sourcing_service import _cache_get, _cache_key
    was_cached = _cache_get(_cache_key(criteria_dict)) is not None

    try:
        results = await run_sourcing_search(criteria_dict)
    except Exception as e:
        logger.exception(f"[Sourcing] Search error: {e}")
        raise HTTPException(status_code=500, detail=f"Sourcing search failed: {str(e)}")

    return SourcingResponse(
        results=[SourcingResultItem(**r) for r in results],
        total=len(results),
        criteria_used=criteria_dict,
        cached=was_cached,
    )


@router.post("/rescore", response_model=RescoreResponse)
async def rescore_companies(
    payload: RescoreRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Re-score a previously-fetched list of companies with updated fit criteria.
    This does NOT make any new external searches — just reruns the scoring logic.
    """
    criteria_dict = payload.criteria.model_dump(exclude_none=True)

    rescored = []
    for item in payload.companies:
        co = SourcedCompany(
            name=item.get("name", ""),
            source=item.get("source", ""),
            source_url=item.get("source_url", ""),
            description=item.get("description", ""),
            sector=item.get("sector", ""),
            location=item.get("location", ""),
            revenue=item.get("revenue", ""),
            employees=item.get("employees", ""),
            asking_price=item.get("asking_price", ""),
            website=item.get("website", ""),
        )
        score, reasons = score_company(co, criteria_dict)
        co.fit_score = score
        co.fit_reasons = reasons
        rescored.append(co.to_dict())

    rescored.sort(key=lambda c: c.get("fit_score") or 0, reverse=True)
    return RescoreResponse(results=rescored)


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_company(
    payload: AnalyzeRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Generate AI analysis for a single sourced company.
    mode='summary' → fast 2-3 sentence fit blurb (no web research, uses existing data)
    mode='deep_dive' → full profile with web research (history, services, leadership, contact)
    """
    criteria_dict = payload.criteria.model_dump(exclude_none=True)

    try:
        if payload.mode == "deep_dive":
            result = await generate_deep_dive(payload.company, criteria_dict)
            return AnalyzeResponse(
                mode="deep_dive",
                business_summary=result.get("business_summary"),
                service_lines=result.get("service_lines"),
                leadership=result.get("leadership"),
                contact=result.get("contact"),
                fit_rationale=result.get("fit_rationale"),
                research_sources=result.get("research_sources"),
            )
        else:
            summary = await generate_fit_summary(payload.company, criteria_dict)
            return AnalyzeResponse(mode="summary", fit_summary=summary)

    except Exception as e:
        logger.exception(f"[Analyze] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.post("/cache/clear")
async def clear_search_cache(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Clear the in-process sourcing cache so the next search re-fetches fresh data."""
    count = len(_SEARCH_CACHE)
    _SEARCH_CACHE.clear()
    logger.info(f"[Cache] Cleared {count} cached search result(s) by {current_user.id}")
    return {"cleared": count}
