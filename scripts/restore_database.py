"""
eFlora Database Restore Utility (Railway)
-----------------------------------------
Restores a generated SQL backup file into a target PostgreSQL database.

Usage:
    python scripts/restore_database.py <path_to_backup_file.sql>
"""

import os
import sys
import psycopg2

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT_DIR, '.env'))
except Exception:
    pass


def run_restore(backup_file):
    if not os.path.exists(backup_file):
        print(f"[ERROR] Backup file not found: {backup_file}")
        sys.exit(1)

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("[ERROR] DATABASE_URL is not set.")
        sys.exit(1)

    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    print("=" * 60)
    print(" eFlora — Database Restore Utility")
    print(f" Target File: {backup_file}")
    print("=" * 60)

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
    except Exception as e:
        print(f"[ERROR] Could not connect to database: {e}")
        sys.exit(1)

    with open(backup_file, 'r', encoding='utf-8') as f:
        sql = f.read()

    print("Executing restore SQL statements...")
    try:
        cur.execute(sql)
        conn.commit()
        print("[SUCCESS] Database restored successfully!")
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Restore failed: {e}")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/restore_database.py backups/<backup_file.sql>")
        sys.exit(1)
    run_restore(sys.argv[1])
