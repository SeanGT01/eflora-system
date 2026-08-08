"""add password_reset_otps table

Revision ID: add_password_reset_otps_001
Revises:
Create Date: 2026-08-08 20:20:00.000000

NOTE
----
Apply out-of-band when Alembic heads are tangled — see apply_password_reset_otps.py.
The API also auto-creates the table via _ensure_password_reset_otps_table().
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_password_reset_otps_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'password_reset_otps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=False),
        sa.Column('otp_hash', sa.String(length=255), nullable=False),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('last_sent_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email', name='uq_password_reset_otps_email'),
    )
    op.create_index('ix_password_reset_otps_email', 'password_reset_otps', ['email'], unique=False)


def downgrade():
    op.drop_index('ix_password_reset_otps_email', table_name='password_reset_otps')
    op.drop_table('password_reset_otps')
