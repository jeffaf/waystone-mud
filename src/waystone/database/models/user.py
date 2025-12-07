"""User model for Waystone MUD authentication and account management."""

import uuid
from typing import TYPE_CHECKING

import bcrypt
from sqlalchemy import Boolean, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .character import Character


class User(Base, TimestampMixin):
    """User account model for authentication and character management."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique user identifier",
    )

    username: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique username (3-20 characters)",
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="User email address",
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Bcrypt hashed password",
    )

    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
        comment="Whether user has admin privileges",
    )

    # Relationship to characters
    characters: Mapped[list["Character"]] = relationship(
        "Character",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """String representation of User."""
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"

    @classmethod
    def hash_password(cls, plain_password: str) -> str:
        """
        Hash a plain text password using bcrypt.

        Args:
            plain_password: The plain text password to hash

        Returns:
            The bcrypt hashed password as a string
        """
        password_bytes = plain_password.encode("utf-8")
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password_bytes, salt)
        return hashed.decode("utf-8")

    def verify_password(self, plain_password: str) -> bool:
        """
        Verify a plain text password against the stored hash.

        Args:
            plain_password: The plain text password to verify

        Returns:
            True if the password matches, False otherwise
        """
        password_bytes = plain_password.encode("utf-8")
        hash_bytes = self.password_hash.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hash_bytes)
