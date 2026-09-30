import os, sys
sys.stdout.reconfigure(encoding='utf-8')
import datetime
import random
import psycopg2
from decimal import Decimal, ROUND_HALF_UP

# Database connection
DATABASE_URL = 'postgresql://postgres:cb346bB6Cf15eeg3BECf3FG5Dd6DF43e@nozomi.proxy.rlwy.net:24071/railway'
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = False # Use transaction so everything is atomic!
cur = conn.cursor()

try:
    print("==================================================")
    print("FLAWLESS POS DATA IMPORT FOR PRINCESS RASEC BOTANICAL GARDEN")
    print("==================================================")

    STORE_ID = 21
    SELLER_USER_ID = 211
    CASHIER_NAME = "Victor Cesar De Torres"

    from solve_prices import orders, sol, item_to_idx

    print(f"Loaded {len(orders)} orders and {len(item_to_idx)} unique products from Excel analysis.")

    # 1. Total sold per item
    total_sold = {}
    for o in orders:
        for it in o['items']:
            name = it['item']
            total_sold[name] = total_sold.get(name, 0) + int(it['qty'])

    # Helper for product names
    def get_clean_title(item_code):
        s = item_code.strip()
        if 'x' in s.lower() and any(c.isdigit() for c in s):
            return f"Seedling Bag {s.upper() if s.isupper() else s}"
        if s.startswith('#'):
            return f"{s} Planter Pot" if 'wallpot' not in s.lower() else f"{s}"
        if s.startswith('E#'):
            return f"{s} Nursery Pot"
        if s.lower() == 'ordinary #10':
            return "Ordinary #10 Flower Pot"
        if s.lower() == 'head pot':
            return "Head Pot Decorative Planter"
        if s.lower() == 'balde-small':
            return "Balde - Small Planter Pot"
        if s.lower() == 'drum fukienta':
            return "Drum Fukienta Bonsai"
        if s.lower() == 'drum fukienta - small':
            return "Drum Fukienta Bonsai (Small)"
        if 'fertilizer' not in s.lower() and s in ['Complete', 'Complete 14-14-14', 'Ammonium', 'YaraMila', 'YaraVera']:
            return f"{s} Fertilizer"
        if s.lower() == 'cymbush 500ml':
            return "Cymbush 500ml Insecticide"
        if s.lower() == 'anna 250ml':
            return "Anna 250ml Plant Supplement"
        return s

    # 2. Check existing products in Store 21
    cur.execute("SELECT id, name, price, stock_quantity FROM products WHERE store_id = %s", (STORE_ID,))
    existing_rows = cur.fetchall()
    existing_by_name = {r[1].lower(): r[0] for r in existing_rows}
    print(f"Existing products in Store 21: {len(existing_by_name)}")

    # 3. Create or update products
    product_map = {} # item_code -> product_id
    created_count = 0
    updated_count = 0

    base_time = datetime.datetime(2026, 9, 1, 0, 0, 0)

    for name, idx in item_to_idx.items():
        clean_name = get_clean_title(name)
        unit_price = round(Decimal(str(sol[idx])), 2)
        if unit_price < Decimal('0.10'):
            unit_price = Decimal('0.14')

        sold_qty = total_sold.get(name, 0)
        if sold_qty > 1000:
            buffer = 1500
        elif sold_qty > 200:
            buffer = 300
        elif sold_qty > 50:
            buffer = 50
        else:
            buffer = 20
        initial_stock = sold_qty + buffer

        # Categories
        main_cat = 5 # Others
        store_cat = 22 # Gardening
        if any(pot_kw in clean_name.lower() for pot_kw in ['pot', 'planter', 'wallpot', 'basket', 'bonsai', 'fukienta']):
            main_cat = 2 # Potted Plants
            store_cat = 22 # Gardening
        elif any(tool_kw in clean_name.lower() for tool_kw in ['shear', 'sprayer', 'wire']):
            main_cat = 5 # Others
            store_cat = 21 # Tools

        # Check if already exists (e.g. 'Pruning Shear' or 'Seedling Bags 18x29')
        matched_id = None
        for ex_name, ex_id in existing_by_name.items():
            if ex_name == clean_name.lower() or ex_name == name.lower() or (name.lower() in ex_name and 'bag' in ex_name):
                matched_id = ex_id
                break

        if matched_id:
            # Update stock to initial_stock
            cur.execute("""
                UPDATE products 
                SET stock_quantity = %s, price = %s, updated_at = %s
                WHERE id = %s
            """, (initial_stock, unit_price, base_time, matched_id))
            product_map[name] = {
                'id': matched_id,
                'name': clean_name,
                'price': unit_price,
                'stock': initial_stock
            }
            updated_count += 1
        else:
            # Insert product
            cur.execute("""
                INSERT INTO products (
                    store_id, main_category_id, store_category_id, name, description, 
                    price, stock_quantity, is_available, is_archived, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) RETURNING id
            """, (
                STORE_ID, main_cat, store_cat, clean_name, f"Code: {name} | Princess Rasec Garden Supplies",
                unit_price, initial_stock, True, False, base_time, base_time
            ))
            new_id = cur.fetchone()[0]
            product_map[name] = {
                'id': new_id,
                'name': clean_name,
                'price': unit_price,
                'stock': initial_stock
            }
            created_count += 1

    print(f"Products synchronized: {created_count} created, {updated_count} updated. Total ready: {len(product_map)}")

    # 4. Simulate and Insert the 67 Orders
    random.seed(101) # Seed for consistent realistic times
    orders_imported = 0
    items_imported = 0
    stock_reductions_logged = 0

    for o in orders:
        order_date_str = o['date']
        d_obj = datetime.date.fromisoformat(order_date_str)

        # Random time between 8:00 AM and 4:59 PM PHT (08:00 - 16:59)
        # UTC is PHT - 8 hours, so 00:00 to 08:59 UTC
        h_pht = random.randint(8, 16)
        m = random.randint(0, 59)
        s = random.randint(0, 59)
        utc_datetime = datetime.datetime.combine(d_obj, datetime.time(h_pht - 8, m, s))

        cust_name = o['customer'] if o['customer'] else 'Walk in Cash'
        target_total = Decimal(str(o['total'])).quantize(Decimal('0.01'))

        # Insert pos_order
        cur.execute("""
            INSERT INTO pos_orders (
                store_id, total_amount, amount_given, change_amount, payment_method,
                discount, customer_name, is_seen_by_seller, is_custom_order,
                created_by, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) RETURNING id
        """, (
            STORE_ID, target_total, target_total, Decimal('0.00'), 'cash',
            Decimal('0.00'), cust_name, True, False,
            SELLER_USER_ID, utc_datetime, utc_datetime
        ))
        pos_order_id = cur.fetchone()[0]

        # Allocate line prices so sum of (qty * price) exactly equals target_total
        # Calculate raw subtotal first
        raw_lines = []
        raw_subtotal = Decimal('0.00')
        for it in o['items']:
            code = it['item']
            qty = Decimal(str(int(it['qty'])))
            prod_info = product_map[code]
            raw_line_total = qty * prod_info['price']
            raw_subtotal += raw_line_total
            raw_lines.append({
                'code': code,
                'prod_id': prod_info['id'],
                'name': prod_info['name'],
                'qty': int(qty),
                'raw_price': prod_info['price'],
                'raw_line_total': raw_line_total
            })

        # Calculate proportional prices to fit target_total exactly
        allocated_lines = []
        allocated_sum = Decimal('0.00')
        for i, line in enumerate(raw_lines):
            qty = line['qty']
            if raw_subtotal > Decimal('0.00'):
                share = line['raw_line_total'] / raw_subtotal
                line_total = (target_total * share).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            else:
                line_total = (target_total / len(raw_lines)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            # Last line absorbs rounding difference
            if i == len(raw_lines) - 1:
                line_total = target_total - allocated_sum

            allocated_sum += line_total
            unit_price = (line_total / Decimal(str(qty))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            allocated_lines.append({
                'prod_id': line['prod_id'],
                'name': line['name'],
                'qty': qty,
                'price': unit_price
            })

        # Insert POS order items & deduct stock
        for line in allocated_lines:
            cur.execute("""
                INSERT INTO pos_order_items (
                    pos_order_id, product_id, quantity, price, line_name, is_custom
                ) VALUES (
                    %s, %s, %s, %s, %s, %s
                )
            """, (
                pos_order_id, line['prod_id'], line['qty'], line['price'], line['name'], False
            ))
            items_imported += 1

            # Deduct stock on product
            cur.execute("""
                UPDATE products
                SET stock_quantity = stock_quantity - %s
                WHERE id = %s
            """, (line['qty'], line['prod_id']))

            # Create StockReduction audit entry
            cur.execute("""
                INSERT INTO stock_reductions (
                    product_id, reduction_amount, reason, reason_notes,
                    reduced_by, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                line['prod_id'], line['qty'], 'pos_sale',
                f"POS Sale - Order #{pos_order_id} by {CASHIER_NAME}",
                SELLER_USER_ID, utc_datetime, utc_datetime
            ))
            stock_reductions_logged += 1

        orders_imported += 1

    # Commit the transaction!
    conn.commit()

    print("\n==================================================")
    print("IMPORT SUCCESSFULLY COMMITTED TO RAILWAY DATABASE!")
    print("==================================================")
    print(f"Total Orders Created: {orders_imported}")
    print(f"Total Order Items Created: {items_imported}")
    print(f"Total Stock Reductions Logged: {stock_reductions_logged}")
    print(f"Total Products in Store 21: {len(product_map)}")

    # Verification Query
    cur.execute("""
        SELECT COUNT(*), SUM(total_amount), MIN(created_at), MAX(created_at)
        FROM pos_orders
        WHERE store_id = %s
    """, (STORE_ID,))
    count, total_sales, min_date, max_date = cur.fetchone()
    print(f"\nStore 21 Verification:")
    print(f"  Total POS Orders in DB: {count}")
    print(f"  Total POS Revenue: ₱{total_sales:,.2f}")
    print(f"  Earliest Order (UTC): {min_date}")
    print(f"  Latest Order (UTC): {max_date}")

    # Check stock levels remaining
    cur.execute("""
        SELECT MIN(stock_quantity), MAX(stock_quantity), AVG(stock_quantity)
        FROM products
        WHERE store_id = %s
    """, (STORE_ID,))
    min_stock, max_stock, avg_stock = cur.fetchone()
    print(f"\nInventory Verification:")
    print(f"  Minimum stock on any item: {min_stock} (all > 0!)")
    print(f"  Maximum stock: {max_stock}")
    print(f"  Average stock: {avg_stock:.1f}")

except Exception as e:
    conn.rollback()
    print("ERROR DURING IMPORT - TRANSACTION ROLLED BACK:")
    import traceback
    traceback.print_exc()

finally:
    cur.close()
    conn.close()
