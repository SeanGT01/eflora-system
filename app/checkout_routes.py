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
import re
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request, session
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import inspect

from app.extensions import db
from app.models import Cart, CartItem, Notification, Order, OrderItem, Product, ProductVariant, Store, User, UserAddress, StorePaymentSetting
from app.addon_helpers import (
    resolve_structured_addon_selections,
    structured_addons_subtotal,
    attach_order_item_addons,
    decrement_addon_option_stock,
)

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


def _ensure_store_payment_settings_table():
    try:
        if inspect(db.engine).has_table("store_payment_settings"):
            return True
        StorePaymentSetting.__table__.create(db.engine, checkfirst=True)
        return True
    except Exception:
        return False


def _store_allows_cod(store_id):
    if not _ensure_store_payment_settings_table():
        return False
    row = StorePaymentSetting.query.filter_by(store_id=store_id).first()
    return bool(row.allow_cod) if row else False


def _free_delivery_fields(store, subtotal, delivery_fee):
    """Checkout payload fields for free-delivery min / applied state."""
    enabled = bool(getattr(store, 'free_delivery_enabled', True))
    try:
        minimum = float(store.free_delivery_minimum or 0)
    except Exception:
        minimum = 0.0
    try:
        sub = float(subtotal or 0)
    except Exception:
        sub = 0.0
    applied = False
    remaining = None
    if enabled:
        try:
            fee_val = Decimal(str(delivery_fee if delivery_fee is not None else 0))
        except Exception:
            fee_val = Decimal('0')
        applied = fee_val <= 0
        remaining = 0.0 if applied else max(0.0, round(minimum - sub, 2))
    return {
        "free_delivery_enabled": enabled,
        "free_delivery_minimum": minimum,
        "free_delivery_applied": applied,
        "amount_to_free_delivery": remaining,
    }


def _resolve_buy_now_addons(addons_data, store_id, exclude_product_id=None):
    """
    Validate optional buy-now add-on products (You might also like).
    Returns (resolved_lines, error_response).
    resolved_lines: list of dicts with product, quantity, price (Decimal), name, image_url
    """
    if not addons_data:
        return [], None
    if not isinstance(addons_data, list):
        return None, (jsonify({"error": "addons must be a list"}), 400)

    resolved = []
    seen = set()
    for raw in addons_data:
        if not isinstance(raw, dict):
            return None, (jsonify({"error": "Invalid addon item"}), 400)
        try:
            product_id = int(raw.get("product_id") or raw.get("id"))
            quantity = int(raw.get("quantity") or 1)
        except (TypeError, ValueError):
            return None, (jsonify({"error": "Invalid addon product_id or quantity"}), 400)

        if quantity < 1:
            return None, (jsonify({"error": "Addon quantity must be at least 1"}), 400)
        if exclude_product_id and product_id == int(exclude_product_id):
            continue
        if product_id in seen:
            # Merge quantities for duplicates
            for line in resolved:
                if line["product"].id == product_id:
                    line["quantity"] += quantity
                    break
            continue
        seen.add(product_id)

        addon_product = Product.query.get(product_id)
        if not addon_product:
            return None, (jsonify({"error": f"Addon product #{product_id} not found"}), 404)
        if addon_product.store_id != store_id:
            return None, (jsonify({
                "error": f'"{addon_product.name}" is not from the same store'
            }), 400)
        if not addon_product.is_available or getattr(addon_product, "is_archived", False):
            return None, (jsonify({
                "error": f'"{addon_product.name}" is no longer available'
            }), 400)
        if int(addon_product.stock_quantity or 0) < quantity:
            return None, (jsonify({
                "error": (
                    f'Insufficient stock for "{addon_product.name}". '
                    f'Available: {addon_product.stock_quantity}'
                )
            }), 400)

        primary = None
        try:
            images = list(addon_product.images or [])
            primary = next((img for img in images if getattr(img, "is_primary", False)), None)
            if not primary and images:
                primary = images[0]
        except Exception:
            primary = None
        image_url = ""
        if primary is not None:
            image_url = getattr(primary, "cloudinary_url", None) or getattr(primary, "image_url", "") or ""

        resolved.append({
            "product": addon_product,
            "quantity": quantity,
            "price": Decimal(str(addon_product.effective_price)),
            "name": addon_product.name,
            "image_url": image_url,
        })

    return resolved, None


def _subtotal_from_order_items(order_data):
    line_total = Decimal('0')
    for item_data in order_data.get('items') or []:
        try:
            price = Decimal(str(item_data.get('price') or 0))
            qty = int(item_data.get('quantity') or 0)
        except Exception:
            continue
        line_total += price * qty
        try:
            line_total += Decimal(str(item_data.get('addons_total') or 0))
        except Exception:
            for a in item_data.get('addons') or []:
                try:
                    line_total += Decimal(str(a.get('price') or 0)) * int(a.get('quantity') or 1)
                except Exception:
                    pass
    if line_total > 0:
        return line_total
    try:
        return Decimal(str(order_data.get('subtotal') or 0))
    except Exception:
        return Decimal('0')


def _cart_items_subtotal(cart_items):
    """Product + structured add-ons subtotal from live cart rows."""
    total = Decimal('0')
    for item in cart_items or []:
        try:
            total += Decimal(str(item.subtotal or 0))
        except Exception:
            continue
    return total


def _enrich_order_items_addons_from_cart(order_data, selected_items):
    """Attach addons_total onto payload items from matching cart rows."""
    items = order_data.get('items') or []
    for item_data in items:
        if item_data.get('addons_total') not in (None, '', 0, '0'):
            continue
        cart_match = next(
            (
                ci for ci in selected_items
                if ci.product_id == item_data.get('product_id')
                and (ci.variant_id or None) == (item_data.get('variant_id') or None)
            ),
            None,
        )
        if not cart_match:
            continue
        item_data['addons_total'] = float(cart_match.addons_subtotal or 0)
        item_data['addons'] = [a.to_dict() for a in (cart_match.addons or [])]
    return order_data


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


def _cart_structured_addon_lines(cart_items):
    """Resolved structured add-on lines for cart items (independent of flower qty)."""
    lines = []
    for cart_item in cart_items or []:
        for row in (cart_item.addons or []):
            opt = row.addon_option
            if not opt:
                continue
            unit_qty = max(1, int(row.quantity or 1))
            lines.append({
                'option': opt,
                'quantity': unit_qty,
                'price': Decimal(str(opt.price or 0)),
                'name': opt.name,
                'image_url': opt.image_url or '',
                'group_id': opt.group_id,
                'group_name': opt.group.name if opt.group else None,
                'cart_item_id': cart_item.id,
            })
    return lines


