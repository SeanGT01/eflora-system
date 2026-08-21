# app/customer.py
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt, verify_jwt_in_request
from collections import defaultdict

from app.models import Product, Store, Order, OrderItem, Cart, CartItem, Rider, ProductVariant, SellerApplication, Notification, User, UserAddress, ProductRating, StoreRating, CartItemAddon, ProductAddonOption, WishlistItem
from app.extensions import db
from sqlalchemy.orm import joinedload, selectinload
from functools import wraps
from datetime import datetime
from app.checkout_routes import _check_store_delivery
import jwt
import os


customer_bp = Blueprint('customer', __name__)

def customer_only(f):
    """Decorator: JWT required + must be customer role."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            # Get token from header
            auth_header = request.headers.get('Authorization', '')
            print(f"🔑 Auth header: {auth_header[:50] if auth_header else 'None'}")
            
            if not auth_header or not auth_header.startswith('Bearer '):
                print("❌ No Bearer token found")
                return jsonify({'error': 'Missing or invalid authorization header'}), 401
            
            token = auth_header.split(' ')[1]
            print(f"📝 Token received (first 20 chars): {token[:20]}...")
            
            # Verify JWT token using flask_jwt_extended
            verify_jwt_in_request()
            
            # Get claims and identity
            claims = get_jwt()
            user_id = get_jwt_identity()
            
            print(f"✅ JWT Verification - User ID: {user_id}, Role: {claims.get('role')}")
            
            if not user_id:
                print("❌ No user ID in token")
                return jsonify({'error': 'Invalid token'}), 401
                
            if claims.get('role') != 'customer':
                print(f"❌ Wrong role: {claims.get('role')}, expected 'customer'")
                return jsonify({'error': 'Customer access required'}), 403
                
            return f(*args, **kwargs)
            
        except Exception as e:
            print(f"❌ JWT Error: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': 'Authentication failed', 'detail': str(e)}), 401
    return wrapper


def _get_default_address(user_id):
    return (
        UserAddress.query.filter_by(user_id=user_id, is_default=True).first()
        or UserAddress.query.filter_by(user_id=user_id).order_by(UserAddress.created_at.desc()).first()
    )


def _resolve_optional_customer_address():
    """Resolve customer + default address if a valid customer JWT is present."""
    try:
        verify_jwt_in_request(optional=True)
        user_id = get_jwt_identity()
        if user_id is None or user_id == '':
            return None, None
        uid = int(str(user_id).strip())
        claims = get_jwt() or {}
        # Prefer JWT role; fall back to DB (login tokens may not surface all claims in get_jwt()).
        if claims.get('role') == 'customer':
            return uid, _get_default_address(uid)
        user = User.query.get(uid)
        if user and user.role == 'customer':
            return uid, _get_default_address(uid)
        return None, None
    except Exception:
        return None, None


def _normalize_place_name(value):
    import unicodedata
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return ' '.join(text.casefold().split())


def _listing_delivery_match(store, address):
    """
    Storefront coverage check — aligned with templates_routes._store_delivery_match
    so mobile listing filters match the web landing page.
    """
    if not store or not address:
        return {'can_deliver': False, 'reason': 'Set your default address to check delivery coverage.'}

    address_municipality = _normalize_place_name(address.municipality)
    has_coords = address.latitude is not None and address.longitude is not None
    method = (store.delivery_method or 'radius').strip().casefold()

    try:
        if method == 'municipality':
            selected = store.selected_municipalities or []
            if selected:
                if not address_municipality:
                    return {
                        'can_deliver': False,
                        'reason': 'Your address is missing a municipality.',
                    }
                matched = any(
                    _normalize_place_name(name) == address_municipality
                    for name in selected
                )
                if not matched:
                    return {
                        'can_deliver': False,
                        'reason': f"{store.name} does not deliver to {address.municipality}.",
                    }
                return {'can_deliver': True, 'reason': None}

            if has_coords and (
                store.municipality_delivery_area is not None
                or store.delivery_area is not None
            ):
                try:
                    if store.can_deliver_to(address.latitude, address.longitude):
                        return {'can_deliver': True, 'reason': None}
                    return {
                        'can_deliver': False,
                        'reason': 'Outside this store delivery zone.',
                    }
                except Exception:
                    return {
                        'can_deliver': False,
                        'reason': 'Could not validate delivery coverage right now.',
                    }

            return {
                'can_deliver': False,
                'reason': 'Store has no delivery municipalities configured.',
            }

        if not has_coords:
            return {
                'can_deliver': False,
                'reason': 'Your default address is missing map coordinates.',
            }

        # Reuse checkout geo/fee helper when coordinates exist
        baseline = 1.0
        check = _check_store_delivery(store, address, baseline)

        # Checkout helper can still pass stores with missing zone polygons.
        # For listing filters, require explicit coverage when method is zone.
        if check.get('can_deliver') and method == 'zone':
            has_area = (
                store.zone_delivery_area is not None
                or store.delivery_area is not None
            )
            if not has_area and not float(store.max_delivery_distance or 0):
                return {
                    'can_deliver': False,
                    'reason': 'Store has no delivery area configured.',
                }
            if has_area:
                try:
                    if not store.can_deliver_to(address.latitude, address.longitude):
                        return {
                            'can_deliver': False,
                            'reason': 'Outside this store delivery zone.',
                        }
                except Exception:
                    return {
                        'can_deliver': False,
                        'reason': 'Could not validate delivery coverage right now.',
                    }

        if check.get('can_deliver') and method == 'radius':
            radius_limit = float(
                store.delivery_radius_km or store.max_delivery_distance or 0
            )
            if not radius_limit:
                return {
                    'can_deliver': False,
                    'reason': 'Store has no delivery radius configured.',
                }

        return check
    except Exception:
        return {
            'can_deliver': False,
            'reason': 'Could not validate delivery coverage right now.',
        }


# ══════════════════════════════════════════════════════════════════════════
# PRODUCTS — public
# ══════════════════════════════════════════════════════════════════════════

@customer_bp.route('/products', methods=['GET'])
def get_products():
    """Public — no auth needed."""
    category = request.args.get('category')  # Can be main_category slug
    store_id = request.args.get('store_id', type=int)
    search   = request.args.get('q', '')
    page     = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    _, address = _resolve_optional_customer_address()
    # Match web storefront: when a customer has a default address, hide
    # out-of-range products unless include_outside_location=1.
    include_outside_arg = request.args.get('include_outside_location')
    if include_outside_arg is None:
        include_outside = address is None
    else:
        include_outside = include_outside_arg in ('1', 'true', 'True', 'yes')

    # Catalog listings (home / browse / search without store scope): hide fully
    # out-of-stock products (no main stock and no sellable variant). Store pages
    # pass store_id and keep OOS products visible.
    q = Product.query.join(Store).filter(
        Product.is_available == True,
        Product.is_archived == False,
        Store.status == 'active'
    )
    if not store_id:
        variant_in_stock_exists = db.session.query(ProductVariant.id).filter(
            ProductVariant.product_id == Product.id,
            ProductVariant.is_available == True,
            ProductVariant.stock_quantity > 0
        ).exists()
        q = q.filter(db.or_(
            Product.stock_quantity > 0,
            variant_in_stock_exists,
        ))
    
    # Filter by main category slug if provided
    if category and category != 'all':
        from app.models import Category
        main_cat = Category.query.filter_by(slug=category).first()
        if main_cat:
            q = q.filter(Product.main_category_id == main_cat.id)
    
    if store_id:
        q = q.filter(Product.store_id == store_id)
    if search:
        from sqlalchemy import or_, func
        from app.models import Category, StoreCategory
        import re
        raw = (search or '').strip()
        # Normalize spaces/hyphens so "fresh flower(s)" matches "Fresh Flowers"
        # and slug "fresh-flowers".
        compact = re.sub(r'[\s\-]+', '', raw.lower())
        spaced = re.sub(r'[\s\-]+', ' ', raw.lower()).strip()
        hyphen = spaced.replace(' ', '-')
        variants = {v for v in (raw, spaced, hyphen) if v}

        name_norm = func.replace(func.lower(Product.name), '-', '')
        name_norm = func.replace(name_norm, ' ', '')
        cat_name_norm = func.replace(func.lower(Category.name), '-', '')
        cat_name_norm = func.replace(cat_name_norm, ' ', '')
        cat_slug_norm = func.replace(func.lower(Category.slug), '-', '')
        cat_slug_norm = func.replace(cat_slug_norm, ' ', '')
        sc_name_norm = func.replace(func.lower(StoreCategory.name), '-', '')
        sc_name_norm = func.replace(sc_name_norm, ' ', '')
        sc_slug_norm = func.replace(func.lower(StoreCategory.slug), '-', '')
        sc_slug_norm = func.replace(sc_slug_norm, ' ', '')

        clauses = []
        for v in variants:
            term = f'%{v}%'
            clauses.extend([
                Product.name.ilike(term),
                Category.name.ilike(term),
                Category.slug.ilike(term),
                StoreCategory.name.ilike(term),
                StoreCategory.slug.ilike(term),
            ])
        if compact:
            cterm = f'%{compact}%'
            clauses.extend([
                name_norm.ilike(cterm),
                cat_name_norm.ilike(cterm),
                cat_slug_norm.ilike(cterm),
                sc_name_norm.ilike(cterm),
                sc_slug_norm.ilike(cterm),
            ])

        q = (
            q.outerjoin(Category, Product.main_category_id == Category.id)
             .outerjoin(StoreCategory, Product.store_category_id == StoreCategory.id)
             .filter(or_(*clauses))
        )

    # Over-fetch when location-filtering so a page still has enough cards
    # after out-of-range products are dropped (same idea as web limit=40).
    fetch_size = per_page * 3 if (address and not include_outside) else per_page
    paged = q.paginate(page=page, per_page=fetch_size, error_out=False)

    products = []
    for p in paged.items:
        d = p.to_dict()
        d['store_name'] = p.store.name if p.store else None
        if address and p.store:
            delivery_check = _listing_delivery_match(p.store, address)
            d['can_deliver_to_customer'] = bool(delivery_check.get('can_deliver'))
            d['delivery_reason'] = delivery_check.get('reason')
        else:
            d['can_deliver_to_customer'] = True
            d['delivery_reason'] = None
        if include_outside or d['can_deliver_to_customer']:
            products.append(d)
        if len(products) >= per_page:
            break

    return jsonify({
        'products': products,
        'total':    paged.total,
        'page':     paged.page,
        'pages':    paged.pages,
        'has_next': paged.has_next,
    })


@customer_bp.route('/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    """Single product detail — public."""
    p = Product.query.get_or_404(product_id)
    data = p.to_dict()
    data['store_name'] = p.store.name if p.store else None
    try:
        from app.addon_helpers import ymal_addon_option_dicts
        data['ymal_addon_options'] = ymal_addon_option_dicts(p)
    except Exception:
        data['ymal_addon_options'] = []

    # Related flowers (same store + same main category) for YMAL
    try:
        related = (
            Product.query.filter(
                Product.store_id == p.store_id,
                Product.main_category_id == p.main_category_id,
                Product.id != product_id,
                Product.is_available == True,
                Product.is_archived == False,
            )
            .order_by(Product.stock_quantity.desc(), Product.name.asc())
            .limit(8)
            .all()
        )
        data['related_products'] = [rp.to_dict() for rp in related]
    except Exception:
        data['related_products'] = []

    # Rating summary — avg_rating/total_ratings = Standard (main) only.
    # overall_* = all options; variant_ratings = per option buckets.
    try:
        from sqlalchemy import func
        overall = db.session.query(
            func.avg(ProductRating.rating).label('avg'),
            func.count(ProductRating.id).label('count'),
        ).filter_by(product_id=product_id).first()
        data['overall_avg_rating'] = round(float(overall.avg or 0), 1) if overall else 0.0
        data['overall_total_ratings'] = int(overall.count or 0) if overall else 0

        variant_ratings = {}
        rows = db.session.query(
            ProductRating.variant_id,
            func.avg(ProductRating.rating).label('avg'),
            func.count(ProductRating.id).label('count'),
        ).filter_by(product_id=product_id).group_by(ProductRating.variant_id).all()
        for row in rows:
            key = str(row.variant_id) if row.variant_id else 'main'
            variant_ratings[key] = {
                'avg': round(float(row.avg or 0), 1),
                'count': int(row.count or 0),
            }
        data['variant_ratings'] = variant_ratings
        main_bucket = variant_ratings.get('main') or {'avg': 0.0, 'count': 0}
        data['avg_rating'] = float(main_bucket['avg'])
        data['total_ratings'] = int(main_bucket['count'])
    except Exception:
        data['avg_rating'] = 0.0
        data['total_ratings'] = 0
        data['overall_avg_rating'] = 0.0
        data['overall_total_ratings'] = 0
        data['variant_ratings'] = {}

    if p.store:
        data['store'] = p.store.to_dict()
        _, address = _resolve_optional_customer_address()
        if address:
            unit_price = float(p.effective_price or p.price or 0)
            subtotal_for_coverage = max(unit_price, 1.0)
            delivery_check = _check_store_delivery(p.store, address, subtotal_for_coverage)
            data['can_deliver_to_customer'] = bool(delivery_check.get('can_deliver'))
            data['delivery_reason'] = delivery_check.get('reason')
            store_dict = data.get('store')
            if isinstance(store_dict, dict):
                store_dict['can_deliver_to_customer'] = data['can_deliver_to_customer']
                store_dict['delivery_reason'] = data['delivery_reason']
        else:
            data['can_deliver_to_customer'] = True
            data['delivery_reason'] = None
    else:
        data['can_deliver_to_customer'] = True
        data['delivery_reason'] = None
    return jsonify(data)


@customer_bp.route('/categories', methods=['GET'])
def get_categories():
    """Get all active main categories — public (no auth needed)."""
    from app.models import Category
    
    try:
        # Fetch all active main categories, sorted by sort_order
        categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()
        
        return jsonify({
            'success': True,
            'categories': [cat.to_dict() for cat in categories],
            'total': len(categories)
        })
    except Exception as e:
        print(f'❌ Error fetching categories: {str(e)}')
        return jsonify({
            'success': False,
            'error': f'Failed to fetch categories: {str(e)}'
        }), 500


# ══════════════════════════════════════════════════════════════════════════
# STORES — public
# ══════════════════════════════════════════════════════════════════════════

@customer_bp.route('/stores', methods=['GET'])
def get_stores():
    """Public store listing."""
    _, address = _resolve_optional_customer_address()
    include_outside_arg = request.args.get('include_outside_location')
    if include_outside_arg is None:
        include_outside = address is None
    else:
        include_outside = include_outside_arg in ('1', 'true', 'True', 'yes')
    stores = Store.query.filter_by(status='active').all()
    result = []
    for s in stores:
        sd = s.to_dict()
        if address:
            delivery_check = _listing_delivery_match(s, address)
            sd['can_deliver_to_customer'] = bool(delivery_check.get('can_deliver'))
            sd['delivery_reason'] = delivery_check.get('reason')
        else:
            sd['can_deliver_to_customer'] = True
            sd['delivery_reason'] = None
        if include_outside or sd['can_deliver_to_customer']:
            result.append(sd)
    return jsonify(result)


@customer_bp.route('/stores/<int:store_id>', methods=['GET'])
def get_store(store_id):
    """Public single store detail."""
    store = Store.query.get_or_404(store_id)
    data = store.to_dict()
    # Add product count
    product_count = Product.query.filter_by(store_id=store_id, is_available=True).count()
    data['product_count'] = product_count
    # Match the web storefront: ratings come from completed-order StoreRating
    # records. Keep legacy testimonials only as a fallback for older stores.
    rating_row = db.session.query(
        db.func.coalesce(db.func.avg(StoreRating.rating), 0),
        db.func.count(StoreRating.id),
    ).filter(StoreRating.store_id == store_id).first()
    avg_rating = round(float(rating_row[0]), 1) if rating_row else 0.0
    review_count = int(rating_row[1]) if rating_row else 0

    reviews = [
        rating.to_dict()
        for rating in (
            StoreRating.query
            .filter_by(store_id=store_id)
            .order_by(StoreRating.created_at.desc())
            .limit(50)
            .all()
        )
    ]

    if not reviews:
        from app.models import Testimonial
        testimonials = (
            Testimonial.query
            .filter_by(store_id=store_id)
            .order_by(Testimonial.created_at.desc())
            .limit(50)
            .all()
        )
        reviews = [testimonial.to_dict() for testimonial in testimonials]
        if reviews:
            avg_rating = round(
                sum(float(review.get('rating') or 0) for review in reviews) / len(reviews),
                1,
            )
            review_count = len(reviews)

    data['avg_rating'] = avg_rating
    data['review_count'] = review_count
    data['reviews'] = reviews

    # Match web store detail map: default-address pin + delivery eligibility.
    customer_id, default_address = _resolve_optional_customer_address()
    is_customer = customer_id is not None
    delivery_match = _listing_delivery_match(store, default_address) if default_address else {
        'can_deliver': False,
        'reason': 'Set your default address to check delivery coverage.',
    }
    customer_map_location = None
    if (
        default_address
        and default_address.latitude is not None
        and default_address.longitude is not None
    ):
        customer_map_location = {
            'latitude': default_address.latitude,
            'longitude': default_address.longitude,
            'label': default_address.address_label or 'Default address',
        }

    data['is_customer'] = is_customer
    data['can_deliver_to_customer'] = bool(delivery_match.get('can_deliver'))
    data['delivery_reason'] = delivery_match.get('reason')
    data['customer_map_location'] = customer_map_location
    return jsonify(data)


@customer_bp.route('/stores/<int:store_id>/categories', methods=['GET'])
def get_store_categories(store_id):
    """Public — get store-specific subcategories."""
    from app.models import StoreCategory
    categories = StoreCategory.query.filter_by(
        store_id=store_id, is_active=True
    ).order_by(StoreCategory.sort_order).all()
    return jsonify([c.to_dict() for c in categories])


# ══════════════════════════════════════════════════════════════════════════
# CART — JWT protected
# ══════════════════════════════════════════════════════════════════════════
# app/customer.py - Update the get_cart function

@customer_bp.route('/cart', methods=['GET'])
@customer_only
def get_cart():
    """Get or create cart for the logged-in customer."""
    try:
        user_id = int(get_jwt_identity())
        
        cart = Cart.query.filter_by(user_id=user_id).first()
        if not cart:
            cart = Cart(user_id=user_id)
            db.session.add(cart)
            db.session.commit()
        
        items = (
            CartItem.query
            .filter_by(cart_id=cart.id)
            .options(
                joinedload(CartItem.product).joinedload(Product.store),
                joinedload(CartItem.product).joinedload(Product.main_category),
                joinedload(CartItem.product).joinedload(Product.store_category),
                joinedload(CartItem.product).selectinload(Product.images),
                joinedload(CartItem.product).selectinload(Product.variants),
                joinedload(CartItem.variant),
                selectinload(CartItem.addons).joinedload(CartItemAddon.addon_option).joinedload(ProductAddonOption.group),
            )
            .all()
        )

        cart_data = {
            'id': cart.id,
            'user_id': cart.user_id,
            'created_at': cart.created_at.isoformat() if cart.created_at else None,
            'updated_at': cart.updated_at.isoformat() if cart.updated_at else None,
            'items': [item.to_dict() for item in items],
        }
        
        return jsonify({'success': True, 'cart': cart_data})
    except Exception as e:
        current_app.logger.exception('get_cart: %s', e)
        return jsonify({'error': str(e)}), 500

# app/customer.py - Update the return part of add_to_cart

@customer_bp.route('/cart/items', methods=['POST'])
@customer_only
def add_to_cart():
    """Add a product to the cart. Supports variants. Increments quantity if same product/variant already present."""
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json() or {}
        product_id = data.get('product_id')
        variant_id = data.get('variant_id')  # ✅ GET variant_id from payload
        quantity = int(data.get('quantity', 1))
        addon_option_ids = data.get('addon_option_ids') or data.get('addon_selections') or []

        print(f"🛒 Adding to cart - User: {user_id}, Product: {product_id}, Variant: {variant_id}, Quantity: {quantity}")

        if not product_id or quantity < 1:
            return jsonify({'error': 'product_id and quantity >= 1 are required'}), 400

        product = Product.query.get(product_id)
        if not product or not product.is_available:
            return jsonify({'error': 'Product not available'}), 404

        from app.addon_helpers import resolve_structured_addon_selections, sync_cart_item_addons
        struct_lines, struct_err = resolve_structured_addon_selections(
            product, addon_option_ids, quantity_per_option=1
        )
        if struct_err:
            return struct_err

        # ✅ ALIGNED: If variant_id is provided, check variant exists and has stock
        variant = None
        if variant_id:
            variant = ProductVariant.query.get(variant_id)
            if not variant:
                return jsonify({'error': 'Variant not found'}), 404
            if variant.product_id != product_id:
                return jsonify({'error': 'Variant does not belong to this product'}), 400
            if variant.stock_quantity < quantity:
                return jsonify({'error': f'Only {variant.stock_quantity} of this variant available'}), 400
            print(f"📦 Variant: {variant.name}, Stock: {variant.stock_quantity}")
        else:
            # Check main product stock
            if product.stock_quantity < quantity:
                return jsonify({'error': f'Only {product.stock_quantity} available'}), 400

        print(f"📦 Product: {product.name}, Available: {product.is_available}")

        # Delivery-area guard: browsing outside location is allowed, but adding to cart is blocked
        # when the selected/default address cannot be served by the product's store.
        address = _get_default_address(user_id)
        if address and product.store:
            unit_price = None
            if variant and hasattr(variant, 'effective_price') and variant.effective_price is not None:
                unit_price = float(variant.effective_price)
            elif hasattr(product, 'effective_price') and product.effective_price is not None:
                unit_price = float(product.effective_price)
            else:
                unit_price = float(product.price or 0)
            subtotal = unit_price * quantity
            delivery_check = _check_store_delivery(product.store, address, subtotal)
            if not delivery_check.get('can_deliver'):
                return jsonify({
                    'error': delivery_check.get('reason') or 'This store cannot deliver to your selected address.',
                    'delivery_blocked': True,
                    'store_id': product.store_id,
                    'store_name': product.store.name if product.store else None,
                }), 400

        cart = Cart.query.filter_by(user_id=user_id).first()
        if not cart:
            print(f"🆕 Creating new cart for user: {user_id}")
            cart = Cart(user_id=user_id)
            db.session.add(cart)
            db.session.flush()

        # ✅ FIXED: Check if product/variant combination already in cart
        item = CartItem.query.filter_by(
            cart_id=cart.id, 
            product_id=product_id,
            variant_id=variant_id  # Include variant_id in the query!
        ).first()
        
        if item:
            # Check total quantity against stock
            if variant:
                if variant.stock_quantity < (item.quantity + quantity):
                    return jsonify({'error': f'Only {variant.stock_quantity} available total'}), 400
            else:
                if product.stock_quantity < (item.quantity + quantity):
                    return jsonify({'error': f'Only {product.stock_quantity} available total'}), 400
            print(f"🔄 Updating existing cart item from {item.quantity} to {item.quantity + quantity}")
            item.quantity += quantity
            db.session.flush()
            sync_err = sync_cart_item_addons(item, product, addon_option_ids)
            if sync_err:
                db.session.rollback()
                return sync_err
        else:
            print(f"➕ Adding new cart item")
            item = CartItem(cart_id=cart.id, product_id=product_id, variant_id=variant_id, quantity=quantity)
            db.session.add(item)
            db.session.flush()
            sync_err = sync_cart_item_addons(item, product, addon_option_ids)
            if sync_err:
                db.session.rollback()
                return sync_err

        db.session.commit()
        
        # Get updated cart with all items
        updated_cart = Cart.query.get(cart.id)
        
        # Build the same enhanced cart data
        cart_data = {
            'id': updated_cart.id,
            'user_id': updated_cart.user_id,
            'created_at': updated_cart.created_at.isoformat() if updated_cart.created_at else None,
            'updated_at': updated_cart.updated_at.isoformat() if updated_cart.updated_at else None,
            'items': []
        }
        
        for cart_item in updated_cart.items:
            if cart_item.product:
                # Use model serializer so mobile/web get consistent fields:
                # product.special_price/effective_price/discount_pct and
                # variant.special_price/effective_price/discount_pct.
                cart_data['items'].append(cart_item.to_dict())
        
        print(f"✅ Item added successfully. Cart now has {len(cart_data['items'])} items")
        
        return jsonify({'success': True, 'message': 'Item added to cart', 'cart': cart_data})
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error in add_to_cart: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
    
@customer_bp.route('/cart/items/<int:item_id>', methods=['PUT'])
@customer_only
def update_cart_item(item_id):
    """Update the quantity of a cart item."""
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json() or {}
        quantity = data.get('quantity')

        print(f"🔄 Updating cart item - User: {user_id}, Item: {item_id}, New Quantity: {quantity}")

        if quantity is None or int(quantity) < 1:
            return jsonify({'error': 'quantity >= 1 is required'}), 400

        item = CartItem.query.get_or_404(item_id)
        if item.cart.user_id != user_id:
            return jsonify({'error': 'Unauthorized'}), 403

        print(f"   🔍 Item variant_id: {item.variant_id}")

        # Check stock - use variant stock if variant_id is set
        if item.variant_id:
            variant = ProductVariant.query.get(item.variant_id)
            if variant:
                print(f"   📦 Variant: {variant.name}, Stock: {variant.stock_quantity}")
                if variant.stock_quantity < int(quantity):
                    return jsonify({'error': f'Only {variant.stock_quantity} available'}), 400
            else:
                print(f"   ⚠️ Variant {item.variant_id} not found, falling back to product stock")
                if item.product and item.product.stock_quantity < int(quantity):
                    return jsonify({'error': f'Only {item.product.stock_quantity} available'}), 400
        else:
            print(f"   📦 Product: {item.product.name}, Stock: {item.product.stock_quantity}")
            if item.product and item.product.stock_quantity < int(quantity):
                return jsonify({'error': f'Only {item.product.stock_quantity} available'}), 400

        item.quantity = int(quantity)
        db.session.commit()
        
        print(f"✅ Cart item updated successfully")
        
        # Return full cart with consistent format (same as add_to_cart)
        updated_cart = Cart.query.get(item.cart_id)
        
        cart_data = {
            'id': updated_cart.id,
            'user_id': updated_cart.user_id,
            'created_at': updated_cart.created_at.isoformat() if updated_cart.created_at else None,
            'updated_at': updated_cart.updated_at.isoformat() if updated_cart.updated_at else None,
            'items': []
        }
        
        for cart_item in updated_cart.items:
            if cart_item.product:
                cart_data['items'].append(cart_item.to_dict())
        
        return jsonify({'success': True, 'cart': cart_data})
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error in update_cart_item: {str(e)}")
        return jsonify({'error': str(e)}), 500


@customer_bp.route('/cart/items/<int:item_id>/addons/<int:addon_option_id>', methods=['DELETE'])
@customer_only
def remove_cart_item_addon(item_id, addon_option_id):
    """Remove a single structured add-on from a cart line (parity with web cart)."""
    try:
        user_id = int(get_jwt_identity())
        item = CartItem.query.get_or_404(item_id)
        if item.cart.user_id != user_id:
            return jsonify({'error': 'Unauthorized'}), 403

        row = CartItemAddon.query.filter_by(
            cart_item_id=item.id,
            addon_option_id=addon_option_id,
        ).first()
        if not row:
            return jsonify({'error': 'Add-on not found on this cart item'}), 404

        db.session.delete(row)
        db.session.commit()

        cart = item.cart
        cart_data = {
            'id': cart.id,
            'user_id': cart.user_id,
            'created_at': cart.created_at.isoformat() if cart.created_at else None,
            'updated_at': cart.updated_at.isoformat() if cart.updated_at else None,
            'items': [
                cart_item.to_dict()
                for cart_item in cart.items
                if cart_item.product
            ],
        }
        return jsonify({'success': True, 'message': 'Add-on removed', 'cart': cart_data})
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('remove_cart_item_addon: %s', e)
        return jsonify({'error': str(e)}), 500


@customer_bp.route('/cart/items/<int:item_id>', methods=['DELETE'])
@customer_only
def remove_cart_item(item_id):
    """Remove a specific item from the cart."""
    try:
        user_id = int(get_jwt_identity())
        print(f"🗑️ Removing cart item - User: {user_id}, Item: {item_id}")
        
        item = CartItem.query.get_or_404(item_id)
        if item.cart.user_id != user_id:
            return jsonify({'error': 'Unauthorized'}), 403
            
        cart = item.cart
        db.session.delete(item)
        db.session.commit()
        
        print(f"✅ Item removed successfully")
        
        # Return full cart with consistent format
        cart_data = {
            'id': cart.id,
            'user_id': cart.user_id,
            'created_at': cart.created_at.isoformat() if cart.created_at else None,
            'updated_at': cart.updated_at.isoformat() if cart.updated_at else None,
            'items': []
        }
        
        for cart_item in cart.items:
            if cart_item.product:
                cart_data['items'].append(cart_item.to_dict())
        
        return jsonify({'success': True, 'cart': cart_data})
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error in remove_cart_item: {str(e)}")
        return jsonify({'error': str(e)}), 500


@customer_bp.route('/cart/clear', methods=['POST'])
@customer_only
def clear_cart():
    """Remove all items from the cart."""
    try:
        user_id = int(get_jwt_identity())
        print(f"🧹 Clearing cart for user: {user_id}")
        
        cart = Cart.query.filter_by(user_id=user_id).first()
        if cart:
            item_count = CartItem.query.filter_by(cart_id=cart.id).count()
            CartItem.query.filter_by(cart_id=cart.id).delete()
            db.session.commit()
            print(f"✅ Removed {item_count} items from cart")
        else:
            print(f"📭 No cart found for user")
            
        return jsonify({'success': True, 'message': 'Cart cleared'})
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error in clear_cart: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════════════════
# ORDERS — JWT protected
# ══════════════════════════════════════════════════════════════════════════

@customer_bp.route('/orders', methods=['GET'])
@customer_only
def get_orders():
    """Return paginated orders for the logged-in customer."""
    try:
        user_id = int(get_jwt_identity())
        status = request.args.get('status', '')
        page = request.args.get('page', 1, type=int)

        q = (
            Order.query
            .filter_by(customer_id=user_id)
            .options(
                selectinload(Order.items).joinedload(OrderItem.product).selectinload(Product.images),
                selectinload(Order.items).joinedload(OrderItem.variant),
                selectinload(Order.items).selectinload(OrderItem.addons),
                joinedload(Order.store),
                joinedload(Order.customer),
                joinedload(Order.assigned_rider).joinedload(Rider.user),
            )
        )
        if status:
            q = q.filter_by(status=status)
        orders = q.order_by(Order.created_at.desc()).paginate(
            page=page, per_page=20, error_out=False
        )

        page_order_ids = [o.id for o in orders.items]
        rated_by_order = defaultdict(set)
        item_ratings = {}
        store_rated_ids = set()
        if page_order_ids:
            for pr in ProductRating.query.filter(ProductRating.order_id.in_(page_order_ids)).all():
                if pr.order_item_id is not None:
                    rated_by_order[pr.order_id].add(pr.order_item_id)
                    if pr.rating is not None:
                        item_ratings[pr.order_item_id] = int(pr.rating)
            store_rated_ids = {
                r.order_id for r in StoreRating.query.filter(StoreRating.order_id.in_(page_order_ids)).all()
            }

        result = []
        for o in orders.items:
            d = o.to_dict()
            items = list(o.items or [])
            item_dicts = []
            for i in items:
                idict = i.to_dict()
                rating = item_ratings.get(i.id)
                idict['rating'] = rating
                idict['is_rated'] = i.id in rated_by_order.get(o.id, set())
                item_dicts.append(idict)
            d['items'] = item_dicts
            if o.store:
                d['store_name'] = o.store.name
            elif o.store_id:
                d['store_name'] = None
            n_items = len(items)
            if o.status in ('delivered', 'completed'):
                rid = rated_by_order.get(o.id, set())
                products_ok = len(rid) >= n_items if n_items else True
                sr_ok = o.id in store_rated_ids
                d['store_rated'] = sr_ok
                d['all_rated'] = products_ok and sr_ok
            else:
                d['store_rated'] = True
                d['all_rated'] = True
            result.append(d)

        return jsonify({
            'orders': result,
            'total': orders.total,
            'page': orders.page,
            'pages': orders.pages,
            'has_next': orders.has_next,
        })
    except Exception as e:
        current_app.logger.exception('get_orders: %s', e)
        return jsonify({'error': str(e)}), 500


@customer_bp.route('/orders/<int:order_id>', methods=['GET'])
@customer_only
def get_order(order_id):
    """Return a single order with full item detail."""
    try:
        user_id = int(get_jwt_identity()) 
        order = (
            Order.query
            .filter_by(id=order_id, customer_id=user_id)
            .options(
                selectinload(Order.items).joinedload(OrderItem.product).selectinload(Product.images),
                selectinload(Order.items).joinedload(OrderItem.variant),
                selectinload(Order.items).selectinload(OrderItem.addons),
                joinedload(Order.store),
                joinedload(Order.customer),
                joinedload(Order.assigned_rider).joinedload(Rider.user),
            )
            .first_or_404()
        )
        d = order.to_dict()
        item_ratings = {
            pr.order_item_id: int(pr.rating)
            for pr in ProductRating.query.filter_by(order_id=order.id).all()
            if pr.order_item_id is not None and pr.rating is not None
        }
        d['items'] = []
        for i in (order.items or []):
            idict = i.to_dict()
            idict['rating'] = item_ratings.get(i.id)
            idict['is_rated'] = i.id in item_ratings
            d['items'].append(idict)
        return jsonify(d)
    except Exception as e:
        current_app.logger.exception('get_order: %s', e)
        return jsonify({'error': str(e)}), 500


@customer_bp.route('/orders/<int:order_id>/complete', methods=['POST'])
@customer_only
def complete_order(order_id):
    """Allow customer to mark delivered orders as completed."""
    try:
        user_id = int(get_jwt_identity())
        order = Order.query.filter_by(id=order_id, customer_id=user_id).first()
        if not order:
            return jsonify({'success': False, 'message': 'Order not found'}), 404
        if order.status != 'delivered':
            return jsonify({'success': False, 'message': 'Only delivered orders can be marked as completed.'}), 400

        order.set_status('completed')
        from app.utils.seller_notifications import notify_store_seller
        notify_store_seller(
            store_id=order.store_id,
            title='Order completed',
            message=f'Customer confirmed delivery for Order #{order.id}.',
            type='order_completed',
            reference_id=order.id,
        )
        db.session.commit()
        return jsonify({'success': True, 'message': 'Order marked as completed.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@customer_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
@customer_only
def cancel_order(order_id):
    """Cancel a pending order and restore reserved product stock."""
    try:
        user_id = int(get_jwt_identity())
        order = Order.query.filter_by(id=order_id, customer_id=user_id).first()
        if not order:
            return jsonify({'success': False, 'message': 'Order not found'}), 404
        if order.status != 'pending':
            return jsonify({
                'success': False,
                'message': 'Only pending orders can be cancelled.',
            }), 400

        from app.order_cancel_reasons import normalize_customer_cancel_reason
        payload = request.get_json(silent=True) or {}
        reason_code, reason_text, reason_err = normalize_customer_cancel_reason(payload)
        if reason_err:
            return jsonify({'success': False, 'message': reason_err}), 400

        # Ensure product/variant/add-on rows are available for stock restore
        _ = [(item.addons, item.product, item.variant) for item in (order.items or [])]
        order.restore_stock_on_cancel(user_id)
        order.status = 'cancelled'
        order.cancellation_reason_code = reason_code
        order.cancellation_reason = reason_text
        order.cancelled_at = datetime.utcnow()
        if hasattr(order, 'updated_at'):
            order.updated_at = datetime.utcnow()
        from app.utils.seller_notifications import notify_store_seller
        notify_store_seller(
            store_id=order.store_id,
            title='Order cancelled',
            message=f'Customer cancelled Order #{order.id}. Reason: {reason_text}',
            type='order_cancelled',
            reference_id=order.id,
        )
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Order cancelled successfully',
            'order': order.to_dict(),
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@customer_bp.route('/orders/cancel-reasons', methods=['GET'])
def list_cancel_reasons():
    """Public list of customer cancel reason chips for Flutter/web clients."""
    from app.order_cancel_reasons import CUSTOMER_CANCEL_REASONS
    return jsonify({'success': True, 'reasons': CUSTOMER_CANCEL_REASONS})


# ══════════════════════════════════════════════════════════════════════════
# PRODUCT RATINGS — JWT auth (Flutter)
# ══════════════════════════════════════════════════════════════════════════

@customer_bp.route('/orders/<int:order_id>/ratings', methods=['GET'])
@customer_only
def get_order_ratings(order_id):
    """Get existing ratings for an order's items."""
    try:
        user_id = int(get_jwt_identity())
        order = Order.query.filter_by(id=order_id, customer_id=user_id).first()
        if not order:
            return jsonify({'error': 'Order not found'}), 404

        ratings = ProductRating.query.filter_by(order_id=order_id, customer_id=user_id).all()
        ratings_map = {
            str(r.order_item_id): r.to_dict() for r in ratings if r.order_item_id is not None
        }
        store_row = StoreRating.query.filter_by(order_id=order_id, customer_id=user_id).first()

        return jsonify({
            'success': True,
            'ratings': ratings_map,
            'store_rating': store_row.to_dict() if store_row else None,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@customer_bp.route('/orders/<int:order_id>/rate', methods=['POST'])
@customer_only
def submit_order_ratings(order_id):
    """Submit product ratings for a delivered order."""
    try:
        user_id = int(get_jwt_identity())
        order = Order.query.filter_by(id=order_id, customer_id=user_id).first()
        if not order:
            return jsonify({'error': 'Order not found'}), 404

        if order.status not in ('delivered', 'completed'):
            return jsonify({'error': 'Can only rate delivered or completed orders'}), 400

        data = request.get_json() or {}
        ratings_data = data.get('ratings') or []
        store_payload = data.get('store_rating')

        created = 0
        created_store = False

        if store_payload and isinstance(store_payload, dict):
            rv = store_payload.get('rating')
            try:
                rv = int(rv) if rv is not None else None
            except (TypeError, ValueError):
                rv = None
            if rv is not None and 1 <= rv <= 5:
                existing_sr = StoreRating.query.filter_by(order_id=order_id, customer_id=user_id).first()
                if not existing_sr:
                    comment_s = (store_payload.get('comment') or '').strip() if store_payload.get('comment') else None
                    db.session.add(
                        StoreRating(
                            customer_id=user_id,
                            store_id=order.store_id,
                            order_id=order_id,
                            rating=rv,
                            comment=comment_s or None,
                        )
                    )
                    created_store = True

        for r in ratings_data:
            order_item_id = r.get('order_item_id')
            rating_value = r.get('rating')
            comment = r.get('comment', '').strip() if r.get('comment') else None

            if not order_item_id or not rating_value:
                continue
            if not (1 <= int(rating_value) <= 5):
                continue

            order_item = OrderItem.query.filter_by(id=order_item_id, order_id=order_id).first()
            if not order_item:
                continue

            existing = ProductRating.query.filter_by(
                customer_id=user_id, order_item_id=order_item_id
            ).first()

            if existing:
                continue

            new_rating = ProductRating(
                customer_id=user_id,
                product_id=order_item.product_id,
                variant_id=order_item.variant_id,
                order_id=order_id,
                order_item_id=order_item_id,
                rating=int(rating_value),
                comment=comment,
            )
            db.session.add(new_rating)
            created += 1

        if not ratings_data and not created_store:
            return jsonify({'error': 'No ratings provided'}), 400

        if created or created_store:
            parts = []
            if created_store and store_payload:
                try:
                    sr = int(store_payload.get('rating'))
                    parts.append(f'store {sr}/5')
                except (TypeError, ValueError):
                    parts.append('store')
            if created:
                parts.append(f'{created} product rating(s)')
            summary = ', '.join(parts) if parts else 'new ratings'
            from app.utils.seller_notifications import notify_store_seller
            notify_store_seller(
                store_id=order.store_id,
                title='New rating received',
                message=f'Customer rated Order #{order.id} ({summary}).',
                type='new_rating',
                reference_id=order.id,
            )

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'{created} product rating(s) submitted' + ('; store rated' if created_store else ''),
            'created': created,
            'store_created': created_store,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@customer_bp.route('/products/<int:product_id>/ratings', methods=['GET'])
def get_product_ratings(product_id):
    """Get ratings for a product (public). Optional variant_id filter:
    - omit / empty: all ratings for the product
    - 'main': only standard (variant_id IS NULL)
    - integer: only that variant
    """
    try:
        product = Product.query.get_or_404(product_id)

        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 50)
        variant_raw = request.args.get('variant_id')

        ratings_query = ProductRating.query.filter_by(product_id=product_id)
        if variant_raw is not None and str(variant_raw).strip() != '':
            if str(variant_raw).strip().lower() == 'main':
                ratings_query = ratings_query.filter(ProductRating.variant_id.is_(None))
            else:
                try:
                    vid = int(variant_raw)
                    ratings_query = ratings_query.filter_by(variant_id=vid)
                except (TypeError, ValueError):
                    return jsonify({'error': 'Invalid variant_id'}), 400

        ratings_query = ratings_query.order_by(ProductRating.created_at.desc())

        total = ratings_query.count()
        ratings = ratings_query.offset((page - 1) * per_page).limit(per_page).all()

        from sqlalchemy import func
        agg_q = db.session.query(
            func.avg(ProductRating.rating).label('avg'),
            func.count(ProductRating.id).label('count')
        ).filter_by(product_id=product_id)
        dist_q = db.session.query(
            ProductRating.rating, func.count(ProductRating.id)
        ).filter_by(product_id=product_id)
        if variant_raw is not None and str(variant_raw).strip() != '':
            if str(variant_raw).strip().lower() == 'main':
                agg_q = agg_q.filter(ProductRating.variant_id.is_(None))
                dist_q = dist_q.filter(ProductRating.variant_id.is_(None))
            else:
                vid = int(variant_raw)
                agg_q = agg_q.filter_by(variant_id=vid)
                dist_q = dist_q.filter_by(variant_id=vid)

        agg = agg_q.first()
        dist = dist_q.group_by(ProductRating.rating).all()
        distribution = {str(i): 0 for i in range(1, 6)}
        for star, count in dist:
            distribution[str(star)] = count

        filter_key = None
        if variant_raw is not None and str(variant_raw).strip() != '':
            if str(variant_raw).strip().lower() == 'main':
                filter_key = 'main'
            else:
                filter_key = int(variant_raw)

        return jsonify({
            'success': True,
            'avg_rating': round(float(agg.avg or 0), 1) if agg else 0.0,
            'total_ratings': int(agg.count or 0) if agg else 0,
            'distribution': distribution,
            'ratings': [r.to_dict() for r in ratings],
            'page': page,
            'total_pages': (total + per_page - 1) // per_page if total else 0,
            'variant_id': filter_key,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════════════════
# DEBUG endpoint
# ══════════════════════════════════════════════════════════════════════════

@customer_bp.route('/debug/token', methods=['GET'])
@jwt_required(optional=True)
def debug_token():
    """Debug endpoint to check JWT token"""
    user_id = get_jwt_identity()
    claims = get_jwt()
    
    auth_header = request.headers.get('Authorization', 'Not provided')
    
    return jsonify({
        'authenticated': user_id is not None,
        'user_id': user_id,
        'claims': claims,
        'auth_header': auth_header[:50] if auth_header != 'Not provided' and len(auth_header) > 50 else auth_header,
    })


# Optional: Create a custom decorator that handles both 'sub' and 'user_id'
def customer_jwt_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            # Verify JWT
            auth_header = request.headers.get('Authorization', '')
            if not auth_header or not auth_header.startswith('Bearer '):
                return jsonify({'msg': 'Missing Authorization Header'}), 401
            
            token = auth_header.split(' ')[1]
            
            # Try to decode with PyJWT to check claims
            import jwt as pyjwt
            from flask import current_app
            
            try:
                # Decode without verification first to see claims
                unverified = pyjwt.decode(token, options={"verify_signature": False})
                print(f"Token claims: {unverified}")
                
                # Check if we have either sub or user_id
                user_id = unverified.get('sub') or unverified.get('user_id')
                if user_id:
                    kwargs['user_id'] = user_id
                    return f(*args, **kwargs)
                else:
                    return jsonify({'msg': 'Missing user identifier in token'}), 422
                    
            except Exception as e:
                print(f"Token decode error: {e}")
                return jsonify({'msg': 'Invalid token'}), 422
                
        except Exception as e:
            print(f"JWT error: {e}")
            return jsonify({'msg': str(e)}), 422
    
    return decorated_function


# ══════════════════════════════════════════════════════════════════════════
# SELLER APPLICATION
# ══════════════════════════════════════════════════════════════════════════

@customer_bp.route('/seller-application', methods=['POST'])
@customer_only
def submit_seller_application():
    """Submit a new seller application (JWT)"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    data = request.get_json() or {}
    store_name = data.get('store_name', '').strip()
    store_description = data.get('store_description', '').strip()
    store_logo_url = data.get('store_logo_url', '').strip()
    store_logo_public_id = data.get('store_logo_public_id', '').strip()
    government_id_url = data.get('government_id_url', '').strip()
    government_id_public_id = data.get('government_id_public_id', '').strip()

    # Validation
    errors = {}
    if not store_name:
        errors['store_name'] = 'Store name is required'
    if not store_description:
        errors['store_description'] = 'Store description is required'
    if not store_logo_url or not store_logo_public_id:
        errors['store_logo'] = 'Store logo is required'
    if not government_id_url or not government_id_public_id:
        errors['government_id'] = 'Government ID is required'

    if errors:
        return jsonify({'error': 'Validation failed', 'field_errors': errors}), 400

    # Check for existing in-review application
    existing = SellerApplication.query.filter(
        SellerApplication.user_id == user_id,
        SellerApplication.status.in_(['pending', 'resubmitted'])
    ).first()
    if existing:
        return jsonify({'error': 'You already have a pending application'}), 400

    application = SellerApplication(
        user_id=user_id,
        applicant_full_name=user.full_name,
        applicant_email=user.email,
        applicant_phone=user.phone,
        application_source='customer_account',
        store_name=store_name,
        store_description=store_description,
        store_logo_url=store_logo_url,
        store_logo_public_id=store_logo_public_id,
        government_id_url=government_id_url,
        government_id_public_id=government_id_public_id,
        status='pending',
    )
    db.session.add(application)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Application submitted successfully', 'application': application.to_dict()}), 201


@customer_bp.route('/seller-application', methods=['GET'])
@customer_only
def get_seller_application_status():
    """Get the customer's latest seller application (JWT)"""
    user_id = get_jwt_identity()
    application = SellerApplication.query.filter_by(user_id=user_id)\
        .order_by(SellerApplication.submitted_at.desc()).first()

    if not application:
        return jsonify({'application': None}), 200

    return jsonify({'application': application.to_dict()}), 200


@customer_bp.route('/seller-application/resubmit', methods=['PUT'])
@customer_only
def resubmit_seller_application():
    """Resubmit a rejected seller application with updated fields (JWT)"""
    user_id = get_jwt_identity()
    application = SellerApplication.query.filter_by(user_id=user_id, status='rejected')\
        .order_by(SellerApplication.submitted_at.desc()).first()

    if not application:
        return jsonify({'error': 'No rejected application found to resubmit'}), 404

    data = request.get_json() or {}
    rejection_details = application.rejection_details or {}

    # Only update fields that were rejected
    updated_fields = []
    if rejection_details.get('store_name', {}).get('rejected') and 'store_name' in data:
        val = data['store_name'].strip()
        if not val:
            return jsonify({'error': 'Store name cannot be empty'}), 400
        application.store_name = val
        updated_fields.append('store_name')

    if rejection_details.get('store_description', {}).get('rejected') and 'store_description' in data:
        val = data['store_description'].strip()
        if not val:
            return jsonify({'error': 'Store description cannot be empty'}), 400
        application.store_description = val
        updated_fields.append('store_description')

    if rejection_details.get('store_logo', {}).get('rejected'):
        if 'store_logo_url' in data and 'store_logo_public_id' in data:
            application.store_logo_url = data['store_logo_url']
            application.store_logo_public_id = data['store_logo_public_id']
            updated_fields.append('store_logo')

    if rejection_details.get('government_id', {}).get('rejected'):
        if 'government_id_url' in data and 'government_id_public_id' in data:
            application.government_id_url = data['government_id_url']
            application.government_id_public_id = data['government_id_public_id']
            updated_fields.append('government_id')

    if not updated_fields:
        return jsonify({'error': 'No rejected fields were updated'}), 400

    # Mark explicitly as resubmitted for admin visibility
    application.status = 'resubmitted'
    application.admin_notes = None
    application.rejection_details = None
    application.reviewed_at = None
    application.reviewed_by = None

    db.session.commit()

    return jsonify({'success': True, 'message': 'Application resubmitted', 'application': application.to_dict()}), 200


# ══════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════════════

@customer_bp.route('/notifications', methods=['GET'])
@customer_only
def get_notifications():
    """Get customer's notifications (JWT)"""
    user_id = get_jwt_identity()
    notifications = Notification.query.filter_by(user_id=user_id)\
        .order_by(Notification.created_at.desc()).limit(50).all()
    unread_count = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    return jsonify({
        'notifications': [n.to_dict() for n in notifications],
        'unread_count': unread_count,
    }), 200


@customer_bp.route('/notifications/<int:notif_id>/read', methods=['POST'])
@customer_only
def mark_notification_read(notif_id):
    """Mark a single notification as read (JWT)"""
    user_id = get_jwt_identity()
    notification = Notification.query.filter_by(id=notif_id, user_id=user_id).first()
    if not notification:
        return jsonify({'error': 'Notification not found'}), 404
    notification.is_read = True
    db.session.commit()
    return jsonify({'success': True}), 200


@customer_bp.route('/notifications/read-all', methods=['POST'])
@customer_only
def mark_all_notifications_read():
    """Mark all notifications as read (JWT)"""
    user_id = get_jwt_identity()
    Notification.query.filter_by(user_id=user_id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True}), 200


@customer_bp.route('/stores/<int:store_id>/time-slots', methods=['GET'])
def get_store_time_slots(store_id):
    """Get available delivery time slots for a store based on its schedule.
    Query params: date (YYYY-MM-DD)
    """
    from datetime import datetime as dt
    from app.utils.store_schedule import build_store_time_slots

    store = Store.query.get(store_id)
    if not store:
        return jsonify({'error': 'Store not found'}), 404

    date_str = request.args.get('date')
    target_date = None
    if date_str:
        try:
            target_date = dt.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    return jsonify(build_store_time_slots(store, target_date))


# ── Wishlist ─────────────────────────────────────────────────────────────────

@customer_bp.route('/wishlist', methods=['GET'])
@customer_only
def get_wishlist():
    try:
        user_id = int(get_jwt_identity())
        from app.wishlist_helpers import list_wishlist_items
        items = list_wishlist_items(user_id)
        return jsonify({'success': True, 'items': items, 'count': len(items)})
    except Exception as e:
        current_app.logger.exception('get_wishlist: %s', e)
        return jsonify({'error': str(e)}), 500


@customer_bp.route('/wishlist/product/<int:product_id>', methods=['GET'])
@customer_only
def get_wishlist_for_product(product_id):
    try:
        user_id = int(get_jwt_identity())
        from app.wishlist_helpers import wishlist_variant_keys_for_product
        keys = wishlist_variant_keys_for_product(user_id, product_id)
        return jsonify({'success': True, 'variant_ids': keys})
    except Exception as e:
        current_app.logger.exception('get_wishlist_for_product: %s', e)
        return jsonify({'error': str(e)}), 500


@customer_bp.route('/wishlist/toggle', methods=['POST'])
@customer_only
def toggle_wishlist_api():
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json(silent=True) or {}
        from app.wishlist_helpers import toggle_wishlist
        item, wished, err = toggle_wishlist(user_id, data.get('product_id'), data.get('variant_id'))
        if err:
            return jsonify(err[0]), err[1]
        return jsonify({
            'success': True,
            'wished': wished,
            'item': item,
            'message': 'Added to wishlist' if wished else 'Removed from wishlist',
        })
    except Exception as e:
        current_app.logger.exception('toggle_wishlist_api: %s', e)
        return jsonify({'error': str(e)}), 500


@customer_bp.route('/wishlist/<int:item_id>', methods=['DELETE'])
@customer_only
def delete_wishlist_item(item_id):
    try:
        user_id = int(get_jwt_identity())
        from app.wishlist_helpers import remove_wishlist_item
        ok, err = remove_wishlist_item(user_id, item_id)
        if err:
            return jsonify(err[0]), err[1]
        return jsonify({'success': True, 'message': 'Removed from wishlist'})
    except Exception as e:
        current_app.logger.exception('delete_wishlist_item: %s', e)
        return jsonify({'error': str(e)}), 500


def _format_time_label(hour, minute):
    """Format hour:minute to '7:00 AM' style"""
    period = 'AM' if hour < 12 else 'PM'
    display_h = hour % 12
    if display_h == 0:
        display_h = 12
    if minute == 0:
        return f"{display_h}:{minute:02d} {period}"
    return f"{display_h}:{minute:02d} {period}"