import os
import sys
import json
import random
from datetime import datetime, timedelta, time
from decimal import Decimal

sys.stdout.reconfigure(encoding='utf-8')

from werkzeug.security import generate_password_hash
from app import create_app, db
from app.models import (
    Store, Product, ProductVariant, Rider, User, Order, OrderItem,
    StoreRating, ProductRating, StockReduction, OrderAnalytics
)

app = create_app()

MANIFEST_FILE = os.path.join(os.path.dirname(__file__), 'simulation_manifest.json')
SQL_UNDO_FILE = os.path.join(os.path.dirname(__file__), 'undo_simulation.sql')

# Realistic customer data
CUSTOMERS_DATA = [
    {"name": "Maria Carmela Reyes", "email": "carmela.reyes.ph@gmail.com", "phone": "09173421890", "address": "Block 4 Lot 12, Villa Zaragosa, Barangay Silangan, Calauan, Laguna", "lat": 14.1485, "lng": 121.3150},
    {"name": "Jayson Mark Castro", "email": "jayson.castro.laguna@gmail.com", "phone": "09189214732", "address": "78 J. Rizal St., Poblacion, Luisiana, Laguna", "lat": 14.1873, "lng": 121.5120},
    {"name": "Claire Anne Villanueva", "email": "claire.anne.villanueva@gmail.com", "phone": "09204561289", "address": "Unit 2B, Greenhills Subdivision, San Pablo City, Laguna", "lat": 14.0682, "lng": 121.3255},
    {"name": "Paulo Vincent Dela Cruz", "email": "paulo.delacruz91@gmail.com", "phone": "09165558901", "address": "Zone 3, Barangay Dayap, Calauan, Laguna", "lat": 14.1520, "lng": 121.3210},
    {"name": "Bea Bianca Alvarez", "email": "bea.alvarez.ph@gmail.com", "phone": "09198762341", "address": "15 Mabini St., Barangay Sto. Domingo, Bay, Laguna", "lat": 14.1812, "lng": 121.2840},
    {"name": "Kenneth Joshua Ramos", "email": "kenneth.ramos.ph@gmail.com", "phone": "09278893412", "address": "Sitio Ilaya, Barangay San Buenaventura, Luisiana, Laguna", "lat": 14.1920, "lng": 121.5180},
    {"name": "Angela Mae Soriano", "email": "angela.soriano24@gmail.com", "phone": "09153327618", "address": "Purok 5, Barangay Kanluran Kabubuhayan, Nagcarlan, Laguna", "lat": 14.1350, "lng": 121.4170},
    {"name": "Arvin John Mendoza", "email": "arvin.mendoza.laguna@gmail.com", "phone": "09176641209", "address": "Lot 8, Palm Grove Estate, Los Baños, Laguna", "lat": 14.1700, "lng": 121.2420},
    {"name": "Kristine Joy Bautista", "email": "kristine.bautista.joy@gmail.com", "phone": "09228901435", "address": "Barangay Lamot 1, Calauan, Laguna", "lat": 14.1430, "lng": 121.3090},
    {"name": "Mark Anthony Navarro", "email": "mark.anthony.navarro88@gmail.com", "phone": "09167784321", "address": "22 Bonifacio St., Pila, Laguna", "lat": 14.2340, "lng": 121.3650},
    {"name": "Stephanie Nicole Perez", "email": "stephanie.perez.ph@gmail.com", "phone": "09182239084", "address": "Barangay San Diego, San Pablo City, Laguna", "lat": 14.0750, "lng": 121.3380},
    {"name": "Danilo Gutierrez Jr.", "email": "danilo.gutierrez.jr@gmail.com", "phone": "09201124567", "address": "Barangay Bangyas, Calauan, Laguna", "lat": 14.1620, "lng": 121.3300}
]