def _validate_structured_addon_stock(lines):
    for line in lines or []:
        opt = line['option']
        need = int(line['quantity'])
        if not opt.is_available or not opt.group or not opt.group.is_active:
            raise ValueError(f'"{opt.name}" is no longer available')
        if int(opt.stock_quantity or 0) < need:
            raise ValueError(
                f'Insufficient stock for "{opt.name}". Available: {opt.stock_quantity}'
            )


def _validate_stock_lookup(stock_lookup):
    """Validate that all requested product or variant stock is available."""
    issues = _collect_stock_issues(stock_lookup)
    if issues:
        raise ValueError(issues[0]["message"])


def _collect_stock_issues(stock_lookup):
    """Return structured stock problems for checkout pre-checks."""
    issues = []
    for entry in stock_lookup.values():
        product = entry["product"]
        variant = entry["variant"]
        quantity = int(entry.get("quantity") or 0)
        label = f"{product.name} — {variant.name}" if variant else product.name
        image_url = None
        if variant and getattr(variant, "image_url", None):
            image_url = variant.image_url
        elif product and getattr(product, "images", None):
            primary = next((img for img in product.images if img.is_primary), None)
            image_url = (primary or (product.images[0] if product.images else None))
            image_url = image_url.image_url if image_url else None

        if quantity < 1:
            issues.append({
                "product_id": product.id,
                "variant_id": variant.id if variant else None,
                "name": label,
                "requested": quantity,
                "available": 0,
                "code": "invalid_quantity",
                "message": f'Invalid quantity for "{label}"',
                "image_url": image_url,
            })
            continue

        if not product.is_available or (variant and not variant.is_available):
            issues.append({
                "product_id": product.id,
                "variant_id": variant.id if variant else None,
                "name": label,
                "requested": quantity,
                "available": 0,
                "code": "unavailable",
                "message": f'"{label}" is no longer available from the store.',
                "image_url": image_url,
            })
            continue

        available = int(variant.stock_quantity if variant else product.stock_quantity or 0)
        if available <= 0:
            issues.append({
                "product_id": product.id,
                "variant_id": variant.id if variant else None,
                "name": label,
                "requested": quantity,
                "available": 0,
                "code": "out_of_stock",
                "message": f'"{label}" is out of stock.',
                "image_url": image_url,
            })
        elif available < quantity:
            issues.append({
                "product_id": product.id,
                "variant_id": variant.id if variant else None,
                "name": label,
                "requested": quantity,
                "available": available,
                "code": "insufficient",
                "message": (
                    f'"{label}" only has {available} left, but you selected {quantity}.'
                ),
                "image_url": image_url,
            })
    return issues


def _reduce_stock_lookup(stock_lookup, user_id, reason_notes, store_id=None):
    """Reduce stock with audit trail after an order has been created.

    When store_id is provided, emit low_stock seller notifications for products
    that cross into the low-stock threshold.
    """
    from app.utils.seller_notifications import (
        LOW_STOCK_THRESHOLD,
        notify_low_stock_if_crossed,
    )

    for entry in stock_lookup.values():
        product = entry["product"]
        variant = entry["variant"]
        quantity = entry["quantity"]

        if variant is not None:
            before = int(variant.stock_quantity or 0)
        else:
            before = int(product.stock_quantity or 0)

        product.reduce_stock(
            quantity,
            "other",
            user_id,
            reason_notes=reason_notes,
            variant=variant,
        )

        if variant is not None:
            after = int(variant.stock_quantity or 0)
        else:
            after = int(product.stock_quantity or 0)

        sid = store_id or getattr(product, 'store_id', None)
        if sid is not None:
            notify_low_stock_if_crossed(
                store_id=sid,
                product=product,
                stock_before=before,
                stock_after=after,
                threshold=LOW_STOCK_THRESHOLD,
            )


def _generate_store_time_slots_for_date(store, target_date):
    """Generate bookable time-slot values for a store/date (Philippine time)."""
    from app.utils.store_schedule import build_store_time_slots, slot_values
    return slot_values(build_store_time_slots(store, target_date))


def _validate_requested_delivery_slot(store, requested_delivery_date, requested_delivery_time):
    """
    Validate requested slot against store schedule, delivery window, cutoff, and lead time.
    Returns None if valid/skip; otherwise returns error message.
    """
    from app.utils.store_schedule import validate_delivery_slot

    if not requested_delivery_date or not requested_delivery_time:
        return None

    normalized_slot = _normalize_requested_delivery_time(requested_delivery_time)
    if not normalized_slot:
        return "Invalid delivery time format."

    return validate_delivery_slot(store, requested_delivery_date, normalized_slot)


def _normalize_requested_delivery_time(value):
    """
    Normalize delivery time slot to canonical 24h format: HH:MM-HH:MM.
    Accepts:
      - HH:MM-HH:MM
      - HH:MM - HH:MM
      - h:mm AM - h:mm PM
    """
    if value is None:
        return None

    raw = str(value).strip()
    if not raw:
        return None

    m24 = re.match(r"^(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})$", raw)
    if m24:
        try:
            start = datetime.strptime(m24.group(1), "%H:%M")
            end = datetime.strptime(m24.group(2), "%H:%M")
            return f"{start:%H:%M}-{end:%H:%M}"
        except ValueError:
            return None

    m12 = re.match(
        r"^(\d{1,2}:\d{2}\s*[AaPp][Mm])\s*-\s*(\d{1,2}:\d{2}\s*[AaPp][Mm])$",
        raw,
    )
    if m12:
        try:
            start = datetime.strptime(re.sub(r"\s+", " ", m12.group(1)).upper(), "%I:%M %p")
            end = datetime.strptime(re.sub(r"\s+", " ", m12.group(2)).upper(), "%I:%M %p")
            return f"{start:%H:%M}-{end:%H:%M}"
        except ValueError:
            return None

    return None


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


def _normalize_place_name(value):
    """Case/accent-insensitive place comparison for municipality matching."""
    import unicodedata
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return ' '.join(text.casefold().split())


def _municipality_matches(store, address):
    """True only when the address municipality is in the store's selected list."""
    selected = store.selected_municipalities or []
    if not selected or not address or not address.municipality:
        return False

    address_name = _normalize_place_name(address.municipality)
    if not address_name:
        return False
    return any(_normalize_place_name(name) == address_name for name in selected)


