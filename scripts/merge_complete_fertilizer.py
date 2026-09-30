import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2
from decimal import Decimal

conn = psycopg2.connect('postgresql://postgres:cb346bB6Cf15eeg3BECf3FG5Dd6DF43e@nozomi.proxy.rlwy.net:24071/railway')
conn.autocommit = False
cur = conn.cursor()

try:
    OLD_ID = 348 # Complete Fertilizer
    KEEP_ID = 349 # Complete 14-14-14 Fertilizer

    print(f"Merging Product #{OLD_ID} into Product #{KEEP_ID}...")

    # 1. Update pos_order_items
    cur.execute("""
        UPDATE pos_order_items
        SET product_id = %s, line_name = 'Complete 14-14-14 Fertilizer'
        WHERE product_id = %s
    """, (KEEP_ID, OLD_ID))
    items_updated = cur.rowcount
    print(f"Updated {items_updated} POS order items to reference Product #{KEEP_ID}.")

    # 2. Update stock_reductions
    cur.execute("""
        UPDATE stock_reductions
        SET product_id = %s
        WHERE product_id = %s
    """, (KEEP_ID, OLD_ID))
    reductions_updated = cur.rowcount
    print(f"Updated {reductions_updated} Stock Reduction audit records to Product #{KEEP_ID}.")

    # 3. Get old product stock to combine
    cur.execute("SELECT stock_quantity FROM products WHERE id = %s", (OLD_ID,))
    old_stock = cur.fetchone()[0]

    # 4. Update KEEP product stock and price
    cur.execute("""
        UPDATE products
        SET stock_quantity = stock_quantity + %s,
            price = %s,
            name = 'Complete 14-14-14 Fertilizer',
            description = 'High-grade balanced NPK 14-14-14 granular fertilizer (1kg) | Princess Rasec Garden Supplies'
        WHERE id = %s
    """, (old_stock, Decimal('60.00'), KEEP_ID))
    print(f"Updated Product #{KEEP_ID}: combined remaining stock (+{old_stock}), set price to ₱60.00.")

    # 5. Clean up any foreign key relationships for OLD_ID before deleting
    for table in ['product_images', 'product_variants', 'product_addon_groups', 'cart_items', 'order_items']:
        try:
            cur.execute(f"DELETE FROM {table} WHERE product_id = %s", (OLD_ID,))
        except Exception as e:
            pass

    # 6. Delete OLD product
    cur.execute("DELETE FROM products WHERE id = %s", (OLD_ID,))
    print(f"Deleted duplicate Product #{OLD_ID}.")

    conn.commit()
    print("\nMERGE TRANSACTION COMMITTED SUCCESSFULLY!")

    # Verify
    cur.execute("""
        SELECT p.id, p.name, p.price, p.stock_quantity, count(i.id), count(sr.id)
        FROM products p
        LEFT JOIN pos_order_items i ON i.product_id = p.id
        LEFT JOIN stock_reductions sr ON sr.product_id = p.id
        WHERE p.id = %s
        GROUP BY p.id, p.name, p.price, p.stock_quantity
    """, (KEEP_ID,))
    res = cur.fetchone()
    print(f"\nVerification for Unified Product #{res[0]}:")
    print(f"  Name: {res[1]}")
    print(f"  Price: ₱{res[2]:.2f}")
    print(f"  Remaining Stock: {res[3]} pcs")
    print(f"  Total POS Order Items linked: {res[4]}")

except Exception as e:
    conn.rollback()
    print("ERROR DURING MERGE - ROLLED BACK:")
    import traceback
    traceback.print_exc()

finally:
    cur.close()
    conn.close()
