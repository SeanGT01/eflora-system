"""Add home_page_testimonials for public landing-page reviews

Revision ID: add_home_page_testimonials_001
Revises: add_special_price_001
Create Date: 2026-04-26

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_home_page_testimonials_001'
down_revision = 'add_special_price_001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'home_page_testimonials',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, primary_key=True),
        sa.Column('customer_name', sa.String(length=120), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=False),
        sa.Column('is_approved', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index(
        'ix_home_page_testimonials_created_at',
        'home_page_testimonials',
        ['created_at'],
        unique=False,
    )


def downgrade():
    op.drop_index('ix_home_page_testimonials_created_at', table_name='home_page_testimonials')
    op.drop_table('home_page_testimonials')
