"""Add cancellation reason columns to orders."""
from alembic import op
import sqlalchemy as sa


revision = 'add_order_cancel_reason_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'orders' not in inspector.get_table_names():
        return
    cols = {c['name'] for c in inspector.get_columns('orders')}
    if 'cancellation_reason_code' not in cols:
        op.add_column('orders', sa.Column('cancellation_reason_code', sa.String(length=50), nullable=True))
    if 'cancellation_reason' not in cols:
        op.add_column('orders', sa.Column('cancellation_reason', sa.Text(), nullable=True))
    if 'cancelled_at' not in cols:
        op.add_column('orders', sa.Column('cancelled_at', sa.DateTime(), nullable=True))


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'orders' not in inspector.get_table_names():
        return
    cols = {c['name'] for c in inspector.get_columns('orders')}
    if 'cancelled_at' in cols:
        op.drop_column('orders', 'cancelled_at')
    if 'cancellation_reason' in cols:
        op.drop_column('orders', 'cancellation_reason')
    if 'cancellation_reason_code' in cols:
        op.drop_column('orders', 'cancellation_reason_code')
