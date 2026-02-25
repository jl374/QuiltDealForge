"""
Email Composition Service
Uses Claude to generate highly personalized outreach emails for each
contact in a campaign, based on company data, owner research, and project thesis.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.company import Company
from app.models.contact import Contact
from app.models.project import Project, ProjectCompany
from app.models.outreach import OutreachCampaign, OutreachEmail, OutreachThread, OutreachMessage
from app.services.web_helpers import call_claude_async

logger = logging.getLogger(__name__)

# Concurrency limit for parallel Claude calls
MAX_CONCURRENT_GENERATIONS = 5


async def generate_campaign_emails(db: AsyncSession, campaign_id: str) -> dict:
    """
    Generate personalized emails for all eligible contacts in a campaign.
    Updates campaign status: draft → generating → ready.
    Returns summary of generation results.
    """
    # Load campaign with project
    result = await db.execute(
        select(OutreachCampaign).where(OutreachCampaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    # Load project
    result = await db.execute(
        select(Project).where(Project.id == campaign.project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise ValueError(f"Project {campaign.project_id} not found")

    # Get all companies in this project
    result = await db.execute(
        select(ProjectCompany)
        .options(selectinload(ProjectCompany.company))
        .where(ProjectCompany.project_id == project.id)
    )
    project_companies = result.scalars().all()

    if not project_companies:
        return {"total": 0, "generated": 0, "skipped": 0, "errors": 0}

    # Get enriched principal owner contacts for these companies
    company_ids = [pc.company_id for pc in project_companies]
    result = await db.execute(
        select(Contact).where(
            Contact.company_id.in_(company_ids),
            Contact.is_principal_owner == True,
            Contact.email.isnot(None),
            Contact.email != "",
        )
    )
    contacts = result.scalars().all()

    # Map company_id -> contact
    contact_map = {c.company_id: c for c in contacts}
    # Map company_id -> company
    company_map = {pc.company_id: pc.company for pc in project_companies}

    # Update campaign status
    campaign.status = "generating"
    await db.commit()

    # Delete any existing draft emails for this campaign (regeneration)
    result = await db.execute(
        select(OutreachEmail).where(
            OutreachEmail.campaign_id == campaign.id,
            OutreachEmail.status == "draft",
        )
    )
    old_drafts = result.scalars().all()
    for draft in old_drafts:
        await db.delete(draft)
    await db.commit()

    # Generate emails with concurrency control
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_GENERATIONS)
    generated = 0
    skipped = 0
    errors = 0

    async def _generate_one(company: Company, contact: Contact):
        nonlocal generated, errors
        async with semaphore:
            try:
                email_data = await _compose_email(
                    company=company,
                    contact=contact,
                    project=project,
                    campaign=campaign,
                )
                email = OutreachEmail(
                    campaign_id=campaign.id,
                    contact_id=contact.id,
                    company_id=company.id,
                    to_email=contact.email,
                    subject=email_data["subject"],
                    body_html=email_data["body_html"],
                    status="draft",
                )
                db.add(email)
                generated += 1
            except Exception as e:
                logger.error(f"[Email] Error generating for {contact.name} at {company.name}: {e}")
                errors += 1

    tasks = []
    for company_id, company in company_map.items():
        contact = contact_map.get(company_id)
        if contact:
            tasks.append(_generate_one(company, contact))
        else:
            skipped += 1

    if tasks:
        await asyncio.gather(*tasks)
        await db.commit()

    # Update campaign status
    campaign.status = "ready" if generated > 0 else "draft"
    await db.commit()

    return {
        "total": len(company_ids),
        "generated": generated,
        "skipped": skipped,
        "errors": errors,
    }


async def _compose_email(
    company: Company,
    contact: Contact,
    project: Project,
    campaign: OutreachCampaign,
) -> dict:
    """
    Use Claude to compose a personalized email for a single contact.
    Returns { subject: str, body_html: str }.
    """
    # Build rich context for Claude
    enrichment_notes = ""
    if contact.enrichment_data:
        extracted = contact.enrichment_data.get("extracted", {})
        if extracted:
            enrichment_notes = f"Research findings: {json.dumps(extracted)}"

    revenue_str = ""
    if company.revenue_low and company.revenue_high:
        revenue_str = f"${company.revenue_low:,.0f} - ${company.revenue_high:,.0f}"
    elif company.revenue_low:
        revenue_str = f"${company.revenue_low:,.0f}+"

    prompt = f"""You are a skilled business development professional writing a personalized outreach email.

