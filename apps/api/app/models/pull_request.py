"""PullRequest ORM model."""

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.repository import Repository
    from app.models.review_job import ReviewJob


class PullRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """GitHub Pull Request tracked by CodeGuard."""

    __tablename__ = "pull_requests"

    repository_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), index=True, nullable=False
    )
    github_pr_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, index=True, nullable=False
    )
    number: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    title: Mapped[str] = mapped_column(
        String(512), nullable=False
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    author_login: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    base_sha: Mapped[str] = mapped_column(
        String(40), nullable=False
    )
    head_sha: Mapped[str] = mapped_column(
        String(40), nullable=False
    )
    state: Mapped[str] = mapped_column(
        String(50), default="open", index=True, nullable=False
    )
    is_draft: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Relationships
    repository: Mapped["Repository"] = relationship(
        "Repository", back_populates="pull_requests"
    )
    review_jobs: Mapped[list["ReviewJob"]] = relationship(
        "ReviewJob", back_populates="pull_request", cascade="all, delete-orphan", order_by="desc(ReviewJob.created_at)"
    )

    __table_args__ = (
        Index("ix_pull_requests_repo_number", "repository_id", "number"),
    )
