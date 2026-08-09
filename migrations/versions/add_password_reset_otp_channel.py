"""Add otp_channel to password_reset_otps

Revision ID: add_password_reset_otp_channel
Revises: add_password_reset_otps_table
Create Date: 2026-08-09
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_password_reset_otp_channel'
down_revision = 'add_password_reset_otps_001'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('password_reset_otps') as batch:
        batch.add_column(
            sa.Column('otp_channel', sa.String(length=10), nullable=False, server_default='email')
        )


def downgrade():
    with op.batch_alter_table('password_reset_otps') as batch:
        batch.drop_column('otp_channel')
