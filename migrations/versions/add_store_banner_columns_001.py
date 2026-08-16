"""Add seller-managed storefront banner fields.

Revision ID: add_store_banner_columns_001
Revises: add_store_ratings_001
Create Date: 2026-08-16
"""

from alembic import op
import sqlalchemy as sa


revision = "add_store_banner_columns_001"
down_revision = "add_store_ratings_001"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("stores") as batch_op:
        batch_op.add_column(sa.Column("banner_url", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("banner_public_id", sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table("stores") as batch_op:
        batch_op.drop_column("banner_public_id")
        batch_op.drop_column("banner_url")
