import os, sys
sys.stdout.reconfigure(encoding='utf-8')
import datetime
import random
import psycopg2
from decimal import Decimal

# Connect to railway DB
conn = psycopg2.connect('postgresql://postgres:cb346bB6Cf15eeg3BECf3FG5Dd6DF43e@nozomi.proxy.rlwy.net:24071/railway')
cur = conn.cursor()

from solve_prices import orders, sol, item_to_idx

print(f"Total orders: {len(orders)}")
print(f"Total items: {len(item_to_idx)}")

# Check existing products in Store 21
cur.execute("SELECT id, name, price, stock_quantity FROM products WHERE store_id = 21")
existing = {r[1].lower(): r[0] for r in cur.fetchall()}
print(f"Existing products in Store 21: {existing}")

# Total sold per item
total_sold = {}
for o in orders:
    for it in o['items']:
        name = it['item']
        total_sold[name] = total_sold.get(name, 0) + int(it['qty'])

# Build item product mapping
def get_clean_title(item_code):
    s = item_code.strip()
    if 'x' in s.lower() and any(c.isdigit() for c in s):
        # Seedling bag dimension
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

# Test product dictionary
product_specs = []
for name, idx in item_to_idx.items():
    clean_name = get_clean_title(name)
    price = round(Decimal(str(sol[idx])), 2)
    if price < Decimal('0.10'):
        price = Decimal('0.14')
    sold_qty = total_sold.get(name, 0)
    # Determine buffer
    if sold_qty > 1000:
        buffer = 1500
    elif sold_qty > 200:
        buffer = 300
    elif sold_qty > 50:
        buffer = 50
    else:
        buffer = 20
    initial_stock = sold_qty + buffer

    # Category determination
    main_cat = 5 # Others
    store_cat = 22 # Gardening
    if any(pot_kw in clean_name.lower() for pot_kw in ['pot', 'planter', 'wallpot', 'basket', 'bonsai', 'fukienta']):
        main_cat = 2 # Potted Plants
        store_cat = 22 # Gardening
    elif any(tool_kw in clean_name.lower() for tool_kw in ['shear', 'sprayer', 'wire']):
        main_cat = 5 # Others
        store_cat = 21 # Tools

    product_specs.append({
        'orig_code': name,
        'clean_name': clean_name,
        'price': price,
        'initial_stock': initial_stock,
        'sold_qty': sold_qty,
        'remaining_stock': buffer,
        'main_cat': main_cat,
        'store_cat': store_cat
    })

print(f"\nGenerated specs for {len(product_specs)} products.")
print("Sample product specs:")
for ps in product_specs[:10]:
    print(f"  {ps['orig_code']:15s} -> {ps['clean_name']:32s} | ₱{ps['price']:6.2f} | Init: {ps['initial_stock']:5d} | Sold: {ps['sold_qty']:5d} | Rem: {ps['remaining_stock']:5d}")

# Simulate order dates and times
random.seed(42) # deterministic for reproducibility
print("\n--- SAMPLE ORDER SIMULATION PREVIEW (First 5 orders) ---")
for o in orders[:5]:
    # Parse date
    d_obj = datetime.date.fromisoformat(o['date'])
    h_pht = random.randint(8, 16)
    m = random.randint(0, 59)
    s = random.randint(0, 59)
    # Convert PHT to UTC: PHT = UTC+8, so UTC = PHT - 8
    utc_dt = datetime.datetime.combine(d_obj, datetime.time(h_pht - 8, m, s))
    pht_dt_str = f"{d_obj} {h_pht:02d}:{m:02d}:{s:02d} PHT"
    
    # Calculate item lines
    line_strs = []
    calc_order_total = Decimal('0.00')
    for it in o['items']:
        code = it['item']
        qty = Decimal(str(int(it['qty'])))
        # Find price
        ps = next(p for p in product_specs if p['orig_code'] == code)
        line_total = qty * ps['price']
        calc_order_total += line_total
        line_strs.append(f"{ps['clean_name']} (x{int(qty)} @ ₱{ps['price']} = ₱{line_total:.2f})")
    
    diff = calc_order_total - Decimal(str(o['total']))
    print(f"\nOrder #{o['order_idx']} | Date: {pht_dt_str} (UTC: {utc_dt})")
    print(f"  Customer: {o['customer']}")
    print(f"  Excel Total: ₱{o['total']:.2f} | Calculated: ₱{calc_order_total:.2f} (Diff: ₱{diff:+.2f})")
    print("  Lines: " + "; ".join(line_strs[:3]))

conn.close()
print("\nDry-run simulation script executed successfully!")
