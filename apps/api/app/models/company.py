import uuid
import enum
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, Text, ForeignKey, Enum as SAEnum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class PipelineStage(str, enum.Enum):
    Identified = "Identified"
    OutreachSent = "Outreach Sent"
    Engaged = "Engaged"
    NDASigned = "NDA Signed"
    Diligence = "Diligence"
    LOISubmitted = "LOI Submitted"
    LOISigned = "LOI Signed"
    Closed = "Closed"
    Passed = "Passed"
    OnHold = "On Hold"


class OwnershipType(str, enum.Enum):
    FounderOwned = "Founder-Owned"
    PEBacked = "PE-Backed"
    FamilyOwned = "Family-Owned"
    Public = "Public"
    Unknown = "Unknown"


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    website: Mapped[str | None] = mapped_column(String, nullable=True)
    hq_location: Mapped[str | None] = mapped_column(String, nullable=True)
    employee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sector: Mapped[str] = mapped_column(String, nullable=False, default="Other")
    ownership_type: Mapped[OwnershipType] = mapped_column(
        SAEnum(OwnershipType, name="ownership_type"),
        nullable=False,
        default=OwnershipType.Unknown,
    )
    revenue_low: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    revenue_high: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    ebitda_low: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    ebitda_high: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    stage: Mapped[PipelineStage] = mapped_column(
        SAEnum(PipelineStage, name="pipeline_stage"),
        nullable=False,
        default=PipelineStage.Identified,
    )
    ai_fit_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    contacts: Mapped[list["Contact"]] = relationship(  # noqa: F821
        "Contact", back_populates="company", cascade="all, delete-orphan"
    )
