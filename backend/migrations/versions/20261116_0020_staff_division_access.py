"""Allow staff to view and add leads in multiple divisions."""

import sqlalchemy as sa
from alembic import op

revision = "20261116_0020"
down_revision = "20261116_0019"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("lead_division_access", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_column("lead_division_access")
