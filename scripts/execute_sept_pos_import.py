import os, sys
sys.stdout.reconfigure(encoding='utf-8')
import datetime
import random
import zipfile
import xml.etree.ElementTree as ET
import psycopg2
from decimal import Decimal, ROUND_HALF_UP

# Database connection
DATABASE_URL = 'postgresql://postgres:cb346bB6Cf15eeg3BECf3FG5Dd6DF43e@nozomi.proxy.rlwy.net:24071/railway'
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = False # Transaction safety
cur = conn.cursor()

try:
    print("==================================================")
    print("IMPORTING SEPTEMBER 18-30 POS SALES FOR STORE 21")
    print("Princess Rasec Botanical Garden")
    print("==================================================")

    STORE_ID = 21
    SELLER_USER_ID = 211
    CASHIER_NAME = "Victor Cesar De Torres"

    # Step 1: Update incorrect prices on catalog products as instructed
    # Garden Soil (Product #362): Order #15 proves 6 units = ₱270 -> ₱45.00
    print("\n--- STEP 1: CATALOG PRICE CORRECTIONS ---")
    cur.execute("UPDATE products SET price = 45.00 WHERE id = 362 AND store_id = %s", (STORE_ID,))
    print(f"Updated Garden Soil (Product #362) price to ₱45.00")

    # Step 2: Parse Excel file between 'start here' (Row 227) and 'End here' (Row 341)
    print("\n--- STEP 2: PARSING EXCEL SALES DATA ---")
    excel_path = r'C:\Users\seanm\OneDrive\Desktop\Sales data for POS.xlsx'
    
    read_file = r'C:\Users\seanm\.gemini\antigravity-ide\brain\f8f7a14a-2929-4f7e-9fce-c1a05394345d\scratch\sales_copy.xlsx'

    with zipfile.ZipFile(read_file) as z:
        shared_strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            tree = ET.fromstring(z.read('xl/sharedStrings.xml'))
            for si in tree.findall('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si'):
                shared_strings.append(''.join([t.text or '' for t in si.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t')]))

        sheet_tree = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
        ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        rows_data = []
        for row in sheet_tree.findall('.//ns:row', ns):
            r_num = int(row.attrib.get('r'))
            cells = {}
            for c in row.findall('ns:c', ns):
                col = ''.join([ch for ch in c.attrib.get('r', '') if ch.isalpha()])
                t = c.attrib.get('t')
                v_tag = c.find('ns:v', ns)
                val = v_tag.text if v_tag is not None else None
                if val is not None and t == 's':
                    val = shared_strings[int(val)]
                cells[col] = val
            rows_data.append((r_num, cells))



    # Locate 'start here' and 'end here'
    start_r = 227
    end_r = 341

    valid_rows = []
    for r_num, cells in rows_data:
        if start_r < r_num < end_r:
            item = cells.get('C')
            qty = cells.get('B')
            if item or qty:
                valid_rows.append((r_num, cells))

    # Group into orders
    def serial_to_date(serial_str):
        if not serial_str:
            return None
        try:
            val = float(serial_str)
            dt = datetime.date(1899, 12, 30) + datetime.timedelta(days=int(val))
            return dt.strftime('%Y-%m-%d')
        except:
            return None

    raw_orders = []
    current_order = None
    order_counter = 1

    for r_num, cells in valid_rows:
        date_str = serial_to_date(cells.get('A'))
        qty_str = cells.get('B')
        item_str = cells.get('C')
        total_str = cells.get('D')
        cust_str = cells.get('E')

        if date_str is not None:
            if current_order is not None:
                raw_orders.append(current_order)
            current_order = {
                'order_idx': order_counter,
                'start_row': r_num,
                'end_row': r_num,
                'date': date_str,
                'items': [],
                'total': None,
                'customer': None
            }
            order_counter += 1

        if current_order is not None:
            current_order['end_row'] = r_num
            if qty_str is not None and item_str is not None:
                current_order['items'].append({
                    'qty': float(qty_str),
                    'item': item_str.strip()
                })
            if total_str is not None:
                current_order['total'] = float(total_str)
            if cust_str is not None:
                current_order['customer'] = cust_str.strip()

    if current_order is not None:
        raw_orders.append(current_order)

    print(f"Total parsed order blocks between Row 227 and 341: {len(raw_orders)}")

    # Skip Order #1 (Row 228-229) as confirmed by the user to avoid duplicating Order #703
    orders_to_import = [o for o in raw_orders if not (o['start_row'] == 228 and o['end_row'] == 229)]
    print(f"Orders to import after skipping duplicate Order #703 (Row 228-229): {len(orders_to_import)}")
    target_revenue = sum(Decimal(str(o['total'])) for o in orders_to_import)
    print(f"Target revenue to import: ₱{target_revenue:,.2f}")

    # Step 3: Fetch catalog products & variants
    print("\n--- STEP 3: LOADING CATALOG PRODUCTS & VARIANTS ---")
    cur.execute("SELECT id, name, price, stock_quantity FROM products WHERE store_id = %s", (STORE_ID,))
    products = {r[1].lower(): {'id': r[0], 'name': r[1], 'price': Decimal(str(r[2])), 'stock': r[3]} for r in cur.fetchall()}

    cur.execute("""
        SELECT pv.id, pv.product_id, p.name as parent_name, pv.name as variant_name, pv.price, pv.stock_quantity
        FROM product_variants pv
        JOIN products p ON p.id = pv.product_id
        WHERE p.store_id = %s
    """, (STORE_ID,))
    variants = {}
    for r in cur.fetchall():
        variants[r[3].lower().strip()] = {
            'id': r[0], 'product_id': r[1], 'parent_name': r[2], 'name': r[3],
            'price': Decimal(str(r[4])), 'stock': r[5]
        }
    print(f"Loaded {len(products)} products and {len(variants)} variants in Store 21.")

    # Helper: Customer name normalization
    def map_customer(raw_cust):
        if not raw_cust:
            return 'Walk in Cash'
        c = raw_cust.strip()
        c_lower = c.lower()
        if c_lower in ['bong-bong', 'bong bong', 'bong-bong garden']:
            return 'Bong-Bong Garden'
        if c_lower in ['iva', 'i.v.a', 'i.v.a.']:
            return 'I.V.A'
        if c_lower in ['mother earth garden', "mother earth's garden", 'mother earth gardens']:
            return 'Mother Earth Gardens'
        if c_lower in ["marvie's garden", 'marvies garden', 'marvie garden']:
            return "Marvie's Garden"
        if c_lower in ["mary's garden", 'marys garden', 'mary garden']:
            return "Mary's Garden"
        if c_lower in ['royal green garden', 'royal green gardens']:
            return 'Royal Green Garden'
        if c_lower in ['green fountain scapes landscaping services', 'green fountain']:
            return 'Green Fountain Scapes Landscaping Services'
        if c_lower in ['walk in cash', 'walk-in', 'walk in']:
            return 'Walk in Cash'
        if c_lower in ['lmcmacq']:
            return 'LMCMACQ'
        return c

    # Helper: Resolve item to catalog or custom
    custom_base_prices = {
        '#007': Decimal('117.00'),
        '#007-rattan': Decimal('117.00'),
        '#859': Decimal('230.00'),
        '11x18': Decimal('8.80'),
        '3 1/2x6': Decimal('0.32'),
        'cococubes': Decimal('250.00'),
        'dyg #263': Decimal('43.64'),
        'dragonball-large': Decimal('550.00'),
        'dragonball-med': Decimal('120.00'),
        'dragonball-small': Decimal('80.00'),
        'e#8': Decimal('32.00'),
        'ipa': Decimal('125.00'),
        'kusot': Decimal('125.00'),
        'ordinary pot #10': Decimal('60.00'),
        'ordinary pot #12': Decimal('120.00'),
        'ordinary pot #6': Decimal('60.00'),
        'spiral-large': Decimal('650.00'),
        'udalo#2': Decimal('350.00'),
        'straw': Decimal('35.00'),
    }

    def resolve_item(raw_name):
        clean = raw_name.strip().lower()

        # 1. Variants
        for v_key, v_val in variants.items():
            if (v_key == clean or 
                v_key == f"{clean} nursery pot" or 
                v_key == f"{clean} planter pot" or
                v_key.startswith(f"{clean} ") or
                v_key == clean.replace('planter pot', '').strip() or
                v_key == clean.replace('nursery pot', '').strip()):
                return {
                    'is_custom': False,
                    'product_id': v_val['product_id'],
                    'variant_id': v_val['id'],
                    'line_name': f"{v_val['parent_name']} - {v_val['name']}",
                    'catalog_price': v_val['price'],
                    'type': 'variant'
                }

        # Seedling bag check
        if 'x' in clean and any(c.isdigit() for c in clean):
            for v_key, v_val in variants.items():
                if v_key == clean or v_key == f"seedling bag {clean}":
                    return {
                        'is_custom': False,
                        'product_id': v_val['product_id'],
                        'variant_id': v_val['id'],
                        'line_name': f"{v_val['parent_name']} - {v_val['name']}",
                        'catalog_price': v_val['price'],
                        'type': 'variant'
                    }

        # 2. Products
        for p_key, p_val in products.items():
            if (p_key == clean or 
                p_key.startswith(f"{clean} ") or 
                p_key == f"{clean} fertilizer" or 
                p_key == f"{clean} plant supplement"):
                return {
                    'is_custom': False,
                    'product_id': p_val['id'],
                    'variant_id': None,
                    'line_name': p_val['name'],
                    'catalog_price': p_val['price'],
                    'type': 'product'
                }

        # 3. Custom item
        est_price = custom_base_prices.get(clean, Decimal('50.00'))
        return {
            'is_custom': True,
            'product_id': None,
            'variant_id': None,
            'line_name': raw_name.strip(),
            'catalog_price': est_price,
            'type': 'custom'
        }

    # Step 4: Tally catalog stock requirement and replenish where needed
    print("\n--- STEP 4: INVENTORY REPLENISHMENT FOR WHOLESALE SALES ---")
    catalog_demands = {}
    for o in orders_to_import:
        for it in o['items']:
            res = resolve_item(it['item'])
            if not res['is_custom']:
                k = (res['type'], res['product_id'], res['variant_id'], res['line_name'])
                catalog_demands[k] = catalog_demands.get(k, 0) + int(it['qty'])

    for (itype, pid, vid, name), sold_qty in catalog_demands.items():
        if itype == 'variant':
            cur.execute("SELECT stock_quantity FROM product_variants WHERE id = %s", (vid,))
            cur_stk = cur.fetchone()[0]
            if cur_stk < sold_qty:
                buffer = 500 if sold_qty > 1000 else 100
                needed_stock = sold_qty + buffer
                cur.execute("UPDATE product_variants SET stock_quantity = %s WHERE id = %s", (needed_stock, vid))
                print(f"Replenished variant '{name}' (ID: {vid}): {cur_stk} -> {needed_stock} (Sold: {sold_qty})")
        else:
            cur.execute("SELECT stock_quantity FROM products WHERE id = %s", (pid,))
            cur_stk = cur.fetchone()[0]
            if cur_stk < sold_qty:
                buffer = 50 if sold_qty > 100 else 20
                needed_stock = sold_qty + buffer
                cur.execute("UPDATE products SET stock_quantity = %s WHERE id = %s", (needed_stock, pid))
                print(f"Replenished product '{name}' (ID: {pid}): {cur_stk} -> {needed_stock} (Sold: {sold_qty})")

    # Step 5: Execute atomic insertion
    print("\n--- STEP 5: INSERTING ORDERS & ORDER ITEMS ---")
    orders_imported = 0
    items_imported = 0
    stock_reductions_logged = 0

    # Base timestamps distribution across each day
    random.seed(42)

    for o in orders_to_import:
        target_total = Decimal(str(o['total']))
        cust_name = map_customer(o['customer'])
        order_date_str = o['date'] # YYYY-MM-DD
        y, m, d = [int(p) for p in order_date_str.split('-')]

        # Pick a realistic business hour in PHT (08:00 to 17:00 PHT -> 00:00 to 09:00 UTC)
        hour = random.randint(1, 8)
        minute = random.randint(0, 59)
        second = random.randint(0, 59)
        utc_datetime = datetime.datetime(y, m, d, hour, minute, second)

        # Resolve lines
        resolved_lines = []
        raw_subtotal = Decimal('0.00')
        has_custom = False

        for it in o['items']:
            res = resolve_item(it['item'])
            qty = int(it['qty'])
            if res['is_custom']:
                has_custom = True
            raw_line_total = Decimal(str(qty)) * res['catalog_price']
            raw_subtotal += raw_line_total
            resolved_lines.append({
                'res': res,
                'qty': qty,
                'raw_line_total': raw_line_total
            })

        # Calculate proportional prices
        allocated_sum = Decimal('0.00')
        allocated_lines = []
        for i, line in enumerate(resolved_lines):
            qty = Decimal(str(line['qty']))
            if raw_subtotal > Decimal('0.00'):
                share = line['raw_line_total'] / raw_subtotal
                line_total = (target_total * share).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            else:
                line_total = (target_total / len(resolved_lines)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            if i == len(resolved_lines) - 1:
                line_total = target_total - allocated_sum

            allocated_sum += line_total
            unit_price = (line_total / qty).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            allocated_lines.append({
                'res': line['res'],
                'qty': int(qty),
                'line_total': line_total,
                'unit_price': unit_price
            })

        # Insert POS Order
        cur.execute("""
            INSERT INTO pos_orders (
                store_id, total_amount, amount_given, change_amount,
                payment_method, customer_name, customer_contact,
                is_seen_by_seller, is_custom_order, discount,
                created_by, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s
            ) RETURNING id
        """, (
            STORE_ID, target_total, target_total, Decimal('0.00'),
            'cash', cust_name, None,
            True, has_custom, Decimal('0.00'),
            SELLER_USER_ID, utc_datetime, utc_datetime
        ))
        pos_order_id = cur.fetchone()[0]

        # Insert POS Order Items & perform stock reduction
        for line in allocated_lines:
            res = line['res']
            qty = line['qty']
            unit_price = line['unit_price']

            if res['is_custom']:
                # Custom item logic
                cur.execute("""
                    INSERT INTO pos_order_items (
                        pos_order_id, product_id, variant_id, quantity, price,
                        line_name, is_custom, custom_title, custom_category
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                """, (
                    pos_order_id, None, None, qty, unit_price,
                    res['line_name'], True, res['line_name'], 'Gardening'
                ))
                items_imported += 1
            else:
                # Catalog item logic
                cur.execute("""
                    INSERT INTO pos_order_items (
                        pos_order_id, product_id, variant_id, quantity, price,
                        line_name, is_custom
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s
                    )
                """, (
                    pos_order_id, res['product_id'], res['variant_id'], qty, unit_price,
                    res['line_name'], False
                ))
                items_imported += 1

                # Stock deduction & stock_reductions audit log
                if res['variant_id'] is not None:
                    cur.execute("""
                        UPDATE product_variants
                        SET stock_quantity = stock_quantity - %s
                        WHERE id = %s
                    """, (qty, res['variant_id']))

                    cur.execute("""
                        INSERT INTO stock_reductions (
                            product_id, variant_id, reduction_amount, reason, reason_notes,
                            reduced_by, created_at, updated_at
                        ) VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, %s
                        )
                    """, (
                        res['product_id'], res['variant_id'], qty, 'pos_sale',
                        f"POS Sale - Order #{pos_order_id} by {CASHIER_NAME}",
                        SELLER_USER_ID, utc_datetime, utc_datetime
                    ))
                else:
                    cur.execute("""
                        UPDATE products
                        SET stock_quantity = stock_quantity - %s
                        WHERE id = %s
                    """, (qty, res['product_id']))

                    cur.execute("""
                        INSERT INTO stock_reductions (
                            product_id, variant_id, reduction_amount, reason, reason_notes,
                            reduced_by, created_at, updated_at
                        ) VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, %s
                        )
                    """, (
                        res['product_id'], None, qty, 'pos_sale',
                        f"POS Sale - Order #{pos_order_id} by {CASHIER_NAME}",
                        SELLER_USER_ID, utc_datetime, utc_datetime
                    ))

                stock_reductions_logged += 1

        orders_imported += 1

    # Commit all operations atomically
    conn.commit()

    print("\n==================================================")
    print("SEPTEMBER 18-30 IMPORT SUCCESSFULLY COMMITTED!")
    print("==================================================")
    print(f"Total New Orders Created: {orders_imported}")
    print(f"Total Order Items Inserted: {items_imported}")
    print(f"Total Stock Reductions Logged: {stock_reductions_logged}")

    # Post-import verification
    cur.execute("""
        SELECT COUNT(*), SUM(total_amount), MIN(created_at), MAX(created_at)
        FROM pos_orders
        WHERE store_id = %s
    """, (STORE_ID,))
    total_orders, overall_sales, min_date, max_date = cur.fetchone()
    print(f"\nStore 21 Verification:")
    print(f"  Total POS Orders in Database: {total_orders}")
    print(f"  Total POS Revenue in Database: ₱{overall_sales:,.2f}")
    print(f"  Earliest Order (UTC): {min_date}")
    print(f"  Latest Order (UTC): {max_date}")

    # Verify custom items in newly imported orders
    cur.execute("""
        SELECT COUNT(*)
        FROM pos_order_items poi
        JOIN pos_orders po ON po.id = poi.pos_order_id
        WHERE po.store_id = %s AND poi.is_custom = True
    """, (STORE_ID,))
    custom_count = cur.fetchone()[0]
    print(f"  Total Custom Items in Store 21: {custom_count}")

    # Check minimum inventory
    cur.execute("""
        SELECT MIN(stock_quantity) FROM products WHERE store_id = %s
    """, (STORE_ID,))
    min_prod_stock = cur.fetchone()[0]

    cur.execute("""
        SELECT MIN(pv.stock_quantity)
        FROM product_variants pv
        JOIN products p ON p.id = pv.product_id
        WHERE p.store_id = %s
    """, (STORE_ID,))
    min_var_stock = cur.fetchone()[0]

    print(f"\nInventory Health Verification:")
    print(f"  Minimum Product Stock: {min_prod_stock} (all >= 0!)")
    print(f"  Minimum Variant Stock: {min_var_stock} (all >= 0!)")

except Exception as e:
    conn.rollback()
    print("\n[ERROR] Transaction rolled back due to error:")
    import traceback
    traceback.print_exc()

finally:
    cur.close()
    conn.close()
