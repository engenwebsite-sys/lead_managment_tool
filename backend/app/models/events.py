
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class Event(Base):
    __tablename__ = "events"

    __table_args__ = (
        Index("ix_events_start_at", "start_at"),
        Index("ix_events_status_start", "status", "start_at"),
        CheckConstraint(
            "status IN ('Planned', 'Ongoing', 'Completed', 'Cancelled')",
            name="ck_events_status",
        ),
        CheckConstraint(
            "end_at > start_at",
            name="ck_events_end_after_start",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        default="",
    )

    event_type: Mapped[str] = mapped_column(
        String(50),
        default="Other",
    )

    start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    venue: Mapped[str] = mapped_column(
        String(250),
        default="",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="Planned",
        index=True,
    )

    # Reminder offsets in minutes.
    # Example: [10080, 1440, 60]
    # 1 week, 1 day, 1 hour before.
    reminder_minutes: Mapped[list] = mapped_column(
        JSON,
        default=lambda: [1440, 60],
        nullable=False,
    )

    created_by: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class EventAssignment(Base):
    __tablename__ = "event_assignments"

    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "user_id",
            name="uq_event_assignment_user",
        ),
        Index("ix_event_assignments_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    event_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    attendance_status: Mapped[str] = mapped_column(
        String(20),
        default="Pending",
    )

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
