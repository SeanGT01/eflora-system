"""Add conversations and chat_messages tables

Revision ID: add_chat_tables_001
Revises: add_order_status_timestamps_001
Create Date: 2025-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_chat_tables_001'
down_revision = 'add_order_status_timestamps_001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('conversations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('seller_id', sa.Integer(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('last_message_text', sa.Text(), nullable=True),
        sa.Column('last_message_at', sa.DateTime(), nullable=True),
        sa.Column('last_sender_id', sa.Integer(), nullable=True),
        sa.Column('customer_unread', sa.Integer(), server_default='0', nullable=True),
        sa.Column('seller_unread', sa.Integer(), server_default='0', nullable=True),
        sa.Column('customer_deleted_at', sa.DateTime(), nullable=True),
        sa.Column('seller_deleted_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['seller_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('customer_id', 'store_id', name='unique_customer_store_conversation')
    )

    op.create_table('chat_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('sender_id', sa.Integer(), nullable=False),
        sa.Column('message_type', sa.String(length=20), server_default='text', nullable=True),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('image_url', sa.String(length=500), nullable=True),
        sa.Column('image_public_id', sa.String(length=255), nullable=True),
        sa.Column('is_read', sa.Boolean(), server_default='false', nullable=True),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sender_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Indexes for common queries
    op.create_index('ix_conversations_customer_id', 'conversations', ['customer_id'])
    op.create_index('ix_conversations_seller_id', 'conversations', ['seller_id'])
    op.create_index('ix_conversations_last_message_at', 'conversations', ['last_message_at'])
    op.create_index('ix_chat_messages_conversation_id', 'chat_messages', ['conversation_id'])
    op.create_index('ix_chat_messages_sender_id', 'chat_messages', ['sender_id'])
    op.create_index('ix_chat_messages_created_at', 'chat_messages', ['created_at'])


def downgrade():
    op.drop_index('ix_chat_messages_created_at', 'chat_messages')
    op.drop_index('ix_chat_messages_sender_id', 'chat_messages')
    op.drop_index('ix_chat_messages_conversation_id', 'chat_messages')
    op.drop_index('ix_conversations_last_message_at', 'conversations')
    op.drop_index('ix_conversations_seller_id', 'conversations')
    op.drop_index('ix_conversations_customer_id', 'conversations')
    op.drop_table('chat_messages')
    op.drop_table('conversations')
