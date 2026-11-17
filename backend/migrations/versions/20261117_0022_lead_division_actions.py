"""Add per-division lead editing and deletion grants for Staff."""

import sqlalchemy as sa
from alembic import op

revision = "20261117_0022"
down_revision = "20261117_0021"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("lead_actions", sa.JSON(), nullable=False, server_default="{}"))


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_column("lead_actions")
