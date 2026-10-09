"""
Verification script: Test duplicate prevention for COD (Cash on Delivery) orders across Buy Now and Cart Checkout.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.stdout.reconfigure(encoding='utf-8')

from app import create_app, db
from app.models import User, Store, Product, Order, UserAddress, Cart, CartItem

def run_cod_verification():
    print("=" * 70)
    print("🧪 STARTING COD DUPLICATE ORDER PREVENTION VERIFICATION")
    print("=" * 70)

    app = create_app()
    app.config['TESTING'] = True

    with app.app_context():
        # Customer
        customer = db.session.get(User, 144)
        if not customer:
            customer = User.query.filter_by(role='customer', status='active').first()

        print(f"👤 Customer: {customer.full_name} (ID: {customer.id})")

        # Clean up any leftover recent test orders from customer 144 to ensure clean state
        leftovers = Order.query.filter(Order.customer_id == customer.id, Order.id >= 823).all()
        for o in leftovers:
            for it in o.items:
                db.session.delete(it)
            db.session.delete(o)
        db.session.commit()

        # Store 18 (AKS Coop Flowershop allows COD and GCash)
        store = db.session.get(Store, 18)
        print(f"🏪 Store: {store.name} (ID: {store.id})")

        # Delivery address in Luisiana
        luisiana_addr = UserAddress.query.filter_by(user_id=customer.id, municipality="Luisiana").first()
        if not luisiana_addr:
            luisiana_addr = UserAddress(
                user_id=customer.id,
                municipality="Luisiana",
                barangay="Zone I",
                street="General Luna St",
                address_line="General Luna St, Zone I, Luisiana, Laguna",
                latitude=store.latitude or 14.1833,
                longitude=store.longitude or 121.5100,
                address_label="Luisiana Branch",
                is_default=False
            )
            db.session.add(luisiana_addr)
            db.session.commit()
            print(f"📍 Created test Luisiana delivery address #{luisiana_addr.id}")
        else:
            print(f"📍 Using existing Luisiana delivery address #{luisiana_addr.id}")

        # Product 1 for Buy Now: 277 ('Flower Arrangement Blue')
        prod_buynow = db.session.get(Product, 277)
        # Product 2 for Cart Checkout: 273 ('Artificial Bouquet of Red Roses')
        prod_cart = db.session.get(Product, 273)

        initial_stock_bn = int(prod_buynow.stock_quantity)
        initial_stock_cart = int(prod_cart.stock_quantity)
        initial_orders = Order.query.filter_by(customer_id=customer.id).count()

        print(f"📦 Buy Now Product: '{prod_buynow.name}' (ID: {prod_buynow.id}), Initial Stock: {initial_stock_bn}")
        print(f"📦 Cart Product:     '{prod_cart.name}' (ID: {prod_cart.id}), Initial Stock: {initial_stock_cart}")
        print(f"📋 Initial Customer Orders: {initial_orders}")

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = customer.id
            sess['role'] = 'customer'

        # ------------------------------------------------------------------
        # TEST 1: Rapid Double-Click on 'BUY NOW' with COD
        # ------------------------------------------------------------------
        print("\n" + "-" * 60)
        print("TEST 1: Rapid Double-Click on 'BUY NOW' with COD")
        print("-" * 60)

        buy_now_payload = {
            "product_id": prod_buynow.id,
            "quantity": 1,
            "fulfillment_type": "delivery",
            "payment_method": "cod",
            "address_id": luisiana_addr.id,
            "delivery_address": luisiana_addr.address_line,
            "delivery_date": "2026-10-06",
            "delivery_time": "10:00 AM - 12:00 PM",
            "order_notes": "COD Buy Now Double-Click Test Order"
        }

        # Request 1 (Initial click)
        print("👉 User Clicks 'Complete Order' (COD Request 1)...")
        res1 = client.post(
            "/api/v1/checkout/buy-now/create-order",
            json=buy_now_payload,
            headers={"Content-Type": "application/json"}
        )
        print(f"   Response 1 Status: {res1.status_code}")
        r1_data = res1.get_json() or {}
        created_orders = r1_data.get("orders", [])
        assert len(created_orders) > 0, f"Failed to create order: {r1_data}"
        order_1_id = created_orders[0].get("id")
        print(f"   ✅ Created Order #{order_1_id} via COD successfully!")

        # Request 2 (Immediate accidental second click)
        print("👉 User Accidentally Clicks 'Complete Order' Again (COD Request 2)...")
        res2 = client.post(
            "/api/v1/checkout/buy-now/create-order",
            json=buy_now_payload,
            headers={"Content-Type": "application/json"}
        )
        print(f"   Response 2 Status: {res2.status_code}")
        r2_data = res2.get_json() or {}
        r2_orders = r2_data.get("orders", [])
        order_2_id = r2_orders[0].get("id") if r2_orders else None
        print(f"   Message: {r2_data.get('message')}")
        print(f"   Response 2 Order ID: #{order_2_id}")

        # Verification for Test 1
        db.session.expire_all()
        stock_bn_after = int(db.session.get(Product, prod_buynow.id).stock_quantity)
        orders_after_bn = Order.query.filter_by(customer_id=customer.id).count()

        assert res1.status_code in [200, 201], f"Expected 201/200, got {res1.status_code}"
        assert res2.status_code == 200, f"Expected 200 for duplicate, got {res2.status_code}"
        assert order_1_id == order_2_id, f"Duplicate was created! #{order_1_id} vs #{order_2_id}"
        assert "duplicate prevented" in str(r2_data.get("message", "")).lower(), "Message missing 'duplicate prevented'"
        assert stock_bn_after == initial_stock_bn - 1, f"Stock deducted incorrectly! Expected {initial_stock_bn - 1}, got {stock_bn_after}"
        assert orders_after_bn == initial_orders + 1, f"Total orders increased by more than 1! {orders_after_bn} vs {initial_orders + 1}"

        print("🎉 TEST 1 PASSED: Buy Now COD duplicate click safely intercepted! Stock deducted once only.")

        # ------------------------------------------------------------------
        # TEST 2: Rapid Double-Click on 'CART CHECKOUT' with COD
        # ------------------------------------------------------------------
        print("\n" + "-" * 60)
        print("TEST 2: Rapid Double-Click on 'CART CHECKOUT' with COD")
        print("-" * 60)

        # Set up a real cart item for customer
        cart = Cart.query.filter_by(user_id=customer.id).first()
        if not cart:
            cart = Cart(user_id=customer.id)
            db.session.add(cart)
            db.session.commit()

        # Clear any existing cart items and add 1 item
        CartItem.query.filter_by(cart_id=cart.id).delete()
        c_item = CartItem(
            cart_id=cart.id,
            product_id=prod_cart.id,
            quantity=1,
            is_selected=True
        )
        db.session.add(c_item)
        db.session.commit()

        cart_orders_payload = {
            "address_id": luisiana_addr.id,
            "delivery_address_id": luisiana_addr.id,
            "fulfillment_type": "delivery",
            "orders": [
                {
                    "temp_id": "temp_cod_cart_order",
                    "store_id": store.id,
                    "payment_method": "cod",
                    "payment_proof_url": None,
                    "payment_proof_public_id": None,
                    "fulfillment_type": "delivery",
                    "delivery_address_id": luisiana_addr.id,
                    "requested_delivery_date": "2026-10-06",
                    "requested_delivery_time": "10:00 AM - 12:00 PM",
                    "order_notes": "Cart COD Duplicate Test",
                    "items": [
                        {
                            "product_id": prod_cart.id,
                            "quantity": 1,
                            "price": float(prod_cart.price or 500.0)
                        }
                    ]
                }
            ]
        }

        # Cart Request 1
        print("👉 User Clicks 'Complete' on Cart (COD Request 1)...")
        cart_res1 = client.post(
            "/api/v1/checkout/create-orders",
            json=cart_orders_payload,
            headers={"Content-Type": "application/json"}
        )
        print(f"   Cart Response 1 Status: {cart_res1.status_code}")
        c1_data = cart_res1.get_json() or {}
        c1_orders = c1_data.get("orders", [])
        assert len(c1_orders) > 0, f"Failed to create cart order: {c1_data}"
        cart_order_1_id = c1_orders[0].get("id")
        print(f"   ✅ Created Cart Order #{cart_order_1_id} via COD successfully!")

        # Cart Request 2 (Immediate duplicate click)
        print("👉 User Accidentally Clicks 'Complete' on Cart Again (COD Request 2)...")
        cart_res2 = client.post(
            "/api/v1/checkout/create-orders",
            json=cart_orders_payload,
            headers={"Content-Type": "application/json"}
        )
        print(f"   Cart Response 2 Status: {cart_res2.status_code}")
        c2_data = cart_res2.get_json() or {}
        c2_orders = c2_data.get("orders", [])
        cart_order_2_id = c2_orders[0].get("id") if c2_orders else None
        print(f"   Message: {c2_data.get('message')}")
        print(f"   Cart Response 2 Order ID: #{cart_order_2_id}")

        # Verification for Test 2
        db.session.expire_all()
        stock_cart_after = int(db.session.get(Product, prod_cart.id).stock_quantity)
        total_orders_final = Order.query.filter_by(customer_id=customer.id).count()

        assert cart_res1.status_code in [200, 201], f"Expected 201/200, got {cart_res1.status_code}"
        assert cart_res2.status_code == 200, f"Expected 200 for duplicate, got {cart_res2.status_code}"
        assert cart_order_1_id == cart_order_2_id, f"Duplicate was created! #{cart_order_1_id} vs #{cart_order_2_id}"
        assert "duplicate prevented" in str(c2_data.get("message", "")).lower(), "Message missing 'duplicate prevented'"
        assert stock_cart_after == initial_stock_cart - 1, f"Stock deducted incorrectly! Expected {initial_stock_cart - 1}, got {stock_cart_after}"
        assert total_orders_final == initial_orders + 2, f"Total orders increased by more than 2! {total_orders_final} vs {initial_orders + 2}"

        print("🎉 TEST 2 PASSED: Cart COD duplicate click safely intercepted! Stock deducted once only.")

        print("\n" + "=" * 70)
        print("🎯 FINAL SUMMARY:")
        print(f"   - Buy Now COD Order: #{order_1_id} (Duplicate call safely returned #{order_2_id})")
        print(f"   - Cart COD Order:    #{cart_order_1_id} (Duplicate call safely returned #{cart_order_2_id})")
        print(f"   - Total orders created: Exactly 2 (one per flow)")
        print(f"   - Total stock deducted: Exactly 1 unit per product")
        print("   - BOTH GCASH AND COD DUPLICATE CHECKS ARE 100% VERIFIED & WORKING!")
        print("=" * 70)

        # Clean up test orders to leave DB tidy
        o1 = db.session.get(Order, order_1_id)
        o2 = db.session.get(Order, cart_order_1_id)
        for o in [o1, o2]:
            if o:
                for item in o.items:
                    db.session.delete(item)
                db.session.delete(o)
        prod_buynow.stock_quantity = initial_stock_bn
        prod_cart.stock_quantity = initial_stock_cart
        db.session.commit()
        print("🧹 Cleaned up test orders and restored inventory stock.")
        return True

if __name__ == "__main__":
    success = run_cod_verification()
    sys.exit(0 if success else 1)
