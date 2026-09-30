import zipfile
import xml.etree.ElementTree as ET
import datetime

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

# Now group into orders
# Look at headers: row 1
header = rows_data[0][1]
print("Header:", header)

orders = []
current_order = None

for r_num, cells in rows_data[1:]:
    # A blank row might separate orders, or a row with Date/Customer/Total
    # Let's see: if cells is empty or has no item:
    if not cells or 'C' not in cells or not cells['C']:
        if current_order and current_order['items']:
            orders.append(current_order)
            current_order = None
        continue

    # If row has Date in col A, or if we don't have current_order:
    if current_order is None or ('A' in cells and cells['A']):
        # If we had a previous order without a blank line but new date:
        if current_order and current_order['items'] and ('A' in cells and cells['A'] and 'D' in current_order and current_order['total'] is not None):
            orders.append(current_order)
            current_order = None

    if current_order is None:
        raw_date = cells.get('A')
        date_str = None
        if raw_date:
            try:
                date_obj = datetime.date(1899, 12, 30) + datetime.timedelta(days=int(float(raw_date)))
                date_str = str(date_obj)
            except:
                date_str = str(raw_date)
        current_order = {
            'first_row': r_num,
            'date_raw': raw_date,
            'date': date_str,
            'items': [],
            'total': None,
            'customer': None
        }

    qty = float(cells.get('B', 1))
    item_name = str(cells.get('C', '')).strip()
    current_order['items'].append({'row': r_num, 'item': item_name, 'qty': qty})

    if 'D' in cells and cells['D']:
        try:
            current_order['total'] = float(cells['D'])
        except:
            current_order['total'] = cells['D']
    if 'E' in cells and cells['E']:
        current_order['customer'] = str(cells['E']).strip()

if current_order and current_order['items']:
    orders.append(current_order)

print(f"\nTotal Orders Found: {len(orders)}")
all_items = set()
for i, o in enumerate(orders, 1):
    items_desc = ", ".join([f"{it['item']} (x{int(it['qty']) if it['qty'].is_integer() else it['qty']})" for it in o['items']])
    for it in o['items']:
        all_items.add(it['item'])
    print(f"Order #{i:02d} [Row {o['first_row']}] | Date: {o['date']} | Cust: {o['customer']} | Total: {o['total']} | Items: {items_desc}")

print(f"\nTotal Unique Items: {len(all_items)}")
print("Unique Items:")
for it in sorted(all_items):
    print(f"  - {it}")
