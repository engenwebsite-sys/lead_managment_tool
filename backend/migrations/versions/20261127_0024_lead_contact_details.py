"""Add optional lead email and phone without changing existing contact names."""
import sqlalchemy as sa
from alembic import op

revision = "20261127_0024"
down_revision = "20261127_0023"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("leads", sa.Column("contact_email", sa.String(254), nullable=False, server_default=""))
    op.add_column("leads", sa.Column("contact_phone", sa.String(40), nullable=False, server_default=""))


def downgrade():
    with op.batch_alter_table("leads") as batch:
        batch.drop_column("contact_phone")
        batch.drop_column("contact_email")
