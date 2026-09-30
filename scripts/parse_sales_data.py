import zipfile
import xml.etree.ElementTree as ET
import os

path = r'C:\Users\seanm\OneDrive\Documents\Sales data for POS.xlsx'

with zipfile.ZipFile(path) as z:
    # 1. Parse shared strings
    shared_strings = []
    if 'xl/sharedStrings.xml' in z.namelist():
        tree = ET.fromstring(z.read('xl/sharedStrings.xml'))
        for si in tree.findall('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si'):
            # Text can be in <t> or nested in <r><t>
            texts = [t.text or '' for t in si.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t')]
            shared_strings.append(''.join(texts))

    # 2. Parse sheet1.xml
    sheet_tree = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
    ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    rows_data = []

    for row in sheet_tree.findall('.//ns:row', ns):
        row_num = row.attrib.get('r')
        cells = {}
        for c in row.findall('ns:c', ns):
            ref = c.attrib.get('r', '')
            # Extract col letters
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
                # inline string
                is_tag = c.find('ns:is/ns:t', ns)
                if is_tag is not None:
                    val = is_tag.text
            cells[col_letters] = val
        rows_data.append((row_num, cells))

print(f"Total rows parsed: {len(rows_data)}")
for r_num, cells in rows_data[:40]:
    print(f"Row {r_num}: {cells}")
