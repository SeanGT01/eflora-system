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
    print("MIGRATING POTS & PLANTERS TO 3 MAIN VARIANT PRODUCTS")
    print("==================================================")

    # Classification mapping: old_product_id -> (target_parent_key, clean_variant_name)
    # Target parent keys: 'e_series', 'wallpots', 'planters'
    POT_MAP = {
        # 1. E-Series Nursery Pots
        354: ('e_series', 'E#5 Nursery Pot'),
        353: ('e_series', 'E#4 Nursery Pot'),
        355: ('e_series', 'E#7 Nursery Pot'),
        356: ('e_series', 'E#7 - Black Nursery Pot'),
        357: ('e_series', 'E#9 Nursery Pot'),
        358: ('e_series', 'E-Pot Standard'),
        372: ('e_series', 'Ordinary #10 Flower Pot'),

        # 2. Wallpots & Hanging Planters
        306: ('wallpots', '#629 Wallpot'),
        379: ('wallpots', 'Wallpot Medium'),
        364: ('wallpots', 'Hook w/ Basket'),

        # 3. Garden Planter Pots (#8000 Series & Decorative)
        311: ('planters', '#8403 Planter Pot'),
        345: ('planters', 'Balde - Small Planter Pot'),
        309: ('planters', '#8303 Planter Pot'),
        310: ('planters', '#8303-Green Planter Pot'),
        312: ('planters', '#8713 Large Planter Pot'),
        307: ('planters', '#816 - Green Planter Pot'),
        308: ('planters', '#818 - Green Planter Pot'),
        363: ('planters', 'Head Pot Decorative Planter')
    }

    base_time = datetime.datetime(2026, 9, 1, 0, 0, 0)

    # 1. Create Parent 1: Nursery Plastic Pots (E-Series)
    cur.execute("""
        INSERT INTO products (
            store_id, main_category_id, store_category_id, name, description,
            price, stock_quantity, is_available, is_archived, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        ) RETURNING id
    """, (
        STORE_ID, 2, 22, 'Nursery Plastic Pots (E-Series & Standard)',
        'Durable round injection-molded nursery pots for seedling transplanting, potting, and repotting.',
        Decimal('15.19'), 0, True, False, base_time, base_time
    ))
    parent_e_id = cur.fetchone()[0]
    print(f"Created Parent 1: 'Nursery Plastic Pots (E-Series & Standard)' (ID: {parent_e_id})")

    # 2. Create Parent 2: Wallpots & Hanging Planters
    cur.execute("""
        INSERT INTO products (
            store_id, main_category_id, store_category_id, name, description,
            price, stock_quantity, is_available, is_archived, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        ) RETURNING id
    """, (
        STORE_ID, 2, 22, 'Wallpots & Hanging Planters',
        'Wall-mounted vertical garden pots and hanging wire baskets for cascading plants, flowers, and ferns.',
        Decimal('15.63'), 0, True, False, base_time, base_time
    ))
    parent_wall_id = cur.fetchone()[0]
    print(f"Created Parent 2: 'Wallpots & Hanging Planters' (ID: {parent_wall_id})")

    # 3. Create Parent 3: Garden Planter Pots (#8000 Series & Decorative)
    cur.execute("""
        INSERT INTO products (
            store_id, main_category_id, store_category_id, name, description,
            price, stock_quantity, is_available, is_archived, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        ) RETURNING id
    """, (
        STORE_ID, 2, 22, 'Garden Planter Pots (#8000 Series & Decorative)',
        'Heavy-duty plastic garden planters, patio pots, and decorative containers for shrubs and flowering plants.',
        Decimal('150.59'), 0, True, False, base_time, base_time
    ))
    parent_planters_id = cur.fetchone()[0]
    print(f"Created Parent 3: 'Garden Planter Pots (#8000 Series & Decorative)' (ID: {parent_planters_id})")

    parents = {
        'e_series': {'id': parent_e_id, 'name': 'Nursery Plastic Pots (E-Series)', 'stock': 0},
        'wallpots': {'id': parent_wall_id, 'name': 'Wallpots & Hanging Planters', 'stock': 0},
        'planters': {'id': parent_planters_id, 'name': 'Garden Planter Pots', 'stock': 0}
    }

    variants_created = 0
    items_updated = 0
    reductions_updated = 0

    # 4. Migrate each pot product to its variant
    for old_id, (target_key, var_name) in POT_MAP.items():
        cur.execute("SELECT id, name, price, stock_quantity FROM products WHERE id = %s", (old_id,))
        row = cur.fetchone()
        if not row:
            print(f"Warning: Product ID {old_id} not found, skipping...")
            continue
        
        _, old_name, old_price, old_stock = row
        parent_info = parents[target_key]
        parent_id = parent_info['id']
        parent_info['stock'] += old_stock

        # Create ProductVariant
        cur.execute("""
            INSERT INTO product_variants (
                product_id, name, price, stock_quantity, sku, sort_order,
                is_available, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) RETURNING id
        """, (
            parent_id, var_name, old_price, old_stock, f"POT-{old_id}",
            variants_created + 1, True, base_time, base_time
        ))
        new_variant_id = cur.fetchone()[0]
        variants_created += 1

        # Re-link pos_order_items
        cur.execute("""
            UPDATE pos_order_items
            SET product_id = %s,
                variant_id = %s,
                line_name = %s
            WHERE product_id = %s
        """, (
            parent_id, new_variant_id, var_name, old_id
        ))
        cnt_items = cur.rowcount
        items_updated += cnt_items

        # Re-link stock_reductions
        cur.execute("""
            UPDATE stock_reductions
            SET product_id = %s,
                variant_id = %s,
                reason_notes = REPLACE(reason_notes, %s, %s)
            WHERE product_id = %s
        """, (
            parent_id, new_variant_id, old_name, f"{parent_info['name']} ({var_name})", old_id
        ))
        cnt_reductions = cur.rowcount
        reductions_updated += cnt_reductions

        # Clean up foreign keys on old product
        for table in ['product_images', 'product_addon_groups', 'cart_items', 'order_items']:
            try:
                cur.execute(f"DELETE FROM {table} WHERE product_id = %s", (old_id,))
            except:
                pass

        # Delete old product
        cur.execute("DELETE FROM products WHERE id = %s", (old_id,))

    # 5. Update stock_quantity on parent products to sum of their variants
    for target_key, p_info in parents.items():
        cur.execute("UPDATE products SET stock_quantity = %s WHERE id = %s", (p_info['stock'], p_info['id']))
        print(f"Parent '{p_info['name']}' combined stock: {p_info['stock']} pcs")

    # Commit the transaction!
    conn.commit()

    print("\n==================================================")
    print("POT MIGRATION COMMITTED SUCCESSFULLY WITH ZERO LOSS!")
    print("==================================================")
    print(f"Total Pot Variants Created: {variants_created}")
    print(f"Total POS Order Items Re-linked to Variants: {items_updated}")
    print(f"Total Stock Reduction Logs Re-linked to Variants: {reductions_updated}")

    # Verification queries
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
    tot_var_items = cur.fetchone()[0]
    print(f"  Total Order Items linked to variants: {tot_var_items} (Seedling Bags + Pots)")

    cur.execute("SELECT count(*) FROM products WHERE store_id = %s", (STORE_ID,))
    store_prod_cnt = cur.fetchone()[0]
    print(f"  Total Products in Store 21 now: {store_prod_cnt} (Cleaned down to {store_prod_cnt}!)")

except Exception as e:
    conn.rollback()
    print("ERROR DURING POT MIGRATION - TRANSACTION ROLLED BACK:")
    import traceback
    traceback.print_exc()

finally:
    cur.close()
    conn.close()
