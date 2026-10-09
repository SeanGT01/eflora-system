"""
Test script to verify online checkout order placement and double-click / duplicate order prevention.
"""
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.stdout.reconfigure(encoding='utf-8')

from app import create_app, db
from app.models import User, Store, Product, Order, UserAddress

def run_test():
    print("🚀 Initializing test client for online checkout...")
    app = create_app()
    app.config['TESTING'] = True

    with app.app_context():
        # Find an active customer who has a saved address
        customer = User.query.join(UserAddress, User.id == UserAddress.user_id).filter(
            User.role == 'customer',
            User.status == 'active'
        ).first()

        if not customer:
            customer = User.query.filter_by(role='customer', status='active').first()

        if not customer:
            print("❌ No active customer found in database.")
            return False

        print(f"👤 Found test customer: {customer.full_name} (ID: {customer.id}, Email: {customer.email})")

        address = UserAddress.query.filter_by(user_id=customer.id).first()
        if not address:
            address = UserAddress(
                user_id=customer.id,
                municipality="Calauan",
                barangay="Silangan",
                street="123 Rizal St",
                address_line="123 Rizal St, Silangan, Calauan, Laguna",
                latitude=14.1500,
                longitude=121.3150,
                address_label="Home",
                is_default=True
            )
            db.session.add(address)
            db.session.commit()
            print(f"📍 Created test address: {address.address_line}")
        else:
            print(f"📍 Using existing address #{address.id}: {address.address_line}")

        # Find an available product from Store 21 (Princess Rasec, which delivers to Calauan)
        product = Product.query.filter(
            Product.store_id == 21,
            Product.is_available == True,
            Product.stock_quantity > 5
        ).first()

        if not product:
            product = Product.query.filter(
                Product.is_available == True,
                Product.stock_quantity > 5
            ).first()

        if not product:
            print("❌ No product with sufficient stock found.")
            return False

        store = product.store
        initial_stock = int(product.stock_quantity)
        initial_order_count = Order.query.filter_by(customer_id=customer.id).count()

        print(f"🛍️ Product: '{product.name}' (ID: {product.id}) from Store '{store.name}' (ID: {store.id})")
        print(f"📦 Initial stock: {initial_stock}")
        print(f"📋 Initial customer order count: {initial_order_count}")

        client = app.test_client()

        # Set session for client
        with client.session_transaction() as sess:
            sess['user_id'] = customer.id
            sess['role'] = 'customer'

        from app.checkout_routes import _store_allows_cod, _store_allows_gcash

        if _store_allows_gcash(store.id):
            payment_method = "gcash"
        elif _store_allows_cod(store.id):
            payment_method = "cod"
        else:
            payment_method = "cop"

        print(f"💳 Using allowed payment method: {payment_method}")

        payload = {
            "product_id": product.id,
            "quantity": 1,
            "fulfillment_type": "delivery" if payment_method != "cop" else "pickup",
            "address_id": address.id,
            "payment_method": payment_method,
            "delivery_notes": "Test double-click prevention order",
            "payment_proof_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/v1789115952/e-flowers/payments/gcash_receipt_sample_01.jpg" if payment_method == "gcash" else None
        }

        print("\n--- STEP 1: Sending Order Request 1 (Normal Checkout Click) ---")
        res1 = client.post(
            '/api/v1/checkout/buy-now/create-order',
            json=payload,
            headers={'Content-Type': 'application/json'}
        )

        print(f"Response 1 Status: {res1.status_code}")
        data1 = res1.get_json() or {}
        print(f"Response 1 Data: {data1}")

        if res1.status_code not in (200, 201) or not data1.get('success'):
            print(f"❌ Initial order creation failed: {data1.get('error')}")
            return False

        orders1 = data1.get('orders', [])
        order_id_1 = orders1[0]['id'] if orders1 else None
        print(f"✅ Order 1 placed successfully! Order ID: #{order_id_1}")

        # Refresh product from DB
        db.session.expire_all()
        stock_after_first = int(Product.query.get(product.id).stock_quantity)
        print(f"📦 Stock after first order: {stock_after_first} (Reduced by {initial_stock - stock_after_first})")

        print("\n--- STEP 2: Sending Order Request 2 Immediately (Simulating Delayed Double-Click) ---")
        res2 = client.post(
            '/api/v1/checkout/buy-now/create-order',
            json=payload,
            headers={'Content-Type': 'application/json'}
        )

        print(f"Response 2 Status: {res2.status_code}")
        data2 = res2.get_json() or {}
        print(f"Response 2 Data: {data2}")

        orders2 = data2.get('orders', [])
        order_id_2 = orders2[0]['id'] if orders2 else None

        print(f"\n--- STEP 3: Verification of Duplicate Prevention ---")
        print(f"Order ID from Request 1: #{order_id_1}")
        print(f"Order ID from Request 2: #{order_id_2}")

        db.session.expire_all()
        final_stock = int(Product.query.get(product.id).stock_quantity)
        final_order_count = Order.query.filter_by(customer_id=customer.id).count()

        print(f"📦 Final Stock: {final_stock}")
        print(f"📋 Total Orders for Customer: {final_order_count} (Started at {initial_order_count})")

        # Checks:
        # 1. Order ID 2 should be the same as Order ID 1
        assert order_id_1 == order_id_2, f"❌ DUPLICATE CREATED! Order 1: #{order_id_1}, Order 2: #{order_id_2}"
        print("✅ Check 1 Passed: Request 2 returned the existing order rather than creating a duplicate!")

        # 2. Total orders increased by exactly 1, not 2
        assert final_order_count == initial_order_count + 1, f"❌ Order count mismatch! Expected {initial_order_count + 1}, got {final_order_count}"
        print("✅ Check 2 Passed: Exactly 1 new order exists in the database!")

        # 3. Stock was only reduced once (by 1)
        assert final_stock == initial_stock - 1, f"❌ Stock reduced multiple times! Expected {initial_stock - 1}, got {final_stock}"
        print("✅ Check 3 Passed: Stock was deducted exactly once!")

        print("\n🎉 BUY NOW TEST PASSED! Now testing Cart Checkout (/create-orders)...")

        # Set up a cart item for customer
        from app.models import Cart, CartItem
        cart = Cart.query.filter_by(user_id=customer.id).first()
        if not cart:
            cart = Cart(user_id=customer.id)
            db.session.add(cart)
            db.session.commit()

        # Clear any existing cart items
        CartItem.query.filter_by(cart_id=cart.id).delete()
        db.session.commit()

        # Add 1 item to cart
        c_item = CartItem(
            cart_id=cart.id,
            product_id=product.id,
            quantity=1,
            is_selected=True
        )
        db.session.add(c_item)
        db.session.commit()

        cart_initial_stock = int(Product.query.get(product.id).stock_quantity)
        cart_initial_order_count = Order.query.filter_by(customer_id=customer.id).count()

        cart_payload = {
            "address_id": address.id,
            "fulfillment_type": "delivery",
            "delivery_notes": "Cart test duplicate prevention",
            "orders": [{
                "temp_id": "temp_test_cart_order",
                "store_id": store.id,
                "store_name": store.name,
                "payment_method": payment_method,
                "fulfillment_type": "delivery",
                "subtotal": float(product.effective_price),
                "delivery_fee": 100.0,
                "total": float(product.effective_price) + 100.0,
                "items": [{
                    "product_id": product.id,
                    "quantity": 1,
                    "price": float(product.effective_price)
                }],
                "payment_proof_url": "https://res.cloudinary.com/dgyq49vi2/image/upload/v1789115952/e-flowers/payments/gcash_receipt_cart_01.jpg" if payment_method == "gcash" else None
            }]
        }

        print("\n--- STEP 4: Sending Cart Order Request 1 ---")
        c_res1 = client.post(
            '/api/v1/checkout/create-orders',
            json=cart_payload,
            headers={'Content-Type': 'application/json'}
        )
        print(f"Cart Response 1 Status: {c_res1.status_code}")
        c_data1 = c_res1.get_json() or {}
        assert c_res1.status_code in (200, 201) and c_data1.get('success'), f"Cart order 1 failed: {c_data1}"
        cart_order_id_1 = c_data1['orders'][0]['id']
        print(f"✅ Cart Order 1 placed successfully! Order ID: #{cart_order_id_1}")

        print("\n--- STEP 5: Sending Cart Order Request 2 Immediately (Simulating Double-Click) ---")
        c_res2 = client.post(
            '/api/v1/checkout/create-orders',
            json=cart_payload,
            headers={'Content-Type': 'application/json'}
        )
        print(f"Cart Response 2 Status: {c_res2.status_code}")
        c_data2 = c_res2.get_json() or {}
        cart_order_id_2 = c_data2['orders'][0]['id']
        print(f"Cart Response 2 Order ID: #{cart_order_id_2}")

        db.session.expire_all()
        cart_final_stock = int(Product.query.get(product.id).stock_quantity)
        cart_final_order_count = Order.query.filter_by(customer_id=customer.id).count()

        assert cart_order_id_1 == cart_order_id_2, f"❌ Cart duplicate created! {cart_order_id_1} vs {cart_order_id_2}"
        assert cart_final_order_count == cart_initial_order_count + 1, f"❌ Cart order count mismatch! Expected {cart_initial_order_count + 1}, got {cart_final_order_count}"
        assert cart_final_stock == cart_initial_stock - 1, f"❌ Cart stock deducted more than once! Expected {cart_initial_stock - 1}, got {cart_final_stock}"

        print("✅ Cart Check Passed: Request 2 returned existing order without creating a duplicate!")
        print(f"📦 Cart Final Stock: {cart_final_stock} (Deducted once)")
        print(f"📋 Cart Total Orders: {cart_final_order_count} (Incremented by 1)")

        print("\n🎉 ALL TESTS (BUY NOW & CART CHECKOUT) COMPLETED AND VERIFIED SUCCESSFULLY!")
        return True

if __name__ == '__main__':
    success = run_test()
    sys.exit(0 if success else 1)
