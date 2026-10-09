import os
import sys
import json
import random
from datetime import datetime, timedelta, time
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
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
UPLOADED_ASSETS_FILE = os.path.join(os.path.dirname(__file__), 'uploaded_simulation_assets.json')

with open(UPLOADED_ASSETS_FILE, 'r') as f:
    CLOUDINARY_URLS = json.load(f)

# 11 Natural Customers with un-patterned emails
CUSTOMERS_DATA = [
    {
        "name": "Mark Anthony Ramos",
        "email": "marky_boy98@yahoo.com",
        "phone": "09173421890",
        "address": "Block 4 Lot 12, Villa Zaragosa, Barangay Silangan, Calauan, Laguna",
        "lat": 14.1485, "lng": 121.3150
    },
    {
        "name": "Chelsea Torres",
        "email": "chelseatorres.laguna@gmail.com",
        "phone": "09189214732",
        "address": "78 J. Rizal St., Poblacion, Luisiana, Laguna",
        "lat": 14.1873, "lng": 121.5120
    },
    {
        "name": "Dranreb Santos",
        "email": "dranreb_santos@outlook.com",
        "phone": "09204561289",
        "address": "Unit 2B, Greenhills Subdivision, San Pablo City, Laguna",
        "lat": 14.0682, "lng": 121.3255
    },
    {
        "name": "Katrina Mendoza",
        "email": "katrina.mendoza14@gmail.com",
        "phone": "09165558901",
        "address": "Zone 3, Barangay Dayap, Calauan, Laguna",
        "lat": 14.1520, "lng": 121.3210
    },
    {
        "name": "Alyssa Joy Bautista",
        "email": "aly_bautista95@yahoo.com",
        "phone": "09198762341",
        "address": "15 Mabini St., Barangay Sto. Domingo, Bay, Laguna",
        "lat": 14.1812, "lng": 121.2840
    },
    {
        "name": "Arjay Dela Cruz",
        "email": "arjaydelacruz@gmail.com",
        "phone": "09278893412",
        "address": "Sitio Ilaya, Barangay San Buenaventura, Luisiana, Laguna",
        "lat": 14.1920, "lng": 121.5180
    },
    {
        "name": "Patricia Nicole Lim",
        "email": "patricia_lim02@yahoo.com",
        "phone": "09153327618",
        "address": "Purok 5, Barangay Kanluran Kabubuhayan, Nagcarlan, Laguna",
        "lat": 14.1350, "lng": 121.4170
    },
    {
        "name": "Joshua Cortez",
        "email": "joshua_cortez21@outlook.com",
        "phone": "09176641209",
        "address": "Lot 8, Palm Grove Estate, Los Baños, Laguna",
        "lat": 14.1700, "lng": 121.2420
    },
    {
        "name": "Bea Louise Reyes",
        "email": "bealouise.reyes@gmail.com",
        "phone": "09228901435",
        "address": "Barangay Lamot 1, Calauan, Laguna",
        "lat": 14.1430, "lng": 121.3090
    },
    {
        "name": "Ronnie Alvarez",
        "email": "ronnie.alvarez77@gmail.com",
        "phone": "09167784321",
        "address": "22 Bonifacio St., Pila, Laguna",
        "lat": 14.2340, "lng": 121.3650
    },
    {
        "name": "Mariel Fernando",
        "email": "mariel_fernando@yahoo.com",
        "phone": "09182239084",
        "address": "Barangay San Diego, San Pablo City, Laguna",
        "lat": 14.0750, "lng": 121.3380
    }
]

