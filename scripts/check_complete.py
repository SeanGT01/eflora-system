import sys
sys.stdout.reconfigure(encoding='utf-8')
from solve_prices import orders

print("Orders with Complete or Complete 14-14-14:")
for o in orders:
    for it in o['items']:
        if 'complete' in it['item'].lower():
            oid = o['order_idx']
            cust = o['customer']
            tot = o['total']
            item = it['orig_item']
            qty = it['qty']
            d = o['date']
            items_in_order = [f"{x['item']} (x{int(x['qty'])})" for x in o['items']]
            print(f"Order #{oid:02d} | Date: {d} | Customer: {cust} | Total: ₱{tot:.2f}")
            print(f"  Target line: {item} (x{int(qty)})")
            print(f"  All items: {', '.join(items_in_order)}\n")
