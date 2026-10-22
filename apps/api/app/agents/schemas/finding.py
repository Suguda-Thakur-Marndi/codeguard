"""Pydantic schemas for structured candidate review findings and evidence."""

import enum
import uuid

from pydantic import BaseModel, Field


class EvidenceType(enum.StrEnum):
    CODE = "CODE"
    AST = "AST"
    CALLER = "CALLER"
    DEPENDENCY = "DEPENDENCY"
    IMPORT = "IMPORT"
    TEST = "TEST"
    DIFF = "DIFF"
    STATIC_ANALYSIS = "STATIC_ANALYSIS"
    RUNTIME = "RUNTIME"


class EvidenceItem(BaseModel):
    """Grounding evidence item verifying a finding against real repository code."""

    type: EvidenceType = Field(..., description="Evidence type: CODE, AST, CALLER, DEPENDENCY, IMPORT, TEST, DIFF, STATIC_ANALYSIS, RUNTIME")
    file: str = Field(..., description="Repository relative file path where evidence exists")
    line_start: int | None = Field(default=None, description="Starting line number of the grounded code/symbol")
    line_end: int | None = Field(default=None, description="Ending line number of the grounded code/symbol")
    symbol: str | None = Field(default=None, description="Symbol name involved in the evidence if applicable")
    description: str = Field(..., description="Concise explanation of how this evidence demonstrates the issue")


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


class ReviewFinding(BaseModel):
    """Strict structured review finding model produced by AI specialists and Adversarial Judge."""

    finding_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    file_path: str = Field(..., description="File path within the repository where the finding applies")
    line_number: int = Field(..., description="Specific line number in the diff where the issue is located")
    side: str = Field(default="RIGHT", description="Diff side: RIGHT (head additions/context) or LEFT (base deletions)")
    start_line: int | None = Field(default=None, description="Optional multi-line start line")
    start_side: str | None = Field(default=None, description="Optional multi-line start side")

    category: FindingCategory = Field(..., description="Category: SECURITY, BUG, ERROR_HANDLING, TEST_COVERAGE, CONTRACT, PERFORMANCE")
    severity: FindingSeverity = Field(..., description="Severity: CRITICAL, HIGH, MEDIUM, LOW, ADVISORY")
    original_severity: str | None = Field(default=None, description="Initial severity before judge review")
    final_severity: str | None = Field(default=None, description="Final severity normalized by judge")

    title: str = Field(..., description="Concise, one-sentence headline of the issue")
    description: str = Field(..., description="Detailed explanation of the issue grounded in repository code")
    impact: str = Field(..., description="Concrete operational, security, or architectural impact")
    recommendation: str = Field(..., description="Actionable recommendation on how to fix or address the issue")

    confidence: float = Field(default=0.9, ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    specialist_confidence: float = Field(default=0.9, ge=0.0, le=1.0, description="Confidence assigned by specialist agent")
    judge_confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="Confidence assigned by judge")
    final_confidence: float = Field(default=0.9, ge=0.0, le=1.0, description="Audited combined confidence")

    evidence: list[EvidenceItem] = Field(default_factory=list, description="Grounding evidence list from repository code")

    affected_symbol: str | None = Field(default=None, description="Name of the function, class, or method containing the issue")
    related_files: list[str] = Field(default_factory=list, description="Other repository files relevant to the issue")
    related_symbols: list[str] = Field(default_factory=list, description="Other symbols referenced in or affected by the issue")

    agent_name: str = Field(default="", description="Name of the specialist agent that produced this finding")
    source_agents: list[str] = Field(default_factory=list, description="All agents that reported this issue (provenance)")
    duplicate_of: str | None = Field(default=None, description="ID of canonical finding if deduplicated")
    root_cause_id: str | None = Field(default=None, description="Identifier for grouped root cause")
    finding_group_id: str | None = Field(default=None, description="Identifier for symptom group")

    status: FindingStatus = Field(default=FindingStatus.CANDIDATE)
    validation_notes: str | None = Field(default=None, description="Notes from deterministic validation stage")


class SpecialistFindingsOutput(BaseModel):
    """Structured response schema requested from all specialist review agents."""

    findings: list[ReviewFinding] = Field(
        default_factory=list,
        description="List of verified findings. Must be empty if code is safe or no issue is grounded in code.",
    )
    analysis_summary: str = Field(
        default="Analysis completed.",
        description="Brief high-level summary of what was analyzed and whether issues were found.",
    )
    has_findings: bool = Field(
        default=False,
        description="True if one or more valid findings are present, False if NO_FINDING.",
    )