RECIPIENT:
- Name: {contact.name}
- Title: {contact.title or "Owner/Principal"}
- Company: {company.name}
- Location: {company.hq_location or "Unknown"}
- Sector: {company.sector or "Unknown"}
- Company Revenue: {revenue_str or "Unknown"}
- Employees: {company.employee_count or "Unknown"}
- LinkedIn: {contact.linkedin_url or "N/A"}
{enrichment_notes}

PROJECT CONTEXT (our investment thesis):
- Project: {project.name}
- Description: {project.description or "Investment opportunity evaluation"}

CAMPAIGN INSTRUCTIONS:
- Subject line guidance: {campaign.subject_template}
- Email approach/angle: {campaign.body_prompt}

IMPORTANT RULES:
1. Write a highly personalized email — reference specific details about their company, their role, their industry
2. Keep it concise (3-5 short paragraphs max)
3. Sound natural and human, not like a template
4. Include a clear but soft call-to-action (suggest a brief call)
5. Be professional but warm
6. Do NOT use generic phrases like "I came across your company" — be specific
7. Sign off with just a first name placeholder: [SENDER_NAME]

Return ONLY a JSON object:
{{
  "subject": "The personalized subject line",
  "body_html": "<p>The email body in HTML paragraphs</p>"
}}

Return ONLY the JSON. No other text."""

    raw = await call_claude_async(prompt, max_tokens=600)

    # Parse JSON
    try:
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return {
                "subject": data.get("subject", f"Opportunity discussion - {company.name}"),
                "body_html": data.get("body_html", "<p>Email generation failed. Please edit manually.</p>"),
            }
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"[Email] Failed to parse Claude response: {e}")

    # Fallback
    return {
        "subject": f"Regarding {company.name}",
        "body_html": "<p>Email generation failed. Please edit this email manually.</p>",
    }


# ---------------------------------------------------------------------------
# Thread-based outreach (CRM model)
# ---------------------------------------------------------------------------

QUILT_CAPITAL_INTRO = (
    "Quilt Capital is an AI-native PE firm that partners with lower middle market "
    "services businesses ($5-25M EBITDA) to embed proprietary AI and accelerate growth."
)


def _revenue_str(company: Company) -> str:
    if company.revenue_low and company.revenue_high:
        return f"${company.revenue_low:,.0f} - ${company.revenue_high:,.0f}"
    elif company.revenue_low:
        return f"${company.revenue_low:,.0f}+"
    return "Unknown"


def _enrichment_context(contact: Contact) -> str:
    if not contact.enrichment_data:
        return ""
    extracted = contact.enrichment_data.get("extracted", {})
    research = contact.enrichment_data.get("research", {})
    parts = []
    if extracted:
        parts.append(f"Extracted info: {json.dumps(extracted)}")
    if isinstance(research, dict):
        for key, val in research.items():
            if val and isinstance(val, str) and len(val) > 40:
                parts.append(f"[{key}]: {val[:800]}")
    return "\n".join(parts) if parts else ""


def _personality_context(contact: Contact) -> str:
    """Format personality data from enrichment_data into a structured block
    for use in email composition prompts."""
    if not contact.enrichment_data:
        return ""
    personality = contact.enrichment_data.get("personality", {})
    if not personality:
        return ""

    sections = []

    bg = personality.get("professional_background")
    if bg:
        sections.append(f"Professional Background: {bg}")

    interests = personality.get("interests_and_passions")
    if interests and isinstance(interests, list):
        sections.append(f"Interests & Passions: {', '.join(interests)}")

    style = personality.get("communication_style")
    if style:
        sections.append(f"Communication Style: {style}")

    values = personality.get("values_and_priorities")
    if values and isinstance(values, list):
        sections.append(f"Values & Priorities: {', '.join(values)}")

    personal = personality.get("personal_details")
    if personal:
        sections.append(f"Personal Details: {personal}")

    ice_breakers = personality.get("ice_breakers")
    if ice_breakers and isinstance(ice_breakers, list):
        sections.append("Ice Breakers:\n" + "\n".join(f"  - {ib}" for ib in ice_breakers))

    angle = personality.get("outreach_angle")
    if angle:
        sections.append(f"Recommended Outreach Angle: {angle}")

    return "\n".join(sections) if sections else ""


def _parse_claude_email_json(raw: str, fallback_subject: str) -> dict:
    """Parse Claude's JSON response for email subject + body."""
    try:
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return {
                "subject": data.get("subject", fallback_subject),
                "body_html": data.get(
                    "body_html",
                    "<p>Email generation failed. Please edit manually.</p>",
                ),
            }
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"[Email] Failed to parse Claude response: {e}")
    return {
        "subject": fallback_subject,
        "body_html": "<p>Email generation failed. Please edit this email manually.</p>",
    }


