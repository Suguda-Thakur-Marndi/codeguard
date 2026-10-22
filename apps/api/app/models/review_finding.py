"""ReviewFinding ORM model for storing candidate and verified code review findings."""

import enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.agent_run import AgentRun
    from app.models.finding_evidence import FindingEvidenceModel
    from app.models.judge_decision import JudgeDecisionModel
    from app.models.review_job import ReviewJob
    from app.models.validation_scenario import ValidationScenarioModel


class FindingCategory(enum.StrEnum):
    SECURITY = "SECURITY"
    BUG = "BUG"
    ERROR_HANDLING = "ERROR_HANDLING"
    TEST_COVERAGE = "TEST_COVERAGE"
    CONTRACT = "CONTRACT"
    PERFORMANCE = "PERFORMANCE"
    ARCHITECTURE = "ARCHITECTURE"


class FindingSeverity(enum.StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    ADVISORY = "ADVISORY"


class FindingStatus(enum.StrEnum):
    CANDIDATE = "CANDIDATE"
    VALID = "VALID"
    INVALID = "INVALID"
    VALIDATED = "VALIDATED"
    EXECUTION_VERIFIED = "EXECUTION_VERIFIED"
    REJECTED = "REJECTED"
    PUBLISHABLE = "PUBLISHABLE"
    PUBLISHED = "PUBLISHED"


class ReviewFindingModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Candidate or verified code review finding produced by Phase 3 & 4 AI agents and Judge."""

    __tablename__ = "review_findings"

    review_job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("review_jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    agent_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_runs.id", ondelete="SET NULL"), index=True, nullable=True
    )
    file_path: Mapped[str] = mapped_column(
        String(500), index=True, nullable=False
    )
    line_number: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    side: Mapped[str] = mapped_column(
        String(10), default="RIGHT", nullable=False
    )
    start_line: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    start_side: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )
    category: Mapped[FindingCategory] = mapped_column(
        Enum(FindingCategory, name="finding_category", native_enum=False),
        index=True,
        nullable=False,
    )
    severity: Mapped[FindingSeverity] = mapped_column(
        Enum(FindingSeverity, name="finding_severity", native_enum=False),
        index=True,
        nullable=False,
    )
    original_severity: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    final_severity: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    title: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    description: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    impact: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    recommendation: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    confidence: Mapped[float] = mapped_column(
        Float, default=1.0, nullable=False
    )
    specialist_confidence: Mapped[float] = mapped_column(
        Float, default=1.0, nullable=False
    )
    judge_confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    final_confidence: Mapped[float] = mapped_column(
        Float, default=1.0, nullable=False
    )
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    affected_symbol: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    related_files: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    related_symbols: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    agent_name: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    source_agents: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    duplicate_of: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    root_cause_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    finding_group_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    status: Mapped[FindingStatus] = mapped_column(
        Enum(FindingStatus, name="finding_status", native_enum=False),
        default=FindingStatus.CANDIDATE,
        index=True,
        nullable=False,
    )
    validation_notes: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    # Relationships
    review_job: Mapped["ReviewJob"] = relationship(
        "ReviewJob", back_populates="findings"
    )
    agent_run: Mapped["AgentRun | None"] = relationship(
        "AgentRun", back_populates="findings"
    )
    judge_decisions: Mapped[list["JudgeDecisionModel"]] = relationship(
        "JudgeDecisionModel", back_populates="finding", cascade="all, delete-orphan"
    )
    validation_scenarios: Mapped[list["ValidationScenarioModel"]] = relationship(
        "ValidationScenarioModel", back_populates="finding", cascade="all, delete-orphan"
    )
    grounding_evidence: Mapped[list["FindingEvidenceModel"]] = relationship(
        "FindingEvidenceModel", back_populates="finding", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_review_findings_job_severity", "review_job_id", "severity"),
        Index("ix_review_findings_job_category", "review_job_id", "category"),
        Index("ix_review_findings_job_status", "review_job_id", "status"),
        Index("ix_review_findings_file_line", "file_path", "line_number"),
        Index("ix_review_findings_root_cause", "root_cause_id"),
        Index("ix_review_findings_duplicate_of", "duplicate_of"),
    )
