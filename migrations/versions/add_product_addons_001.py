"""Add product addon groups/options and cart/order item addon tables.

Revision ID: add_product_addons_001
Revises: add_free_delivery_enabled_001
Create Date: 2026-08-21
"""

from alembic import op
import sqlalchemy as sa


revision = "add_product_addons_001"
down_revision = "add_free_delivery_enabled_001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "product_addon_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_product_addon_groups_product_id", "product_addon_groups", ["product_id"])

    op.create_table(
        "product_addon_options",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("product_addon_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("stock_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("image_filename", sa.String(length=255), nullable=True),
        sa.Column("image_public_id", sa.String(length=255), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "show_in_you_may_also_like",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_product_addon_options_group_id", "product_addon_options", ["group_id"])

    op.create_table(
        "cart_item_addons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "cart_item_id",
            sa.Integer(),
            sa.ForeignKey("cart_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "addon_option_id",
            sa.Integer(),
            sa.ForeignKey("product_addon_options.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "cart_item_id",
            "addon_option_id",
            name="unique_cart_item_addon_option",
        ),
    )

    op.create_table(
        "order_item_addons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "order_item_id",
            sa.Integer(),
            sa.ForeignKey("order_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "addon_option_id",
            sa.Integer(),
            sa.ForeignKey("product_addon_options.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("image_url", sa.String(length=500), nullable=True),
    )


def downgrade():
    op.drop_table("order_item_addons")
    op.drop_table("cart_item_addons")
    op.drop_index("ix_product_addon_options_group_id", table_name="product_addon_options")
    op.drop_table("product_addon_options")
    op.drop_index("ix_product_addon_groups_product_id", table_name="product_addon_groups")
    op.drop_table("product_addon_groups")
