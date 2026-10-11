"""
eFlora Database Backup Utility (Railway Hobby Plan)
---------------------------------------------------
Connects to the deployed Railway PostgreSQL database and generates
a complete, timestamped SQL backup file in the `backups/` directory.

Usage:
    python scripts/backup_database.py
"""

import os
import sys
import datetime
from urllib.parse import urlparse
import psycopg2
from psycopg2.extras import RealDictCursor

# Ensure project root is in sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT_DIR, '.env'))
except Exception:
    pass

# Exclude system/PostGIS spatial extension tables from dump
SYSTEM_TABLES = {
    'spatial_ref_sys', 'topology', 'layer', 'addr', 'geocode_settings',
    'geocode_settings_default', 'direction_lookup', 'secondary_unit_lookup',
    'state_lookup', 'street_type_lookup', 'place_lookup', 'county_lookup',
    'countysub_lookup', 'zip_lookup_all', 'zip_lookup_base', 'zip_lookup',
    'county', 'state', 'place', 'zip_state', 'zip_state_loc', 'cousub',
    'edges', 'addrfeat', 'zcta5', 'tabblock20', 'faces', 'loader_platform',
    'loader_variables', 'loader_lookuptables', 'tract', 'tabblock', 'bg',
    'pagc_gaz', 'pagc_lex', 'pagc_rules', 'featnames'
}


def get_database_url():
    url = os.getenv("DATABASE_URL")
    if not url:
        # Fallback to config if available
        try:
            from app.config import Config
            url = getattr(Config, 'DATABASE_URL', None) or getattr(Config, 'SQLALCHEMY_DATABASE_URI', None)
        except Exception:
            pass
    return url


def run_backup():
    db_url = get_database_url()
    if not db_url:
        print("[ERROR] DATABASE_URL is not set in environment or .env file.")
        sys.exit(1)

    print("=" * 60)
    print(" eFlora — Database Backup Utility (Railway)")
    print("=" * 60)

    # Normalize url if needed
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    parsed = urlparse(db_url)
    print(f"Connecting to database at {parsed.hostname}:{parsed.port}/{parsed.path.lstrip('/')}...")

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor(cursor_factory=RealDictCursor)
    except Exception as e:
        print(f"[ERROR] Failed to connect to database: {e}")
        sys.exit(1)

    # Ensure backup directory exists
    backup_dir = os.path.join(ROOT_DIR, "backups")
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"eflora_backup_{timestamp}.sql")

    # Fetch list of application tables in public schema
    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name;
    """)
    all_tables = [row['table_name'] for row in cur.fetchall()]
    app_tables = [t for t in all_tables if t not in SYSTEM_TABLES]

    print(f"Found {len(app_tables)} application tables to backup.")

    with open(backup_file, 'w', encoding='utf-8') as f:
        f.write(f"-- ============================================================\n")
        f.write(f"-- eFlora Database Backup\n")
        f.write(f"-- Created: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"-- Host: {parsed.hostname}\n")
        f.write(f"-- Database: {parsed.path.lstrip('/')}\n")
        f.write(f"-- Total Tables: {len(app_tables)}\n")
        f.write(f"-- ============================================================\n\n")
        f.write("BEGIN;\n\n")

        total_rows_backed_up = 0

        for table in app_tables:
            # Get column info
            cur.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position;
            """, (table,))
            columns = cur.fetchall()
            col_names = [col['column_name'] for col in columns]

            # Fetch all rows
            cur.execute(f'SELECT * FROM "{table}";')
            rows = cur.fetchall()
            total_rows_backed_up += len(rows)

            f.write(f"-- Table: {table} ({len(rows)} records)\n")
            if rows:
                cols_str = ', '.join([f'"{c}"' for c in col_names])
                for r in rows:
                    values = []
                    for c in col_names:
                        val = r[c]
                        if val is None:
                            values.append("NULL")
                        elif isinstance(val, (int, float)):
                            values.append(str(val))
                        elif isinstance(val, bool):
                            values.append("TRUE" if val else "FALSE")
                        elif isinstance(val, (datetime.datetime, datetime.date, datetime.time)):
                            values.append(f"'{val.isoformat()}'")
                        elif isinstance(val, (dict, list)):
                            import json
                            escaped = json.dumps(val).replace("'", "''")
                            values.append(f"'{escaped}'")
                        else:
                            escaped = str(val).replace("'", "''")
                            values.append(f"'{escaped}'")
                    vals_str = ', '.join(values)
                    f.write(f'INSERT INTO "{table}" ({cols_str}) VALUES ({vals_str}) ON CONFLICT DO NOTHING;\n')
            f.write("\n")
            print(f"  [OK] {table:<28} : {len(rows):>5} rows")

        f.write("COMMIT;\n")

    cur.close()
    conn.close()

    file_size_kb = os.path.getsize(backup_file) / 1024
    print("=" * 60)
    print(f" [SUCCESS] Backup completed successfully!")
    print(f" File: {os.path.relpath(backup_file, ROOT_DIR)}")
    print(f" Size: {file_size_kb:.2f} KB ({total_rows_backed_up:,} total records)")
    print("=" * 60)


if __name__ == "__main__":
    run_backup()
