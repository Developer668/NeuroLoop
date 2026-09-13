"""Persist separately attributed notebook evidence without changing run decisions."""
from alembic import op
import sqlalchemy as sa
revision = "20260913_02"
down_revision = "20260912_01"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("notebook_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("input_asset_id", sa.String(36), sa.ForeignKey("creative_assets.id"), nullable=False),
        sa.Column("source_receipt", sa.String(300), nullable=False, unique=True),
        sa.Column("source_kind", sa.String(40), nullable=False),
        sa.Column("title", sa.String(250), nullable=False),
        sa.Column("evaluator", sa.String(40), nullable=False),
        sa.Column("comparison_key", sa.String(64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False))
    op.create_index("ix_notebook_evidence_campaign_id", "notebook_evidence", ["campaign_id"])
    op.create_index("ix_notebook_evidence_input_asset_id", "notebook_evidence", ["input_asset_id"])

def downgrade():
    op.drop_table("notebook_evidence")
