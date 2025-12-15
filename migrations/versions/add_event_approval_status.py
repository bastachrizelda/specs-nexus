"""Add approval_status and decline_reason to events

This migration is written to work across DB backends.

Revision ID: add_event_approval_status
Revises: 303f1350b778
Create Date: 2025-12-01 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = 'add_event_approval_status'
down_revision: Union[str, None] = '303f1350b778'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Add approval_status and decline_reason columns to events table."""

    bind = op.get_bind()
    dialect = bind.dialect.name
    inspector = inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("events")}

    if "approval_status" not in existing_cols:
        if dialect == "postgresql":
            op.execute(
                """
                DO $$ BEGIN
                    CREATE TYPE event_approval_status AS ENUM ('pending', 'approved', 'declined');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
                """
            )
            from sqlalchemy.dialects.postgresql import ENUM as PGEnum

            approval_enum = PGEnum(
                "pending",
                "approved",
                "declined",
                name="event_approval_status",
                create_type=False,
            )
            op.add_column(
                "events",
                sa.Column(
                    "approval_status",
                    approval_enum,
                    nullable=True,
                    server_default=sa.text("'pending'"),
                ),
            )
        else:
            approval_enum = sa.Enum(
                "pending",
                "approved",
                "declined",
                name="event_approval_status",
            )
            op.add_column(
                "events",
                sa.Column(
                    "approval_status",
                    approval_enum,
                    nullable=True,
                    server_default="pending",
                ),
            )

    if "decline_reason" not in existing_cols:
        op.add_column("events", sa.Column("decline_reason", sa.String(length=500), nullable=True))

    op.execute("UPDATE events SET approval_status = 'approved' WHERE approval_status IS NULL")


def downgrade() -> None:
    """Remove approval_status and decline_reason columns from events table."""
    bind = op.get_bind()
    dialect = bind.dialect.name
    inspector = inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("events")}

    if "decline_reason" in existing_cols:
        op.drop_column("events", "decline_reason")

    if "approval_status" in existing_cols:
        op.drop_column("events", "approval_status")

    if dialect == "postgresql":
        op.execute("DROP TYPE IF EXISTS event_approval_status")

