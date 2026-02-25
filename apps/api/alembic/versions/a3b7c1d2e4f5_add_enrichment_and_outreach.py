"""add_enrichment_and_outreach

Revision ID: a3b7c1d2e4f5
Revises: 9596a6cf36e6
Create Date: 2026-02-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a3b7c1d2e4f5'
down_revision: Union[str, None] = '9596a6cf36e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Contact enrichment fields ---
    op.add_column('contacts', sa.Column('facebook_url', sa.String(), nullable=True))
    op.add_column('contacts', sa.Column('is_principal_owner', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('contacts', sa.Column('enrichment_status', sa.String(length=20), nullable=True))
    op.add_column('contacts', sa.Column('enrichment_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('contacts', sa.Column('enrichment_source', sa.String(length=20), nullable=True))
    op.add_column('contacts', sa.Column('enriched_at', sa.DateTime(), nullable=True))

    # --- Outreach campaigns ---
    op.create_table('outreach_campaigns',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=300), nullable=False),
        sa.Column('subject_template', sa.Text(), nullable=False),
        sa.Column('body_prompt', sa.Text(), nullable=False),
        sa.Column('sender_email', sa.String(), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='draft', nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_outreach_campaigns_project_id'), 'outreach_campaigns', ['project_id'], unique=False)

    # --- Outreach emails ---
    op.create_table('outreach_emails',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('campaign_id', sa.Uuid(), nullable=False),
        sa.Column('contact_id', sa.Uuid(), nullable=False),
        sa.Column('company_id', sa.Uuid(), nullable=False),
        sa.Column('to_email', sa.String(), nullable=False),
        sa.Column('subject', sa.String(), nullable=False),
        sa.Column('body_html', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='draft', nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('gmail_message_id', sa.String(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['outreach_campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_outreach_emails_campaign_id'), 'outreach_emails', ['campaign_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_outreach_emails_campaign_id'), table_name='outreach_emails')
    op.drop_table('outreach_emails')
    op.drop_index(op.f('ix_outreach_campaigns_project_id'), table_name='outreach_campaigns')
    op.drop_table('outreach_campaigns')
    op.drop_column('contacts', 'enriched_at')
    op.drop_column('contacts', 'enrichment_source')
    op.drop_column('contacts', 'enrichment_data')
    op.drop_column('contacts', 'enrichment_status')
    op.drop_column('contacts', 'is_principal_owner')
    op.drop_column('contacts', 'facebook_url')
