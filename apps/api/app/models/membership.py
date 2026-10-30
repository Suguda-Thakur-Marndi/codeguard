"""User-Organization membership ORM model."""

from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User


class MembershipRole(StrEnum):
    """Membership access roles."""

    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"
    REVIEWER = "REVIEWER"


class MembershipStatus(StrEnum):
    """Membership lifecycle statuses."""

    ACTIVE = "ACTIVE"
    INVITED = "INVITED"
    SUSPENDED = "SUSPENDED"


class UserOrganizationMembership(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Association table linking users and organizations with explicit role and status."""

    __tablename__ = "user_organization_memberships"

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(50),
        default=MembershipRole.MEMBER.value,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default=MembershipStatus.ACTIVE.value,
        index=True,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "organization_id", name="uq_user_organization_membership"
        ),
        Index("ix_membership_user_org_status", "user_id", "organization_id", "status"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="memberships")
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="memberships"
    )
