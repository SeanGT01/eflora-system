"""add customer_otps table

Revision ID: add_customer_otps_001
Revises:
Create Date: 2026-04-25 22:00:00.000000

NOTE
----
The existing migration tree has multiple heads (chat / order-status / OTP
branches). To avoid forcing a merge revision we leave `down_revision = None`
and apply this table out-of-band — the same pattern used by
`add_chat_reply_delete_001`. There is also an idempotent helper script at
`apply_customer_otps.py` for direct invocation.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_customer_otps_001'
down_revision = None  # Run manually — see apply_customer_otps.py
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'customer_otps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=False),
        sa.Column('otp_hash', sa.String(length=255), nullable=False),
        sa.Column('customer_data', sa.JSON(), nullable=False),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('last_sent_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email', name='uq_customer_otps_email'),
    )
    op.create_index('ix_customer_otps_email', 'customer_otps', ['email'], unique=False)


def downgrade():
    op.drop_index('ix_customer_otps_email', table_name='customer_otps')
    op.drop_table('customer_otps')
