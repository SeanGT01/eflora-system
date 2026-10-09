import os, sys
sys.stdout.reconfigure(encoding='utf-8')
import datetime
import psycopg2
from decimal import Decimal

DATABASE_URL = 'postgresql://postgres:cb346bB6Cf15eeg3BECf3FG5Dd6DF43e@nozomi.proxy.rlwy.net:24071/railway'
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = False # Transaction safety
cur = conn.cursor()

try:
    print("==================================================")
    print("UPLOADING MISSING SEEDLING BAG SIZES AS VARIANTS")
    print("==================================================")

    STORE_ID = 21
    SELLER_USER_ID = 211
    CASHIER_NAME = "Victor Cesar De Torres"

    PARENT_SMALL_ID = 382  # Seedling Bags - Small (Sizes 2" to 6")
    PARENT_LARGE_ID = 383  # Seedling Bags - Medium & Large (Sizes 7" to 18")

    # 1. Insert Variant: 3 1/2x6 under Product #382
    print("\n--- 1. CREATING VARIANT '3 1/2x6' (Small) ---")
    cur.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM product_variants WHERE product_id = %s", (PARENT_SMALL_ID,))
    next_sort_small = cur.fetchone()[0]

    # Initial stock before order deduction was 1500, sold 1000 in Order #750 -> remaining stock: 500
    cur.execute("""
        INSERT INTO product_variants (
            product_id, name, price, stock_quantity, sku, sort_order,
            is_available, attributes, image_url, image_filename, image_public_id,
            created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s
        ) RETURNING id
    """, (
        PARENT_SMALL_ID,
        '3 1/2x6',
        Decimal('0.32'),
        500,
        'SB-3 1/2X6',
        next_sort_small,
        True,
        '{}',
        'https://res.cloudinary.com/dgyq49vi2/image/upload/v1790769733/e-flowers/variants/28325fefa1444afcb75e0f127609bb_769732_c304e9b9.jpg',
        'variant_e-flowers/variants/28325fefa1444afcb75e0f127609bb_769732_c304e9b9.jpg',
        'e-flowers/variants/28325fefa1444afcb75e0f127609bb_769732_c304e9b9',
        datetime.datetime(2026, 9, 1, 0, 0, 0),
        datetime.datetime(2026, 9, 28, 5, 44, 59)
    ))
    var_small_id = cur.fetchone()[0]
    print(f"Created Variant #3 1/2x6 (ID: {var_small_id}) under Parent #{PARENT_SMALL_ID}")

    # 2. Insert Variant: 11x18 under Product #383
    print("\n--- 2. CREATING VARIANT '11x18' (Medium & Large) ---")
    cur.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM product_variants WHERE product_id = %s", (PARENT_LARGE_ID,))
    next_sort_large = cur.fetchone()[0]

    # Initial stock before order deduction was 50, sold 10 in Order #737 -> remaining stock: 40
    cur.execute("""
        INSERT INTO product_variants (
            product_id, name, price, stock_quantity, sku, sort_order,
            is_available, attributes, image_url, image_filename, image_public_id,
            created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s
        ) RETURNING id
    """, (
        PARENT_LARGE_ID,
        '11x18',
        Decimal('8.80'),
        40,
        'SB-11X18',
        next_sort_large,
        True,
        '{}',
        'https://res.cloudinary.com/dgyq49vi2/image/upload/v1790769854/e-flowers/variants/28325fefa1444afcb75e0f127609bb_769854_eefb8af7.jpg',
        'variant_e-flowers/variants/28325fefa1444afcb75e0f127609bb_769854_eefb8af7.jpg',
        'e-flowers/variants/28325fefa1444afcb75e0f127609bb_769854_eefb8af7',
        datetime.datetime(2026, 9, 1, 0, 0, 0),
        datetime.datetime(2026, 9, 23, 2, 22, 54)
    ))
    var_large_id = cur.fetchone()[0]
    print(f"Created Variant #11x18 (ID: {var_large_id}) under Parent #{PARENT_LARGE_ID}")

    # 3. Update Order #750 Item #952 (3 1/2x6)
    print("\n--- 3. UPDATING POS ORDER #750 ---")
    cur.execute("""
        UPDATE pos_order_items
        SET is_custom = False,
            product_id = %s,
            variant_id = %s,
            line_name = 'Seedling Bags - Small (Sizes 2" to 6") - 3 1/2x6',
            custom_title = NULL,
            custom_category = NULL,
            custom_inclusions = NULL
        WHERE id = 952
    """, (PARENT_SMALL_ID, var_small_id))
    print(f"Updated pos_order_items #952 to Variant #{var_small_id}")

    # Order #750 now has 0 custom items (both 3 1/2x6 and 4x7 are catalog items)
    cur.execute("""
        UPDATE pos_orders
        SET is_custom_order = False
        WHERE id = 750
    """)
    print("Updated pos_orders #750: is_custom_order = False")

    # Log Stock Reduction for 3 1/2x6 (1,000 units)
    cur.execute("""
        INSERT INTO stock_reductions (
            product_id, variant_id, reduction_amount, reason, reason_notes,
            reduced_by, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s
        ) RETURNING id
    """, (
        PARENT_SMALL_ID, var_small_id, 1000, 'pos_sale',
        f'POS Sale - Order #750 by {CASHIER_NAME}',
        SELLER_USER_ID, datetime.datetime(2026, 9, 28, 5, 44, 59), datetime.datetime(2026, 9, 28, 5, 44, 59)
    ))
    sr_small_id = cur.fetchone()[0]
    print(f"Logged stock_reductions #{sr_small_id} for 3 1/2x6 (1,000 units)")

    # 4. Update Order #737 Item #916 (11x18)
    print("\n--- 4. UPDATING POS ORDER #737 ---")
    cur.execute("""
        UPDATE pos_order_items
        SET is_custom = False,
            product_id = %s,
            variant_id = %s,
            line_name = 'Seedling Bags - Medium & Large (Sizes 7" to 18") - 11x18',
            custom_title = NULL,
            custom_category = NULL,
            custom_inclusions = NULL
        WHERE id = 916
    """, (PARENT_LARGE_ID, var_large_id))
    print(f"Updated pos_order_items #916 to Variant #{var_large_id}")

    # Order #737 now has 0 custom items (6x12, 7x12, and 11x18 are all catalog items)
    cur.execute("""
        UPDATE pos_orders
        SET is_custom_order = False
        WHERE id = 737
    """)
    print("Updated pos_orders #737: is_custom_order = False")

    # Log Stock Reduction for 11x18 (10 units)
    cur.execute("""
        INSERT INTO stock_reductions (
            product_id, variant_id, reduction_amount, reason, reason_notes,
            reduced_by, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s
        ) RETURNING id
    """, (
        PARENT_LARGE_ID, var_large_id, 10, 'pos_sale',
        f'POS Sale - Order #737 by {CASHIER_NAME}',
        SELLER_USER_ID, datetime.datetime(2026, 9, 23, 2, 22, 54), datetime.datetime(2026, 9, 23, 2, 22, 54)
    ))
    sr_large_id = cur.fetchone()[0]
    print(f"Logged stock_reductions #{sr_large_id} for 11x18 (10 units)")

    # Commit transaction
    conn.commit()
    print("\n==================================================")
    print("ALL CHANGES SUCCESSFULLY COMMITTED TO RAILWAY DB!")
    print("==================================================")

except Exception as e:
    conn.rollback()
    print("\n[ERROR] Rolled back due to error:", e)
    import traceback
    traceback.print_exc()

finally:
    cur.close()
    conn.close()
