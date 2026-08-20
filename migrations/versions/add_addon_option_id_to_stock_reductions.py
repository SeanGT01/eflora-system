"""Add addon_option_id to stock_reductions for add-on stock audit.

Revision ID: add_addon_option_stock_reductions_001
Revises: add_product_addons_001
Create Date: 2026-08-21
"""

from alembic import op
import sqlalchemy as sa


revision = "add_addon_option_stock_reductions_001"
down_revision = "add_product_addons_001"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("stock_reductions")]

    if "addon_option_id" not in columns:
        op.add_column(
            "stock_reductions",
            sa.Column("addon_option_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_stock_reductions_addon_option_id",
            "stock_reductions",
            "product_addon_options",
            ["addon_option_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            "ix_stock_reductions_addon_option_id",
            "stock_reductions",
            ["addon_option_id"],
        )


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("stock_reductions")]

    if "addon_option_id" in columns:
        op.drop_index("ix_stock_reductions_addon_option_id", table_name="stock_reductions")
        op.drop_constraint(
            "fk_stock_reductions_addon_option_id",
            "stock_reductions",
            type_="foreignkey",
        )
        op.drop_column("stock_reductions", "addon_option_id")
