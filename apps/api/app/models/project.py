import uuid
from datetime import datetime
from sqlalchemy import String, Text, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Project(Base):
    """A named folder/list for grouping companies under a specific deal thesis or project."""
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="slate")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    companies: Mapped[list["ProjectCompany"]] = relationship(
        "ProjectCompany", back_populates="project", cascade="all, delete-orphan"
    )


class ProjectCompany(Base):
    """Join table: which companies belong to which projects (many-to-many)."""
    __tablename__ = "project_companies"
    __table_args__ = (
        UniqueConstraint("project_id", "company_id", name="uq_project_company"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    added_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="companies")
    company: Mapped["Company"] = relationship("Company")  # noqa: F821
