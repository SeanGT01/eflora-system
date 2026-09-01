"""Allow YMAL add-ons to stay listed when the source product is unavailable.

Revision ID: add_keep_ymal_addons_when_unavailable
Revises: add_product_addons_001
Create Date: 2026-09-01
"""

from alembic import op
import sqlalchemy as sa


revision = "add_keep_ymal_addons_when_unavailable"
down_revision = "add_product_addons_001"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("products") as batch_op:
        batch_op.add_column(
            sa.Column(
                "keep_ymal_addons_when_unavailable",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )


def downgrade():
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_column("keep_ymal_addons_when_unavailable")