def _check_store_delivery(store, address, subtotal):
    """Validate delivery eligibility for a store against the customer address.

    Coverage rules follow the store's active delivery_method only:
    - municipality → selected cities/towns (ignore leftover radius/max-distance)
    - radius → radius / max distance
    - zone → drawn polygon (optional max distance hard limit)
    """
    if not store or not address:
        return {
            "can_deliver": False,
            "reason": "Selected address is missing.",
            "distance_km": None,
            "delivery_fee": None,
        }

    method = (store.delivery_method or 'radius').strip().casefold()
    has_coords = address.latitude is not None and address.longitude is not None
    distance = None
    if has_coords and store.latitude is not None and store.longitude is not None:
        distance = store.calculate_distance(address.latitude, address.longitude)
        if distance is not None and math.isinf(distance):
            distance = None

    # ── Municipality coverage: city/town list only ──
    if method == 'municipality':
        selected = store.selected_municipalities or []
        if not selected:
            # Fall back to polygon if list missing but geometry exists
            if has_coords and (
                store.municipality_delivery_area is not None
                or store.delivery_area is not None
            ):
                try:
                    if not store.can_deliver_to(address.latitude, address.longitude):
                        return {
                            "can_deliver": False,
                            "reason": "Selected address is outside the store delivery area.",
                            "distance_km": distance,
                            "delivery_fee": None,
                        }
                except Exception as exc:
                    print(f"Municipality geometry validation failed for store {store.id}: {exc}")
                    return {
                        "can_deliver": False,
                        "reason": "Could not validate delivery coverage right now.",
                        "distance_km": distance,
                        "delivery_fee": None,
                    }
            else:
                return {
                    "can_deliver": False,
                    "reason": "Store has no delivery municipalities configured.",
                    "distance_km": distance,
                    "delivery_fee": None,
                }
        elif not _municipality_matches(store, address):
            return {
                "can_deliver": False,
                "reason": f"{store.name} does not deliver to {address.municipality}.",
                "distance_km": distance,
                "delivery_fee": None,
            }

        delivery_fee = store.calculate_delivery_fee(distance or 0, subtotal)
        return {
            "can_deliver": True,
            "reason": None,
            "distance_km": distance,
            "delivery_fee": delivery_fee,
        }

    # ── Radius / zone need map coordinates ──
    if not has_coords:
        return {
            "can_deliver": False,
            "reason": "Selected address is missing map coordinates.",
            "distance_km": None,
            "delivery_fee": None,
        }

    if distance is None:
        return {
            "can_deliver": False,
            "reason": "Store location is incomplete.",
            "distance_km": None,
            "delivery_fee": None,
        }

    max_distance = float(store.max_delivery_distance or 0)

    if method == 'radius':
        radius_limit = float(store.delivery_radius_km or max_distance or 0)
        hard_limit = max_distance or radius_limit
        if hard_limit and distance > hard_limit:
            return {
                "can_deliver": False,
                "reason": (
                    f"This shop can't deliver to your location. Your address exceeds "
                    f"the maximum delivery distance of {hard_limit:.1f} km for this store."
                ),
                "distance_km": distance,
                "delivery_fee": None,
            }
        if radius_limit and distance > radius_limit:
            return {
                "can_deliver": False,
                "reason": f"Address is outside this store's delivery radius of {radius_limit:.1f} km.",
                "distance_km": distance,
                "delivery_fee": None,
            }
    else:
        # Zone / custom polygon — optional max-distance hard limit still applies
        if max_distance and distance > max_distance:
            return {
                "can_deliver": False,
                "reason": (
                    f"This shop can't deliver to your location. Your address exceeds "
                    f"the maximum delivery distance of {max_distance:.1f} km for this store."
                ),
                "distance_km": distance,
                "delivery_fee": None,
            }

        has_area = (
            store.zone_delivery_area is not None
            or store.delivery_area is not None
            or store.municipality_delivery_area is not None
        )
        if has_area:
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
                return {
                    "can_deliver": False,
                    "reason": "Could not validate delivery coverage right now.",
                    "distance_km": distance,
                    "delivery_fee": None,
                }
        elif not max_distance:
            return {
                "can_deliver": False,
                "reason": "Store has no delivery area configured.",
                "distance_km": distance,
                "delivery_fee": None,
            }

    delivery_fee = store.calculate_delivery_fee(distance, subtotal)
    return {
        "can_deliver": True,
        "reason": None,
        "distance_km": distance,
        "delivery_fee": delivery_fee,
    }