# Order blueprints
ORDER_CONFIGS = [
    # Store 21 (Princess Rasec) - 6 orders
    {
        "store_id": 21,
        "customer_idx": 0,
        "date_offset": 8,  # Sep 22
        "hour": 9, "minute": 15,
        "items": [(368, 3), (384, 10)],  # Loam soil x3, Nursery pots x10
        "delivery_fee": Decimal("60.00"),
        "payment_method": "gcash",
        "payment_proof_key": "gcash_406_90",
        "seller_prep_key": "seller_garden",
        "rider_proof_key": "rider_garden",
        "store_rating": (5, "Super ganda ng nursery pots at mabigat, fertile ang loam soil! Walang tapon nung dineliver."),
        "product_ratings": [
            (5, "Napakaganda ng lupa, buhaghag at walang halo na basura. Perfect sa orchids at monstera."),
            (5, "Very sturdy nursery pots, hindi madaling mapunit kahit mabilad sa araw.")
        ]
    },
    {
        "store_id": 21,
        "customer_idx": 1,
        "date_offset": 7,  # Sep 23
        "hour": 10, "minute": 30,
        "items": [(352, 1), (347, 1)],  # Bonsai x1, Cocopeat x1
        "delivery_fee": Decimal("75.00"),
        "payment_method": "gcash",
        "payment_proof_key": "gcash_836_16",
        "seller_prep_key": "seller_garden",
        "rider_proof_key": "rider_garden",
        "store_rating": (5, "Napakaganda nung bonsai, buhay na buhay at secure ang packaging. Salamat kay seller at rider!"),
        "product_ratings": [
            (5, "Fresh na fresh ang bonsai plant at buong-buo ang paso. Ganda ng porma!"),
            (5, "Fine quality cocopeat, malinis at ready to use agad.")
        ]
    },
    {
        "store_id": 21,
        "customer_idx": 2,
        "date_offset": 6,  # Sep 24
        "hour": 11, "minute": 20,
        "items": [(386, 2), (380, 2)],  # Garden planter pots x2, YaraMila x2
        "delivery_fee": Decimal("65.00"),
        "payment_method": "gcash",
        "payment_proof_key": "gcash_562_18",
        "seller_prep_key": "seller_garden",
        "rider_proof_key": "rider_garden",
        "store_rating": (5, "Makapal ang paso at kumpleto ang pataba. Dito na ako laging oorder para sa halamanan ko."),
        "product_ratings": [
            (5, "Elegant white planters, matibay at maganda ang drainage."),
            (5, "Subok na pataba ang YaraMila, mabilis mamulaklak ang mga halaman ko.")
        ]
    },
    {
        "store_id": 21,
        "customer_idx": 3,
        "date_offset": 5,  # Sep 25
        "hour": 13, "minute": 45,
        "items": [(368, 5), (349, 2)],  # Loam soil x5, 14-14-14 Fertilizer x2
        "delivery_fee": Decimal("60.00"),
        "payment_method": "cod",
        "payment_proof_key": None,
        "seller_prep_key": "seller_garden",
        "rider_proof_key": "rider_garden",
        "store_rating": (4, "Mabilis ang COD transaction. Tinulungan pa ako ni kuya rider magbuhat. Salamat!"),
        "product_ratings": [
            (4, "Well packed ang lupa, mabilis nakarating dito sa Calauan."),
            (5, "Complete 14-14-14 fertilizer, maayos ang pagkaka-seal.")
        ]
    },
    {
        "store_id": 21,
        "customer_idx": 4,
        "date_offset": 4,  # Sep 26
        "hour": 14, "minute": 10,
        "items": [(303, 1), (375, 2)],  # Pruning shear x1, Sprayer x2
        "delivery_fee": Decimal("55.00"),
        "payment_method": "gcash",
        "payment_proof_key": "gcash_314_64",
        "seller_prep_key": "seller_garden",
        "rider_proof_key": "rider_garden",
        "store_rating": (5, "Matulis yung shear at maayos ang sprayers. Sulit ang presyo kumpara sa hardware."),
        "product_ratings": [
            (5, "Very sharp shears, easy grip and high quality steel."),
            (5, "Good pressure sprayers, works perfectly for misting.")
        ]
    },
    {
        "store_id": 21,
        "customer_idx": 5,
        "date_offset": 3,  # Sep 27
        "hour": 15, "minute": 30,
        "items": [(382, 100), (362, 2)],  # Seedling bags x100, Garden soil x2
        "delivery_fee": Decimal("60.00"),
        "payment_method": "gcash",
        "payment_proof_key": "gcash_313_54",
        "seller_prep_key": "seller_garden",
        "rider_proof_key": "rider_garden",
        "store_rating": (5, "Complete 100pcs seedling bags at maayos ang garden soil. Mabilis ang delivery."),
        "product_ratings": [
            (5, "Tamang-tama ang kapal ng seedling bags, hindi agad napupunit."),
            (5, "Rich black garden soil, maganda ipangtanim ng gulay.")
        ]
    },

    # Store 18 (AKS Coop) - 4 orders
    {
        "store_id": 18,
        "customer_idx": 6,
        "date_offset": 5,  # Sep 25
        "hour": 9, "minute": 40,
        "items": [(273, 1)],  # Artificial Red Rose Bouquet x1
        "delivery_fee": Decimal("70.00"),
        "payment_method": "gcash",
        "payment_proof_key": "gcash_570_00",
        "seller_prep_key": "seller_flower",
        "rider_proof_key": "rider_flower",
        "store_rating": (5, "Sobrang ganda po ng bouquet! Very neat packaging at mabilis dumating. Perfect gift."),
        "product_ratings": [
            (5, "Ang ganda ng pagkakagawa, parang totoo! Tuwang-tuwa ang girlfriend ko.")
        ]
    },
    {
        "store_id": 18,
        "customer_idx": 7,
        "date_offset": 4,  # Sep 26
        "hour": 10, "minute": 15,
        "items": [(286, 2)],  # Mini Ribbon Sunflower Bouquet x2
        "delivery_fee": Decimal("65.00"),
        "payment_method": "gcash",
        "payment_proof_key": "gcash_565_00",
        "seller_prep_key": "seller_flower",
        "rider_proof_key": "rider_flower",
        "store_rating": (5, "Ang cute ng sunflower bouquets! Tuwang tuwa yung mga binigyan ko. Highly recommended!"),
        "product_ratings": [
            (5, "High quality ribbons and neat arrangement. Very vibrant sunflowers!")
        ]
    },
    {
        "store_id": 18,
        "customer_idx": 8,
        "date_offset": 3,  # Sep 27
        "hour": 13, "minute": 20,
        "items": [(277, 1)],  # Flower Arrangement Blue x1
        "delivery_fee": Decimal("80.00"),
        "payment_method": "gcash",
        "payment_proof_key": "gcash_880_00",
        "seller_prep_key": "seller_flower",
        "rider_proof_key": "rider_flower",
        "store_rating": (5, "Napakaganda nung blue arrangement! Fresh na fresh tingnan at mabait si kuya rider."),
        "product_ratings": [
            (5, "Masterpiece bouquet! Elegant color combination and well-wrapped.")
        ]
    },
    {
        "store_id": 18,
        "customer_idx": 9,
        "date_offset": 2,  # Sep 28
        "hour": 14, "minute": 50,
        "items": [(305, 1)],  # Money Bouquet Assorted x1
        "delivery_fee": Decimal("75.00"),
        "payment_method": "cod",
        "payment_proof_key": None,
        "seller_prep_key": "seller_flower",
        "rider_proof_key": "rider_flower",
        "store_rating": (4, "Maayos ang pagkagawa nung money bouquet, pulido ang tupi. Thank you seller!"),
        "product_ratings": [
            (5, "Clean folds and secured money bills. Great presentation for birthdays!")
        ]
    },

    # Store 22 (Speaking Flowers) - 1 order
    {
        "store_id": 22,
        "customer_idx": 10,
        "date_offset": 2,  # Sep 28
        "hour": 11, "minute": 10,
        "items": [(388, 1)],  # Premium Rose Bouquet x1
        "delivery_fee": Decimal("120.00"),
        "payment_method": "gcash",
        "payment_proof_key": "gcash_3320_00",
        "seller_prep_key": "seller_luxury",
        "rider_proof_key": "rider_luxury",
        "store_rating": (5, "Breathtaking bouquet! Premium roses talaga, fresh petals with matching black box and card. Worth every peso!"),
        "product_ratings": [
            (5, "Absolute luxury quality roses! The matte black packaging and satin bow are top notch.")
        ]
    }
]

