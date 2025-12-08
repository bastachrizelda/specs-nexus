"""Add approval_status and decline_reason to events

Revision ID: add_event_approval
Revises: 303f1350b778
Create Date: 2025-12-01 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_event_approval'
down_revision: Union[str, None] = '303f1350b778'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add approval_status and decline_reason columns to events table."""
    # Create the enum type if it doesn't exist
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE event_approval_status AS ENUM ('pending', 'approved', 'declined');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Add approval_status column with default value
    op.execute("""
        ALTER TABLE events 
        ADD COLUMN IF NOT EXISTS approval_status event_approval_status DEFAULT 'pending';
    """)
    
    # Add decline_reason column
    op.execute("""
        ALTER TABLE events 
        ADD COLUMN IF NOT EXISTS decline_reason VARCHAR(500);
    """)
    
    # Update existing events to 'approved' status (assuming they were already visible)
    op.execute("""
        UPDATE events 
        SET approval_status = 'approved' 
        WHERE approval_status IS NULL;
    """)


def downgrade() -> None:
    """Remove approval_status and decline_reason columns from events table."""
    op.execute("ALTER TABLE events DROP COLUMN IF EXISTS decline_reason;")
    op.execute("ALTER TABLE events DROP COLUMN IF EXISTS approval_status;")
    op.execute("DROP TYPE IF EXISTS event_approval_status;")

