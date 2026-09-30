import zipfile
import xml.etree.ElementTree as ET
import datetime
import numpy as np
import sys
sys.stdout.reconfigure(encoding='utf-8')

path = r'C:\Users\seanm\OneDrive\Documents\Sales data for POS.xlsx'

with zipfile.ZipFile(path) as z:
    shared_strings = []
    if 'xl/sharedStrings.xml' in z.namelist():
        tree = ET.fromstring(z.read('xl/sharedStrings.xml'))
        for si in tree.findall('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si'):
            texts = [t.text or '' for t in si.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t')]
            shared_strings.append(''.join(texts))

    sheet_tree = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
    ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    rows_data = []

    for row in sheet_tree.findall('.//ns:row', ns):
        row_num = int(row.attrib.get('r'))
        cells = {}
        for c in row.findall('ns:c', ns):
            ref = c.attrib.get('r', '')
            col_letters = ''.join([ch for ch in ref if ch.isalpha()])
            t = c.attrib.get('t')
            v_tag = c.find('ns:v', ns)
            val = v_tag.text if v_tag is not None else None
            if val is not None:
                if t == 's':
                    val = shared_strings[int(val)]
                elif t == 'b':
                    val = bool(int(val))
            else:
                is_tag = c.find('ns:is/ns:t', ns)
                if is_tag is not None:
                    val = is_tag.text
            cells[col_letters] = val
        rows_data.append((row_num, cells))

orders = []
current_order = None
prev_row = None
last_known_date = None

for row_num, cells in rows_data:
    if row_num == 1:
        continue
    
    is_new_order = False
    if prev_row is not None and row_num > prev_row + 1:
        is_new_order = True
    elif 'A' in cells and cells['A']:
        if current_order and current_order.get('total') is not None:
            is_new_order = True

    if is_new_order:
        if current_order:
            orders.append(current_order)
            current_order = None

    if current_order is None:
        raw_date = cells.get('A')
        if raw_date:
            try:
                date_obj = datetime.date(1899, 12, 30) + datetime.timedelta(days=int(float(raw_date)))
                last_known_date = str(date_obj)
            except:
                last_known_date = str(raw_date)
        current_order = {
            'order_idx': len(orders) + 1,
            'start_row': row_num,
            'end_row': row_num,
            'date': last_known_date,
            'items': [],
            'total': None,
            'customer': None
        }

    current_order['end_row'] = row_num
    qty = float(cells.get('B', 1)) if cells.get('B') else 1.0
    item_name = str(cells.get('C', '')).strip()
    if item_name and item_name != 'None':
        # Normalize uppercase variations like 6X12 -> 6x12
        norm_item = item_name.lower() if 'x' in item_name.lower() and any(c.isdigit() for c in item_name) else item_name
        current_order['items'].append({'row': row_num, 'orig_item': item_name, 'item': norm_item, 'qty': qty})

    if 'D' in cells and cells['D']:
        try:
            current_order['total'] = float(cells['D'])
        except:
            current_order['total'] = cells['D']
    if 'E' in cells and cells['E']:
        current_order['customer'] = str(cells['E']).strip()

    prev_row = row_num

if current_order:
    orders.append(current_order)

# Build inventory of all items
item_names = sorted(list(set(it['item'] for o in orders for it in o['items'])))
item_to_idx = {name: i for i, name in enumerate(item_names)}
num_items = len(item_names)

print(f"Total Unique Normalized Items: {num_items}")

# Filter valid orders with total
valid_orders = [o for o in orders if o['total'] is not None and len(o['items']) > 0]
print(f"Valid Orders with Total: {len(valid_orders)}")

# Check exact single item orders
exact_prices = {}
for o in valid_orders:
    if len(o['items']) == 1:
        it = o['items'][0]
        p = round(o['total'] / it['qty'], 4)
        if it['item'] not in exact_prices:
            exact_prices[it['item']] = []
        exact_prices[it['item']].append((p, o['order_idx']))

print("\nExact Single-Item Prices found:")
for it, p_list in sorted(exact_prices.items()):
    prices_str = ", ".join([f"₱{p} (Order #{oid})" for p, oid in p_list])
    print(f"  {it:25s}: {prices_str}")

# Set up linear system: A * x = b
# with bounds x >= 0 (using scipy.optimize.lsq_linear or nnls)
from scipy.optimize import lsq_linear

A = np.zeros((len(valid_orders), num_items))
b = np.zeros(len(valid_orders))

for i, o in enumerate(valid_orders):
    b[i] = o['total']
    for it in o['items']:
        j = item_to_idx[it['item']]
        A[i, j] += it['qty']

res = lsq_linear(A, b, bounds=(0.01, 10000.0), lsmr_tol='auto')
sol = res.x

print("\n--- CALCULATED ITEM PRICES (LSQ / Exact Solved) ---")
results = []
for name, idx in sorted(item_to_idx.items()):
    price = sol[idx]
    # Check if exact single item exists
    exact = exact_prices.get(name)
    results.append({
        'name': name,
        'calculated_price': round(price, 2),
        'exact': [p for p, _ in exact] if exact else None
    })
    exact_marker = f" [EXACT: ₱{exact[0][0]:.2f}]" if exact else ""
    print(f"  {name:30s} : ₱{price:8.2f}{exact_marker}")

# Check order reconstruction errors
print("\n--- ORDER RECONSTRUCTION VERIFICATION ---")
errors = []
for i, o in enumerate(valid_orders):
    calc_total = sum(sol[item_to_idx[it['item']]] * it['qty'] for it in o['items'])
    diff = calc_total - o['total']
    errors.append(abs(diff))
    if abs(diff) > 5.0:
        print(f"  Order #{o['order_idx']:02d} [Row {o['start_row']}] {o['customer']}: Actual=₱{o['total']}, Calc=₱{calc_total:.2f} (Diff: ₱{diff:+.2f})")

print(f"\nAverage absolute difference across {len(valid_orders)} orders: ₱{np.mean(errors):.2f}")
print(f"Max absolute difference: ₱{np.max(errors):.2f}")
