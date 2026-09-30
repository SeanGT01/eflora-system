import os, sys
sys.stdout.reconfigure(encoding='utf-8')
import datetime
import random
import psycopg2
from decimal import Decimal

# Connect to database
conn = psycopg2.connect('postgresql://postgres:cb346bB6Cf15eeg3BECf3FG5Dd6DF43e@nozomi.proxy.rlwy.net:24071/railway')
cur = conn.cursor()

# 1. Load parsed orders from solve_prices
from solve_prices import orders, sol, item_to_idx, exact_prices

print(f"Total parsed orders to import: {len(orders)}")
print(f"Total unique products to create: {len(item_to_idx)}")

# Check if any products already exist for store 21 with these names
cur.execute("SELECT id, name, price, stock_quantity FROM products WHERE store_id = 21")
existing_products = {r[1].lower(): (r[0], r[1], float(r[2]), r[3]) for r in cur.fetchall()}
print(f"Existing products in Store 21: {len(existing_products)}")

# Calculate total quantity needed for each item
total_sold_per_item = {}
for o in orders:
    for it in o['items']:
        name = it['item']
        total_sold_per_item[name] = total_sold_per_item.get(name, 0) + int(it['qty'])

print("\nSample Item totals sold & prices:")
for name in sorted(item_to_idx.keys())[:15]:
    price = round(sol[item_to_idx[name]], 2)
    sold = total_sold_per_item.get(name, 0)
    print(f"  {name:25s} | Price: ₱{price:7.2f} | Sold: {sold:5d} pcs")

conn.close()
