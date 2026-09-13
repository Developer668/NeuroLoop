"""Provider OAuth connections and immutable creative publishing receipts."""
from alembic import op
import sqlalchemy as sa

revision = "20260913_04"
down_revision = "20260913_03"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("ad_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(30), nullable=False, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("external_user_id", sa.String(200), nullable=True),
        sa.Column("display_name", sa.String(300), nullable=True),
        sa.Column("access_token_ciphertext", sa.Text(), nullable=False),
        sa.Column("refresh_token_ciphertext", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.Float(), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False))
    op.create_index("ix_ad_connections_provider", "ad_connections", ["provider"], unique=True)
    op.create_table("ad_oauth_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("state_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False))
    op.create_index("ix_ad_oauth_attempts_provider", "ad_oauth_attempts", ["provider"])
    op.create_table("ad_publications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("connection_id", sa.String(36), sa.ForeignKey("ad_connections.id"), nullable=False),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("asset_id", sa.String(36), sa.ForeignKey("creative_assets.id"), nullable=False),
        sa.Column("account_id", sa.String(200), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False, unique=True),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("remote", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False))
    op.create_index("ix_ad_publications_provider", "ad_publications", ["provider"])
    op.create_index("ix_ad_publications_connection_id", "ad_publications", ["connection_id"])
    op.create_index("ix_ad_publications_campaign_id", "ad_publications", ["campaign_id"])
    op.create_index("ix_ad_publications_asset_id", "ad_publications", ["asset_id"])
    op.create_index("ix_ad_publications_state", "ad_publications", ["state"])


def downgrade():
    op.drop_table("ad_publications")
    op.drop_table("ad_oauth_attempts")
    op.drop_table("ad_connections")
