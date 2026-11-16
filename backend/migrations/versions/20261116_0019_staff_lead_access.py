"""Store per-staff lead access and align calendar assignment timestamps."""

import sqlalchemy as sa
from alembic import op

revision = "20261116_0019"
down_revision = "20261111_0018"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("lead_division", sa.String(40), nullable=True))
    op.add_column("users", sa.Column("can_create_leads", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE event_assignments SET assigned_at = CURRENT_TIMESTAMP WHERE assigned_at IS NULL")
    with op.batch_alter_table("event_assignments") as batch:
        batch.alter_column("assigned_at", existing_type=sa.DateTime(timezone=True), nullable=False)


def downgrade():
    with op.batch_alter_table("event_assignments") as batch:
        batch.alter_column("assigned_at", existing_type=sa.DateTime(timezone=True), nullable=True)
    with op.batch_alter_table("users") as batch:
        batch.drop_column("can_create_leads")
        batch.drop_column("lead_division")
