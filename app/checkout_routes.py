"""
Checkout endpoints for cart selection, delivery validation, and GCash checkout.
"""

print("=" * 60)
print("🔵 LOADING CHECKOUT_ROUTES.PY")
print("=" * 60)

from decimal import Decimal
import math
from functools import wraps
import json
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request, session
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request
from geoalchemy2.shape import from_shape
from shapely.geometry import Point

from app.extensions import db
from app.models import Cart, CartItem, Order, OrderItem, Store, User, UserAddress

# Create blueprint
checkout_bp = Blueprint("checkout", __name__)
print(f"✅ checkout_bp created: {checkout_bp}")

# Test route
@checkout_bp.route("/test", methods=["GET"])
def test_checkout():
    """Simple test route to verify blueprint is working"""
    print("✅ TEST ROUTE HIT! Checkout blueprint is working.")
    return jsonify({
        "success": True,
        "message": "Checkout blueprint is working!",
        "available_routes": [
            "/validate",
            "/create-orders",
            "/upload-proof",
            "/delete-temp-proof",
            "/process",
            "/cart/items/<int:item_id>/toggle",
            "/cart/store/<int:store_id>/toggle",
            "/order/<int:order_id>/payment-proof",
            "/order/<int:order_id>/status"
        ]
    }), 200

print("✅ Test route added to checkout_bp")
print("=" * 60)


def _build_stock_lookup(cart_items):
    """Aggregate requested quantities by product/variant from cart items."""
    stock_lookup = {}

    for cart_item in cart_items:
        if not cart_item.product:
            raise ValueError(f"Cart item {cart_item.id} has no product")

        key = (cart_item.product_id, cart_item.variant_id)
        if key not in stock_lookup:
            stock_lookup[key] = {
                "product": cart_item.product,
                "variant": cart_item.variant,
                "quantity": 0,
            }

        stock_lookup[key]["quantity"] += int(cart_item.quantity or 0)

    return stock_lookup


def _validate_stock_lookup(stock_lookup):
    """Validate that all requested product or variant stock is available."""
    for entry in stock_lookup.values():
        product = entry["product"]
        variant = entry["variant"]
        quantity = entry["quantity"]

        if quantity < 1:
            raise ValueError(f'Invalid quantity for "{product.name}"')

        if not product.is_available:
            raise ValueError(f'"{product.name}" is no longer available')

        if variant:
            if not variant.is_available:
                raise ValueError(f'"{product.name}" - {variant.name} is no longer available')
            if variant.stock_quantity < quantity:
                raise ValueError(
                    f'Insufficient stock for "{product.name}" - {variant.name}. '
                    f"Available: {variant.stock_quantity}, requested: {quantity}."
                )
        else:
            if product.stock_quantity < quantity:
                raise ValueError(
                    f'Insufficient stock for "{product.name}". '
                    f"Available: {product.stock_quantity}, requested: {quantity}."
                )


def _reduce_stock_lookup(stock_lookup, user_id, reason_notes):
    """Reduce stock with audit trail after an order has been created."""
    for entry in stock_lookup.values():
        product = entry["product"]
        variant = entry["variant"]
        quantity = entry["quantity"]
        product.reduce_stock(
            quantity,
            "other",
            user_id,
            reason_notes=reason_notes,
            variant=variant,
        )


