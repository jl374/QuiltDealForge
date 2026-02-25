import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import auth, companies, contacts, sourcing, projects, enrichment, outreach, analytics

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Marvin API",
    version="0.1.0",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-User-Id", "X-User-Role", "X-Internal-Key", "X-Gmail-Token"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(companies.router, prefix="/companies", tags=["companies"])
app.include_router(contacts.router, prefix="/contacts", tags=["contacts"])
app.include_router(sourcing.router, prefix="/sourcing", tags=["sourcing"])
app.include_router(projects.router, prefix="/projects", tags=["projects"])
app.include_router(enrichment.router, prefix="/enrichment", tags=["enrichment"])
app.include_router(outreach.router, prefix="/outreach", tags=["outreach"])
app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])


@app.on_event("startup")
async def _log_enrichment_readiness():
    from app.services.web_helpers import get_search_provider
    search = get_search_provider()
    claude = "configured" if settings.ANTHROPIC_API_KEY else "NOT configured"
    apollo = "configured" if settings.APOLLO_API_KEY else "not configured (optional)"
    logger.info(f"[Enrichment] Search: {search} | Claude: {claude} | Apollo: {apollo}")
    if not settings.SERPER_API_KEY and not settings.TAVILY_API_KEY:
        logger.warning(
            "[Enrichment] No search API key set (SERPER_API_KEY or TAVILY_API_KEY). "
            "Falling back to Google scraping which is frequently blocked. "
            "Get a free key at serper.dev or tavily.com."
        )
    if not settings.ANTHROPIC_API_KEY:
        logger.warning(
            "[Enrichment] ANTHROPIC_API_KEY is empty. Claude extraction and personality "
            "analysis will be unavailable — rule-based fallback only."
        )


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