# ===== NEW ENDPOINT: Validate delivery and calculate totals (no order creation) =====
@checkout_bp.route("/validate-stock", methods=["POST"])
@customer_only
def validate_checkout_stock():
    """Pre-checkout stock check for selected cart items or a buy-now item."""
    try:
        user_id = request.user_id
        data = request.get_json() or {}
        mode = (data.get("mode") or "cart").strip().lower()

        stock_lookup = {}

        if mode == "buy_now":
            product_id = data.get("product_id")
            variant_id = data.get("variant_id")
            quantity = int(data.get("quantity") or 1)
            if not product_id:
                return jsonify({"success": False, "error": "product_id is required"}), 400

            product = Product.query.get(product_id)
            if not product:
                return jsonify({"success": False, "error": "Product not found"}), 404

            variant = None
            if variant_id:
                variant = ProductVariant.query.filter_by(id=variant_id, product_id=product.id).first()
                if not variant:
                    return jsonify({"success": False, "error": "Variant not found"}), 404

            stock_lookup[(product.id, variant.id if variant else None)] = {
                "product": product,
                "variant": variant,
                "quantity": quantity,
            }

            # Include You might also like / add-on selections
            addon_lines, addon_err = _resolve_buy_now_addons(
                data.get("addons") or [],
                product.store_id,
                exclude_product_id=product.id,
            )
            if addon_err:
                return addon_err
            for line in addon_lines:
                key = (line["product"].id, None)
                if key not in stock_lookup:
                    stock_lookup[key] = {
                        "product": line["product"],
                        "variant": None,
                        "quantity": 0,
                    }
                stock_lookup[key]["quantity"] += int(line["quantity"] or 0)

            struct_lines, struct_err = resolve_structured_addon_selections(
                product,
                data.get("addon_option_ids") or data.get("addon_selections") or [],
                quantity_per_option=quantity,
            )
            if struct_err:
                return struct_err
            try:
                _validate_structured_addon_stock(struct_lines)
            except ValueError as e:
                return jsonify({"success": False, "error": str(e)}), 400
        else:
            cart = Cart.query.filter_by(user_id=user_id).first()
            if not cart:
                return jsonify({"success": False, "error": "Cart is empty"}), 404

            requested_items = data.get("items") or []
            selected_item_ids = [
                int(item["item_id"])
                for item in requested_items
                if item.get("item_id") is not None
            ]

            selected_items_query = CartItem.query.filter(CartItem.cart_id == cart.id)
            if selected_item_ids:
                selected_items_query = selected_items_query.filter(CartItem.id.in_(selected_item_ids))
            else:
                selected_items_query = selected_items_query.filter(CartItem.is_selected == True)

            selected_items = selected_items_query.all()
            if not selected_items:
                return jsonify({"success": False, "error": "No items selected for checkout"}), 400

            # Prefer quantities from the request payload when provided
            qty_by_id = {}
            for item in requested_items:
                if item.get("item_id") is not None:
                    qty_by_id[int(item["item_id"])] = int(item.get("quantity") or 0)

            for cart_item in selected_items:
                if not cart_item.product:
                    continue
                key = (cart_item.product_id, cart_item.variant_id)
                qty = qty_by_id.get(cart_item.id, int(cart_item.quantity or 0))
                if key not in stock_lookup:
                    stock_lookup[key] = {
                        "product": cart_item.product,
                        "variant": cart_item.variant,
                        "quantity": 0,
                    }
                stock_lookup[key]["quantity"] += max(qty, 0)

            try:
                _validate_structured_addon_stock(_cart_structured_addon_lines(selected_items))
            except ValueError as e:
                return jsonify({"success": False, "error": str(e)}), 400

        issues = _collect_stock_issues(stock_lookup)
        if issues:
            return jsonify({
                "success": False,
                "error": "Some selected items are unavailable or have insufficient stock.",
                "stock_issues": issues,
            }), 400

        return jsonify({"success": True, "stock_issues": []}), 200

    except Exception as e:
        print(f"Validate stock error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


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

                src = item.variant if item.variant else item.product
                if item.variant and not item.variant.is_available:
                    raise Exception(f"{item.product.name} — {item.variant.name} is no longer available")
                available = int(src.stock_quantity or 0)
                if available < int(item.quantity or 0):
                    label = (
                        f"{item.product.name} — {item.variant.name}"
                        if item.variant else item.product.name
                    )
                    if available <= 0:
                        raise Exception(f'"{label}" is out of stock')
                    raise Exception(
                        f'"{label}" only has {available} left, but you selected {item.quantity}.'
                    )

                item_price = Decimal(str(src.effective_price))
                orig_price = float(src.price)
                disc_pct = src.discount_pct
                line_addons = []
                addons_sum = Decimal('0')
                for row in (item.addons or []):
                    opt = row.addon_option
                    if not opt:
                        continue
                    # Cart stores fixed addon units; flower qty does not scale add-on price.
                    units = max(1, int(row.quantity or 1))
                    if not opt.is_available or int(opt.stock_quantity or 0) < units:
                        raise Exception(
                            f'Insufficient stock for add-on "{opt.name}"'
                            if opt.is_available else f'Add-on "{opt.name}" is no longer available'
                        )
                    ap = Decimal(str(opt.price or 0))
                    addons_sum += ap * units
                    line_addons.append({
                        'addon_option_id': opt.id,
                        'name': opt.name,
                        'price': float(ap),
                        'quantity': units,
                        'units': units,
                        'image_url': opt.image_url or '',
                        'group_name': opt.group.name if opt.group else None,
                    })
                subtotal += item_price * item.quantity + addons_sum
                order_items_data.append({
                    "product_id": item.product_id,
                    "variant_id": item.variant_id,
                    "quantity": item.quantity,
                    "price": float(item_price),
                    "original_price": orig_price if disc_pct else None,
                    "discount_pct": disc_pct,
                    "addons": line_addons,
                    "addons_total": float(addons_sum),
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
                    "gcash_instructions": store.gcash_instructions,
                    "allow_cod": _store_allows_cod(store.id),
                    "store_schedule": store.store_schedule,
                    **_free_delivery_fields(store, subtotal, delivery_check["delivery_fee"]),
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

        allowed_extensions = {"jpg", "jpeg", "png", "gif", "webp", "heic", "heif"}
        if not ("." in file.filename and file.filename.rsplit(".", 1)[1].lower() in allowed_extensions):
            return jsonify({"error": "Only image files allowed (jpg, jpeg, png, gif, webp, heic, heif)"}), 400

        try:
            from app.utils.cloudinary_helper import upload_to_cloudinary

            result = upload_to_cloudinary(
                file,
                folder=f"temp_payment_proofs/{datetime.utcnow().strftime('%Y-%m-%d')}",
                resource_type="image",
            )

            if not result or not result.get("success"):
                error_message = (result or {}).get("error") or "Upload failed"
                print(f"❌ Temp proof upload failed: {error_message}")
                return jsonify({"error": f"Upload failed: {error_message}"}), 500

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
        cart_addon_lines = _cart_structured_addon_lines(selected_items)
        _validate_structured_addon_stock(cart_addon_lines)

        delivery_point = from_shape(Point(address.longitude, address.latitude), srid=4326)
        orders_created = []

        for order_data in orders_data:
            store = Store.query.get(order_data.get("store_id"))
            if not store:
                print(f"⚠️ Store not found: {order_data.get('store_id')}")
                continue

            payment_method = str(order_data.get("payment_method") or "gcash").strip().lower()
            if payment_method not in {"gcash", "cod"}:
                return jsonify({"error": "Invalid payment method"}), 400
            if payment_method == "cod" and not _store_allows_cod(store.id):
                return jsonify({"error": f"Cash on Delivery is not enabled for {store.name}"}), 400

            # Phase 1: Extract and parse per-store delivery date/time
            order_delivery_date_str = order_data.get("requested_delivery_date")
            order_delivery_time = _normalize_requested_delivery_time(
                order_data.get("requested_delivery_time")
            )
            order_delivery_date = None
            
            if order_delivery_date_str:
                try:
                    order_delivery_date = datetime.strptime(order_delivery_date_str, '%Y-%m-%d').date()
                    print(f"✅ Parsed delivery date for {store.name}: {order_delivery_date}")
                except ValueError as e:
                    print(f"⚠️ Failed to parse delivery date '{order_delivery_date_str}': {e}")
                    return jsonify({"error": f"Invalid delivery date format for {store.name}. Use YYYY-MM-DD."}), 400

            if order_data.get("requested_delivery_time") and not order_delivery_time:
                return jsonify({"error": f"Invalid delivery time format for {store.name}."}), 400

            slot_error = _validate_requested_delivery_slot(
                store,
                order_delivery_date,
                order_delivery_time,
            )
            if slot_error:
                return jsonify({"error": slot_error}), 400

            store_cart_items = [
                ci for ci in selected_items
                if ci.product and ci.product.store_id == store.id
            ]
            # Always prefer cart-derived subtotal so structured add-ons are included
            # even when the client omits addons_total on payload items.
            _enrich_order_items_addons_from_cart(order_data, selected_items)
            cart_subtotal = _cart_items_subtotal(store_cart_items)
            payload_subtotal = _subtotal_from_order_items(order_data)
            computed_subtotal = cart_subtotal if store_cart_items else payload_subtotal
            if cart_subtotal > payload_subtotal:
                computed_subtotal = cart_subtotal

            delivery_check = _check_store_delivery(store, address, computed_subtotal)
            if not delivery_check["can_deliver"]:
                return jsonify({
                    "error": delivery_check["reason"] or f"Cannot deliver from {store.name}."
                }), 400
            computed_fee = delivery_check["delivery_fee"]
            computed_distance = delivery_check["distance_km"]
            computed_total = computed_subtotal + Decimal(str(computed_fee or 0))

            order = Order(
                customer_id=user_id,
                store_id=store.id,
                order_type="online",
                status="pending",
                subtotal_amount=computed_subtotal,
                delivery_fee=computed_fee,
                distance_km=computed_distance,
                total_amount=computed_total,
                payment_method="cod" if payment_method == "cod" else "gcash",
                payment_status="cod_pending" if payment_method == "cod" else "pending_verification",
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
            if payment_method == "gcash" and not payment_proof_url:
                return jsonify({"error": f"Payment proof is required for GCash on {store.name}"}), 400
            if payment_method == "cod":
                payment_proof_url = None
                payment_proof_public_id = None
            if payment_proof_url:
                order.payment_proof_url = payment_proof_url
                order.payment_proof_public_id = payment_proof_public_id
                print(f"  📸 Added payment proof: {payment_proof_url}")

            db.session.add(order)
            db.session.flush()
            
            # Ensure total_amount is always calculated correctly
            if not order.total_amount or order.total_amount == 0:
                order.compute_total()
            
            print(f"  ✅ Created order #{order.id} for store {store.name} - Total: ₱{float(order.total_amount):,.2f}")

            for item_data in order_data.get("items", []):
                order_item = OrderItem(
                    order_id=order.id,
                    product_id=item_data["product_id"],
                    variant_id=item_data.get("variant_id"),
                    quantity=item_data["quantity"],
                    price=item_data["price"],
                )
                db.session.add(order_item)
                db.session.flush()

                cart_match = next(
                    (
                        ci for ci in selected_items
                        if ci.product_id == item_data["product_id"]
                        and ci.variant_id == item_data.get("variant_id")
                    ),
                    None,
                )
                if cart_match:
                    lines = []
                    for row in (cart_match.addons or []):
                        opt = row.addon_option
                        if not opt:
                            continue
                        lines.append({
                            'option': opt,
                            'quantity': max(1, int(row.quantity or 1)),
                            'price': Decimal(str(opt.price or 0)),
                            'name': opt.name,
                            'image_url': opt.image_url or '',
                        })
                    attach_order_item_addons(order_item, lines)
                print(f"    ✅ Added item: product {item_data['product_id']} x {item_data['quantity']}")

            db.session.flush()

            db.session.add(Notification(
                user_id=store.seller_id,
                title='New Order Received',
                message=(
                    f'Order #{order.id} — ₱{float(order.total_amount):,.2f} was placed via Cash on Delivery.'
                    if payment_method == "cod"
                    else f'Order #{order.id} — ₱{float(order.total_amount):,.2f} is awaiting payment verification.'
                ),
                type='new_order',
                reference_id=order.id,
            ))

            orders_created.append(order.to_dict())

        _reduce_stock_lookup(
            stock_lookup,
            user_id,
            f"Reduced automatically after online checkout by customer #{user_id}",
        )
        decrement_addon_option_stock(
            cart_addon_lines,
            user_id=user_id,
            reason='other',
            reason_notes=f"Reduced automatically after online checkout by customer #{user_id}",
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

        # Return full cart with consistent format (matching add_to_cart/update_cart_item)
        cart = item.cart
        cart_data = {
            'id': cart.id,
            'user_id': cart.user_id,
            'created_at': cart.created_at.isoformat() if cart.created_at else None,
            'updated_at': cart.updated_at.isoformat() if cart.updated_at else None,
            'items': []
        }
        
        for cart_item in cart.items:
            prod = cart_item.product
            if prod:
                # Get product images
                images = []
                for img in prod.images:
                    images.append({
                        'id': img.id,
                        'filename': img.filename,
                        'is_primary': img.is_primary,
                        'sort_order': img.sort_order
                    })
                
                product_data = {
                    'id': prod.id,
                    'name': prod.name,
                    'description': prod.description,
                    'price': float(prod.price),
                    'special_price': float(prod.special_price) if prod.special_price else None,
                    'effective_price': prod.effective_price,
                    'discount_pct': prod.discount_pct,
                    'stock_quantity': prod.stock_quantity,
                    'main_category_id': prod.main_category_id,
                    'main_category_name': prod.main_category.name if prod.main_category else 'Uncategorized',
                    'store_category_name': prod.store_category.name if prod.store_category else None,
                    'category_display': prod.category_display,
                    'is_available': prod.is_available,
                    'store_id': prod.store_id,
                    'images': images,
                    'store_name': prod.store.name if prod.store else None
                }
                
                # Include variant data if present
                variant_data = None
                if cart_item.variant:
                    variant_data = cart_item.variant.to_dict()
                
                item_data = {
                    'id': cart_item.id,
                    'cart_id': cart_item.cart_id,
                    'product_id': cart_item.product_id,
                    'variant_id': cart_item.variant_id,
                    'quantity': cart_item.quantity,
                    'is_selected': cart_item.is_selected,
                    'created_at': cart_item.created_at.isoformat() if cart_item.created_at else None,
                    'updated_at': cart_item.updated_at.isoformat() if cart_item.updated_at else None,
                    'product': product_data,
                    'variant': variant_data  # Include variant if present
                }
                cart_data['items'].append(item_data)
        
        return jsonify({
            "success": True,
            "item_id": item_id,
            "is_selected": item.is_selected,
            "cart": cart_data,
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
        
        # Return full cart with consistent format (matching add_to_cart/update_cart_item)
        cart_data = {
            'id': cart.id,
            'user_id': cart.user_id,
            'created_at': cart.created_at.isoformat() if cart.created_at else None,
            'updated_at': cart.updated_at.isoformat() if cart.updated_at else None,
            'items': []
        }
        
        for cart_item in cart.items:
            prod = cart_item.product
            if prod:
                # Get product images
                images = []
                for img in prod.images:
                    images.append({
                        'id': img.id,
                        'filename': img.filename,
                        'is_primary': img.is_primary,
                        'sort_order': img.sort_order
                    })
                
                product_data = {
                    'id': prod.id,
                    'name': prod.name,
                    'description': prod.description,
                    'price': float(prod.price),
                    'special_price': float(prod.special_price) if prod.special_price else None,
                    'effective_price': prod.effective_price,
                    'discount_pct': prod.discount_pct,
                    'stock_quantity': prod.stock_quantity,
                    'main_category_id': prod.main_category_id,
                    'main_category_name': prod.main_category.name if prod.main_category else 'Uncategorized',
                    'store_category_name': prod.store_category.name if prod.store_category else None,
                    'category_display': prod.category_display,
                    'is_available': prod.is_available,
                    'store_id': prod.store_id,
                    'images': images,
                    'store_name': prod.store.name if prod.store else None
                }
                
                # Include variant data if present
                variant_data = None
                if cart_item.variant:
                    variant_data = cart_item.variant.to_dict()
                
                item_data = {
                    'id': cart_item.id,
                    'cart_id': cart_item.cart_id,
                    'product_id': cart_item.product_id,
                    'variant_id': cart_item.variant_id,
                    'quantity': cart_item.quantity,
                    'is_selected': cart_item.is_selected,
                    'created_at': cart_item.created_at.isoformat() if cart_item.created_at else None,
                    'updated_at': cart_item.updated_at.isoformat() if cart_item.updated_at else None,
                    'product': product_data,
                    'variant': variant_data  # Include variant if present
                }
                cart_data['items'].append(item_data)
        
        return jsonify({
            "success": True,
            "store_id": store_id,
            "items_updated": items_updated,
            "cart": cart_data,
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
        payment_proof_url = data.get("payment_proof_url")
        payment_proof_public_id = data.get("payment_proof_public_id")
        requested_delivery_date = data.get("requested_delivery_date")
        requested_delivery_time = _normalize_requested_delivery_time(data.get("requested_delivery_time"))
        requested_delivery_date_obj = None
        if requested_delivery_date:
            try:
                requested_delivery_date_obj = datetime.strptime(requested_delivery_date, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({"error": "Invalid requested_delivery_date format. Use YYYY-MM-DD"}), 400

        if data.get("requested_delivery_time") and not requested_delivery_time:
            return jsonify({"error": "Invalid requested_delivery_time format. Use HH:MM-HH:MM"}), 400

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

                src = item.variant if item.variant else item.product
                item_price = Decimal(str(src.effective_price))
                orig_price = float(src.price)
                disc_pct = src.discount_pct
                addons_sum = Decimal(str(item.addons_subtotal or 0))
                subtotal += item_price * item.quantity + addons_sum
                order_items_data.append({
                    "product_id": int(item.product_id),
                    "variant_id": int(item.variant_id) if item.variant_id else None,
                    "quantity": int(item.quantity),
                    "price": float(item_price),
                    "original_price": orig_price if disc_pct else None,
                    "discount_pct": disc_pct,
                    "addons_total": float(addons_sum),
                    "cart_item_id": item.id,
                })

            store_checkout_data[store_id] = {
                "store": store,
                "subtotal": subtotal,
                "order_items_data": order_items_data,
                "store_items": store_items,
                "delivery_check": _check_store_delivery(store, address, subtotal),
            }

            slot_error = _validate_requested_delivery_slot(
                store,
                requested_delivery_date_obj,
                requested_delivery_time,
            )
            if slot_error:
                return jsonify({"error": slot_error}), 400

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
            store_items = checkout_data.get("store_items") or []
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
                payment_status="pending_verification",
                delivery_location=delivery_point,
                payment_proof_url=payment_proof_url,
                payment_proof_public_id=payment_proof_public_id,
                delivery_address=address.address_line,
                delivery_notes=delivery_notes,
                requested_delivery_date=requested_delivery_date_obj,
                requested_delivery_time=requested_delivery_time,
                customer_latitude=address.latitude,
                customer_longitude=address.longitude,
                mapbox_place_id=address.place_id,
            )

            db.session.add(order)
            db.session.flush()

            for item_data in order_items_data:
                order_item = OrderItem(
                    order_id=order.id,
                    product_id=item_data["product_id"],
                    variant_id=item_data["variant_id"],
                    quantity=item_data["quantity"],
                    price=item_data["price"],
                )
                db.session.add(order_item)
                db.session.flush()

                cart_match = next(
                    (
                        ci for ci in store_items
                        if ci.id == item_data.get("cart_item_id")
                        or (
                            ci.product_id == item_data["product_id"]
                            and (ci.variant_id or None) == (item_data.get("variant_id") or None)
                        )
                    ),
                    None,
                )
                if cart_match:
                    lines = []
                    for row in (cart_match.addons or []):
                        opt = row.addon_option
                        if not opt:
                            continue
                        lines.append({
                            'option': opt,
                            'quantity': max(1, int(row.quantity or 1)),
                            'price': Decimal(str(opt.price or 0)),
                            'name': opt.name,
                            'image_url': opt.image_url or '',
                        })
                    attach_order_item_addons(order_item, lines)

            db.session.flush()

            db.session.add(Notification(
                user_id=store.seller_id,
                title='New Order Received',
                message=f'Order #{order.id} — ₱{float(order.total_amount):,.2f} from {customer.full_name} is awaiting payment verification.',
                type='new_order',
                reference_id=order.id,
            ))

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
            from app.utils.seller_notifications import notify_store_seller
            notify_store_seller(
                store_id=order.store_id,
                title='Payment proof uploaded',
                message=(
                    f'Customer uploaded GCash proof for Order #{order.id}. '
                    'Please verify payment.'
                ),
                type='payment_proof',
                reference_id=order.id,
            )
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
            from app.utils.seller_notifications import notify_store_seller
            notify_store_seller(
                store_id=order.store_id,
                title='Payment proof uploaded',
                message=(
                    f'Customer uploaded GCash proof for Order #{order.id}. '
                    'Please verify payment.'
                ),
                type='payment_proof',
                reference_id=order.id,
            )
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


# ═══════════════════════════════════════════════════════════════════════════════
# BUY NOW — Skip cart, go directly to checkout
# ═══════════════════════════════════════════════════════════════════════════════

@checkout_bp.route("/buy-now/validate", methods=["POST"])
@customer_only
def buy_now_validate():
    """Validate delivery for a direct buy-now (no cart involved)."""
    print("🔵🔵🔵 BUY NOW VALIDATE ROUTE WAS CALLED! 🔵🔵🔵")
    try:
        user_id = request.user_id
        data = request.get_json() or {}
        
        print(f"📨 Request data received: {data}")

        product_id = data.get("product_id")
        variant_id = data.get("variant_id")
        address_id = data.get("delivery_address_id")
        
        try:
            quantity = int(data.get("quantity", 1))
        except (ValueError, TypeError) as e:
            print(f"❌ Quantity conversion error: {e}")
            return jsonify({"error": "quantity must be a valid integer"}), 400
        
        print(f"🔍 Parsed values:")
        print(f"   product_id: {product_id} (type: {type(product_id)})")
        print(f"   variant_id: {variant_id} (type: {type(variant_id)})")
        print(f"   quantity: {quantity} (type: {type(quantity)})")
        print(f"   address_id: {address_id} (type: {type(address_id)})")

        if not product_id:
            print(f"❌ product_id validation failed: {product_id}")
            return jsonify({"error": "product_id is required"}), 400
        if not address_id:
            print(f"❌ address_id validation failed: {address_id}")
            return jsonify({"error": "delivery_address_id is required"}), 400
        if quantity < 1:
            print(f"❌ quantity validation failed: {quantity}")
            return jsonify({"error": "Quantity must be at least 1"}), 400

        product = Product.query.get(product_id)
        if not product:
            return jsonify({"error": "Product not found"}), 404
        if not product.is_available:
            return jsonify({"error": f'"{product.name}" is no longer available'}), 400

        variant = None
        item_price = Decimal(str(product.effective_price))
        if variant_id:
            variant = ProductVariant.query.filter_by(id=variant_id, product_id=product_id).first()
            if not variant:
                return jsonify({"error": "Variant not found"}), 404
            if not variant.is_available:
                return jsonify({"error": f'"{variant.name}" is no longer available'}), 400
            if variant.stock_quantity < quantity:
                return jsonify({"error": f'Insufficient stock for "{variant.name}". Available: {variant.stock_quantity}'}), 400
            item_price = Decimal(str(variant.effective_price))
        else:
            if product.stock_quantity < quantity:
                return jsonify({"error": f'Insufficient stock for "{product.name}". Available: {product.stock_quantity}'}), 400

        address = UserAddress.query.filter_by(id=address_id, user_id=user_id).first()
        if not address:
            return jsonify({"error": "Delivery address not found"}), 404

        store = Store.query.get(product.store_id)
        if not store:
            return jsonify({"error": "Store not found"}), 404

        addon_lines, addon_err = _resolve_buy_now_addons(
            data.get("addons") or [],
            store.id,
            exclude_product_id=product.id,
        )
        if addon_err:
            return addon_err

        struct_lines, struct_err = resolve_structured_addon_selections(
            product,
            data.get("addon_option_ids") or data.get("addon_selections") or [],
            quantity_per_option=quantity,
        )
        if struct_err:
            return struct_err

        subtotal = item_price * quantity
        order_items = [{
            "product_id": product.id,
            "variant_id": variant.id if variant else None,
            "quantity": quantity,
            "price": float(item_price),
            "name": product.name if not variant else f"{variant.name} {product.name}",
            "image_url": (
                (variant.image_url if variant and getattr(variant, "image_url", None) else None)
                or (product.images[0].cloudinary_url if product.images else None)
                or ""
            ),
            "addons": [
                {
                    "addon_option_id": line["option"].id,
                    "name": line["name"],
                    "price": float(line["price"]),
                    "quantity": line["quantity"],
                    "image_url": line.get("image_url") or "",
                    "group_name": line.get("group_name"),
                }
                for line in struct_lines
            ],
            "addons_total": float(structured_addons_subtotal(struct_lines)),
        }]
        subtotal += structured_addons_subtotal(struct_lines)
        for line in addon_lines:
            subtotal += line["price"] * line["quantity"]
            order_items.append({
                "product_id": line["product"].id,
                "variant_id": None,
                "quantity": line["quantity"],
                "price": float(line["price"]),
                "name": line["name"],
                "image_url": line["image_url"] or "",
            })

        delivery_check = _check_store_delivery(store, address, subtotal)

        if not delivery_check["can_deliver"]:
            return jsonify({
                "success": False,
                "error": "Cannot deliver to this address.",
                "undeliverable_stores": [{
                    "store_id": store.id,
                    "store_name": store.name,
                    "reason": delivery_check["reason"],
                    "distance_km": round(delivery_check["distance_km"], 2) if delivery_check["distance_km"] is not None else None,
                }],
            }), 400

        return jsonify({
            "success": True,
            "orders": [{
                "temp_id": f"buynow_{uuid.uuid4().hex[:8]}",
                "store_id": store.id,
                "store_name": store.name,
                "subtotal": float(subtotal),
                "delivery_fee": float(delivery_check["delivery_fee"]),
                "distance_km": delivery_check["distance_km"],
                "total": float(subtotal + delivery_check["delivery_fee"]),
                "items": order_items,
                "gcash_qr_codes": [qr.to_dict() for qr in store.gcash_qr_images],
                "gcash_instructions": store.gcash_instructions,
                "allow_cod": _store_allows_cod(store.id),
                "store_schedule": store.store_schedule,
                **_free_delivery_fields(store, subtotal, delivery_check["delivery_fee"]),
            }],
            "address": address.to_dict(),
        }), 200

    except Exception as e:
        print(f"❌ Buy now validate error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@checkout_bp.route("/buy-now/create-order", methods=["POST"])
@customer_only
def buy_now_create_order():
    """Create an order directly from product data (no cart involved)."""
    print("🔵🔵🔵 BUY NOW CREATE ORDER ROUTE WAS CALLED! 🔵🔵🔵")
    try:
        user_id = request.user_id
        data = request.get_json() or {}

        product_id = data.get("product_id")
        variant_id = data.get("variant_id")
        quantity = int(data.get("quantity", 1))
        address_id = data.get("address_id")
        delivery_notes = data.get("delivery_notes", "")
        requested_delivery_date_str = data.get("requested_delivery_date")
        requested_delivery_time = _normalize_requested_delivery_time(data.get("requested_delivery_time"))
        payment_proof_url = data.get("payment_proof_url")
        payment_proof_public_id = data.get("payment_proof_public_id")
        payment_method = str(data.get("payment_method") or "gcash").strip().lower()

        if not product_id:
            return jsonify({"error": "product_id is required"}), 400
        if not address_id:
            return jsonify({"error": "address_id is required"}), 400
        if quantity < 1:
            return jsonify({"error": "Quantity must be at least 1"}), 400
        if payment_method not in {"gcash", "cod"}:
            return jsonify({"error": "Invalid payment method"}), 400

        product = Product.query.get(product_id)
        if not product:
            return jsonify({"error": "Product not found"}), 404
        if not product.is_available:
            return jsonify({"error": f'"{product.name}" is no longer available'}), 400

        variant = None
        item_price = Decimal(str(product.effective_price))
        if variant_id:
            variant = ProductVariant.query.filter_by(id=variant_id, product_id=product_id).first()
            if not variant:
                return jsonify({"error": "Variant not found"}), 404
            if not variant.is_available:
                return jsonify({"error": f'"{variant.name}" is no longer available'}), 400
            if variant.stock_quantity < quantity:
                return jsonify({"error": f'Insufficient stock for "{variant.name}".'}), 400
            item_price = Decimal(str(variant.effective_price))
        else:
            if product.stock_quantity < quantity:
                return jsonify({"error": f'Insufficient stock for "{product.name}".'}), 400

        address = UserAddress.query.filter_by(id=address_id, user_id=user_id).first()
        if not address:
            return jsonify({"error": "Delivery address not found"}), 404

        store = Store.query.get(product.store_id)
        if not store:
            return jsonify({"error": "Store not found"}), 404
        if payment_method == "cod" and not _store_allows_cod(store.id):
            return jsonify({"error": "Cash on Delivery is not enabled for this store"}), 400
        if payment_method == "gcash" and not payment_proof_url:
            return jsonify({"error": "Payment proof is required for GCash"}), 400
        if payment_method == "cod":
            payment_proof_url = None
            payment_proof_public_id = None

        addon_lines, addon_err = _resolve_buy_now_addons(
            data.get("addons") or [],
            store.id,
            exclude_product_id=product.id,
        )
        if addon_err:
            return addon_err

        struct_lines, struct_err = resolve_structured_addon_selections(
            product,
            data.get("addon_option_ids") or data.get("addon_selections") or [],
            quantity_per_option=quantity,
        )
        if struct_err:
            return struct_err

        subtotal = item_price * quantity
        subtotal += structured_addons_subtotal(struct_lines)
        for line in addon_lines:
            subtotal += line["price"] * line["quantity"]

        delivery_check = _check_store_delivery(store, address, subtotal)

        if not delivery_check["can_deliver"]:
            return jsonify({"error": delivery_check["reason"]}), 400

        delivery_fee = delivery_check["delivery_fee"]
        distance = delivery_check["distance_km"]
        delivery_point = from_shape(Point(address.longitude, address.latitude), srid=4326)

        requested_delivery_date = None
        if requested_delivery_date_str:
            try:
                requested_delivery_date = datetime.strptime(requested_delivery_date_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        if data.get("requested_delivery_time") and not requested_delivery_time:
            return jsonify({"error": "Invalid requested_delivery_time format. Use HH:MM-HH:MM"}), 400

        slot_error = _validate_requested_delivery_slot(
            store,
            requested_delivery_date,
            requested_delivery_time,
        )
        if slot_error:
            return jsonify({"error": slot_error}), 400

        order = Order(
            customer_id=int(user_id),
            store_id=int(store.id),
            order_type="online",
            status="pending",
            subtotal_amount=float(subtotal),
            delivery_fee=float(delivery_fee),
            distance_km=float(distance) if distance else None,
            total_amount=float(subtotal + delivery_fee),
            payment_method="cod" if payment_method == "cod" else "gcash",
            payment_status="cod_pending" if payment_method == "cod" else "pending_verification",
            delivery_location=delivery_point,
            payment_proof_url=payment_proof_url,
            payment_proof_public_id=payment_proof_public_id,
            delivery_address=address.address_line,
            delivery_notes=delivery_notes,
            requested_delivery_date=requested_delivery_date,
            requested_delivery_time=requested_delivery_time,
            customer_latitude=address.latitude,
            customer_longitude=address.longitude,
            mapbox_place_id=address.place_id,
        )
        db.session.add(order)
        db.session.flush()
        
        # Ensure total_amount is always calculated correctly
        if not order.total_amount or order.total_amount == 0:
            order.compute_total()

        main_order_item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            variant_id=variant.id if variant else None,
            quantity=quantity,
            price=float(item_price),
        )
        db.session.add(main_order_item)
        db.session.flush()
        attach_order_item_addons(main_order_item, struct_lines)

        for line in addon_lines:
            db.session.add(OrderItem(
                order_id=order.id,
                product_id=line["product"].id,
                variant_id=None,
                quantity=line["quantity"],
                price=float(line["price"]),
            ))

        db.session.flush()

        # Reduce stock for main item
        if variant is not None:
            stock_before = int(variant.stock_quantity or 0)
        else:
            stock_before = int(product.stock_quantity or 0)

        product.reduce_stock(
            quantity,
            "other",
            user_id,
            reason_notes=f"Buy Now order #{order.id} by customer #{user_id}",
            variant=variant,
        )
        decrement_addon_option_stock(
            struct_lines,
            user_id=user_id,
            reason='other',
            reason_notes=f"Buy Now order #{order.id} by customer #{user_id}",
        )

        if variant is not None:
            stock_after = int(variant.stock_quantity or 0)
        else:
            stock_after = int(product.stock_quantity or 0)

        from app.utils.seller_notifications import notify_low_stock_if_crossed
        notify_low_stock_if_crossed(
            store_id=store.id,
            product=product,
            stock_before=stock_before,
            stock_after=stock_after,
        )

        # Reduce stock for add-ons
        for line in addon_lines:
            addon_product = line["product"]
            addon_before = int(addon_product.stock_quantity or 0)
            addon_product.reduce_stock(
                line["quantity"],
                "other",
                user_id,
                reason_notes=f"Buy Now add-on on order #{order.id} by customer #{user_id}",
                variant=None,
            )
            notify_low_stock_if_crossed(
                store_id=store.id,
                product=addon_product,
                stock_before=addon_before,
                stock_after=int(addon_product.stock_quantity or 0),
            )

        _customer = User.query.get(user_id)
        _customer_name = _customer.full_name if _customer else f'Customer #{user_id}'
        db.session.add(Notification(
            user_id=store.seller_id,
            title='New Order Received',
            message=(
                f'Order #{order.id} — ₱{float(order.total_amount):,.2f} from {_customer_name} was placed via Cash on Delivery.'
                if payment_method == "cod"
                else f'Order #{order.id} — ₱{float(order.total_amount):,.2f} from {_customer_name} is awaiting payment verification.'
            ),
            type='new_order',
            reference_id=order.id,
        ))

        db.session.commit()
        print(f"✅ Buy Now order #{order.id} created successfully")

        order_dict = order.to_dict()
        order_dict["items"] = [oi.to_dict() for oi in order.items]
        order_dict["gcash_qr_codes"] = [qr.to_dict() for qr in store.gcash_qr_images]
        order_dict["gcash_instructions"] = store.gcash_instructions
        order_dict["allow_cod"] = _store_allows_cod(store.id)
        order_dict["distance_km"] = round(distance, 2) if distance is not None else None
        order_dict["selected_address"] = address.to_dict()

        return jsonify({
            "success": True,
            "message": "Order created successfully",
            "orders": [order_dict],
        }), 201

    except Exception as e:
        db.session.rollback()
        print(f"❌ Buy now create order error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


print("✅ checkout_routes.py loaded successfully")
print("=" * 60)