def customer_only(f):
    """Decorator: Session or JWT required + must be customer role."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        # First check session (for web users)
        if 'user_id' in session:
            role = session.get('role')
            if role == 'customer':
                print(f"✅ User authenticated via session as customer (ID: {session['user_id']})")
                request.user_id = session['user_id']
                return f(*args, **kwargs)
            else:
                print(f"❌ Session user is {role}, customer required")
                return jsonify({"error": "Customer access required"}), 403
        
        # Otherwise check JWT token
        try:
            verify_jwt_in_request()
            claims = get_jwt()
            user_id = get_jwt_identity()
            role = claims.get("role")

            if not user_id:
                return jsonify({"error": "Invalid token"}), 401

            if role != "customer":
                return jsonify({"error": "Customer access required"}), 403

            request.user_id = user_id
            return f(*args, **kwargs)
        except Exception as e:
            print(f"JWT error: {e}")
            return jsonify({"error": "Authentication failed"}), 401
    return wrapper


def _municipality_matches(store, address):
    if not store.selected_municipalities or not address or not address.municipality:
        return True

    address_name = address.municipality.strip().casefold()
    return any(str(name).strip().casefold() == address_name for name in store.selected_municipalities)


def _check_store_delivery(store, address, subtotal):
    """Validate delivery eligibility for a store against the customer address."""
    if not address or address.latitude is None or address.longitude is None:
        return {
            "can_deliver": False,
            "reason": "Selected address is missing map coordinates.",
            "distance_km": None,
            "delivery_fee": None,
        }

    distance = store.calculate_distance(address.latitude, address.longitude)
    if distance is None or math.isinf(distance):
        return {
            "can_deliver": False,
            "reason": "Store location is incomplete.",
            "distance_km": None,
            "delivery_fee": None,
        }

    max_distance = float(store.max_delivery_distance or 0)
    if max_distance and distance > max_distance:
        return {
            "can_deliver": False,
            "reason": f"Address is outside the maximum delivery distance of {max_distance:.1f} km.",
            "distance_km": distance,
            "delivery_fee": None,
        }

    if store.delivery_method == "radius":
        radius_limit = float(store.delivery_radius_km or max_distance or 0)
        if radius_limit and distance > radius_limit:
            return {
                "can_deliver": False,
                "reason": f"Address is outside this store's delivery radius of {radius_limit:.1f} km.",
                "distance_km": distance,
                "delivery_fee": None,
            }
    elif store.delivery_method == "municipality" and not _municipality_matches(store, address):
        return {
            "can_deliver": False,
            "reason": f"{store.name} does not deliver to {address.municipality}.",
            "distance_km": distance,
            "delivery_fee": None,
        }
    elif store.delivery_area is not None:
        try:
            if not store.can_deliver_to(address.latitude, address.longitude):
                return {
                    "can_deliver": False,
                    "reason": "Selected address is outside the store delivery area.",
                    "distance_km": distance,
                    "delivery_fee": None,
                }
        except Exception as exc:
            print(f"Delivery area validation failed for store {store.id}: {exc}")

    delivery_fee = store.calculate_delivery_fee(distance, subtotal)
    return {
        "can_deliver": True,
        "reason": None,
        "distance_km": distance,
        "delivery_fee": delivery_fee,
    }


# ===== NEW ENDPOINT: Validate delivery and calculate totals (no order creation) =====
@checkout_bp.route("/validate", methods=["POST"])
@customer_only
def validate_checkout():
    """Validate delivery and calculate totals without creating orders."""
    print("🔵🔵🔵 VALIDATE CHECKOUT ROUTE WAS CALLED! 🔵🔵🔵")
    try:
        user_id = request.user_id
        data = request.get_json() or {}

        customer = User.query.get(user_id)
        if not customer:
            return jsonify({"error": "User not found"}), 404

        address_id = data.get("delivery_address_id")
        delivery_notes = data.get("delivery_notes", "")
        requested_items = data.get("items") or []

        if not address_id:
            return jsonify({"error": "delivery_address_id is required"}), 400

        address = UserAddress.query.filter_by(id=address_id, user_id=user_id).first()
        if not address:
            return jsonify({"error": "Delivery address not found"}), 404

        cart = Cart.query.filter_by(user_id=user_id).first()
        if not cart:
            return jsonify({"error": "Cart is empty"}), 404

        selected_item_ids = [int(item["item_id"]) for item in requested_items if item.get("item_id")]
        selected_items_query = CartItem.query.filter(CartItem.cart_id == cart.id)
        if selected_item_ids:
            selected_items_query = selected_items_query.filter(CartItem.id.in_(selected_item_ids))
        else:
            selected_items_query = selected_items_query.filter(CartItem.is_selected == True)

        selected_items = selected_items_query.all()
        if not selected_items:
            return jsonify({"error": "No items selected for checkout"}), 400

        items_by_store = {}
        for item in selected_items:
            if not item.product:
                raise Exception(f"Cart item {item.id} has no product")
            items_by_store.setdefault(item.product.store_id, []).append(item)

        store_checkout_data = []
        undeliverable_stores = []

        for store_id, store_items in items_by_store.items():
            store = Store.query.get(store_id)
            if not store:
                raise Exception(f"Store {store_id} not found")

            subtotal = Decimal("0")
            order_items_data = []

            for item in store_items:
                if not item.product.is_available:
                    raise Exception(f"{item.product.name} is no longer available")

                item_price = item.variant.price if item.variant else item.product.price
                subtotal += item_price * item.quantity
                order_items_data.append({
                    "product_id": item.product_id,
                    "variant_id": item.variant_id,
                    "quantity": item.quantity,
                    "price": float(item_price),
                })

            delivery_check = _check_store_delivery(store, address, subtotal)
            
            if not delivery_check["can_deliver"]:
                undeliverable_stores.append({
                    "store_id": store.id,
                    "store_name": store.name,
                    "reason": delivery_check["reason"],
                    "distance_km": round(delivery_check["distance_km"], 2) if delivery_check["distance_km"] is not None else None,
                })
            else:
                store_checkout_data.append({
                    "temp_id": f"temp_{uuid.uuid4().hex[:8]}",
                    "store_id": store.id,
                    "store_name": store.name,
                    "subtotal": float(subtotal),
                    "delivery_fee": float(delivery_check["delivery_fee"]),
                    "distance_km": delivery_check["distance_km"],
                    "total": float(subtotal + delivery_check["delivery_fee"]),
                    "items": order_items_data,
                    "gcash_qr_codes": [qr.to_dict() for qr in store.gcash_qr_images],
                    "gcash_instructions": store.gcash_instructions
                })

        if undeliverable_stores:
            return jsonify({
                "success": False,
                "error": "Some selected items cannot be delivered to this address.",
                "undeliverable_stores": undeliverable_stores,
            }), 400

        return jsonify({
            "success": True,
            "orders": store_checkout_data,
            "address": address.to_dict()
        }), 200

    except Exception as e:
        print(f"Validate checkout error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ===== NEW ENDPOINT: Delete temporary proof (for abandoned checkouts) =====
@checkout_bp.route("/delete-temp-proof", methods=["POST"])
@customer_only
def delete_temp_proof():
    """Delete a temporary payment proof that was not used in checkout."""
    print("🔵🔵🔵 DELETE TEMP PROOF ROUTE WAS CALLED! 🔵🔵🔵")
    try:
        data = request.get_json()
        public_id = data.get("public_id")
        
        if not public_id:
            return jsonify({"error": "public_id required"}), 400
        
        from app.utils.cloudinary_helper import delete_from_cloudinary
        
        result = delete_from_cloudinary(public_id)
        
        if result:
            print(f"✅ Deleted temp proof: {public_id}")
            return jsonify({
                "success": True,
                "message": "Temp proof deleted"
            })
        else:
            print(f"⚠️ Failed to delete temp proof: {public_id}")
            return jsonify({
                "success": False,
                "message": "Delete failed"
            }), 500
        
    except Exception as e:
        print(f"Delete temp proof error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ===== UPLOAD PROOF WITHOUT CREATING ORDER =====
@checkout_bp.route("/upload-proof", methods=["POST"])
@customer_only
def upload_proof_temp():
    """Upload payment proof temporarily without creating an order."""
    print("🔵🔵🔵 UPLOAD PROOF (TEMP) ROUTE WAS CALLED! 🔵🔵🔵")
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        if not file or file.filename == "":
            return jsonify({"error": "No file selected"}), 400

        allowed_extensions = {"jpg", "jpeg", "png", "gif"}
        if not ("." in file.filename and file.filename.rsplit(".", 1)[1].lower() in allowed_extensions):
            return jsonify({"error": "Only image files allowed (jpg, png, gif)"}), 400

        try:
            from app.utils.cloudinary_helper import upload_to_cloudinary

            result = upload_to_cloudinary(
                file,
                folder=f"temp_payment_proofs/{datetime.utcnow().strftime('%Y-%m-%d')}",
                resource_type="image",
            )

            if not result or not result.get("success"):
                return jsonify({"error": "Upload failed"}), 500

            return jsonify({
                "success": True,
                "url": result["url"],
                "public_id": result["public_id"]
            }), 200

        except ImportError:
            return jsonify({"error": "Cloudinary not configured"}), 500

    except Exception as e:
        print(f"Upload proof error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ===== CREATE ORDERS ENDPOINT =====
@checkout_bp.route("/create-orders", methods=["POST"])
@customer_only
def create_orders():
    """Create orders after payment proof has been uploaded."""
    print("🔵🔵🔵 CREATE ORDERS ROUTE WAS CALLED! 🔵🔵🔵")
    try:
        user_id = request.user_id
        data = request.get_json() or {}
        
        print(f"📦 Received create-orders data: {data}")

        orders_data = data.get("orders", [])
        address_id = data.get("address_id")
        delivery_notes = data.get("delivery_notes", "")

        print(f"📌 Address ID: {address_id}")
        print(f"📝 Delivery notes: {delivery_notes}")
        print(f"📦 Orders count: {len(orders_data)}")

        if not address_id:
            return jsonify({"error": "Address ID required"}), 400

        if not orders_data:
            return jsonify({"error": "No orders data provided"}), 400

        address = UserAddress.query.filter_by(id=address_id, user_id=user_id).first()
        if not address:
            return jsonify({"error": "Delivery address not found"}), 404

        cart = Cart.query.filter_by(user_id=user_id).first()
        if not cart:
            return jsonify({"error": "Cart not found"}), 404

        selected_items = []
        
        for order_data in orders_data:
            for item in order_data.get("items", []):
                cart_item = CartItem.query.filter_by(
                    cart_id=cart.id,
                    product_id=item.get("product_id"),
                    variant_id=item.get("variant_id")
                ).first()
                if cart_item and cart_item.is_selected:
                    selected_items.append(cart_item)
                    print(f"  ✅ Found cart item: {cart_item.id} - {cart_item.product.name}")

        stock_lookup = _build_stock_lookup(selected_items)
        _validate_stock_lookup(stock_lookup)

        delivery_point = from_shape(Point(address.longitude, address.latitude), srid=4326)
        orders_created = []

        for order_data in orders_data:
            store = Store.query.get(order_data.get("store_id"))
            if not store:
                print(f"⚠️ Store not found: {order_data.get('store_id')}")
                continue

            # Phase 1: Extract and parse per-store delivery date/time
            order_delivery_date_str = order_data.get("requested_delivery_date")
            order_delivery_time = order_data.get("requested_delivery_time")
            order_delivery_date = None
            
            if order_delivery_date_str:
                try:
                    order_delivery_date = datetime.strptime(order_delivery_date_str, '%Y-%m-%d').date()
                    print(f"✅ Parsed delivery date for {store.name}: {order_delivery_date}")
                except ValueError as e:
                    print(f"⚠️ Failed to parse delivery date '{order_delivery_date_str}': {e}")

            order = Order(
                customer_id=user_id,
                store_id=store.id,
                order_type="online",
                status="pending",
                subtotal_amount=order_data.get("subtotal", 0),
                delivery_fee=order_data.get("delivery_fee", 0),
                distance_km=order_data.get("distance_km"),
                total_amount=order_data.get("total", 0),
                payment_method="gcash",
                payment_status="pending_verification",
                delivery_location=delivery_point,
                delivery_address=address.address_line,
                delivery_notes=delivery_notes,
                requested_delivery_date=order_delivery_date,  # Phase 1: Per-store date
                requested_delivery_time=order_delivery_time,  # Phase 1: Per-store time
                customer_latitude=address.latitude,
                customer_longitude=address.longitude,
                mapbox_place_id=address.place_id,
            )

            payment_proof_url = order_data.get("payment_proof_url")
            payment_proof_public_id = order_data.get("payment_proof_public_id")
            if payment_proof_url:
                order.payment_proof_url = payment_proof_url
                order.payment_proof_public_id = payment_proof_public_id
                print(f"  📸 Added payment proof: {payment_proof_url}")

            db.session.add(order)
            db.session.flush()
            print(f"  ✅ Created order #{order.id} for store {store.name}")

            for item_data in order_data.get("items", []):
                db.session.add(OrderItem(
                    order_id=order.id,
                    product_id=item_data["product_id"],
                    variant_id=item_data.get("variant_id"),
                    quantity=item_data["quantity"],
                    price=item_data["price"],
                ))
                print(f"    ✅ Added item: product {item_data['product_id']} x {item_data['quantity']}")

            db.session.flush()
            orders_created.append(order.to_dict())

        _reduce_stock_lookup(
            stock_lookup,
            user_id,
            f"Reduced automatically after online checkout by customer #{user_id}",
        )

        print(f"🗑️ Removing {len(selected_items)} selected items from cart")
        for item in selected_items:
            db.session.delete(item)

        db.session.commit()
        print(f"✅ Successfully created {len(orders_created)} orders")

        return jsonify({
            "success": True,
            "message": f"Created {len(orders_created)} order(s)",
            "orders": orders_created
        }), 201

    except Exception as e:
        db.session.rollback()
        print(f"❌ Create orders error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@checkout_bp.route("/cart/items/<int:item_id>/toggle", methods=["PUT"])
@customer_only
def toggle_item_selection(item_id):
    """Toggle selection status of a cart item."""
    try:
        user_id = request.user_id

        item = CartItem.query.get_or_404(item_id)
        if item.cart.user_id != user_id:
            return jsonify({"error": "Unauthorized"}), 403

        item.is_selected = not item.is_selected
        db.session.commit()

        return jsonify({
            "success": True,
            "item_id": item_id,
            "is_selected": item.is_selected,
            "cart": item.cart.to_dict(),
        })
    except Exception as e:
        db.session.rollback()
        print(f"Error toggling selection: {e}")
        return jsonify({"error": str(e)}), 500


@checkout_bp.route("/cart/store/<int:store_id>/toggle", methods=["PUT"])
@customer_only
def toggle_store_selection(store_id):
    """Toggle selection of all cart items from a store."""
    try:
        user_id = request.user_id
        data = request.get_json() or {}
        selected = bool(data.get("selected", True))

        cart = Cart.query.filter_by(user_id=user_id).first()
        if not cart:
            return jsonify({"error": "Cart not found"}), 404

        items_updated = 0
        for item in cart.items.all():
            if item.product and item.product.store_id == store_id:
                item.is_selected = selected
                items_updated += 1

        db.session.commit()
        return jsonify({
            "success": True,
            "store_id": store_id,
            "items_updated": items_updated,
            "cart": cart.to_dict(),
        })
    except Exception as e:
        db.session.rollback()
        print(f"Error toggling store selection: {e}")
        return jsonify({"error": str(e)}), 500


# Keep the original process endpoint for backward compatibility
@checkout_bp.route("/process", methods=["POST"])
@customer_only
def process_checkout():
    """Original checkout endpoint - kept for backward compatibility."""
    print("🔵🔵🔵 PROCESS CHECKOUT ROUTE WAS CALLED! 🔵🔵🔵")
    try:
        user_id = request.user_id
        data = request.get_json() or {}

        customer = User.query.get(user_id)
        if not customer:
            return jsonify({"error": "User not found"}), 404

        address_id = data.get("delivery_address_id")
        delivery_notes = data.get("delivery_notes", "")
        requested_items = data.get("items") or []

        if not address_id:
            return jsonify({"error": "delivery_address_id is required"}), 400

        # Ensure address_id is an integer
        try:
            address_id = int(address_id)
        except (ValueError, TypeError):
            return jsonify({"error": "delivery_address_id must be a valid integer"}), 400

        address = UserAddress.query.filter_by(id=address_id, user_id=user_id).first()
        if not address:
            return jsonify({"error": "Delivery address not found"}), 404

        cart = Cart.query.filter_by(user_id=user_id).first()
        if not cart:
            return jsonify({"error": "Cart is empty"}), 404

        selected_item_ids = [int(item["item_id"]) for item in requested_items if item.get("item_id")]
        selected_items_query = CartItem.query.filter(CartItem.cart_id == cart.id)
        if selected_item_ids:
            selected_items_query = selected_items_query.filter(CartItem.id.in_(selected_item_ids))
        else:
            selected_items_query = selected_items_query.filter(CartItem.is_selected == True)

        selected_items = selected_items_query.all()
        if not selected_items:
            return jsonify({"error": "No items selected for checkout"}), 400

        stock_lookup = _build_stock_lookup(selected_items)
        _validate_stock_lookup(stock_lookup)

        items_by_store = {}
        for item in selected_items:
            if not item.product:
                raise Exception(f"Cart item {item.id} has no product")
            items_by_store.setdefault(item.product.store_id, []).append(item)

        store_checkout_data = {}
        for store_id, store_items in items_by_store.items():
            store = Store.query.get(store_id)
            if not store:
                raise Exception(f"Store {store_id} not found")

            subtotal = Decimal("0")
            order_items_data = []

            for item in store_items:
                if not item.product.is_available:
                    raise Exception(f"{item.product.name} is no longer available")

                item_price = item.variant.price if item.variant else item.product.price
                subtotal += item_price * item.quantity
                order_items_data.append({
                    "product_id": int(item.product_id),
                    "variant_id": int(item.variant_id) if item.variant_id else None,
                    "quantity": int(item.quantity),
                    "price": float(item_price),
                })

            store_checkout_data[store_id] = {
                "store": store,
                "subtotal": subtotal,
                "order_items_data": order_items_data,
                "delivery_check": _check_store_delivery(store, address, subtotal),
            }

        undeliverable_stores = []
        for checkout_data in store_checkout_data.values():
            delivery_check = checkout_data["delivery_check"]
            if delivery_check["can_deliver"]:
                continue

            store = checkout_data["store"]
            undeliverable_stores.append({
                "store_id": store.id,
                "store_name": store.name,
                "reason": delivery_check["reason"],
                "distance_km": round(delivery_check["distance_km"], 2) if delivery_check["distance_km"] is not None else None,
            })

        if undeliverable_stores:
            return jsonify({
                "error": "Some selected items cannot be delivered to this address.",
                "undeliverable_stores": undeliverable_stores,
            }), 400

        delivery_point = from_shape(Point(address.longitude, address.latitude), srid=4326)
        orders_created = []

        for checkout_data in store_checkout_data.values():
            store = checkout_data["store"]
            subtotal = checkout_data["subtotal"]
            order_items_data = checkout_data["order_items_data"]
            delivery_check = checkout_data["delivery_check"]
            distance = delivery_check["distance_km"]
            delivery_fee = delivery_check["delivery_fee"]

            order = Order(
                customer_id=int(user_id),
                store_id=int(store.id),
                order_type="online",
                status="pending",
                subtotal_amount=float(subtotal),
                delivery_fee=float(delivery_fee),
                distance_km=float(distance) if distance else None,
                total_amount=float(subtotal + delivery_fee),
                payment_method="gcash",
                payment_status="pending",
                delivery_location=delivery_point,
                delivery_address=address.address_line,
                delivery_notes=delivery_notes,
                customer_latitude=address.latitude,
                customer_longitude=address.longitude,
                mapbox_place_id=address.place_id,
            )

            db.session.add(order)
            db.session.flush()

            for item_data in order_items_data:
                db.session.add(OrderItem(
                    order_id=order.id,
                    product_id=item_data["product_id"],
                    variant_id=item_data["variant_id"],
                    quantity=item_data["quantity"],
                    price=item_data["price"],
                ))

            db.session.flush()

            order_dict = order.to_dict()
            order_dict["items"] = [oi.to_dict() for oi in order.items]
            order_dict["gcash_qr_codes"] = [qr.to_dict() for qr in store.gcash_qr_images]
            order_dict["gcash_instructions"] = store.gcash_instructions
            order_dict["distance_km"] = round(distance, 2) if distance is not None else None
            order_dict["selected_address"] = address.to_dict()

            orders_created.append(order_dict)

        _reduce_stock_lookup(
            stock_lookup,
            user_id,
            f"Reduced automatically after online checkout by customer #{user_id}",
        )

        CartItem.query.filter(
            CartItem.id.in_([item.id for item in selected_items])
        ).delete()

        db.session.commit()
        return jsonify({
            "success": True,
            "message": f"Created {len(orders_created)} order(s). Please upload payment proof.",
            "orders": orders_created,
        }), 201

    except Exception as e:
        db.session.rollback()
        print(f"Checkout error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@checkout_bp.route("/order/<int:order_id>/payment-proof", methods=["POST"])
@customer_only
def upload_payment_proof(order_id):
    """Upload GCash payment proof image for an order."""
    try:
        user_id = request.user_id
        order = Order.query.get_or_404(order_id)

        if order.customer_id != user_id:
            return jsonify({"error": "Unauthorized"}), 403

        if order.payment_status == "verified":
            return jsonify({"error": "Payment already verified"}), 400

        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        if not file or file.filename == "":
            return jsonify({"error": "No file selected"}), 400

        allowed_extensions = {"jpg", "jpeg", "png", "gif"}
        if not ("." in file.filename and file.filename.rsplit(".", 1)[1].lower() in allowed_extensions):
            return jsonify({"error": "Only image files allowed (jpg, png, gif)"}), 400

        try:
            from app.utils.cloudinary_helper import delete_from_cloudinary, upload_to_cloudinary

            result = upload_to_cloudinary(
                file,
                folder=f"payment_proofs/order_{order_id}",
                resource_type="image",
            )

            if not result or not result.get("success"):
                return jsonify({"error": "Upload failed"}), 500

            if order.payment_proof_public_id:
                delete_from_cloudinary(order.payment_proof_public_id)

            order.payment_proof = file.filename
            order.payment_proof_public_id = result["public_id"]
            order.payment_proof_url = result["url"]
            order.payment_status = "pending_verification"
            db.session.commit()

            return jsonify({
                "success": True,
                "message": "Payment proof submitted. Awaiting seller verification.",
                "order": order.to_dict(),
                "payment_proof_url": result["url"],
            }), 200

        except ImportError:
            order.payment_proof = file.filename
            order.payment_status = "pending_verification"
            db.session.commit()

            return jsonify({
                "success": True,
                "message": "Payment proof submitted. Awaiting seller verification.",
                "order": order.to_dict(),
            }), 200

    except Exception as e:
        db.session.rollback()
        print(f"Upload error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@checkout_bp.route("/order/<int:order_id>/status", methods=["GET"])
@customer_only
def get_order_payment_status(order_id):
    """Get current payment status of an order."""
    try:
        user_id = request.user_id
        order = Order.query.get_or_404(order_id)

        if order.customer_id != user_id:
            return jsonify({"error": "Unauthorized"}), 403

        return jsonify({
            "success": True,
            "order_id": order_id,
            "payment_status": order.payment_status,
            "payment_method": order.payment_method,
            "has_payment_proof": bool(order.payment_proof_url),
            "payment_proof_url": order.payment_proof_url,
            "total_amount": float(order.total_amount),
            "status": order.status,
        })
    except Exception as e:
        print(f"Error getting status: {e}")
        return jsonify({"error": str(e)}), 500


print("✅ checkout_routes.py loaded successfully")
print("=" * 60)
