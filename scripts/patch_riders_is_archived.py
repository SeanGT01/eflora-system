import os
import sqlite3

from dotenv import load_dotenv


def patch_postgres(db_url: str) -> None:
    import psycopg2

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "ALTER TABLE riders ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE"
            )
        conn.commit()
        print("Patched postgres: riders.is_archived")
    finally:
        conn.close()


def patch_sqlite(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cols = [row[1] for row in cur.execute("PRAGMA table_info(riders)").fetchall()]
        if "is_archived" not in cols:
            cur.execute("ALTER TABLE riders ADD COLUMN is_archived INTEGER NOT NULL DEFAULT 0")
            conn.commit()
            print("Patched sqlite: riders.is_archived")
        else:
            print("sqlite already has riders.is_archived")
    finally:
        conn.close()


def main() -> None:
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if db_url and db_url.startswith("postgres"):
        patch_postgres(db_url)
    else:
        patch_sqlite(os.path.join("app", "dev.db"))


if __name__ == "__main__":
    main()
