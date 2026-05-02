"""Seller signup portal: OTP table, application source, nullable user_id.

Revision ID: seller_signup_portal_001
Revises: split_conversation_unique_001
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa

revision = "seller_signup_portal_001"
down_revision = "split_conversation_unique_001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "seller_signup_otps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=120), nullable=False),
        sa.Column("otp_hash", sa.String(length=255), nullable=False),
        sa.Column("signup_data", sa.JSON(), nullable=False),
        sa.Column(
            "is_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(), nullable=False),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_seller_signup_otps_email"),
    )
    op.create_index(
        "ix_seller_signup_otps_email", "seller_signup_otps", ["email"], unique=False
    )

    with op.batch_alter_table("seller_applications", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("applicant_full_name", sa.String(length=120), nullable=True)
        )
        batch_op.add_column(
            sa.Column("applicant_email", sa.String(length=120), nullable=True)
        )
        batch_op.add_column(sa.Column("applicant_phone", sa.String(length=20), nullable=True))
        batch_op.add_column(
            sa.Column(
                "application_source",
                sa.String(length=30),
                nullable=True,
                server_default="customer_account",
            )
        )
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=True)

    op.execute(
        """
        UPDATE seller_applications AS sa
        SET applicant_email = u.email,
            applicant_full_name = u.full_name,
            applicant_phone = u.phone,
            application_source = COALESCE(sa.application_source, 'customer_account')
        FROM users AS u
        WHERE sa.user_id = u.id
        """
    )


def downgrade():
    op.execute(
        """
        UPDATE seller_applications
        SET user_id = (
            SELECT id FROM users u WHERE u.email = seller_applications.applicant_email LIMIT 1
        )
        WHERE user_id IS NULL AND applicant_email IS NOT NULL
        """
    )

    with op.batch_alter_table("seller_applications", schema=None) as batch_op:
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("application_source")
        batch_op.drop_column("applicant_phone")
        batch_op.drop_column("applicant_email")
        batch_op.drop_column("applicant_full_name")

    op.drop_index("ix_seller_signup_otps_email", table_name="seller_signup_otps")
    op.drop_table("seller_signup_otps")