def run_simulation():
    print("🚀 Running Online Orders Simulation V2 (11 Orders)...")
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
        "product_stock_snapshots": {}
    }

    with app.app_context():
        # Snapshot product stock levels
        all_pids = set()
        for oc in ORDER_CONFIGS:
            for pid, _ in oc["items"]:
                all_pids.add(pid)
        
        for pid in all_pids:
            p = Product.query.filter_by(id=pid).first()
            if p:
                manifest["product_stock_snapshots"][str(pid)] = p.stock_quantity
                # Ensure baseline stock so stock never goes negative
                if p.stock_quantity < 50:
                    p.stock_quantity += 100
        db.session.commit()

        # 1. Setup Riders
        # Store 18: Lito Dela Torre
        lito_rider = Rider.query.filter_by(store_id=18, is_archived=False).first()
        if not lito_rider:
            lito_user = User(
                email="lito.rider@gmail.com",
                full_name="Lito Dela Torre",
                phone_number="09191234567",
                role="rider",
                status="active",
                password_hash=generate_password_hash("RiderPass123!")
            )
            db.session.add(lito_user)
            db.session.flush()
            manifest["rider_user_ids"].append(lito_user.id)
            lito_rider = Rider(
                user_id=lito_user.id,
                store_id=18,
                vehicle_type="Yamaha Sight 115",
                license_plate="ND-1102",
                is_archived=False
            )
            db.session.add(lito_rider)
            db.session.flush()
            manifest["rider_ids"].append(lito_rider.id)

        # Store 21: Eduardo "Eddie" Santos
        eddie_user = User.query.filter_by(email="eddie.santos.rider@gmail.com").first()
        if not eddie_user:
            eddie_user = User(
                email="eddie.santos.rider@gmail.com",
                full_name="Eduardo Santos",
                phone="09171234567",
                role="rider",
                status="active",
                password_hash=generate_password_hash("RiderPass123!")
            )
            db.session.add(eddie_user)
            db.session.flush()
            manifest["rider_user_ids"].append(eddie_user.id)

        eddie_rider = Rider.query.filter_by(store_id=21, user_id=eddie_user.id).first()
        if not eddie_rider:
            eddie_rider = Rider(
                user_id=eddie_user.id,
                store_id=21,
                vehicle_type="Honda Wave 110",
                license_plate="ND-4821",
                is_archived=False
            )
            db.session.add(eddie_rider)
            db.session.flush()
            manifest["rider_ids"].append(eddie_rider.id)

        # Store 22: Ramil "Mac" Hernandez
        mac_user = User.query.filter_by(email="ramil.hernandez.rider@gmail.com").first()
        if not mac_user:
            mac_user = User(
                email="ramil.hernandez.rider@gmail.com",
                full_name="Ramil Hernandez",
                phone="09187654321",
                role="rider",
                status="active",
                password_hash=generate_password_hash("RiderPass123!")
            )
            db.session.add(mac_user)
            db.session.flush()
            manifest["rider_user_ids"].append(mac_user.id)

        mac_rider = Rider.query.filter_by(store_id=22, user_id=mac_user.id).first()
        if not mac_rider:
            mac_rider = Rider(
                user_id=mac_user.id,
                store_id=22,
                vehicle_type="Yamaha Mio i125",
                license_plate="DA-9032",
                is_archived=False
            )
            db.session.add(mac_rider)
            db.session.flush()
            manifest["rider_ids"].append(mac_rider.id)

        db.session.commit()
        print("✅ Riders configured.")

        # 2. Setup Customers
        customer_users = []
        for cdata in CUSTOMERS_DATA:
            u = User.query.filter_by(email=cdata["email"]).first()
            if not u:
                u = User(
                    email=cdata["email"],
                    full_name=cdata["name"],
                    phone=cdata["phone"],
                    role="customer",
                    status="active",
                    password_hash=generate_password_hash("CustomerPass123!")
                )
                db.session.add(u)
                db.session.flush()
                manifest["customer_user_ids"].append(u.id)
            customer_users.append(u)
        db.session.commit()
        print(f"✅ {len(customer_users)} Customers ready.")

        store_riders = {
            21: eddie_rider,
            18: lito_rider,
            22: mac_rider
        }

        # Base reference date: Sept 30, 2026
        base_ref_date = datetime(2026, 9, 30, 0, 0, 0)

        # 3. Create Orders
        for idx, oc in enumerate(ORDER_CONFIGS):
            store_id = oc["store_id"]
            cust = customer_users[oc["customer_idx"]]
            rider = store_riders[store_id]
            order_date = base_ref_date - timedelta(days=oc["date_offset"])
            
            pht_order_time = order_date.replace(hour=oc["hour"], minute=oc["minute"], second=0)
            utc_created_at = pht_order_time - timedelta(hours=8)

            t_accepted = utc_created_at + timedelta(minutes=15)
            t_preparing = t_accepted + timedelta(minutes=5)
            t_done_prep = t_preparing + timedelta(minutes=45)
            t_confirmed = t_done_prep + timedelta(minutes=15)
            t_delivered = t_confirmed + timedelta(minutes=35)
            t_completed = t_delivered + timedelta(minutes=20)

            # Get images
            payment_url = CLOUDINARY_URLS.get(oc["payment_proof_key"]) if oc["payment_proof_key"] else None
            seller_prep_url = CLOUDINARY_URLS.get(oc["seller_prep_key"])
            rider_proof_url = CLOUDINARY_URLS.get(oc["rider_proof_key"])

            is_gcash = (oc["payment_method"] == "gcash")
            payment_status = "verified" if is_gcash else "cod_approved"

            order = Order(
                customer_id=cust.id,
                store_id=store_id,
                rider_id=rider.id,
                order_type="online",
                fulfillment_type="delivery",
                status="completed",
                payment_method=oc["payment_method"],
                payment_status=payment_status,
                payment_proof_url=payment_url,
                done_preparing_proof_url=seller_prep_url,
                delivery_proof_url=rider_proof_url,
                delivery_proof_2_url=None,
                
                delivery_fee=oc["delivery_fee"],
                delivery_address=CUSTOMERS_DATA[oc["customer_idx"]]["address"],
                customer_latitude=CUSTOMERS_DATA[oc["customer_idx"]]["lat"],
                customer_longitude=CUSTOMERS_DATA[oc["customer_idx"]]["lng"],
                mapbox_place_id=f"place_sim_{idx}_{cust.id}",
                
                created_at=utc_created_at,
                pending_at=utc_created_at,
                accepted_at=t_accepted,
                preparing_at=t_preparing,
                done_preparing_at=t_done_prep,
                confirmed_at=t_confirmed,
                delivered_at=t_delivered,
                completed_at=t_completed,
                updated_at=t_completed
            )
            db.session.add(order)
            db.session.flush()
            manifest["order_ids"].append(order.id)

            subtotal = Decimal("0.00")
            for p_idx, (pid, qty) in enumerate(oc["items"]):
                prod = Product.query.filter_by(id=pid).first()
                item_price = Decimal(str(prod.price))
                line_total = item_price * qty
                subtotal += line_total

                item = OrderItem(
                    order_id=order.id,
                    product_id=prod.id,
                    product_name=prod.name,
                    product_image_url=prod.image_url,
                    quantity=qty,
                    price=item_price
                )
                db.session.add(item)
                db.session.flush()
                manifest["order_item_ids"].append(item.id)

                # Inventory reduction
                prod.stock_quantity = max(0, prod.stock_quantity - qty)
                red = StockReduction(
                    product_id=prod.id,
                    reduction_amount=qty,
                    reason="other",
                    reason_notes=f"Online order #{order.id} checkout deduction",
                    reduced_by=cust.id,
                    created_at=utc_created_at
                )
                db.session.add(red)
                db.session.flush()
                manifest["stock_reduction_ids"].append(red.id)

                # Product rating for this line item
                if p_idx < len(oc["product_ratings"]):
                    p_stars, p_comment = oc["product_ratings"][p_idx]
                else:
                    p_stars, p_comment = (5, "Quality product and fast shipping. Highly recommended!")
                
                pr = ProductRating(
                    product_id=pid,
                    customer_id=cust.id,
                    order_id=order.id,
                    order_item_id=item.id,
                    rating=p_stars,
                    comment=p_comment,
                    created_at=t_completed + timedelta(minutes=15)
                )
                db.session.add(pr)
                db.session.flush()
                manifest["product_rating_ids"].append(pr.id)

            order.subtotal_amount = subtotal
            order.total_amount = subtotal + oc["delivery_fee"]

            # Store rating
            s_stars, s_feedback = oc["store_rating"]
            s_rating = StoreRating(
                store_id=store_id,
                customer_id=cust.id,
                order_id=order.id,
                rating=s_stars,
                comment=s_feedback,
                created_at=t_completed + timedelta(minutes=10)
            )
            db.session.add(s_rating)
            db.session.flush()
            manifest["store_rating_ids"].append(s_rating.id)

            print(f"  • Created Order #{order.id} | Store {store_id} | ₱{order.total_amount} | Pay: {order.payment_method} | Proofs: {bool(payment_url)}, {bool(seller_prep_url)}, {bool(rider_proof_url)}")

        db.session.commit()

        # Write manifest file
        with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        print(f"✅ Manifest saved to {MANIFEST_FILE}")

        # Generate Standby SQL Undo Script
        generate_sql_undo(manifest)

    print("\n🎉 Online Orders Simulation V2 Completed Successfully!")

