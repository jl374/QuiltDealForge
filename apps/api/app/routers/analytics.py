"""
Analytics Router
Provides pipeline analytics data: stage distribution, outreach funnel stats,
and per-project breakdowns for the analytics dashboard.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func, case, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_current_user, CurrentUser
from app.models.company import Company
from app.models.project import Project, ProjectCompany
from app.models.outreach import OutreachThread, OutreachMessage

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class StageCount(BaseModel):
    stage: str
    count: int


class FunnelStats(BaseModel):
    total_in_projects: int
    contacted: int         # have an outreach thread (any status except draft)
    emails_sent: int       # thread status >= sent
    responded: int         # thread status == responded or meeting_scheduled
    meetings_set: int      # thread status == meeting_scheduled
    passed: int            # thread status == passed
    # Percentages (0-100)
    pct_contacted: float
    pct_sent: float
    pct_responded: float
    pct_meetings: float


class ProjectSummary(BaseModel):
    id: str
    name: str
    color: str
    company_count: int
    contacted_count: int
    responded_count: int


class PipelineAnalytics(BaseModel):
    stage_distribution: list[StageCount]
    funnel: FunnelStats
    projects: list[ProjectSummary]
    total_companies: int
    total_projects: int


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("/pipeline", response_model=PipelineAnalytics)
async def get_pipeline_analytics(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Returns pipeline analytics across all projects:
    - Stage distribution bar chart data (companies in projects, grouped by stage)
    - Outreach funnel statistics with percentages
    - Per-project summary
    """

    # 1. Get all company IDs that are in at least one project
    pc_query = select(
        ProjectCompany.company_id,
    ).distinct()
    pc_result = await db.execute(pc_query)
    in_project_ids = {row[0] for row in pc_result.all()}

    if not in_project_ids:
        return PipelineAnalytics(
            stage_distribution=[],
            funnel=FunnelStats(
                total_in_projects=0, contacted=0, emails_sent=0,
                responded=0, meetings_set=0, passed=0,
                pct_contacted=0, pct_sent=0, pct_responded=0, pct_meetings=0,
            ),
            projects=[],
            total_companies=0,
            total_projects=0,
        )

    # 2. Stage distribution — count companies at each pipeline stage
    #    Only includes companies that are in at least one project
    stage_query = (
        select(Company.stage, func.count(Company.id))
        .where(Company.id.in_(in_project_ids))
        .group_by(Company.stage)
    )
    stage_result = await db.execute(stage_query)
    stage_counts_raw = {row[0]: row[1] for row in stage_result.all()}

    # Ensure all stages appear in order (even if count=0)
    ordered_stages = [
        "Identified",
        "Outreach Sent",
        "Engaged",
        "NDA Signed",
        "Diligence",
        "LOI Submitted",
        "LOI Signed",
        "Closed",
        "Passed",
        "On Hold",
    ]
    stage_distribution = [
        StageCount(stage=s, count=stage_counts_raw.get(s, 0))
        for s in ordered_stages
    ]

    total_in_projects = len(in_project_ids)

    # 3. Outreach funnel — based on OutreachThread statuses
    #    One thread per company per project; a company might be in multiple projects
    #    We count unique companies that have reached each outreach milestone
    thread_query = (
        select(
            OutreachThread.company_id,
            OutreachThread.status,
        )
        .where(OutreachThread.company_id.in_(in_project_ids))
    )
    thread_result = await db.execute(thread_query)
    threads = thread_result.all()

    # For each company, take the "best" thread status
    # (if a company is in multiple projects, count the furthest-along thread)
    status_rank = {
        "draft": 0,
        "sent": 1,
        "awaiting_response": 2,
        "responded": 3,
        "meeting_scheduled": 4,
        "passed": -1,  # separate track
    }
    company_best_status: dict[str, str] = {}
    company_passed: set = set()
    for company_id, thread_status in threads:
        cid = str(company_id)
        if thread_status == "passed":
            company_passed.add(cid)
            continue
        rank = status_rank.get(thread_status, 0)
        existing = company_best_status.get(cid)
        if existing is None or rank > status_rank.get(existing, 0):
            company_best_status[cid] = thread_status

    # Count funnel milestones
    contacted = 0     # has any thread (non-draft)
    emails_sent = 0   # status >= sent
    responded = 0     # status >= responded
    meetings_set = 0  # status == meeting_scheduled

    for cid, best in company_best_status.items():
        rank = status_rank.get(best, 0)
        if rank >= 1:
            contacted += 1
        if rank >= 1:
            emails_sent += 1
        if rank >= 3:
            responded += 1
        if rank >= 4:
            meetings_set += 1

    passed = len(company_passed)

    def pct(num: int, denom: int) -> float:
        return round((num / denom) * 100, 1) if denom > 0 else 0.0

    funnel = FunnelStats(
        total_in_projects=total_in_projects,
        contacted=contacted,
        emails_sent=emails_sent,
        responded=responded,
        meetings_set=meetings_set,
        passed=passed,
        pct_contacted=pct(contacted, total_in_projects),
        pct_sent=pct(emails_sent, total_in_projects),
        pct_responded=pct(responded, total_in_projects),
        pct_meetings=pct(meetings_set, total_in_projects),
    )

    # 4. Per-project summary
    proj_query = (
        select(
            Project.id,
            Project.name,
            Project.color,
            func.count(ProjectCompany.id).label("company_count"),
        )
        .join(ProjectCompany, ProjectCompany.project_id == Project.id, isouter=True)
        .group_by(Project.id, Project.name, Project.color)
        .order_by(func.count(ProjectCompany.id).desc())
    )
    proj_result = await db.execute(proj_query)
    projects_raw = proj_result.all()

    # Get per-project outreach thread counts
    proj_thread_query = (
        select(
            OutreachThread.project_id,
            OutreachThread.status,
            func.count(OutreachThread.id),
        )
        .group_by(OutreachThread.project_id, OutreachThread.status)
    )
    proj_thread_result = await db.execute(proj_thread_query)
    proj_thread_counts: dict[str, dict[str, int]] = {}
    for pid, tstatus, tcount in proj_thread_result.all():
        pid_str = str(pid)
        if pid_str not in proj_thread_counts:
            proj_thread_counts[pid_str] = {}
        proj_thread_counts[pid_str][tstatus] = tcount

    project_summaries = []
    for proj_id, proj_name, proj_color, comp_count in projects_raw:
        pid_str = str(proj_id)
        tc = proj_thread_counts.get(pid_str, {})
        contacted_c = sum(
            v for k, v in tc.items() if k != "draft"
        )
        responded_c = tc.get("responded", 0) + tc.get("meeting_scheduled", 0)
        project_summaries.append(ProjectSummary(
            id=pid_str,
            name=proj_name,
            color=proj_color,
            company_count=comp_count,
            contacted_count=contacted_c,
            responded_count=responded_c,
        ))

    # 5. Total counts
    total_companies_result = await db.execute(select(func.count(Company.id)))
    total_companies = total_companies_result.scalar() or 0

    total_projects = len(projects_raw)

    return PipelineAnalytics(
        stage_distribution=stage_distribution,
        funnel=funnel,
        projects=project_summaries,
        total_companies=total_companies,
        total_projects=total_projects,
    )
