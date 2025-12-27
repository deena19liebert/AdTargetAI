"""add_performance_indexes

Revision ID: 09c235a5a95b
Revises: ca5315e446bb
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '09c235a5a95b'  # ✅ THIS LINE IS REQUIRED
down_revision = None  # or '<previous_revision_id>'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Campaign indexes
    op.create_index('ix_campaigns_status', 'campaigns', ['status'])
    op.create_index('ix_campaigns_generated_at', 'campaigns', ['generated_at'])
    
    # Platform feed indexes
    op.create_index('ix_platform_feeds_export_status', 'platform_feeds', ['export_status'])
    op.create_index('ix_platform_feeds_platform', 'platform_feeds', ['platform'])
    
    # Export log indexes
    op.create_index('ix_export_logs_created_at', 'export_logs', ['created_at'])
    op.create_index('ix_export_logs_success', 'export_logs', ['success'])
    
    # Composite indexes for common queries
    op.create_index(
        'ix_platform_feeds_campaign_platform',
        'platform_feeds',
        ['campaign_id', 'platform']
    )

def downgrade() -> None:
    op.drop_index('ix_campaigns_status')
    op.drop_index('ix_campaigns_generated_at')
    op.drop_index('ix_platform_feeds_export_status')
    op.drop_index('ix_platform_feeds_platform')
    op.drop_index('ix_export_logs_created_at')
    op.drop_index('ix_export_logs_success')
    op.drop_index('ix_platform_feeds_campaign_platform')