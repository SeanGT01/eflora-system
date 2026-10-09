import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.stdout.reconfigure(encoding='utf-8')

from sqlalchemy import text
from app import create_app, db
from app.models import Product, ProductVariant

app = create_app()

MANIFEST_FILE = os.path.join(os.path.dirname(__file__), 'simulation_manifest.json')

def undo_simulation():
    print("🔄 Starting Undo of Online Orders Simulation...")

    if not os.path.exists(MANIFEST_FILE):
        print(f"❌ Manifest file not found: {MANIFEST_FILE}")
        return

    with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    order_ids = manifest.get("order_ids", [])
    reduction_ids = manifest.get("stock_reduction_ids", [])
    rider_ids = manifest.get("rider_ids", [])
    rider_user_ids = manifest.get("rider_user_ids", [])
    customer_user_ids = manifest.get("customer_user_ids", [])
    orig_prod_stocks = manifest.get("original_product_stocks", {})
    orig_var_stocks = manifest.get("original_variant_stocks", {})

    with app.app_context():
        try:
            # 1. Delete ratings
            if order_ids:
                oids = tuple(order_ids) if len(order_ids) > 1 else f"({order_ids[0]})"
                db.session.execute(text(f"DELETE FROM product_ratings WHERE order_id IN {oids}"))
                db.session.execute(text(f"DELETE FROM store_ratings WHERE order_id IN {oids}"))
                print(f"✅ Deleted product and store ratings for {len(order_ids)} orders")

                # 2. Delete order items & orders
                db.session.execute(text(f"DELETE FROM order_items WHERE order_id IN {oids}"))
                db.session.execute(text(f"DELETE FROM orders WHERE id IN {oids}"))
                print(f"✅ Deleted {len(order_ids)} orders and their line items")

            # 3. Delete stock reductions
            if reduction_ids:
                rids = tuple(reduction_ids) if len(reduction_ids) > 1 else f"({reduction_ids[0]})"
                db.session.execute(text(f"DELETE FROM stock_reductions WHERE id IN {rids}"))
                print(f"✅ Deleted {len(reduction_ids)} stock reduction audit records")

            # 4. Restore original product & variant stock
            for pid_str, stock in orig_prod_stocks.items():
                p = Product.query.get(int(pid_str))
                if p:
                    p.stock_quantity = stock
            for vid_str, stock in orig_var_stocks.items():
                v = ProductVariant.query.get(int(vid_str))
                if v:
                    v.stock_quantity = stock
            print("✅ Restored original product and variant stock quantities")

            # 5. Delete created riders & user profiles
            if rider_ids:
                r_ids = tuple(rider_ids) if len(rider_ids) > 1 else f"({rider_ids[0]})"
                db.session.execute(text(f"DELETE FROM riders WHERE id IN {r_ids}"))
                print(f"✅ Deleted {len(rider_ids)} simulated riders")

            user_del = set(rider_user_ids + customer_user_ids)
            if user_del:
                u_ids = tuple(user_del) if len(user_del) > 1 else f"({list(user_del)[0]})"
                db.session.execute(text(f"DELETE FROM users WHERE id IN {u_ids}"))
                print(f"✅ Deleted {len(user_del)} simulated user accounts")

            db.session.commit()
            print("\n🎉 Reversal complete! Database has been cleanly restored.")

        except Exception as e:
            db.session.rollback()
            print(f"❌ Error during rollback: {e}")

if __name__ == '__main__':
    undo_simulation()
