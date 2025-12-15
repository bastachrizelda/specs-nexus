"""Add reference_number to clearances

Revision ID: add_reference_number
Revises: add_approved_by
Create Date: 2025-12-13

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'add_reference_number'
down_revision = 'add_approved_by'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    existing_cols = {c["name"] for c in inspector.get_columns("clearances")}
    if "reference_number" not in existing_cols:
        op.add_column("clearances", sa.Column("reference_number", sa.String(length=100), nullable=True))

    existing_uq = {uc["name"] for uc in inspector.get_unique_constraints("clearances") if uc.get("name")}
    if "uq_clearances_payment_method_reference_number" not in existing_uq:
        op.create_unique_constraint(
            "uq_clearances_payment_method_reference_number",
            "clearances",
            ["payment_method", "reference_number"],
        )


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    existing_uq = {uc["name"] for uc in inspector.get_unique_constraints("clearances") if uc.get("name")}
    if "uq_clearances_payment_method_reference_number" in existing_uq:
        op.drop_constraint("uq_clearances_payment_method_reference_number", "clearances", type_="unique")

    existing_cols = {c["name"] for c in inspector.get_columns("clearances")}
    if "reference_number" in existing_cols:
        op.drop_column("clearances", "reference_number")
