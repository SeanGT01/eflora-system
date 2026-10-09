import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.stdout.reconfigure(encoding='utf-8')

from sqlalchemy import func
from app import create_app, db
from app.models import Store, Order, OrderItem, ProductRating, StoreRating, StockReduction, Rider

app = create_app()

with app.app_context():
    print("=" * 80)
    print("📊 ONLINE ORDER SIMULATION V2 VERIFICATION")
    print("=" * 80)

    stores = [
        (21, "Princess Rasec Botanical Garden", 6),
        (18, "AKS Coop Flowershop", 4),
        (22, "Speaking Flowers", 1)
    ]

    total_orders_verified = 0

    for sid, name, expected_count in stores:
        orders = Order.query.filter_by(store_id=sid, order_type='online').order_by(Order.id).all()
        total_rev = sum(float(o.total_amount or 0) for o in orders)
        riders = Rider.query.filter_by(store_id=sid, is_archived=False).all()
        rider_names = [r.user.full_name for r in riders if r.user]
        
        # Store ratings
        s_ratings = StoreRating.query.filter_by(store_id=sid).all()
        avg_s_rating = (sum(r.rating for r in s_ratings) / len(s_ratings)) if s_ratings else 0

        print(f"\n🏪 Store {sid}: {name}")
        print(f"  • Expected Orders: {expected_count} | Actual Online Orders: {len(orders)}")
        print(f"  • Active Riders: {', '.join(rider_names)}")
        print(f"  • Online Revenue: ₱{total_rev:,.2f}")
        print(f"  • Store Reviews: {len(s_ratings)} (Average: {avg_s_rating:.2f} ⭐)")
        
        total_orders_verified += len(orders)

        print(f"  • Detailed Orders:")
        for o in orders:
            item_names = [f"{i.product_name} (x{i.quantity})" for i in o.items]
            has_done_prep_img = bool(o.done_preparing_proof_url)
            has_del_img = bool(o.delivery_proof_url)
            has_payment_img = bool(o.payment_proof_url)
            print(f"    - Order #{o.id:3d} | ₱{float(o.total_amount):8.2f} | Pay: {o.payment_method:5s} ({o.payment_status:12s}) | PrepProof: {has_done_prep_img} | DelProof: {has_del_img} | PayReceipt: {has_payment_img}")
            print(f"      Items: {', '.join(item_names)}")
            print(f"      Customer: {o.customer.full_name} ({o.customer.email})")
            if o.payment_proof_url:
                print(f"      GCash Receipt URL: {o.payment_proof_url}")
            print(f"      Done Prep URL:     {o.done_preparing_proof_url}")
            print(f"      Rider Proof URL:   {o.delivery_proof_url}")

    print("\n" + "=" * 80)
    print(f"Total Online Orders Created & Verified: {total_orders_verified}/11")
    
    # Check total product ratings
    p_ratings = ProductRating.query.count()
    print(f"Total Product Ratings in Database: {p_ratings}")
    
    # Check stock reductions
    reductions = StockReduction.query.filter(StockReduction.reason_notes.like('%Online order%')).count()
    print(f"Total Online Order Stock Reductions: {reductions}")
    print("=" * 80)
