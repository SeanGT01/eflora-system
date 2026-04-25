"""Create the customer_otps table.

Idempotent helper that mirrors apply_chat_reply_delete.py — useful when the
Alembic head graph is tangled (multiple branches) and you just need the table
created on Railway / production.

Usage:
    python apply_customer_otps.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from app.extensions import db
from sqlalchemy import text


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS customer_otps (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(120)  NOT NULL,
    otp_hash        VARCHAR(255)  NOT NULL,
    customer_data   JSON          NOT NULL,
    is_verified     BOOLEAN       NOT NULL DEFAULT FALSE,
    attempts        INTEGER       NOT NULL DEFAULT 0,
    expires_at      TIMESTAMP     NOT NULL,
    last_sent_at    TIMESTAMP     NOT NULL DEFAULT NOW(),
    verified_at     TIMESTAMP,
    created_at      TIMESTAMP     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_customer_otps_email UNIQUE (email)
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_customer_otps_email ON customer_otps (email);
"""


def main():
    app = create_app()
    with app.app_context():
        with db.engine.connect() as conn:
            conn.execute(text(CREATE_TABLE_SQL))
            conn.execute(text(CREATE_INDEX_SQL))
            conn.commit()
        print("[OK] customer_otps table is ready (created or already existed).")


if __name__ == "__main__":
    main()
