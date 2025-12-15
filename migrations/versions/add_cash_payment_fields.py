"""Add cash payment verification fields

Revision ID: add_cash_payment_fields
Revises: add_reference_number
Create Date: 2025-12-15

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'add_cash_payment_fields'
down_revision = ('add_reference_number', 'add_event_attendance')
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    existing_cols = {c["name"] for c in inspector.get_columns("clearances")}

    if "receipt_number" not in existing_cols:
        op.add_column("clearances", sa.Column("receipt_number", sa.String(length=100), nullable=True))

    if "verified_by" not in existing_cols:
        op.add_column("clearances", sa.Column("verified_by", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_clearances_verified_by_officers",
            "clearances",
            "officers",
            ["verified_by"],
            ["id"],
        )

    if "verified_at" not in existing_cols:
        op.add_column("clearances", sa.Column("verified_at", sa.DateTime(), nullable=True))

    existing_uq = {uc["name"] for uc in inspector.get_unique_constraints("clearances") if uc.get("name")}
    if "uq_clearances_receipt_number" not in existing_uq:
        op.create_unique_constraint(
            "uq_clearances_receipt_number",
            "clearances",
            ["receipt_number"],
        )

    # Expand payment_status enum in Postgres if needed.
    # Note: this is a best-effort, idempotent approach.
    try:
        op.execute("ALTER TYPE payment_status ADD VALUE IF NOT EXISTS 'Pending'")
    except Exception:
        pass
    try:
        op.execute("ALTER TYPE payment_status ADD VALUE IF NOT EXISTS 'Rejected'")
    except Exception:
        pass


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    existing_uq = {uc["name"] for uc in inspector.get_unique_constraints("clearances") if uc.get("name")}
    if "uq_clearances_receipt_number" in existing_uq:
        op.drop_constraint("uq_clearances_receipt_number", "clearances", type_="unique")

    existing_fks = {fk.get("name") for fk in inspector.get_foreign_keys("clearances") if fk.get("name")}
    if "fk_clearances_verified_by_officers" in existing_fks:
        op.drop_constraint("fk_clearances_verified_by_officers", "clearances", type_="foreignkey")

    existing_cols = {c["name"] for c in inspector.get_columns("clearances")}
    if "verified_at" in existing_cols:
        op.drop_column("clearances", "verified_at")
    if "verified_by" in existing_cols:
        op.drop_column("clearances", "verified_by")
    if "receipt_number" in existing_cols:
        op.drop_column("clearances", "receipt_number")
