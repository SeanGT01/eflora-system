"""merge_heads

Revision ID: bdc4653a5797
Revises: add_addon_option_stock_reductions_001, add_chat_reply_delete_001, add_chat_tables_001, add_customer_otps_001, add_keep_ymal_addons_when_unavailable, add_order_cancel_reason_001, add_password_reset_otp_channel, add_wishlist_items_001
Create Date: 2026-09-10 05:10:00.236270

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bdc4653a5797'
down_revision = ('add_addon_option_stock_reductions_001', 'add_chat_reply_delete_001', 'add_chat_tables_001', 'add_customer_otps_001', 'add_keep_ymal_addons_when_unavailable', 'add_order_cancel_reason_001', 'add_password_reset_otp_channel', 'add_wishlist_items_001')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
