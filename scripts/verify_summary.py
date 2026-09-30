import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2, datetime

conn = psycopg2.connect('postgresql://postgres:cb346bB6Cf15eeg3BECf3FG5Dd6DF43e@nozomi.proxy.rlwy.net:24071/railway')
cur = conn.cursor()

cur.execute('''
    SELECT o.id, o.customer_name, o.total_amount, o.created_at, count(i.id)
    FROM pos_orders o
    JOIN pos_order_items i ON i.pos_order_id = o.id
    WHERE o.store_id = 21
    GROUP BY o.id, o.customer_name, o.total_amount, o.created_at
    ORDER BY o.created_at ASC
    LIMIT 6
''')

print("Sample Verified Imported Orders:")
for r in cur.fetchall():
    pht = r[3] + datetime.timedelta(hours=8)
    print(f"  Order #{r[0]} | {r[1]:30s} | ₱{r[2]:>9.2f} | {pht.strftime('%b %d, %Y  %I:%M:%S %p')} PHT | Items: {r[4]}")

cur.execute('''
    SELECT count(*) FROM stock_reductions sr
    JOIN products p ON sr.product_id = p.id
    WHERE p.store_id = 21 AND sr.reason = 'pos_sale'
''')
print(f"\nTotal Stock Reduction audit entries logged for Store 21: {cur.fetchone()[0]}")

cur.execute('''
    SELECT count(*), min(stock_quantity), max(stock_quantity) FROM products WHERE store_id = 21
''')
prod_cnt, min_s, max_s = cur.fetchone()
print(f"Total Products in Store 21: {prod_cnt} (Min stock: {min_s}, Max stock: {max_s})")

conn.close()
