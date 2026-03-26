"""rider_otps_verification_token

Revision ID: 371af7b5640f
Revises: fd93ea55a6ab
Create Date: 2026-03-26 15:23:05.660859

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '371af7b5640f'
down_revision = 'fd93ea55a6ab'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('rider_otps', schema=None) as batch_op:
        batch_op.add_column(sa.Column('verification_token', sa.String(length=64), nullable=True))
        batch_op.drop_column('otp_code')
        batch_op.drop_column('attempts')

    # Backfill any existing rows with a placeholder token, then make NOT NULL
    op.execute("UPDATE rider_otps SET verification_token = 'migrated_' || id WHERE verification_token IS NULL")

    with op.batch_alter_table('rider_otps', schema=None) as batch_op:
        batch_op.alter_column('verification_token', nullable=False)
        batch_op.create_index(batch_op.f('ix_rider_otps_verification_token'), ['verification_token'], unique=True)


def downgrade():
    with op.batch_alter_table('rider_otps', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_rider_otps_verification_token'))
        batch_op.drop_column('verification_token')
        batch_op.add_column(sa.Column('otp_code', sa.VARCHAR(length=6), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('attempts', sa.INTEGER(), autoincrement=False, nullable=True))
