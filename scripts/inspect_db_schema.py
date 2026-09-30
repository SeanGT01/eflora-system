import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres:cb346bB6Cf15eeg3BECf3FG5Dd6DF43e@nozomi.proxy.rlwy.net:24071/railway')
cur = conn.cursor()

# Get columns of stores
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'stores'")
cols = [r[0] for r in cur.fetchall()]
print('Stores columns:', cols)

cur.execute("SELECT * FROM stores WHERE id = 21")
row = cur.fetchone()
store_dict = dict(zip(cols, row))
print('\nStore 21 data:')
for k, v in store_dict.items():
    print(f"  {k}: {v}")

# Get columns of products
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'products'")
prod_cols = [r[0] for r in cur.fetchall()]
print('\nProducts columns:', prod_cols)

# Get columns of pos_orders
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'pos_orders'")
pos_cols = [r[0] for r in cur.fetchall()]
print('\nPOS Orders columns:', pos_cols)

# Get columns of pos_order_items
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'pos_order_items'")
pos_item_cols = [r[0] for r in cur.fetchall()]
print('\nPOS Order Items columns:', pos_item_cols)

# Get columns of stock_reductions
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'stock_reductions'")
stock_cols = [r[0] for r in cur.fetchall()]
print('\nStock Reductions columns:', stock_cols)

# Check recent POS orders
cur.execute("SELECT id, created_at, total_amount, customer_name, created_by FROM pos_orders ORDER BY id DESC LIMIT 5")
print('\nRecent POS orders:', cur.fetchall())

conn.close()
