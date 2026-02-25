"""
Outreach Router
Campaign CRUD, AI email generation, and Gmail sending.
"""
import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from datetime import datetime

from app.dependencies import get_db, get_current_user, CurrentUser
from app.models.contact import Contact
from app.models.outreach import OutreachCampaign, OutreachEmail, OutreachThread, OutreachMessage
from app.services.email_service import generate_campaign_emails, generate_thread_draft, bulk_generate_initial_drafts
from app.services.gmail_service import send_campaign, send_thread_message, send_bulk_thread_messages

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CampaignCreate(BaseModel):
    project_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=300)
    subject_template: str = Field(..., min_length=1)
    body_prompt: str = Field(..., min_length=1)
    sender_email: str


class CampaignUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=300)
    subject_template: Optional[str] = None
    body_prompt: Optional[str] = None


class EmailUpdate(BaseModel):
    subject: Optional[str] = None
    body_html: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern=r"^(draft|approved)$")


# Thread schemas
class ThreadCreate(BaseModel):
    project_id: uuid.UUID
    company_id: uuid.UUID
    contact_id: Optional[uuid.UUID] = None


class ThreadUpdate(BaseModel):
    status: Optional[str] = Field(
        default=None,
        pattern=r"^(draft|sent|awaiting_response|responded|meeting_scheduled|passed)$",
    )
    next_follow_up_at: Optional[str] = None  # ISO datetime string
    proposed_slots: Optional[list[dict]] = None
    response_summary: Optional[str] = None


class GenerateDraftRequest(BaseModel):
    message_type: str = Field(
        default="initial", pattern=r"^(initial|follow_up|scheduling_reply)$"
    )
    custom_prompt: Optional[str] = None
    proposed_slots: Optional[list[dict]] = None


class BulkGenerateRequest(BaseModel):
    project_id: uuid.UUID
    company_ids: list[uuid.UUID]
    message_type: str = Field(default="initial", pattern=r"^(initial)$")


class BulkSendRequest(BaseModel):
    message_ids: list[uuid.UUID]
    sender_email: str


class MessageUpdate(BaseModel):
    subject: Optional[str] = None
    body_html: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern=r"^(draft|approved)$")


class MarkRespondedRequest(BaseModel):
    response_summary: Optional[str] = None


class SchedulingReplyRequest(BaseModel):
    proposed_slots: list[dict]
    assistant_name: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _campaign_out(c: OutreachCampaign, include_emails: bool = False) -> dict:
    out = {
        "id": str(c.id),
        "project_id": str(c.project_id),
        "name": c.name,
        "subject_template": c.subject_template,
        "body_prompt": c.body_prompt,
        "sender_email": c.sender_email,
        "status": c.status,
        "created_by": str(c.created_by) if c.created_by else None,
        "email_count": len(c.emails) if c.emails else 0,
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
    }
    if include_emails and c.emails:
        out["emails"] = [_email_out(e) for e in c.emails]
    return out


def _email_out(e: OutreachEmail) -> dict:
    return {
        "id": str(e.id),
        "campaign_id": str(e.campaign_id),
        "contact_id": str(e.contact_id),
        "company_id": str(e.company_id),
        "to_email": e.to_email,
        "subject": e.subject,
        "body_html": e.body_html,
        "status": e.status,
        "sent_at": e.sent_at.isoformat() if e.sent_at else None,
        "gmail_message_id": e.gmail_message_id,
        "error_message": e.error_message,
        "created_at": e.created_at.isoformat(),
        "contact_name": e.contact.name if e.contact else None,
        "company_name": e.company.name if e.company else None,
    }


def _to_uuid(val: str | None) -> uuid.UUID | None:
    if not val:
        return None
    try:
        return uuid.UUID(val)
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Campaign CRUD
# ---------------------------------------------------------------------------

