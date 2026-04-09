"""Apply reply_to_id and is_deleted columns to chat_messages."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from app.extensions import db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS reply_to_id INTEGER REFERENCES chat_messages(id)"))
        conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT false"))
        conn.commit()
    print("✅ Added reply_to_id and is_deleted columns to chat_messages")
