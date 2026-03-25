# app/customer.py
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt, verify_jwt_in_request
from app.models import Product, Store, Order, OrderItem, Cart, CartItem, Rider, ProductVariant
from app.extensions import db
from functools import wraps
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

    q = Product.query.join(Store).filter(
        Product.is_available == True,
        Store.status == 'active',
        Product.stock_quantity > 0
    )
    
    # Filter by main category slug if provided
    if category and category != 'all':
        from app.models import Category
        main_cat = Category.query.filter_by(slug=category).first()
        if main_cat:
            q = q.filter(Product.main_category_id == main_cat.id)
    
    if store_id:
        q = q.filter(Product.store_id == store_id)
    if search:
        q = q.filter(Product.name.ilike(f'%{search}%'))

    paged = q.paginate(page=page, per_page=per_page, error_out=False)

    products = []
    for p in paged.items:
        d = p.to_dict()
        d['store_name'] = p.store.name if p.store else None
        products.append(d)

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
    if p.store:
        data['store'] = p.store.to_dict()
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
    stores = Store.query.filter_by(status='active').all()
    return jsonify([s.to_dict() for s in stores])


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
        print(f"🛒 Getting cart for user: {user_id}")
        
        cart = Cart.query.filter_by(user_id=user_id).first()
        if not cart:
            print(f"🆕 Creating new cart for user: {user_id}")
            cart = Cart(user_id=user_id)
            db.session.add(cart)
            db.session.commit()
        
        # Custom serialization to ensure images are included
        cart_data = {
            'id': cart.id,
            'user_id': cart.user_id,
            'created_at': cart.created_at.isoformat() if cart.created_at else None,
            'updated_at': cart.updated_at.isoformat() if cart.updated_at else None,
            'items': []
        }
        
        for item in cart.items:
            product = item.product
            if product:
                # Use product.to_dict() to get complete product data with all category fields
                product_data = product.to_dict()
                product_data['store_name'] = product.store.name if product.store else None
                
                # Build cart item data
                item_data = {
                    'id': item.id,
                    'cart_id': item.cart_id,
                    'product_id': item.product_id,
                    'quantity': item.quantity,
                    'created_at': item.created_at.isoformat() if item.created_at else None,
                    'updated_at': item.updated_at.isoformat() if item.updated_at else None,
                    'product': product_data
                }
                cart_data['items'].append(item_data)
        
        print(f"✅ Cart retrieved: {len(cart_data['items'])} items")
        
        # Debug: Print first item's image info
        if cart_data['items']:
            first_item = cart_data['items'][0]
            print(f"🔍 First item: {first_item['product']['name']}")
            print(f"📸 Images count: {len(first_item['product'].get('images', []))}")
            if first_item['product'].get('images'):
                print(f"📸 First image filename: {first_item['product']['images'][0].get('filename')}")
        
        return jsonify({'success': True, 'cart': cart_data})
    except Exception as e:
        print(f"❌ Error in get_cart: {str(e)}")
        import traceback
        traceback.print_exc()
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

        print(f"🛒 Adding to cart - User: {user_id}, Product: {product_id}, Variant: {variant_id}, Quantity: {quantity}")

        if not product_id or quantity < 1:
            return jsonify({'error': 'product_id and quantity >= 1 are required'}), 400

        product = Product.query.get(product_id)
        if not product or not product.is_available:
            return jsonify({'error': 'Product not available'}), 404

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
        else:
            print(f"➕ Adding new cart item")
            item = CartItem(cart_id=cart.id, product_id=product_id, variant_id=variant_id, quantity=quantity)
            db.session.add(item)

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
                
                # ✅ ALIGNED: Include variant data if present
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
                    'variant': variant_data  # ✅ Include variant if present
                }
                cart_data['items'].append(item_data)
        
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

        # Check stock
        if item.product and item.product.stock_quantity < int(quantity):
            return jsonify({'error': f'Only {item.product.stock_quantity} available'}), 400

        item.quantity = int(quantity)
        db.session.commit()
        
        print(f"✅ Cart item updated successfully")
        
        return jsonify({'success': True, 'cart': item.cart.to_dict()})
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error in update_cart_item: {str(e)}")
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
        
        return jsonify({'success': True, 'cart': cart.to_dict()})
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

        print(f"📦 Getting orders for user: {user_id}, status: {status}, page: {page}")

        q = Order.query.filter_by(customer_id=user_id)
        if status:
            q = q.filter_by(status=status)
        orders = q.order_by(Order.created_at.desc()).paginate(
            page=page, per_page=20, error_out=False
        )

        result = []
        for o in orders.items:
            d = o.to_dict()
            # Attach order items with product info
            items = OrderItem.query.filter_by(order_id=o.id).all()
            d['items'] = [i.to_dict() for i in items]
            # Attach store name
            if o.store_id:
                store = Store.query.get(o.store_id)
                d['store_name'] = store.name if store else None
            # Attach rider name if assigned
            if o.rider_id:
                rider = Rider.query.get(o.rider_id)
                if rider and rider.user:
                    d['rider_name'] = rider.user.full_name
            result.append(d)

        print(f"✅ Found {len(result)} orders")
        
        return jsonify({
            'orders': result,
            'total': orders.total,
            'page': orders.page,
            'pages': orders.pages,
            'has_next': orders.has_next,
        })
    except Exception as e:
        print(f"❌ Error in get_orders: {str(e)}")
        return jsonify({'error': str(e)}), 500


@customer_bp.route('/orders/<int:order_id>', methods=['GET'])
@customer_only
def get_order(order_id):
    """Return a single order with full item detail."""
    try:
        user_id = int(get_jwt_identity())
        print(f"📦 Getting order: {order_id} for user: {user_id}")
        
        order = Order.query.filter_by(id=order_id, customer_id=user_id).first_or_404()
        d = order.to_dict()

        items = OrderItem.query.filter_by(order_id=order.id).all()
        d['items'] = [i.to_dict() for i in items]

        if order.store_id:
            store = Store.query.get(order.store_id)
            d['store_name'] = store.name if store else None

        if order.rider_id:
            rider = Rider.query.get(order.rider_id)
            if rider and rider.user:
                d['rider_name'] = rider.user.full_name

        return jsonify(d)
    except Exception as e:
        print(f"❌ Error in get_order: {str(e)}")
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