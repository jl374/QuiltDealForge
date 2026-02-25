import uuid
from datetime import datetime, date
from sqlalchemy import String, Text, Date, Boolean, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String, nullable=True)
    facebook_url: Mapped[str | None] = mapped_column(String, nullable=True)
    is_principal_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    enrichment_status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # pending | completed | failed
    enrichment_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    enrichment_source: Mapped[str | None] = mapped_column(String(20), nullable=True)  # web | apollo | manual
    enriched_at: Mapped[datetime | None] = mapped_column(nullable=True)
    relationship_owner: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_contact_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship("Company", back_populates="contacts")  # noqa: F821
