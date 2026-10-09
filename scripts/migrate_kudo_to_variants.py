import sys
sys.stdout.reconfigure(encoding='utf-8')
import datetime
import psycopg2
from decimal import Decimal

conn = psycopg2.connect('postgresql://postgres:cb346bB6Cf15eeg3BECf3FG5Dd6DF43e@nozomi.proxy.rlwy.net:24071/railway')
conn.autocommit = False
cur = conn.cursor()

try:
    STORE_ID = 21
    PARENT_ID = 367  # Current "Kudo Stone #0"
    OLD_KUDO_20_ID = 365
    OLD_KUDO_25_ID = 366

    print("==================================================")
    print("MIGRATING KUDO PRODUCTS AS VARIANTS UNDER KUDO #0")
    print("==================================================")

    now = datetime.datetime.utcnow()

    # 1. Rename Parent Product 367 to 'Kudo #0'
    cur.execute("""
        UPDATE products
        SET name = 'Kudo #0',
            description = 'Code: Kudo #0 | Princess Rasec Garden Supplies',
            updated_at = %s
        WHERE id = %s AND store_id = %s
    """, (now, PARENT_ID, STORE_ID))
    print(f"✅ Renamed Product #{PARENT_ID} to 'Kudo #0'")

    # 2. Fetch current prices & stock for #20 and #25
    cur.execute("SELECT id, name, price, stock_quantity FROM products WHERE id = %s", (OLD_KUDO_20_ID,))
    p20 = cur.fetchone()
    cur.execute("SELECT id, name, price, stock_quantity FROM products WHERE id = %s", (OLD_KUDO_25_ID,))
    p25 = cur.fetchone()

    price_20 = p20[2] if p20 else Decimal('265.72')
    stock_20 = p20[3] if p20 else 20

    price_25 = p25[2] if p25 else Decimal('605.05')
    stock_25 = p25[3] if p25 else 20

    # 3. Create Variant 1: Kudo #20
    cur.execute("""
        INSERT INTO product_variants (
            product_id, name, price, stock_quantity, sku, sort_order,
            is_available, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s
        ) RETURNING id
    """, (
        PARENT_ID, 'Kudo #20', price_20, stock_20, 'KUDO-20',
        0, True, now, now
    ))
    var_20_id = cur.fetchone()[0]
    print(f"✅ Created Variant 'Kudo #20' (ID: {var_20_id}) with Price: ₱{price_20}, Stock: {stock_20}")

    # 4. Create Variant 2: Kudo #25
    cur.execute("""
        INSERT INTO product_variants (
            product_id, name, price, stock_quantity, sku, sort_order,
            is_available, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s
        ) RETURNING id
    """, (
        PARENT_ID, 'Kudo #25', price_25, stock_25, 'KUDO-25',
        1, True, now, now
    ))
    var_25_id = cur.fetchone()[0]
    print(f"✅ Created Variant 'Kudo #25' (ID: {var_25_id}) with Price: ₱{price_25}, Stock: {stock_25}")

    # 5. Re-link POS Order Items from Old #20 to new Variant
    cur.execute("""
        UPDATE pos_order_items
        SET product_id = %s,
            variant_id = %s,
            line_name = 'Kudo #20'
        WHERE product_id = %s
    """, (PARENT_ID, var_20_id, OLD_KUDO_20_ID))
    pos_20_count = cur.rowcount
    print(f"✅ Re-linked {pos_20_count} POS order item(s) from Product #{OLD_KUDO_20_ID} to Variant {var_20_id}")

    # 6. Re-link POS Order Items from Old #25 to new Variant
    cur.execute("""
        UPDATE pos_order_items
        SET product_id = %s,
            variant_id = %s,
            line_name = 'Kudo #25'
        WHERE product_id = %s
    """, (PARENT_ID, var_25_id, OLD_KUDO_25_ID))
    pos_25_count = cur.rowcount
    print(f"✅ Re-linked {pos_25_count} POS order item(s) from Product #{OLD_KUDO_25_ID} to Variant {var_25_id}")

    # 7. Re-link Stock Reductions from Old #20
    cur.execute("""
        UPDATE stock_reductions
        SET product_id = %s,
            variant_id = %s,
            reason_notes = REPLACE(reason_notes, 'Kudo #20', 'Kudo #0 (Kudo #20)')
        WHERE product_id = %s
    """, (PARENT_ID, var_20_id, OLD_KUDO_20_ID))
    sr_20_count = cur.rowcount
    print(f"✅ Re-linked {sr_20_count} Stock Reduction(s) from Product #{OLD_KUDO_20_ID} to Variant {var_20_id}")

    # 8. Re-link Stock Reductions from Old #25
    cur.execute("""
        UPDATE stock_reductions
        SET product_id = %s,
            variant_id = %s,
            reason_notes = REPLACE(reason_notes, 'Kudo #25', 'Kudo #0 (Kudo #25)')
        WHERE product_id = %s
    """, (PARENT_ID, var_25_id, OLD_KUDO_25_ID))
    sr_25_count = cur.rowcount
    print(f"✅ Re-linked {sr_25_count} Stock Reduction(s) from Product #{OLD_KUDO_25_ID} to Variant {var_25_id}")

    # 9. Clean up any child records on old products if any
    for old_id in [OLD_KUDO_20_ID, OLD_KUDO_25_ID]:
        for table in ['product_images', 'product_addon_groups', 'cart_items', 'order_items']:
            cur.execute(f"DELETE FROM {table} WHERE product_id = %s", (old_id,))

    # 10. Delete old standalone products 365 and 366
    cur.execute("DELETE FROM products WHERE id IN (%s, %s)", (OLD_KUDO_20_ID, OLD_KUDO_25_ID))
    deleted_count = cur.rowcount
    print(f"✅ Removed {deleted_count} standalone product(s) (IDs #{OLD_KUDO_20_ID}, #{OLD_KUDO_25_ID}) from product list")

    # Commit all changes atomically
    conn.commit()
    print("==================================================")
    print("SUCCESS: Migration committed successfully!")
    print("==================================================")

    # Verification
    cur.execute("""
        SELECT p.id, p.name, p.price, p.stock_quantity
        FROM products p
        WHERE p.id = %s
    """, (PARENT_ID,))
    parent_row = cur.fetchone()
    print(f"\nParent Product: ID {parent_row[0]} | Name: '{parent_row[1]}' | Price: ₱{parent_row[2]} | Stock: {parent_row[3]}")

    cur.execute("""
        SELECT pv.id, pv.name, pv.price, pv.stock_quantity, pv.sku, pv.sort_order
        FROM product_variants pv
        WHERE pv.product_id = %s
        ORDER BY pv.sort_order
    """, (PARENT_ID,))
    variants = cur.fetchall()
    print(f"Variants under '{parent_row[1]}' ({len(variants)}):")
    for v in variants:
        print(f"  - Variant ID {v[0]}: '{v[1]}' | Price: ₱{v[2]} | Stock: {v[3]} | SKU: {v[4]}")

    # Check remaining kudo products in store 21
    cur.execute("""
        SELECT id, name, price, stock_quantity
        FROM products
        WHERE store_id = %s AND name ILIKE '%kudo%'
    """, (STORE_ID,))
    remaining = cur.fetchall()
    print(f"\nRemaining Kudo products on product list for Store #{STORE_ID} ({len(remaining)}):")
    for r in remaining:
        print(f"  - ID {r[0]}: '{r[1]}' | Price: ₱{r[2]}")

    # Verify POS orders intact
    cur.execute("SELECT count(*), sum(total_amount) FROM pos_orders WHERE store_id = %s", (STORE_ID,))
    orders_cnt, total_rev = cur.fetchone()
    print(f"\nPOS Integrity Check:")
    print(f"  Total POS Orders: {orders_cnt}")
    print(f"  Total POS Revenue: ₱{total_rev:,.2f}")

except Exception as e:
    conn.rollback()
    print(f"❌ Error during migration: {e}")
    import traceback
    traceback.print_exc()

finally:
    cur.close()
    conn.close()
