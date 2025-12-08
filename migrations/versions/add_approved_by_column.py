"""Add approved_by column to clearances table

Revision ID: add_approved_by
Revises: add_event_approval_status
Create Date: 2024-12-08

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_approved_by'
down_revision = 'add_event_approval_status'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('clearances', sa.Column('approved_by', sa.String(255), nullable=True))


def downgrade():
    op.drop_column('clearances', 'approved_by')