# Realistic Store reviews
STORE_REVIEWS = {
    18: [  # AKS Coop
        (5, "Sobrang ganda po ng bouquet! Very fresh and maayos ang pagka-arrange. Fast delivery din si kuya rider."),
        (5, "Second time ordering from AKS Coop. Consistent ang quality and laging on-time. Highly recommended!"),
        (4, "Maganda yung flowers, nagustuhan ng mama ko for her birthday. Thank you seller sa mabilis na response."),
        (5, "Ang bait ni seller and ni kuya rider. Sinunod po lahat ng requests ko sa dedication card. 10/10!"),
        (5, "Super satisfied customer here! Secure ang packaging at buo ang bulaklak nung dumating."),
        (4, "Nice arrangement, fresh and mabango. Will definitely order again next occasion.")
    ],
    21: [  # Princess Rasec
        (5, "Solid quality ng loam soil at nursery pots! Sobrang kapal at maayos ang balot, walang tapon."),
        (5, "Dumating nang buo at walang basag yung mga paso. Napakabilis din ng delivery dito sa Calauan."),
        (5, "Complete items received. Eto talaga hinahanap kong quality ng plastic planters, pang matagalan."),
        (4, "Good job seller! Well-packaged ang items at accommodating sa mga inquiries. Thank you!"),
        (5, "Suki na ako sa garden supplies nila pero first time ko umorder online. Sobrang convenient!"),
        (5, "Mabait si kuya rider, tinulungan pa ako ibaba yung mabigat na bags ng lupa. Salamat!"),
        (4, "Very high quality planters and fertile soil. Buhay na buhay agad ang mga tanim ko."),
        (5, "Fast transaction! Shipped right on time and very responsive seller. 5 stars!"),
        (5, "Dito na talaga ako palagi bibili ng pots and garden needs ko. Mura at matibay!")
    ],
    22: [  # Speaking Flowers
        (5, "Napaka-romantic nung Valentine rose bouquet! Tuwang-tuwa si girlfriend, fresh na fresh ang petals."),
        (5, "High-end presentation and premium quality roses. Kumpleto kasama chocolate, safe na nakarating."),
        (5, "Best flower shop in town! Maayos ang delivery at napakaganda ng actual arrangement kumpara sa picture.")
    ]
}

PRODUCT_REVIEWS = [
    (5, "Gandang-ganda ako sa item, fresh and true to picture. Walang damage pagdating."),
    (5, "Super nice quality! Packed with care and exactly as described. Sulit ang bayad."),
    (4, "Very good quality, matibay at maayos ang pagkakagawa. Thank you seller!"),
    (5, "Love it so much! Perfect gift and excellent customer service."),
    (5, "Satisfied buyer here, maayos ang packaging at mabilis dumating."),
    (4, "Ganda ng pagkaka-wrap, mabango at maaliwalas. Recommended product!"),
    (5, "10/10 highly recommended! Deserves 5 stars."),
    (5, "Sobrang sulit! Will order again soon.")
]

# Real Cloudinary assets from existing DB
DEFAULT_GCASH_PROOFS = [
    "https://res.cloudinary.com/dgyq49vi2/image/upload/v1789115952/e-flowers/payments/gcash_receipt_sample_01.jpg",
    "https://res.cloudinary.com/dgyq49vi2/image/upload/v1789116928/e-flowers/payments/gcash_receipt_sample_02.jpg",
    "https://res.cloudinary.com/dgyq49vi2/image/upload/v1789019123/e-flowers/payments/gcash_receipt_sample_03.jpg"
]
DEFAULT_DELIVERY_PROOFS = [
    "https://res.cloudinary.com/dgyq49vi2/image/upload/v1789019123/e-flowers/delivery-proofs/del_proof_01.jpg",
    "https://res.cloudinary.com/dgyq49vi2/image/upload/v1789115952/e-flowers/delivery-proofs/del_proof_02.jpg"
]


