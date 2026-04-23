"""Add special_price to products and product_variants

Revision ID: add_special_price_001
Revises: add_variant_id_to_stock_reductions
Create Date: 2026-04-23 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_special_price_001'
down_revision = 'add_variant_id_to_stock_reductions'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.add_column(sa.Column('special_price', sa.Numeric(precision=10, scale=2), nullable=True))

    with op.batch_alter_table('product_variants', schema=None) as batch_op:
        batch_op.add_column(sa.Column('special_price', sa.Numeric(precision=10, scale=2), nullable=True))


def downgrade():
    with op.batch_alter_table('product_variants', schema=None) as batch_op:
        batch_op.drop_column('special_price')

    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_column('special_price')
