"""Add reply_to_id and is_deleted to chat_messages

Revision ID: add_chat_reply_delete_001
Revises: add_chat_tables_001
Create Date: 2025-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_chat_reply_delete_001'
down_revision = None  # Run manually
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('chat_messages', sa.Column('reply_to_id', sa.Integer(), sa.ForeignKey('chat_messages.id'), nullable=True))
    op.add_column('chat_messages', sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False))


def downgrade():
    op.drop_column('chat_messages', 'is_deleted')
    op.drop_column('chat_messages', 'reply_to_id')
