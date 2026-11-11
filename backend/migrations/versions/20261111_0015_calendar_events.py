
"""Create Calendar and Events tables.

Revision ID: 20261111_0015
Revises: 20261106_0014
"""

from alembic import op
import sqlalchemy as sa


revision = "20261111_0015"
down_revision = "20261106_0014"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column(
            "start_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "end_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("venue", sa.String(length=250), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "reminder_minutes",
            sa.JSON(),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('Planned', 'Ongoing', 'Completed', 'Cancelled')",
            name="ck_events_status",
        ),
        sa.CheckConstraint(
            "end_at > start_at",
            name="ck_events_end_after_start",
        ),
    )

    op.create_index(
        "ix_events_start_at",
        "events",
        ["start_at"],
    )

    op.create_index(
        "ix_events_status_start",
        "events",
        ["status", "start_at"],
    )

    op.create_index(
        "ix_events_created_by",
        "events",
        ["created_by"],
    )

    op.create_table(
        "event_assignments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "attendance_status",
            sa.String(length=20),
            nullable=False,
        ),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "event_id",
            "user_id",
            name="uq_event_assignment_user",
        ),
    )

    op.create_index(
        "ix_event_assignments_event_id",
        "event_assignments",
        ["event_id"],
    )

    op.create_index(
        "ix_event_assignments_user",
        "event_assignments",
        ["user_id"],
    )


def downgrade():
    op.drop_index(
        "ix_event_assignments_user",
        table_name="event_assignments",
    )

    op.drop_index(
        "ix_event_assignments_event_id",
        table_name="event_assignments",
    )

    op.drop_table("event_assignments")

    op.drop_index(
        "ix_events_created_by",
        table_name="events",
    )

    op.drop_index(
        "ix_events_status_start",
        table_name="events",
    )

    op.drop_index(
        "ix_events_start_at",
        table_name="events",
    )

    op.drop_table("events")