@router.post("/campaigns", status_code=201)
async def create_campaign(
    payload: CampaignCreate,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new outreach campaign for a project."""
    campaign = OutreachCampaign(
        project_id=payload.project_id,
        name=payload.name,
        subject_template=payload.subject_template,
        body_prompt=payload.body_prompt,
        sender_email=payload.sender_email,
        created_by=_to_uuid(current_user.id),
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)

    # Reload with emails
    result = await db.execute(
        select(OutreachCampaign)
        .options(selectinload(OutreachCampaign.emails))
        .where(OutreachCampaign.id == campaign.id)
    )
    campaign = result.scalar_one()
    logger.info(f"[Outreach] Created campaign '{campaign.name}' for project {payload.project_id}")
    return _campaign_out(campaign)


@router.get("/campaigns")
async def list_campaigns(
    project_id: uuid.UUID,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List campaigns for a project."""
    result = await db.execute(
        select(OutreachCampaign)
        .options(selectinload(OutreachCampaign.emails))
        .where(OutreachCampaign.project_id == project_id)
        .order_by(OutreachCampaign.created_at.desc())
    )
    campaigns = result.scalars().all()
    return [_campaign_out(c) for c in campaigns]


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: uuid.UUID,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get campaign detail with all emails."""
    result = await db.execute(
        select(OutreachCampaign)
        .options(
            selectinload(OutreachCampaign.emails)
            .selectinload(OutreachEmail.contact),
            selectinload(OutreachCampaign.emails)
            .selectinload(OutreachEmail.company),
        )
        .where(OutreachCampaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return _campaign_out(campaign, include_emails=True)


@router.patch("/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: uuid.UUID,
    payload: CampaignUpdate,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update a campaign's name, subject template, or body prompt."""
    result = await db.execute(
        select(OutreachCampaign)
        .options(selectinload(OutreachCampaign.emails))
        .where(OutreachCampaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if payload.name is not None:
        campaign.name = payload.name
    if payload.subject_template is not None:
        campaign.subject_template = payload.subject_template
    if payload.body_prompt is not None:
        campaign.body_prompt = payload.body_prompt

    await db.commit()
    await db.refresh(campaign)
    result = await db.execute(
        select(OutreachCampaign)
        .options(selectinload(OutreachCampaign.emails))
        .where(OutreachCampaign.id == campaign_id)
    )
    campaign = result.scalar_one()
    return _campaign_out(campaign)


@router.delete("/campaigns/{campaign_id}", status_code=204)
async def delete_campaign(
    campaign_id: uuid.UUID,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete a campaign and all its emails."""
    result = await db.execute(
        select(OutreachCampaign).where(OutreachCampaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await db.delete(campaign)
    await db.commit()


# ---------------------------------------------------------------------------
# Email generation & sending
# ---------------------------------------------------------------------------

@router.post("/campaigns/{campaign_id}/generate")
async def generate_emails(
    campaign_id: uuid.UUID,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Generate personalized emails for all enriched contacts in the campaign's project."""
    try:
        result = await generate_campaign_emails(db, str(campaign_id))
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[Outreach] Generate failed: {e}")
        raise HTTPException(status_code=500, detail="Email generation failed")


@router.patch("/emails/{email_id}")
async def update_email(
    email_id: uuid.UUID,
    payload: EmailUpdate,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Edit a single generated email (subject, body, status)."""
    result = await db.execute(
        select(OutreachEmail)
        .options(selectinload(OutreachEmail.contact), selectinload(OutreachEmail.company))
        .where(OutreachEmail.id == email_id)
    )
    email = result.scalar_one_or_none()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    if payload.subject is not None:
        email.subject = payload.subject
    if payload.body_html is not None:
        email.body_html = payload.body_html
    if payload.status is not None:
        email.status = payload.status

    await db.commit()
    await db.refresh(email)
    # Reload with relations
    result = await db.execute(
        select(OutreachEmail)
        .options(selectinload(OutreachEmail.contact), selectinload(OutreachEmail.company))
        .where(OutreachEmail.id == email_id)
    )
    email = result.scalar_one()
    return _email_out(email)


@router.post("/campaigns/{campaign_id}/send")
async def send_campaign_emails(
    campaign_id: uuid.UUID,
    x_gmail_token: str = Header(..., alias="X-Gmail-Token"),
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Send all approved/draft emails in a campaign via Gmail API."""
    try:
        result = await send_campaign(db, str(campaign_id), x_gmail_token)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[Outreach] Send failed: {e}")
        raise HTTPException(status_code=500, detail="Email sending failed")


# ---------------------------------------------------------------------------
# Thread-based outreach (CRM model)
# ---------------------------------------------------------------------------

def _thread_out(t: OutreachThread, include_messages: bool = True) -> dict:
    out = {
        "id": str(t.id),
        "project_id": str(t.project_id),
        "company_id": str(t.company_id),
        "contact_id": str(t.contact_id) if t.contact_id else None,
        "status": t.status,
        "follow_up_count": t.follow_up_count or 0,
        "next_follow_up_at": t.next_follow_up_at.isoformat() if t.next_follow_up_at else None,
        "last_sent_at": t.last_sent_at.isoformat() if t.last_sent_at else None,
        "response_received_at": t.response_received_at.isoformat() if t.response_received_at else None,
        "response_summary": t.response_summary,
        "proposed_slots": t.proposed_slots,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
        # Joined data
        "company_name": t.company.name if t.company else None,
        "company_sector": t.company.sector if t.company else None,
        "company_location": t.company.hq_location if t.company else None,
        "contact_name": t.contact.name if t.contact else None,
        "contact_email": t.contact.email if t.contact else None,
        "contact_title": t.contact.title if t.contact else None,
    }
    if include_messages and t.messages:
        out["messages"] = [_message_out(m) for m in t.messages]
    else:
        out["messages"] = []
    return out


def _message_out(m: OutreachMessage) -> dict:
    return {
        "id": str(m.id),
        "thread_id": str(m.thread_id),
        "sequence": m.sequence,
        "message_type": m.message_type,
        "to_email": m.to_email,
        "subject": m.subject,
        "body_html": m.body_html,
        "status": m.status,
        "sent_at": m.sent_at.isoformat() if m.sent_at else None,
        "gmail_message_id": m.gmail_message_id,
        "gmail_thread_id": m.gmail_thread_id,
        "error_message": m.error_message,
        "created_at": m.created_at.isoformat(),
    }


# --- Thread CRUD ---

@router.get("/threads")
async def list_threads(
    project_id: uuid.UUID,
    status: Optional[str] = None,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all outreach threads for a project."""
    q = (
        select(OutreachThread)
        .options(
            selectinload(OutreachThread.company),
            selectinload(OutreachThread.contact),
            selectinload(OutreachThread.messages),
        )
        .where(OutreachThread.project_id == project_id)
        .order_by(OutreachThread.created_at.desc())
    )
    if status:
        q = q.where(OutreachThread.status == status)

    result = await db.execute(q)
    threads = result.scalars().all()
    return [_thread_out(t) for t in threads]


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: uuid.UUID,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get full thread detail with all messages."""
    result = await db.execute(
        select(OutreachThread)
        .options(
            selectinload(OutreachThread.company),
            selectinload(OutreachThread.contact),
            selectinload(OutreachThread.messages),
        )
        .where(OutreachThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return _thread_out(thread)


@router.post("/threads", status_code=201)
async def create_thread(
    payload: ThreadCreate,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new outreach thread. Auto-selects principal owner contact if not provided."""
    contact_id = payload.contact_id

    # Auto-select principal owner contact if not provided
    if not contact_id:
        result = await db.execute(
            select(Contact).where(
                Contact.company_id == payload.company_id,
                Contact.is_principal_owner == True,  # noqa: E712
            )
        )
        contact = result.scalar_one_or_none()
        if contact:
            contact_id = contact.id

    thread = OutreachThread(
        project_id=payload.project_id,
        company_id=payload.company_id,
        contact_id=contact_id,
        status="draft",
        created_by=_to_uuid(current_user.id),
    )
    db.add(thread)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        # Likely a unique constraint violation — thread already exists
        result = await db.execute(
            select(OutreachThread)
            .options(
                selectinload(OutreachThread.company),
                selectinload(OutreachThread.contact),
                selectinload(OutreachThread.messages),
            )
            .where(
                OutreachThread.project_id == payload.project_id,
                OutreachThread.company_id == payload.company_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            # Auto-link principal owner if thread has no contact yet
            if not existing.contact_id and contact_id:
                existing.contact_id = contact_id
                await db.commit()
                await db.refresh(existing)
            return _thread_out(existing)
        raise HTTPException(status_code=400, detail="Failed to create thread")

    # Reload with relations
    result = await db.execute(
        select(OutreachThread)
        .options(
            selectinload(OutreachThread.company),
            selectinload(OutreachThread.contact),
            selectinload(OutreachThread.messages),
        )
        .where(OutreachThread.id == thread.id)
    )
    thread = result.scalar_one()
    return _thread_out(thread)


@router.patch("/threads/{thread_id}")
async def update_thread(
    thread_id: uuid.UUID,
    payload: ThreadUpdate,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update thread status, follow-up timing, response info."""
    result = await db.execute(
        select(OutreachThread)
        .options(
            selectinload(OutreachThread.company),
            selectinload(OutreachThread.contact),
            selectinload(OutreachThread.messages),
        )
        .where(OutreachThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if payload.status is not None:
        thread.status = payload.status
    if payload.next_follow_up_at is not None:
        thread.next_follow_up_at = datetime.fromisoformat(payload.next_follow_up_at)
    if payload.proposed_slots is not None:
        thread.proposed_slots = payload.proposed_slots
    if payload.response_summary is not None:
        thread.response_summary = payload.response_summary

    await db.commit()
    await db.refresh(thread)

    # Reload with relations
    result = await db.execute(
        select(OutreachThread)
        .options(
            selectinload(OutreachThread.company),
            selectinload(OutreachThread.contact),
            selectinload(OutreachThread.messages),
        )
        .where(OutreachThread.id == thread_id)
    )
    thread = result.scalar_one()
    return _thread_out(thread)


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: uuid.UUID,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete a thread and all its messages."""
    result = await db.execute(
        select(OutreachThread).where(OutreachThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    await db.delete(thread)
    await db.commit()


# --- Draft generation ---

@router.post("/threads/{thread_id}/generate-draft")
async def generate_draft(
    thread_id: uuid.UUID,
    payload: GenerateDraftRequest,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Generate a draft message for a thread via Claude."""
    try:
        message = await generate_thread_draft(
            db,
            str(thread_id),
            message_type=payload.message_type,
            custom_prompt=payload.custom_prompt,
            proposed_slots=payload.proposed_slots,
        )
        return _message_out(message)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[Outreach] Draft generation failed: {e}")
        raise HTTPException(status_code=500, detail="Draft generation failed")


@router.post("/threads/bulk-generate")
async def bulk_generate(
    payload: BulkGenerateRequest,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Bulk-generate initial drafts for multiple companies."""
    try:
        result = await bulk_generate_initial_drafts(
            db,
            str(payload.project_id),
            [str(cid) for cid in payload.company_ids],
            created_by=current_user.id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[Outreach] Bulk generation failed: {e}")
        raise HTTPException(status_code=500, detail="Bulk generation failed")


# --- Message operations ---

@router.patch("/messages/{message_id}")
async def update_message(
    message_id: uuid.UUID,
    payload: MessageUpdate,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Edit a single message (subject, body, status)."""
    result = await db.execute(
        select(OutreachMessage).where(OutreachMessage.id == message_id)
    )
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    if payload.subject is not None:
        message.subject = payload.subject
    if payload.body_html is not None:
        message.body_html = payload.body_html
    if payload.status is not None:
        message.status = payload.status

    await db.commit()
    await db.refresh(message)
    return _message_out(message)


@router.post("/messages/{message_id}/send")
async def send_message(
    message_id: uuid.UUID,
    x_gmail_token: str = Header(..., alias="X-Gmail-Token"),
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Send a single thread message via Gmail."""
    try:
        result = await send_thread_message(
            db,
            str(message_id),
            x_gmail_token,
            sender_email=current_user.email,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[Outreach] Message send failed: {e}")
        raise HTTPException(status_code=500, detail="Message send failed")


@router.post("/threads/bulk-send")
async def bulk_send(
    payload: BulkSendRequest,
    x_gmail_token: str = Header(..., alias="X-Gmail-Token"),
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Send multiple thread messages with rate limiting."""
    try:
        result = await send_bulk_thread_messages(
            db,
            [str(mid) for mid in payload.message_ids],
            x_gmail_token,
            sender_email=payload.sender_email,
        )
        return result
    except Exception as e:
        logger.error(f"[Outreach] Bulk send failed: {e}")
        raise HTTPException(status_code=500, detail="Bulk send failed")


# --- Response handling ---

@router.post("/threads/{thread_id}/mark-responded")
async def mark_responded(
    thread_id: uuid.UUID,
    payload: MarkRespondedRequest,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Mark a thread as having received a response."""
    result = await db.execute(
        select(OutreachThread)
        .options(
            selectinload(OutreachThread.company),
            selectinload(OutreachThread.contact),
            selectinload(OutreachThread.messages),
        )
        .where(OutreachThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread.status = "responded"
    thread.response_received_at = datetime.utcnow()
    if payload.response_summary:
        thread.response_summary = payload.response_summary

    await db.commit()
    await db.refresh(thread)

    # Reload with relations
    result = await db.execute(
        select(OutreachThread)
        .options(
            selectinload(OutreachThread.company),
            selectinload(OutreachThread.contact),
            selectinload(OutreachThread.messages),
        )
        .where(OutreachThread.id == thread_id)
    )
    thread = result.scalar_one()
    return _thread_out(thread)


@router.post("/threads/{thread_id}/generate-scheduling-reply")
async def generate_scheduling_reply(
    thread_id: uuid.UUID,
    payload: SchedulingReplyRequest,
    db=Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Generate a scheduling reply suggesting time slots."""
    try:
        # Update proposed slots on thread
        result = await db.execute(
            select(OutreachThread).where(OutreachThread.id == thread_id)
        )
        thread = result.scalar_one_or_none()
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

        thread.proposed_slots = payload.proposed_slots
        await db.commit()

        message = await generate_thread_draft(
            db,
            str(thread_id),
            message_type="scheduling_reply",
            proposed_slots=payload.proposed_slots,
        )
        return _message_out(message)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[Outreach] Scheduling reply failed: {e}")
        raise HTTPException(status_code=500, detail="Scheduling reply generation failed")
