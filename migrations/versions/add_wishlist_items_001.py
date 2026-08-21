"""Create wishlist_items table (safe if Alembic chain is broken)."""
from alembic import op
import sqlalchemy as sa


revision = 'add_wishlist_items_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'wishlist_items' in inspector.get_table_names():
        return
    op.create_table(
        'wishlist_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('variant_id', sa.Integer(), sa.ForeignKey('product_variants.id', ondelete='CASCADE'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_wishlist_items_user_id', 'wishlist_items', ['user_id'])
    op.create_index('ix_wishlist_items_product_id', 'wishlist_items', ['product_id'])
    op.create_index('ix_wishlist_items_variant_id', 'wishlist_items', ['variant_id'])


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'wishlist_items' not in inspector.get_table_names():
        return
    op.drop_index('ix_wishlist_items_variant_id', table_name='wishlist_items')
    op.drop_index('ix_wishlist_items_product_id', table_name='wishlist_items')
    op.drop_index('ix_wishlist_items_user_id', table_name='wishlist_items')
    op.drop_table('wishlist_items')
