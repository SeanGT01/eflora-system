"""Add store toggle to disable free-delivery minimum.

Revision ID: add_free_delivery_enabled_001
Revises: add_store_banner_columns_001
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa


revision = "add_free_delivery_enabled_001"
down_revision = "add_store_banner_columns_001"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("stores") as batch_op:
        batch_op.add_column(
            sa.Column(
                "free_delivery_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            )
        )


def downgrade():
    with op.batch_alter_table("stores") as batch_op:
        batch_op.drop_column("free_delivery_enabled")
