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

# Group orders: whenever row_num > prev_row + 1 OR Col A has a date when previous order has total
orders = []
current_order = None
prev_row = None
last_known_date = None

for row_num, cells in rows_data:
    if row_num == 1:
        continue # header
    
    # Check if this starts a new order:
    is_new_order = False
    if prev_row is not None and row_num > prev_row + 1:
        is_new_order = True
    elif 'A' in cells and cells['A']:
        # If we have current_order and it already has a total
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
    if item_name:
        current_order['items'].append({'row': row_num, 'item': item_name, 'qty': qty})

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

print(f"Total parsed orders: {len(orders)}\n")
for o in orders:
    items_str = ", ".join([f"{it['item']} (x{int(it['qty']) if it['qty'].is_integer() else it['qty']})" for it in o['items']])
    print(f"Order #{o['order_idx']:02d} [Rows {o['start_row']}-{o['end_row']}] | {o['date']} | Cust: {o['customer']} | Total: {o['total']} | Items: {items_str}")
