"""Add store_ratings table for per-order store experience ratings.

Revision ID: add_store_ratings_001
Revises: seller_signup_portal_001
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa

revision = "add_store_ratings_001"
down_revision = "seller_signup_portal_001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "store_ratings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "customer_id", "order_id", name="unique_customer_order_store_rating"
        ),
    )


def downgrade():
    op.drop_table("store_ratings")
