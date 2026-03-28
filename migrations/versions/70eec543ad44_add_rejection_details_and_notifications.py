"""Add rejection_details and notifications

Revision ID: 70eec543ad44
Revises: 371af7b5640f
Create Date: 2026-03-28 18:15:41.980456

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '70eec543ad44'
down_revision = '371af7b5640f'
branch_labels = None
depends_on = None


def upgrade():
    # Create notifications table
    op.create_table('notifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('type', sa.String(length=50), nullable=False),
    sa.Column('reference_id', sa.Integer(), nullable=True),
    sa.Column('is_read', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    # Add rejection_details JSON column to seller_applications
    with op.batch_alter_table('seller_applications', schema=None) as batch_op:
        batch_op.add_column(sa.Column('rejection_details', postgresql.JSON(astext_type=sa.Text()), nullable=True))


def downgrade():
    with op.batch_alter_table('seller_applications', schema=None) as batch_op:
        batch_op.drop_column('rejection_details')

    op.drop_table('notifications')
