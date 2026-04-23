"""Add variant_id column to stock_reductions table

Revision ID: add_variant_id_stock_reductions_001
Revises: add_stock_reduction_001
Create Date: 2026-04-23 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_variant_id_stock_reductions_001'
down_revision = 'add_stock_reduction_001'
branch_labels = None
depends_on = None


def upgrade():
    # Check if the column already exists before adding it
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    columns = [c['name'] for c in inspector.get_columns('stock_reductions')]
    
    if 'variant_id' not in columns:
        op.add_column('stock_reductions',
            sa.Column('variant_id', sa.Integer(), nullable=True)
        )
        op.create_foreign_key(
            'fk_stock_reductions_variant_id',
            'stock_reductions', 'product_variants',
            ['variant_id'], ['id'],
            ondelete='SET NULL'
        )


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    columns = [c['name'] for c in inspector.get_columns('stock_reductions')]
    
    if 'variant_id' in columns:
        op.drop_constraint('fk_stock_reductions_variant_id', 'stock_reductions', type_='foreignkey')
        op.drop_column('stock_reductions', 'variant_id')
