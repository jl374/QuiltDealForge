"""
Gmail Sending Service
Sends outreach emails via Gmail API using the user's OAuth access token.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.outreach import OutreachCampaign, OutreachEmail, OutreachThread, OutreachMessage

logger = logging.getLogger(__name__)

# Rate limit: 1 email per N seconds to avoid Gmail throttling
SEND_DELAY_SECONDS = 2


def _build_gmail_service(access_token: str):
    """Build a Gmail API service client from an OAuth access token."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(token=access_token)
    service = build("gmail", "v1", credentials=creds)
    return service


def _create_message(to: str, subject: str, body_html: str, sender_email: str) -> dict:
    """Create a Gmail-compatible message dict."""
    msg = MIMEMultipart("alternative")
    msg["to"] = to
    msg["from"] = sender_email
    msg["subject"] = subject

    # Plain text fallback
    from html import unescape
    import re
    plain_text = re.sub(r"<[^>]+>", "", body_html)
    plain_text = unescape(plain_text)

    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    return {"raw": raw}


def _send_single_email(service, message: dict) -> str:
    """Send a single email via Gmail API. Returns message ID."""
    sent = service.users().messages().send(userId="me", body=message).execute()
    return sent.get("id", "")


async def send_campaign(
    db: AsyncSession,
    campaign_id: str,
    access_token: str,
) -> dict:
    """
    Send all approved (or draft) emails in a campaign via Gmail.
    Returns summary of send results.
    """
    # Load campaign with emails
    result = await db.execute(
        select(OutreachCampaign)
        .options(selectinload(OutreachCampaign.emails))
        .where(OutreachCampaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    # Filter to sendable emails (draft or approved)
    sendable = [e for e in campaign.emails if e.status in ("draft", "approved")]
    if not sendable:
        return {"total": 0, "sent": 0, "failed": 0, "message": "No emails to send"}

    # Update campaign status
    campaign.status = "sending"
    await db.commit()

    # Build Gmail service (sync operation, run in executor)
    loop = asyncio.get_event_loop()
    service = await loop.run_in_executor(None, _build_gmail_service, access_token)

    sent_count = 0
    failed_count = 0

    for email in sendable:
        try:
            message = _create_message(
                to=email.to_email,
                subject=email.subject,
                body_html=email.body_html,
                sender_email=campaign.sender_email,
            )
            gmail_id = await loop.run_in_executor(
                None, _send_single_email, service, message
            )
            email.status = "sent"
            email.gmail_message_id = gmail_id
            email.sent_at = datetime.utcnow()
            sent_count += 1

            logger.info(f"[Gmail] Sent email to {email.to_email} (gmail_id={gmail_id})")

        except Exception as e:
            email.status = "failed"
            email.error_message = str(e)[:500]
            failed_count += 1
            logger.error(f"[Gmail] Failed to send to {email.to_email}: {e}")

        await db.commit()

        # Rate limiting
        if email != sendable[-1]:
            await asyncio.sleep(SEND_DELAY_SECONDS)

    # Update campaign status
    campaign.status = "sent" if failed_count == 0 else "paused"
    await db.commit()

    return {
        "total": len(sendable),
        "sent": sent_count,
        "failed": failed_count,
    }


# ---------------------------------------------------------------------------
# Thread-based message sending
# ---------------------------------------------------------------------------

async def send_thread_message(
    db: AsyncSession,
    message_id: str,
    access_token: str,
    sender_email: str,
) -> dict:
    """
    Send a single OutreachMessage via Gmail.
    Updates message status and thread status.
    Returns { message_id, gmail_message_id, gmail_thread_id }.
    """
    result = await db.execute(
        select(OutreachMessage)
        .options(selectinload(OutreachMessage.thread))
        .where(OutreachMessage.id == message_id)
    )
    message = result.scalar_one_or_none()
    if not message:
        raise ValueError(f"Message {message_id} not found")

    if message.status == "sent":
        raise ValueError("Message already sent")

    thread = message.thread

    loop = asyncio.get_event_loop()
    service = await loop.run_in_executor(None, _build_gmail_service, access_token)

    gmail_msg = _create_message(
        to=message.to_email,
        subject=message.subject,
        body_html=message.body_html,
        sender_email=sender_email,
    )

    # If we have a gmail_thread_id from a prior message, thread the reply
    prior_thread_id = None
    if thread and thread.messages:
        for m in sorted(thread.messages, key=lambda x: x.sequence):
            if m.gmail_thread_id and m.id != message.id:
                prior_thread_id = m.gmail_thread_id
                break

    if prior_thread_id:
        gmail_msg["threadId"] = prior_thread_id

    try:
        sent = await loop.run_in_executor(
            None,
            lambda: service.users().messages().send(userId="me", body=gmail_msg).execute(),
        )
        gmail_id = sent.get("id", "")
        gmail_tid = sent.get("threadId", "")

        message.status = "sent"
        message.sent_at = datetime.utcnow()
        message.gmail_message_id = gmail_id
        message.gmail_thread_id = gmail_tid

        # Update thread status
        if thread:
            thread.status = "awaiting_response"
            thread.last_sent_at = datetime.utcnow()
            if message.message_type == "follow_up":
                thread.follow_up_count = (thread.follow_up_count or 0) + 1

        await db.commit()
        logger.info(f"[Gmail] Sent message to {message.to_email} (gmail_id={gmail_id})")

        return {
            "message_id": str(message.id),
            "gmail_message_id": gmail_id,
            "gmail_thread_id": gmail_tid,
        }

    except Exception as e:
        message.status = "failed"
        message.error_message = str(e)[:500]
        await db.commit()
        logger.error(f"[Gmail] Failed to send to {message.to_email}: {e}")
        raise


async def send_bulk_thread_messages(
    db: AsyncSession,
    message_ids: list[str],
    access_token: str,
    sender_email: str,
) -> dict:
    """
    Send multiple OutreachMessages with rate limiting.
    Returns summary { total, sent, failed }.
    """
    sent_count = 0
    failed_count = 0

    for i, mid in enumerate(message_ids):
        try:
            await send_thread_message(db, mid, access_token, sender_email)
            sent_count += 1
        except Exception as e:
            logger.error(f"[Gmail] Bulk send failed for {mid}: {e}")
            failed_count += 1

        # Rate limiting between sends
        if i < len(message_ids) - 1:
            await asyncio.sleep(SEND_DELAY_SECONDS)

    return {
        "total": len(message_ids),
        "sent": sent_count,
        "failed": failed_count,
    }
