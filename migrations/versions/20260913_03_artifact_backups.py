"""Durable W&B artifact delivery receipts."""
from alembic import op
import sqlalchemy as sa
revision = "20260913_03"
down_revision = "20260913_02"
branch_labels = None
depends_on = None
def upgrade():
    op.create_table("artifact_backups",
        sa.Column("id",sa.String(100),primary_key=True),
        sa.Column("content_hash",sa.String(64),nullable=False),
        sa.Column("status",sa.String(30),nullable=False),
        sa.Column("url",sa.String(1000),nullable=True),
        sa.Column("error",sa.String(300),nullable=True),
        sa.Column("next_attempt",sa.Float(),nullable=False),
        sa.Column("updated_at",sa.Float(),nullable=False))
def downgrade():
    op.drop_table("artifact_backups")
