import sys
import random
from datetime import datetime, time, timedelta
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

from app import create_app, db
from app.models import POSOrder

app = create_app()

with app.app_context():
    # Only store_id = 18 (AKS Coop Flowershop)
    orders = POSOrder.query.filter_by(store_id=18).order_by(POSOrder.id).all()
    print(f"Found {len(orders)} POS orders for AKS Coop (Store ID: 18).\n")

    # In Philippine Time (UTC+8), the user wants 8:00 AM (08:00) to 5:00 PM (17:00).
    # Since the DB stores naive UTC timestamps:
    # 08:00 AM PHT - 8 hours = 00:00:00 UTC (12:00 AM UTC)
    # 05:00 PM PHT - 8 hours = 09:00:00 UTC (09:00 AM UTC)
    #
    # When displayed in PHT:
    # 00:00 UTC + 8h = 08:00 AM PHT
    # 09:00 UTC + 8h = 05:00 PM PHT
    START_SEC_UTC = 0          # 00:00:00 UTC -> 08:00:00 AM PHT
    END_SEC_UTC = 9 * 3600     # 09:00:00 UTC -> 05:00:00 PM PHT

    # Group orders by their intended calendar date
    orders_by_date = defaultdict(list)
    for o in orders:
        orders_by_date[o.created_at.date()].append(o)

    changes = []
    for order_date, day_orders in sorted(orders_by_date.items()):
        count = len(day_orders)
        # Sample unique random seconds between 00:00:00 UTC and 09:00:00 UTC
        random_seconds = sorted(random.sample(range(START_SEC_UTC, END_SEC_UTC + 1), count))
        
        for o, sec in zip(day_orders, random_seconds):
            h = sec // 3600
            m = (sec % 3600) // 60
            s = sec % 60
            us = random.randint(100000, 999999)
            
            old_dt = o.created_at
            # Store UTC timestamp
            new_utc_dt = datetime.combine(order_date, time(h, m, s, us))
            o.created_at = new_utc_dt
            o.updated_at = new_utc_dt
            
            # Equivalent PHT timestamp (UTC + 8 hours)
            pht_dt = new_utc_dt + timedelta(hours=8)
            changes.append((o.id, o.customer_name, new_utc_dt, pht_dt))

    db.session.commit()
    print("Successfully committed updated timestamps!\n")

    print(f"{'Order ID':<10} | {'Customer':<25} | {'DB UTC Timestamp':<28} | {'Displayed PHT Time (Dashboard)':<28}")
    print("-" * 105)
    for oid, cust, utc_dt, pht_dt in changes:
        print(f"{oid:<10} | {str(cust):<25} | {str(utc_dt):<28} | {str(pht_dt):<28}")

    print("\nVerification of PHT display time:")
    all_valid = all(time(8, 0, 0) <= (o.created_at + timedelta(hours=8)).time() <= time(17, 0, 0) for o in orders)
    print(f"All orders strictly between 08:00:00 and 17:00:00 PHT: {all_valid}")
