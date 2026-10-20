"""
One-time database migration script to add cost_price and stock addition financial columns.
Run with: python add_cost_price_columns.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app import create_app
from app.extensions import db

app = create_app()

columns_to_add = [
    ("products", "cost_price", "NUMERIC(10,2) DEFAULT 0.00"),
    ("product_variants", "cost_price", "NUMERIC(10,2) DEFAULT 0.00"),
    ("product_addon_options", "cost_price", "NUMERIC(10,2) DEFAULT 0.00"),
    ("stock_reductions", "unit_cost", "NUMERIC(10,2) NULL"),
    ("stock_reductions", "total_cost", "NUMERIC(10,2) NULL"),
    ("order_items", "cost_price", "NUMERIC(10,2) DEFAULT 0.00"),
    ("pos_order_items", "cost_price", "NUMERIC(10,2) DEFAULT 0.00"),
    ("order_item_addons", "cost_price", "NUMERIC(10,2) DEFAULT 0.00"),
]

with app.app_context():
    with db.engine.connect() as conn:
        for table, col, col_type in columns_to_add:
            try:
                conn.execute(db.text(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {col_type}"
                ))
                conn.commit()
                print(f"[OK] Added {col} to {table}")
            except Exception as e:
                if "already exists" in str(e).lower():
                    print(f"[SKIP] {col} already exists in {table}")
                else:
                    print(f"[ERROR] Error adding {col} to {table}: {e}")
                    conn.rollback()

    print("\n[DONE] Migration completed successfully!")