async def generate_thread_draft(
    db: AsyncSession,
    thread_id: str,
    message_type: str = "initial",
    custom_prompt: str | None = None,
    proposed_slots: list[dict] | None = None,
) -> OutreachMessage:
    """
    Generate a single draft message for a thread.
    Returns the created OutreachMessage.
    """
    # Load thread with relationships
    result = await db.execute(
        select(OutreachThread)
        .options(
            selectinload(OutreachThread.company),
            selectinload(OutreachThread.contact),
            selectinload(OutreachThread.project),
            selectinload(OutreachThread.messages),
        )
        .where(OutreachThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise ValueError(f"Thread {thread_id} not found")

    # Auto-link principal owner if thread has no contact yet (e.g. thread created before enrichment)
    if not thread.contact and thread.company_id:
        from app.models.contact import Contact as ContactModel
        owner_result = await db.execute(
            select(ContactModel).where(
                ContactModel.company_id == thread.company_id,
                ContactModel.is_principal_owner == True,
            )
        )
        owner = owner_result.scalar_one_or_none()
        if owner:
            thread.contact_id = owner.id
            thread.contact = owner
            await db.flush()

    if not thread.contact:
        raise ValueError("Thread has no contact associated. Please enrich this company or add contact info manually.")
    # Note: we allow draft generation even without an email.
    # The email is only required at send time, not for drafting.

    company = thread.company
    contact = thread.contact
    project = thread.project
    existing_messages = sorted(thread.messages, key=lambda m: m.sequence)

    if message_type == "initial":
        email_data = await _compose_initial_outreach(
            company, contact, project, custom_prompt
        )
    elif message_type == "follow_up":
        email_data = await _compose_follow_up(
            company, contact, project, existing_messages
        )
    elif message_type == "scheduling_reply":
        email_data = await _compose_scheduling_reply(
            company, contact, existing_messages, proposed_slots or []
        )
    else:
        raise ValueError(f"Unknown message_type: {message_type}")

    # Determine sequence number
    next_seq = max((m.sequence for m in existing_messages), default=0) + 1

    # Delete any existing draft of the same type (regeneration)
    for m in existing_messages:
        if m.status == "draft" and m.message_type == message_type:
            await db.delete(m)

    message = OutreachMessage(
        thread_id=thread.id,
        sequence=next_seq,
        message_type=message_type,
        to_email=contact.email or "",
        subject=email_data["subject"],
        body_html=email_data["body_html"],
        status="draft",
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    return message


async def _compose_initial_outreach(
    company: Company,
    contact: Contact,
    project: Project,
    custom_prompt: str | None = None,
) -> dict:
    """
    Compose a punchy, high-response-rate cold outreach email.
    Short, specific, conversational — optimized for busy owners.
    """
    enrichment_notes = _enrichment_context(contact)
    personality_notes = _personality_context(contact)
    revenue = _revenue_str(company)
    first_name = (contact.name or "").split()[0] if contact.name else ""

    personalization_block = ""
    if personality_notes:
        personalization_block = f"""
PERSONALITY INTEL (use to make the email feel 1-to-1, not mass-blasted):
{personality_notes}

HOW TO USE THIS:
- Your OPENING LINE must reference a specific detail from above — a fact, an achievement, a passion
- Present your knowledge naturally (never say "I saw your LinkedIn" or "I researched you")
- Match their communication style (if casual, be casual; if formal, be crisp)
- If ice breakers are listed, use one as a P.S. line at the end
"""

    prompt = f"""Write a cold outreach email from a partner at Quilt Capital.

WHO IS QUILT: {QUILT_CAPITAL_INTRO}

RECIPIENT:
- Name: {contact.name} (use "{first_name}" in greeting)
- Title: {contact.title or "Owner"}
- Company: {company.name}
- Location: {company.hq_location or "Unknown"}
- Sector: {company.sector or "Unknown"}
- Revenue: {revenue}

RESEARCH ON THEM:
{enrichment_notes or "No additional research available."}
{personalization_block}
INVESTMENT THESIS: {project.name} — {project.description or "Investment opportunity evaluation"}

{f"EXTRA INSTRUCTIONS: {custom_prompt}" if custom_prompt else ""}

EMAIL STRUCTURE (follow this exactly):
1. Opening line: One specific observation about THEM — a number, trend, achievement, or challenge in their world. Lead with THEM, not you.
2. Bridge: One sentence connecting that observation to why you're writing.
3. Value prop: One to two sentences on what Quilt does, framed entirely as value to THEM (not your features). What would change for their business?
4. CTA: One simple question. Easy to say yes to. Under 12 words.
5. Sign-off: [SENDER_NAME]
6. P.S. (optional): If personality insights exist, add a brief personal P.S. referencing an interest or ice breaker.

HARD RULES:
- MAXIMUM 125 WORDS in the body (excluding subject). Count them. This is non-negotiable.
- Maximum 5 sentences in the body before the sign-off.
- No sentence longer than 25 words.
- Subject line: lowercase, 3-7 words, spark curiosity. Examples: "quick question about {{company}}", "{{first_name}} — ai in {{sector}}", "idea for {{company}}"
- Tone: smart peer, not pitch deck. Write like you're texting a colleague you respect.
- NEVER use: "I hope this finds you well", "I came across your company", "at the intersection of", "leverage", "synergies", "transformative", "cutting-edge", "world-class", "pioneering", "I'd love to", "I think you'd find", "In today's rapidly evolving", "value creation", "paradigm"
- Do NOT explain what PE is. Do NOT list Quilt's features. Frame everything as THEIR benefit.

Return ONLY valid JSON, nothing else:
{{"subject": "the lowercase subject line", "body_html": "<p>the email body in html paragraphs</p>"}}"""

    raw = await call_claude_async(prompt, max_tokens=400)
    return _parse_claude_email_json(raw, f"quick question about {company.name}")


async def _compose_follow_up(
    company: Company,
    contact: Contact,
    project: Project,
    existing_messages: list[OutreachMessage],
) -> dict:
    """
    Compose a ultra-short follow-up. Different angle, zero pressure, easy CTA.
    """
    prior = [m for m in existing_messages if m.status == "sent"]
    prior_context = ""
    prior_subject = ""
    if prior:
        latest = prior[-1]
        sent_date = latest.sent_at.strftime("%B %d") if latest.sent_at else "recently"
        prior_subject = latest.subject
        prior_context = (
            f"- Previous email sent on {sent_date}\n"
            f"- Previous subject: {latest.subject}\n"
            f"- This will be follow-up #{len(prior)}"
        )

    personality_notes = _personality_context(contact)
    first_name = (contact.name or "").split()[0] if contact.name else ""

    personality_block = ""
    if personality_notes:
        personality_block = f"""
PERSONALITY (use a DIFFERENT angle than initial email — pick one detail):
{personality_notes}
"""

    prompt = f"""Write a follow-up cold email for a Quilt Capital partner. No response yet to the initial email.

RECIPIENT: {contact.name} ({contact.title or "Owner"}) at {company.name} ({company.sector or "services"})

PREVIOUS OUTREACH:
{prior_context or "Initial email was sent recently."}
{personality_block}
STRUCTURE (exactly this):
1. One sentence: Acknowledge the previous email casually. No guilt.
2. One to two sentences: A NEW angle — a specific insight, trend, or value relevant to their business. Something they haven't heard.
3. One sentence: Binary CTA question. Make it easy to reply.
4. [SENDER_NAME]

HARD RULES:
- MAXIMUM 60 WORDS total. This is non-negotiable.
- Maximum 3 sentences before sign-off.
- Subject: "Re: {prior_subject or 'previous subject'}" (keep the thread)
- Tone: casual, human, zero pressure. "Totally get it if timing's off" energy.
- CTA must be a binary question: "Worth a chat, or bad timing?" / "Interested or not the right fit?"
- NEVER repeat the Quilt pitch. NEVER use corporate jargon.
- NEVER use: "just circling back", "touching base", "checking in", "I hope this finds you well"

Return ONLY valid JSON, nothing else:
{{"subject": "Re: ...", "body_html": "<p>...</p>"}}"""

    raw = await call_claude_async(prompt, max_tokens=250)
    return _parse_claude_email_json(raw, f"Re: {prior_subject or company.name}")


async def _compose_scheduling_reply(
    company: Company,
    contact: Contact,
    existing_messages: list[OutreachMessage],
    proposed_slots: list[dict],
) -> dict:
    """
    Compose a scheduling reply in the voice of an EA/assistant,
    suggesting time slots the prospect can choose from.
    """
    slots_text = "\n".join(
        f"  {i+1}. {slot.get('label', slot.get('datetime', 'TBD'))}"
        for i, slot in enumerate(proposed_slots)
    )

    prompt = f"""You are writing an email as a scheduling assistant / executive assistant
at Quilt Capital. You are responding to {contact.name} at {company.name} who has
expressed interest in a conversation.

PROPOSED MEETING TIMES:
{slots_text or "  (No specific times provided — ask for their availability)"}

RULES:
1. Write as a professional scheduling assistant
2. Reference that you're reaching out on behalf of [SENDER_NAME] from Quilt Capital
3. Thank them briefly for their interest / response
4. Present the time slots clearly, numbered
5. Ask them to pick whatever works best, or suggest alternatives if none work
6. Keep it brief and efficient — 2-3 short paragraphs max
7. Sign off as "Best regards,\\n[ASSISTANT_NAME]\\nScheduling · Quilt Capital"
8. Be warm but businesslike

Return ONLY JSON:
{{"subject": "Scheduling a conversation — Quilt Capital × {company.name}", "body_html": "<p>...</p>"}}

Return ONLY the JSON. No other text."""

    raw = await call_claude_async(prompt, max_tokens=400)
    return _parse_claude_email_json(
        raw, f"Scheduling a conversation — Quilt Capital × {company.name}"
    )


async def bulk_generate_initial_drafts(
    db: AsyncSession,
    project_id: str,
    company_ids: list[str],
    created_by: str | None = None,
) -> dict:
    """
    For each company_id, find or create an OutreachThread,
    then generate an initial draft OutreachMessage.
    Returns { total, generated, skipped, errors }.
    """
    # Load project
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise ValueError(f"Project {project_id} not found")

    # Get enriched principal owner contacts for these companies
    result = await db.execute(
        select(Contact).where(
            Contact.company_id.in_(company_ids),
            Contact.is_principal_owner == True,  # noqa: E712
            Contact.email.isnot(None),
            Contact.email != "",
        )
    )
    contacts = result.scalars().all()
    contact_map = {str(c.company_id): c for c in contacts}

    # Load existing threads for this project
    result = await db.execute(
        select(OutreachThread)
        .options(selectinload(OutreachThread.messages))
        .where(
            OutreachThread.project_id == project_id,
            OutreachThread.company_id.in_(company_ids),
        )
    )
    existing_threads = result.scalars().all()
    thread_map = {str(t.company_id): t for t in existing_threads}

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_GENERATIONS)
    generated = 0
    skipped = 0
    errors = 0

    async def _gen_one(cid: str):
        nonlocal generated, skipped, errors
        contact = contact_map.get(cid)
        if not contact:
            skipped += 1
            return

        async with semaphore:
            try:
                # Find or create thread
                thread = thread_map.get(cid)
                if not thread:
                    thread = OutreachThread(
                        project_id=project_id,
                        company_id=cid,
                        contact_id=contact.id,
                        status="draft",
                        created_by=created_by,
                    )
                    db.add(thread)
                    await db.flush()

                # Skip if thread already has a sent initial message
                has_sent = any(
                    m.message_type == "initial" and m.status == "sent"
                    for m in (thread.messages or [])
                )
                if has_sent:
                    skipped += 1
                    return

                await generate_thread_draft(db, str(thread.id), "initial")
                generated += 1
            except Exception as e:
                logger.error(f"[BulkGen] Error for company {cid}: {e}")
                errors += 1

    tasks = [_gen_one(cid) for cid in company_ids]
    if tasks:
        await asyncio.gather(*tasks)
        await db.commit()

    return {
        "total": len(company_ids),
        "generated": generated,
        "skipped": skipped,
        "errors": errors,
    }
