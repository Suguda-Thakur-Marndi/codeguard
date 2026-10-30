"""Organization ORM model."""

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.membership import UserOrganizationMembership
    from app.models.repository import Repository


class Organization(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """GitHub organization or account installation."""

    __tablename__ = "organizations"

    github_installation_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, index=True, nullable=False
    )
    github_account_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False
    )
    github_account_login: Mapped[str] = mapped_column(
        String(255), index=True, nullable=False
    )
    account_type: Mapped[str] = mapped_column(
        String(50), default="Organization", nullable=False
    )

    # Relationships
    repositories: Mapped[list["Repository"]] = relationship(
        "Repository", back_populates="organization", cascade="all, delete-orphan"
    )
    memberships: Mapped[list["UserOrganizationMembership"]] = relationship(
        "UserOrganizationMembership", back_populates="organization", cascade="all, delete-orphan"
    )