def generate_sql_undo(manifest):
    order_ids_str = ", ".join(str(oid) for oid in manifest["order_ids"])
    red_ids_str = ", ".join(str(rid) for rid in manifest["stock_reduction_ids"])
    p_rating_ids_str = ", ".join(str(prid) for prid in manifest["product_rating_ids"])
    s_rating_ids_str = ", ".join(str(srid) for srid in manifest["store_rating_ids"])
    cust_ids_str = ", ".join(str(uid) for uid in manifest["customer_user_ids"])
    rider_user_ids_str = ", ".join(str(ruid) for ruid in manifest["rider_user_ids"])
    rider_ids_str = ", ".join(str(rid) for rid in manifest["rider_ids"])

    sql_lines = [
        "-- =========================================================",
        "-- STANDBY UNDO SCRIPT FOR ONLINE ORDER SIMULATION V2",
        "-- Run this in psql or Railway database query console if needed",
        "-- =========================================================",
        "",
        "BEGIN;",
        "",
        "-- 1. Delete ratings",
        f"DELETE FROM product_ratings WHERE order_id IN ({order_ids_str});" if order_ids_str else "",
        f"DELETE FROM store_ratings WHERE order_id IN ({order_ids_str});" if order_ids_str else "",
        "",
        "-- 2. Delete order items & orders",
        f"DELETE FROM order_items WHERE order_id IN ({order_ids_str});" if order_ids_str else "",
        f"DELETE FROM orders WHERE id IN ({order_ids_str});" if order_ids_str else "",
        "",
        "-- 3. Delete stock reduction audit records",
        f"DELETE FROM stock_reductions WHERE id IN ({red_ids_str});" if red_ids_str else "",
        ""
    ]

    for pid_str, orig_stock in manifest["product_stock_snapshots"].items():
        sql_lines.append(f"UPDATE products SET stock_quantity = {orig_stock} WHERE id = {pid_str};")

    sql_lines.extend([
        "",
        "-- 4. Delete simulated riders and customers",
        f"DELETE FROM riders WHERE id IN ({rider_ids_str});" if rider_ids_str else "",
        f"DELETE FROM users WHERE id IN ({rider_user_ids_str});" if rider_user_ids_str else "",
        f"DELETE FROM users WHERE id IN ({cust_ids_str});" if cust_ids_str else "",
        "",
        "COMMIT;",
        "-- End of undo script"
    ])

    with open(SQL_UNDO_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(sql_lines))
    print(f"✅ Standby SQL script saved to {SQL_UNDO_FILE}")

if __name__ == "__main__":
    run_simulation()
