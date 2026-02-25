import uuid
from datetime import datetime
from sqlalchemy import String, Text, Integer, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class OutreachCampaign(Base):
    __tablename__ = "outreach_campaigns"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    subject_template: Mapped[str] = mapped_column(Text, nullable=False)
    body_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    sender_email: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="draft"
    )  # draft | generating | ready | sending | sent | paused
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    project: Mapped["Project"] = relationship("Project")  # noqa: F821
    emails: Mapped[list["OutreachEmail"]] = relationship(
        "OutreachEmail", back_populates="campaign", cascade="all, delete-orphan"
    )


class OutreachEmail(Base):
    __tablename__ = "outreach_emails"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("outreach_campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    to_email: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="draft"
    )  # draft | approved | sent | failed | bounced
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    gmail_message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    campaign: Mapped["OutreachCampaign"] = relationship("OutreachCampaign", back_populates="emails")
    contact: Mapped["Contact"] = relationship("Contact")  # noqa: F821
    company: Mapped["Company"] = relationship("Company")  # noqa: F821


class OutreachThread(Base):
    """
    Represents the full outreach lifecycle for one company/contact pair
    within a project. This is the core CRM unit — one thread per company
    per project, tracking initial outreach through scheduling.
    """
    __tablename__ = "outreach_threads"
    __table_args__ = (
        UniqueConstraint("project_id", "company_id", name="uq_thread_project_company"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="draft"
    )  # draft | sent | awaiting_response | responded | meeting_scheduled | passed

    # Follow-up tracking
    follow_up_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    next_follow_up_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_sent_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Response tracking
    response_received_at: Mapped[datetime | None] = mapped_column(nullable=True)
    response_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Scheduling — stores proposed time slots as JSON array
    # e.g. [{"datetime": "2026-03-05T10:00", "label": "Wednesday 10am ET"}, ...]
    proposed_slots: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project")  # noqa: F821
    company: Mapped["Company"] = relationship("Company")  # noqa: F821
    contact: Mapped["Contact"] = relationship("Contact")  # noqa: F821
    messages: Mapped[list["OutreachMessage"]] = relationship(
        "OutreachMessage", back_populates="thread",
        cascade="all, delete-orphan",
        order_by="OutreachMessage.sequence",
    )


class OutreachMessage(Base):
    """
    Individual emails within a thread — initial outreach, follow-ups,
    and scheduling replies. Each message has its own send status.
    """
    __tablename__ = "outreach_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("outreach_threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    message_type: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="initial"
    )  # initial | follow_up | scheduling_reply

    to_email: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="draft"
    )  # draft | approved | sent | failed | bounced

    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    gmail_message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    gmail_thread_id: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    thread: Mapped["OutreachThread"] = relationship("OutreachThread", back_populates="messages")
