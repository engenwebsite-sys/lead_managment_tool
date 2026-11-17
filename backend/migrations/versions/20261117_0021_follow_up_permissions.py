"""Add optional Staff permissions to edit and archive follow-ups."""

import sqlalchemy as sa
from alembic import op

revision = "20261117_0021"
down_revision = "20261116_0020"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("can_edit_follow_ups", "can_delete_follow_ups"):
        op.add_column("users", sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_column("can_edit_follow_ups")
        batch.drop_column("can_delete_follow_ups")