def run_simulation():
    print("🚀 Starting Online Orders Simulation...")
    manifest = {
        "created_at": datetime.utcnow().isoformat(),
        "customer_user_ids": [],
        "rider_user_ids": [],
        "rider_ids": [],
        "order_ids": [],
        "order_item_ids": [],
        "stock_reduction_ids": [],
        "store_rating_ids": [],
        "product_rating_ids": [],
        "original_product_stocks": {},
        "original_variant_stocks": {}
    }

    # 1. SETUP RIDERS
    print("\n--- 1. Setting Up Riders ---")
    store_riders = {}

    # Store 18 (AKS Coop)
    aks_rider = Rider.query.filter_by(store_id=18, is_archived=False).first()
    if aks_rider:
        store_riders[18] = aks_rider
        print(f"✅ Store 18 (AKS Coop): Using existing Rider #{aks_rider.id} ({aks_rider.user.full_name})")
    else:
        u = User(
            full_name="Lito Dela Torre",
            email="lito.delatorre.rider@gmail.com",
            password_hash=generate_password_hash("RiderPass123!"),
            role="rider",
            status="active",
            phone="09175551234"
        )
        db.session.add(u)
        db.session.flush()
        manifest["rider_user_ids"].append(u.id)
        r = Rider(user_id=u.id, store_id=18, vehicle_type="Honda Click 125i", license_plate="ND-1845", is_active=True)
        db.session.add(r)
        db.session.flush()
        manifest["rider_ids"].append(r.id)
        store_riders[18] = r
        print(f"✅ Store 18 (AKS Coop): Created Rider #{r.id} ({u.full_name})")

    # Store 21 (Princess Rasec)
    rasec_rider = Rider.query.filter_by(store_id=21, is_archived=False).first()
    if rasec_rider:
        store_riders[21] = rasec_rider
        print(f"✅ Store 21 (Princess Rasec): Using existing Rider #{rasec_rider.id} ({rasec_rider.user.full_name})")
    else:
        u = User(
            full_name='Eduardo "Eddie" Santos',
            email="eddie.santos.rider@gmail.com",
            password_hash=generate_password_hash("RiderPass123!"),
            role="rider",
            status="active",
            phone="09184449876"
        )
        db.session.add(u)
        db.session.flush()
        manifest["rider_user_ids"].append(u.id)
        r = Rider(user_id=u.id, store_id=21, vehicle_type="Honda Wave 110", license_plate="ND-4821", is_active=True)
        db.session.add(r)
        db.session.flush()
        manifest["rider_ids"].append(r.id)
        store_riders[21] = r
        print(f"✅ Store 21 (Princess Rasec): Created Rider #{r.id} ({u.full_name})")

    # Store 22 (Speaking Flowers)
    speaking_rider = Rider.query.filter_by(store_id=22, is_archived=False).first()
    if speaking_rider:
        store_riders[22] = speaking_rider
        print(f"✅ Store 22 (Speaking Flowers): Using existing Rider #{speaking_rider.id} ({speaking_rider.user.full_name})")
    else:
        u = User(
            full_name='Ramil "Mac" Hernandez',
            email="ramil.hernandez.rider@gmail.com",
            password_hash=generate_password_hash("RiderPass123!"),
            role="rider",
            status="active",
            phone="09193335678"
        )
        db.session.add(u)
        db.session.flush()
        manifest["rider_user_ids"].append(u.id)
        r = Rider(user_id=u.id, store_id=22, vehicle_type="Yamaha Mio i125", license_plate="DA-9032", is_active=True)
        db.session.add(r)
        db.session.flush()
        manifest["rider_ids"].append(r.id)
        store_riders[22] = r
        print(f"✅ Store 22 (Speaking Flowers): Created Rider #{r.id} ({u.full_name})")

    # 2. SETUP REALISTIC CUSTOMERS
    print("\n--- 2. Setting Up Customer Profiles ---")
    customer_users = []
    for cdata in CUSTOMERS_DATA:
        existing = User.query.filter_by(email=cdata["email"]).first()
        if not existing:
            u = User(
                full_name=cdata["name"],
                email=cdata["email"],
                password_hash=generate_password_hash("CustomerPass123!"),
                role="customer",
                status="active",
                phone=cdata["phone"]
            )
            db.session.add(u)
            db.session.flush()
            manifest["customer_user_ids"].append(u.id)
            customer_users.append((u, cdata))
        else:
            customer_users.append((existing, cdata))
    print(f"✅ Available simulated customers: {len(customer_users)}")

    # 3. SELECT PRODUCTS & HEALTHY STOCKS
    print("\n--- 3. Preparing Store Product Catalogs ---")
    store_products = {}
    for sid in [18, 21, 22]:
        prods = Product.query.filter_by(store_id=sid, is_archived=False).all()
        # Filter products that have images
        prods_with_img = [p for p in prods if p.images]
        if not prods_with_img:
            prods_with_img = prods
        
        # Ensure products have healthy starting stock so deduction won't drop negative
        for p in prods_with_img:
            manifest["original_product_stocks"][str(p.id)] = p.stock_quantity
            if p.stock_quantity < 10:
                p.stock_quantity = 25
            for v in p.variants:
                manifest["original_variant_stocks"][str(v.id)] = v.stock_quantity
                if v.stock_quantity < 10:
                    v.stock_quantity = 25
        db.session.flush()
        store_products[sid] = prods_with_img
        print(f"✅ Store {sid}: {len(prods_with_img)} active products ready")

    # 4. GENERATE ONLINE ORDERS
    # Store requirements:
    # Princess Rasec: 9 orders
    # AKS Coop: 6 orders
    # Speaking Flowers: 3 orders
    order_plan = [
        (21, 9, "Princess Rasec Botanical Garden"),
        (18, 6, "AKS Coop Flowershop"),
        (22, 3, "Speaking Flowers")
    ]

    print("\n--- 4. Creating Online Orders & Lifecycle History ---")
    # Date spread: Sept 15, 2026 to Sept 28, 2026
    start_date = datetime(2026, 9, 15)
    days_span = 14

    for sid, order_count, store_name in order_plan:
        print(f"\nCreating {order_count} orders for Store {sid} ({store_name})...")
        rider = store_riders[sid]
        catalog = store_products[sid]
        store_review_pool = STORE_REVIEWS[sid]

        # Distribute orders across days
        day_offsets = sorted([random.randint(0, days_span) for _ in range(order_count)])

        for idx, day_offset in enumerate(day_offsets):
            order_date = start_date + timedelta(days=day_offset)
            
            # Random time between 8:00 AM and 3:00 PM PHT (00:00 to 07:00 UTC)
            pht_hour = random.randint(8, 14)
            pht_minute = random.randint(0, 59)
            pht_second = random.randint(0, 59)
            
            # UTC timestamp is PHT - 8 hours
            base_pht_dt = datetime.combine(order_date.date(), time(pht_hour, pht_minute, pht_second))
            pending_utc = base_pht_dt - timedelta(hours=8)
            accepted_utc = pending_utc + timedelta(minutes=random.randint(10, 25))
            preparing_utc = accepted_utc
            done_prep_utc = preparing_utc + timedelta(minutes=random.randint(45, 90))
            confirmed_utc = done_prep_utc + timedelta(minutes=random.randint(15, 25))
            delivered_utc = confirmed_utc + timedelta(minutes=random.randint(30, 60))
            completed_utc = delivered_utc + timedelta(minutes=random.randint(20, 50))

            # Pick customer (reuse some for customer retention simulation)
            cust_user, cust_data = customer_users[idx % len(customer_users)]

            # Payment method: 85% GCash, 15% COD
            is_gcash = (idx % 6) != 0
            payment_method = "gcash" if is_gcash else "cod"
            payment_status = "verified" if is_gcash else "cod_approved"

            # Select 1 to 2 products
            num_items = 1 if len(catalog) < 2 or random.random() > 0.3 else 2
            chosen_prods = random.sample(catalog, min(num_items, len(catalog)))

            # Pick product image for done_preparing proof photo
            primary_product = chosen_prods[0]
            prod_img_url = primary_product.images[0].cloudinary_url if primary_product.images else DEFAULT_GCASH_PROOFS[0]

            dist_km = round(random.uniform(2.5, 9.5), 1)
            delivery_fee = Decimal(str(50.0 + (dist_km * 7.5))).quantize(Decimal('0.01'))

            order = Order(
                customer_id=cust_user.id,
                store_id=sid,
                rider_id=rider.id,
                order_type="online",
                fulfillment_type="delivery",
                status="completed",
                subtotal_amount=Decimal('0.00'),
                delivery_fee=delivery_fee,
                distance_km=dist_km,
                total_amount=Decimal('0.00'),
                payment_method=payment_method,
                payment_status=payment_status,
                payment_proof_url=random.choice(DEFAULT_GCASH_PROOFS) if is_gcash else None,
                delivery_address=cust_data["address"],
                delivery_notes=random.choice([
                    "Please call upon arrival. White gate.",
                    "Leave at the guardhouse if not home.",
                    "Deliver before 4 PM please.",
                    "Ring doorbell twice. Thank you!",
                    None
                ]),
                customer_latitude=cust_data["lat"],
                customer_longitude=cust_data["lng"],
                mapbox_place_id=f"place_sim_{idx}_{cust_user.id}",
                done_preparing_proof_url=prod_img_url,  # Finished product photo sent to customer!
                delivery_proof_url=DEFAULT_DELIVERY_PROOFS[0],
                delivery_proof_2_url=DEFAULT_DELIVERY_PROOFS[1],
                pending_at=pending_utc,
                accepted_at=accepted_utc,
                preparing_at=preparing_utc,
                done_preparing_at=done_prep_utc,
                confirmed_at=confirmed_utc,
                delivered_at=delivered_utc,
                completed_at=completed_utc,
                created_at=pending_utc,
                updated_at=completed_utc
            )
            db.session.add(order)
            db.session.flush()
            manifest["order_ids"].append(order.id)

            subtotal = Decimal('0.00')

            # Create OrderItems and reduce stock
            for prod in chosen_prods:
                variant = prod.variants[0] if prod.variants else None
                item_price = Decimal(str(variant.price if variant else prod.price))
                item_qty = random.randint(1, 2)
                item_img = prod.images[0].cloudinary_url if prod.images else None

                order_item = OrderItem(
                    order_id=order.id,
                    product_id=prod.id,
                    variant_id=variant.id if variant else None,
                    quantity=item_qty,
                    price=item_price,
                    product_name=prod.name,
                    product_image_url=item_img,
                    variant_name=variant.name if variant else None
                )
                db.session.add(order_item)
                db.session.flush()
                manifest["order_item_ids"].append(order_item.id)

                subtotal += (item_price * item_qty)

                # Stock deduction & audit trail
                if variant:
                    variant.stock_quantity = max(0, variant.stock_quantity - item_qty)
                else:
                    prod.stock_quantity = max(0, prod.stock_quantity - item_qty)

                # Inventory reduction record
                reduction = StockReduction(
                    product_id=prod.id,
                    variant_id=variant.id if variant else None,
                    reduction_amount=item_qty,
                    reason="other",
                    reason_notes=f"Online order #{order.id} checkout deduction",
                    reduced_by=cust_user.id,
                    created_at=pending_utc
                )
                db.session.add(reduction)
                db.session.flush()
                manifest["stock_reduction_ids"].append(reduction.id)

                # Product rating for this order item
                pr_rating, pr_comment = random.choice(PRODUCT_REVIEWS)
                pr = ProductRating(
                    customer_id=cust_user.id,
                    product_id=prod.id,
                    variant_id=variant.id if variant else None,
                    order_id=order.id,
                    order_item_id=order_item.id,
                    rating=pr_rating,
                    comment=pr_comment,
                    created_at=completed_utc + timedelta(hours=1, minutes=random.randint(5, 45))
                )
                db.session.add(pr)
                db.session.flush()
                manifest["product_rating_ids"].append(pr.id)

            order.subtotal_amount = subtotal
            order.total_amount = subtotal + delivery_fee

            # Store Rating for this order
            sr_rating, sr_comment = store_review_pool[idx % len(store_review_pool)]
            sr = StoreRating(
                customer_id=cust_user.id,
                store_id=sid,
                order_id=order.id,
                rating=sr_rating,
                comment=sr_comment,
                created_at=completed_utc + timedelta(hours=1, minutes=random.randint(5, 45))
            )
            db.session.add(sr)
            db.session.flush()
            manifest["store_rating_ids"].append(sr.id)

            print(f"  📦 Order #{order.id} | Date: {base_pht_dt.strftime('%Y-%m-%d %I:%M %p')} PHT | Cust: {cust_user.full_name[:20]:20s} | Sub: ₱{subtotal:,.2f} | Del: ₱{delivery_fee} | Tot: ₱{order.total_amount:,.2f} | Method: {payment_method.upper()}")

    # Commit all orders
    db.session.commit()
    print("\n✅ Successfully committed all orders to PostgreSQL!")

    # Write Manifest
    with open(MANIFEST_FILE, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
    print(f"✅ Saved rollback manifest to: {MANIFEST_FILE}")

    # Generate SQL Undo File
    generate_sql_undo(manifest)

    print("\n🎉 Simulation complete! 18 realistic online orders successfully created.")


def generate_sql_undo(manifest):
    order_ids_str = ", ".join(map(str, manifest["order_ids"]))
    reduction_ids_str = ", ".join(map(str, manifest["stock_reduction_ids"]))
    rider_ids_str = ", ".join(map(str, manifest["rider_ids"]))
    rider_user_ids_str = ", ".join(map(str, manifest["rider_user_ids"]))
    cust_user_ids_str = ", ".join(map(str, manifest["customer_user_ids"]))

    sql = f"""-- =========================================================
-- STANDBY UNDO SCRIPT FOR ONLINE ORDER SIMULATION
-- Run this in psql or Railway database query console if needed
-- =========================================================

BEGIN;

-- 1. Delete ratings
DELETE FROM product_ratings WHERE order_id IN ({order_ids_str});
DELETE FROM store_ratings WHERE order_id IN ({order_ids_str});

-- 2. Delete order items & orders
DELETE FROM order_items WHERE order_id IN ({order_ids_str});
DELETE FROM orders WHERE id IN ({order_ids_str});

-- 3. Delete stock reduction audit records
DELETE FROM stock_reductions WHERE id IN ({reduction_ids_str});
"""
    # Restore product stocks
    for pid, stock in manifest["original_product_stocks"].items():
        sql += f"UPDATE products SET stock_quantity = {stock} WHERE id = {pid};\n"
    for vid, stock in manifest["original_variant_stocks"].items():
        sql += f"UPDATE product_variants SET stock_quantity = {stock} WHERE id = {vid};\n"

    # Delete riders and dummy users if any were created
    if manifest["rider_ids"]:
        sql += f"DELETE FROM riders WHERE id IN ({rider_ids_str});\n"
    if manifest["rider_user_ids"]:
        sql += f"DELETE FROM users WHERE id IN ({rider_user_ids_str});\n"
    if manifest["customer_user_ids"]:
        sql += f"DELETE FROM users WHERE id IN ({cust_user_ids_str});\n"

    sql += "\nCOMMIT;\n"

    with open(SQL_UNDO_FILE, 'w', encoding='utf-8') as f:
        f.write(sql)
    print(f"✅ Standby SQL Undo file generated at: {SQL_UNDO_FILE}")


if __name__ == '__main__':
    with app.app_context():
        run_simulation()
