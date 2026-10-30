"""User ORM model."""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.membership import UserOrganizationMembership


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Registered application user identified via Google OAuth."""

    __tablename__ = "users"

    google_sub: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    picture: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    memberships: Mapped[list["UserOrganizationMembership"]] = relationship(
        "UserOrganizationMembership",
        back_populates="user",
        cascade="all, delete-orphan",
    )
