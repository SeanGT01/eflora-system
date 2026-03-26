"""add rider_otps table

Revision ID: fd93ea55a6ab
Revises: add_delivery_date_time_001
Create Date: 2026-03-26 14:28:03.791260

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'fd93ea55a6ab'
down_revision = 'add_delivery_date_time_001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('rider_otps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=False),
        sa.Column('otp_code', sa.String(length=6), nullable=False),
        sa.Column('rider_data', sa.JSON(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('is_verified', sa.Boolean(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_rider_otps_email', 'rider_otps', ['email'], unique=False)


def downgrade():
    op.drop_index('ix_rider_otps_email', table_name='rider_otps')
    op.drop_table('rider_otps')
