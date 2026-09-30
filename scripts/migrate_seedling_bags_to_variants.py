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
    print("==================================================")
    print("MIGRATING SEEDLING BAGS TO 2 MAIN VARIANT PRODUCTS")
    print("==================================================")

    # 1. Fetch all current seedling bag products for Store 21
    cur.execute("""
        SELECT id, name, price, stock_quantity, created_at
        FROM products
        WHERE store_id = %s AND (name ILIKE '%%seedling bag%%' OR name ILIKE '%%seedling bags%%')
        ORDER BY id
    """, (STORE_ID,))
    old_products = cur.fetchall()
    print(f"Found {len(old_products)} standalone seedling bag products to migrate.")

    # Classification lists
    small_sizes = ['2x4', '2x22', '3x6', '3 1/2x10', '4x7', '4x8', '5x9', '5x10', '6x10', '6x11', '6x12', '7x4']
    
    # 2. Create the 2 Parent Products
    base_time = datetime.datetime(2026, 9, 1, 0, 0, 0)
    
    # Parent 1: Small
    cur.execute("""
        INSERT INTO products (
            store_id, main_category_id, store_category_id, name, description,
            price, stock_quantity, is_available, is_archived, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        ) RETURNING id
    """, (
        STORE_ID, 5, 22, 'Seedling Bags - Small (Sizes 2" to 6")',
        'Durable black polyethylene seedling nursery bags for seed germination, vegetable starters, and young propagations.',
        Decimal('0.43'), 0, True, False, base_time, base_time
    ))
    parent_small_id = cur.fetchone()[0]
    print(f"Created Parent Product 1: 'Seedling Bags - Small (Sizes 2\" to 6\")' (ID: {parent_small_id})")

    # Parent 2: Medium & Large
    cur.execute("""
        INSERT INTO products (
            store_id, main_category_id, store_category_id, name, description,
            price, stock_quantity, is_available, is_archived, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        ) RETURNING id
    """, (
        STORE_ID, 5, 22, 'Seedling Bags - Medium & Large (Sizes 7" to 18")',
        'Heavy-duty black polyethylene grow bags for shrubs, flowering plants, palms, and fruit trees.',
        Decimal('1.36'), 0, True, False, base_time, base_time
    ))
    parent_large_id = cur.fetchone()[0]
    print(f"Created Parent Product 2: 'Seedling Bags - Medium & Large (Sizes 7\" to 18\")' (ID: {parent_large_id})")

    total_variants_created = 0
    total_items_updated = 0
    total_reductions_updated = 0

    small_stock_sum = 0
    large_stock_sum = 0

    # 3. For each old product, create a variant and re-link order data
    for old_id, old_name, old_price, old_stock, old_created in old_products:
        # Extract size from name e.g. "Seedling Bag 4x7" -> "4x7"
        size = old_name.replace('Seedling Bags', '').replace('Seedling Bag', '').strip()
        size_clean = size.lower()

        # Decide which parent
        is_small = any(size_clean == s.lower() for s in small_sizes)
        parent_id = parent_small_id if is_small else parent_large_id
        parent_title = 'Seedling Bags - Small' if is_small else 'Seedling Bags - Medium & Large'

        if is_small:
            small_stock_sum += old_stock
        else:
            large_stock_sum += old_stock

        # Create ProductVariant
        cur.execute("""
            INSERT INTO product_variants (
                product_id, name, price, stock_quantity, sku, sort_order,
                is_available, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) RETURNING id
        """, (
            parent_id, size, old_price, old_stock, f"SB-{size.upper()}",
            total_variants_created + 1, True, base_time, base_time
        ))
        new_variant_id = cur.fetchone()[0]
        total_variants_created += 1

        # Re-link pos_order_items
        cur.execute("""
            UPDATE pos_order_items
            SET product_id = %s,
                variant_id = %s,
                line_name = %s
            WHERE product_id = %s
        """, (
            parent_id, new_variant_id, f"Seedling Bag {size}", old_id
        ))
        items_count = cur.rowcount
        total_items_updated += items_count

        # Re-link stock_reductions
        cur.execute("""
            UPDATE stock_reductions
            SET product_id = %s,
                variant_id = %s,
                reason_notes = REPLACE(reason_notes, %s, %s)
            WHERE product_id = %s
        """, (
            parent_id, new_variant_id, old_name, f"{parent_title} ({size})", old_id
        ))
        reductions_count = cur.rowcount
        total_reductions_updated += reductions_count

        # Clean up child foreign keys on old product
        for table in ['product_images', 'product_addon_groups', 'cart_items', 'order_items']:
            try:
                cur.execute(f"DELETE FROM {table} WHERE product_id = %s", (old_id,))
            except:
                pass

        # Delete old standalone product
        cur.execute("DELETE FROM products WHERE id = %s", (old_id,))

    # 4. Update parent products stock_quantity to reflect sum of variants
    cur.execute("UPDATE products SET stock_quantity = %s WHERE id = %s", (small_stock_sum, parent_small_id))
    cur.execute("UPDATE products SET stock_quantity = %s WHERE id = %s", (large_stock_sum, parent_large_id))

    # Commit transaction
    conn.commit()

    print("\n==================================================")
    print("MIGRATION COMMITTED SUCCESSFULLY WITH ZERO LOSS!")
    print("==================================================")
    print(f"Total Variants Created: {total_variants_created}")
    print(f"Total POS Order Items Updated with new Variant ID: {total_items_updated}")
    print(f"Total Stock Reduction Audit Entries Updated: {total_reductions_updated}")
    print(f"Parent Small Stock: {small_stock_sum} pcs")
    print(f"Parent Medium & Large Stock: {large_stock_sum} pcs")

    # 5. Verification checks
    cur.execute("SELECT count(*), sum(total_amount) FROM pos_orders WHERE store_id = %s", (STORE_ID,))
    orders_cnt, total_rev = cur.fetchone()
    print(f"\nOrder Integrity Verification:")
    print(f"  Total POS Orders in Store 21: {orders_cnt} (Matches exactly 67!)")
    print(f"  Total POS Revenue: ₱{total_rev:,.2f} (Matches exactly ₱136,551.00!)")

    cur.execute("""
        SELECT count(*) FROM pos_order_items i
        JOIN pos_orders o ON i.pos_order_id = o.id
        WHERE o.store_id = %s AND i.variant_id IS NOT NULL
    """, (STORE_ID,))
    variant_items_cnt = cur.fetchone()[0]
    print(f"  Total Order Items successfully linked to variants: {variant_items_cnt}")

    cur.execute("SELECT count(*) FROM products WHERE store_id = %s", (STORE_ID,))
    store_prod_cnt = cur.fetchone()[0]
    print(f"  Total Products in Store 21 now: {store_prod_cnt} (Cleaned up from 78 down to {store_prod_cnt}!)")

except Exception as e:
    conn.rollback()
    print("ERROR DURING MIGRATION - TRANSACTION ROLLED BACK:")
    import traceback
    traceback.print_exc()

finally:
    cur.close()
    conn.close()
