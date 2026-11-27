"""Preserve opportunity history and support independent action assignments.

Existing rows are retained; NULL action assignments keep the legacy lead owner.
"""
import sqlalchemy as sa
from alembic import op

revision = "20261127_0023"
down_revision = "20261117_0022"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("leads", sa.Column("opportunity_name", sa.String(200), nullable=False, server_default=""))
    op.add_column("leads", sa.Column("history", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("leads", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("follow_ups") as batch:
        batch.add_column(sa.Column("assignee_user_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_follow_ups_assignee", "users", ["assignee_user_id"], ["id"], ondelete="RESTRICT")
        batch.create_index("ix_follow_ups_assignee_user_id", ["assignee_user_id"])


def downgrade():
    with op.batch_alter_table("follow_ups") as batch:
        batch.drop_index("ix_follow_ups_assignee_user_id")
        batch.drop_constraint("fk_follow_ups_assignee", type_="foreignkey")
        batch.drop_column("assignee_user_id")
    with op.batch_alter_table("leads") as batch:
        batch.drop_column("deleted_at")
        batch.drop_column("history")
        batch.drop_column("opportunity_name")
