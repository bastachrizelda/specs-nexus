"""Add event attendance table

Revision ID: add_event_attendance
Revises: add_event_approval_status
Create Date: 2025-12-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_event_attendance'
down_revision: Union[str, None] = 'add_event_approval_status'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create event_attendance table for tracking QR code check-ins."""
    op.create_table(
        'event_attendance',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('checked_in_at', sa.DateTime(), nullable=True),
        sa.Column('checked_in_by', sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', 'user_id', name='uq_event_attendance_event_user')
    )
    op.create_index(op.f('ix_event_attendance_id'), 'event_attendance', ['id'], unique=False)


def downgrade() -> None:
    """Drop event_attendance table."""
    op.drop_index(op.f('ix_event_attendance_id'), table_name='event_attendance')
    op.drop_table('event_attendance')
