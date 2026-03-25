# app/templates_routes.py - FIXED VERSION
from datetime import datetime, timedelta
from flask import Blueprint, app, flash, json, make_response, render_template, jsonify, request, session, redirect, url_for, current_app
from app.archive_routes import get_seller_store
from app.models import MunicipalityBoundary, OrderItem, ProductVariant, User, Store, Rider, Product, Order, SellerApplication, Cart, CartItem, ProductImage, POSOrder, POSOrderItem, Testimonial, MunicipalityBoundary, GCashQR, StockReduction
from app.extensions import db
import os
from werkzeug.utils import secure_filename
from functools import wraps
from decimal import Decimal
import uuid
import time
import jwt
#from PIL import Image
import io
from flask import send_file
from app.laguna_addresses import get_municipalities, get_barangays, get_coordinates, format_address, LAGUNA_ADDRESSES
from app.models import UserAddress

from app.utils.cloudinary_helper import upload_to_cloudinary
# app/templates_routes.py - Add these imports at the top
from flask_wtf.csrf import generate_csrf
from sqlalchemy.orm import joinedload

# Import the extensions from app (they're initialized in __init__.py)
from app import limiter
templates_bp = Blueprint('templates', __name__)




# Configure upload folder
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


# In templates_routes.py, make sure you have this context processor
@templates_bp.context_processor
def inject_csrf_token():
    """Inject CSRF token into all templates"""
    from flask_wtf.csrf import generate_csrf
    return dict(csrf_token=generate_csrf)


# ═════════════════════════════════════════════════════════════════════════════
# AUTHENTICATION HELPER - Supports both Flask Sessions & JWT Tokens
# ═════════════════════════════════════════════════════════════════════════════
def get_authenticated_user_id():
    """
    Get user ID from either:
    1. Flask session (for web browsers)
    2. JWT token in Authorization header (for mobile apps)
    
    Returns: user_id (int) or None if not authenticated
    """
    # Try session first (for web)
    if 'user_id' in session:
        return session['user_id']
    
    # Try JWT token (for mobile apps like Flutter)
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]  # Remove 'Bearer ' prefix
        try:
            from flask_jwt_extended import decode_token
            payload = decode_token(token)
            # Extract user_id from token claims
            user_id = payload.get('user_id') or payload.get('sub')
            if user_id:
                # Convert string user_id to int if needed
                try:
                    return int(user_id)
                except (ValueError, TypeError):
                    return None
        except Exception as e:
            print(f"⚠️ JWT validation failed: {e}")
    
    return None


def _serialize_customer_order(order):
    """Shape order data for the customer account order UI."""
    items_payload = []
    total_quantity = 0

    for item in order.items:
        quantity = item.quantity or 0
        unit_price = float(item.price or 0)
        total_quantity += quantity

        items_payload.append({
            'id': item.id,
            'product_id': item.product_id,
            'variant_id': item.variant_id,
            'product_name': item.product.name if item.product else 'Product',
            'name': item.product.name if item.product else 'Product',
            'variant_name': item.variant.name if item.variant else None,
            'quantity': quantity,
            'price': unit_price,
            'total': float(quantity * unit_price),
            'product_image_url': item.product_image,
            'image_url': item.product_image,
        })

    return {
        'id': order.id,
        'order_number': f'ORD-{order.id:05d}',
        'status': order.status,
        'payment_method': order.payment_method,
        'payment_status': order.payment_status,
        'subtotal_amount': float(order.subtotal_amount or 0),
        'delivery_fee': float(order.delivery_fee or 0),
        'distance_km': order.distance_km,
        'total_amount': float(order.total_amount or 0),
        'delivery_address': order.delivery_address,
        'delivery_notes': order.delivery_notes,
        'payment_proof_url': order.payment_proof_url,
        'created_at': order.created_at.isoformat() if order.created_at else None,
        'updated_at': order.updated_at.isoformat() if order.updated_at else None,
        'store_id': order.store_id,
        'store_name': order.store.name if order.store else 'Store',
        'store_contact': order.store.contact_number if order.store else None,
        'item_count': total_quantity,
        'items': items_payload,
    }


@templates_bp.route('/')
@limiter.limit("5 per minute")
def index():
    """Show the e-commerce landing page to everyone"""
    try:
        # Get all main categories from database for the navigation
        from app.models import Category
        main_categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()

        variant_in_stock_exists = db.session.query(ProductVariant.id).filter(
            ProductVariant.product_id == Product.id,
            ProductVariant.is_available == True,
            ProductVariant.stock_quantity > 0
        ).exists()
        
        # Get products for the landing page - only from active stores with stock
        products = Product.query\
            .join(Store, Product.store_id == Store.id)\
            .filter(
                Product.is_archived == False,
                Product.is_available == True,
                Store.status == 'active',
                db.or_(
                    Product.stock_quantity > 0,
                    variant_in_stock_exists
                )
            )\
            .order_by(Product.created_at.desc())\
            .limit(8)\
            .all()
        
        print("=== DEBUGGING PRODUCTS ===")
        print(f"Raw products count: {len(products)}")
        for p in products:
            print(f"Product ID: {p.id}, Name: {p.name}, Store ID: {p.store_id}, Store: {p.store.name if p.store else 'None'}")
            if p.main_category:
                print(f"  Main Category: {p.main_category.name}")
            if p.store_category:
                print(f"  Store Category: {p.store_category.name}")
        
        # Convert products to dict and add store_name
        product_list = []
        for product in products:
            product_dict = product.to_dict()
            # Add store name to each product
            if product.store:
                product_dict['store_name'] = product.store.name
                print(f"Added store name '{product.store.name}' to product '{product.name}'")
            else:
                product_dict['store_name'] = 'Unknown Store'
                print(f"WARNING: Product '{product.name}' has no associated store!")
            
            # Add main category info
            if product.main_category:
                product_dict['main_category'] = {
                    'id': product.main_category.id,
                    'name': product.main_category.name,
                    'slug': product.main_category.slug
                }
            
            # Add store category info
            if product.store_category:
                product_dict['store_category'] = {
                    'id': product.store_category.id,
                    'name': product.store_category.name,
                    'slug': product.store_category.slug
                }
            
            product_list.append(product_dict)
        
        # Get active stores
        stores = Store.query\
            .filter_by(status='active')\
            .order_by(Store.created_at.desc())\
            .limit(4)\
            .all()
        
        print(f"\nStores found: {len(stores)}")
        for s in stores:
            print(f"Store: {s.id} - {s.name} - Status: {s.status}")
        
        store_list = [store.to_dict() for store in stores]
        
        # Format categories for the template (for featured categories section)
        featured_categories = []
        for cat in main_categories:
            featured_categories.append({
                'id': cat.id,
                'name': cat.name,
                'slug': cat.slug,
                'icon': cat.icon or 'flower-line',  # Default icon if none
                'description': cat.description,
                'image_url': cat.image_url
            })
        
        print(f"\nFinal product_list count: {len(product_list)}")
        print(f"Final store_list count: {len(store_list)}")
        print(f"Main categories count: {len(main_categories)}")
        print("=== END DEBUG ===\n")
        
        return render_template(
            'index.html',
            products=product_list,
            stores=store_list,
            categories=featured_categories,  # For featured categories section
            main_categories=main_categories   # For navigation menu
        )
    except Exception as e:
        print(f"ERROR loading landing page: {str(e)}")
        import traceback
        traceback.print_exc()
        return render_template('index.html', 
                             products=[], 
                             stores=[], 
                             categories=[],
                             main_categories=[])
    


def seller_required(f):
    """Require user to be logged in as a seller."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('templates.login'))
        if session.get('role') != 'seller':
            return redirect(url_for('templates.dashboard'))
        return f(*args, **kwargs)
    return decorated


@templates_bp.route('/seller/products/<int:product_id>/archive-choice', methods=['POST'])
@seller_required
def product_archive_choice(product_id):
    """Handle seller's choice when deleting a product"""
    try:
        store = get_seller_store()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        data = request.get_json()
        action = data.get('action')  # 'archive', 'delete', 'cancel'
        
        if action == 'archive':
            product.archive(session['user_id'])
            db.session.commit()
            return jsonify({
                'success': True,
                'message': 'Product archived successfully',
                'archived': True
            }), 200
            
        elif action == 'delete':
            # Check again if still in carts
            carts_count = CartItem.query.filter_by(product_id=product_id).count()
            if carts_count > 0:
                return jsonify({
                    'error': f'Cannot delete. Product is in {carts_count} carts. Archive it instead.'
                }), 400
            
            # ===== FIX: DELETE FROM CLOUDINARY FIRST =====
            from app.utils.cloudinary_helper import delete_from_cloudinary
            
            # Delete product images from Cloudinary
            for image in product.images:
                if image.public_id:
                    delete_from_cloudinary(image.public_id)
                    print(f"🗑️ Deleted Cloudinary image: {image.public_id}")
            
            # Delete variant images from Cloudinary
            for variant in product.variants:
                if variant.image_public_id:
                    delete_from_cloudinary(variant.image_public_id)
                    print(f"🗑️ Deleted variant Cloudinary image: {variant.image_public_id}")
            
            # Now delete from database
            db.session.delete(product)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Product permanently deleted from database and Cloudinary'
            }), 200
            
        else:  # cancel
            return jsonify({
                'success': True,
                'message': 'Action cancelled'
            }), 200
            
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error in archive choice: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
# ===== HELPER FUNCTIONS =====
def _get_seller_store():
    """Return the active store for the logged-in seller, or None."""
    return (
        Store.query
        .filter_by(seller_id=session['user_id'], status='active')
        .first()
    )

def _get_primary_image(product):
    """Return the URL path for the primary (or first) product image."""
    if not product.images:
        return None
    primary = next((img for img in product.images if img.is_primary), None)
    img = primary or product.images[0]
    return f'/static/uploads/products/{img.filename}'



# Add context processor to make user available to all templates
@templates_bp.context_processor
def inject_user():
    """Make user available to all templates"""
    user = None
    if session.get('user_id'):
        user_obj = User.query.get(session['user_id'])
        if user_obj:
            user = user_obj.to_dict()
    return dict(user=user)


@templates_bp.route('/seller/apply', methods=['POST'])
def seller_apply():
    """Handle seller application form submission with Cloudinary"""
    if 'user_id' not in session:
        return jsonify({'error': 'Please login first'}), 401
    
    try:
        # Get the user from database
        user = User.query.get(session['user_id'])
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get form data
        store_name = request.form.get('store_name')
        store_description = request.form.get('store_description')
        agree_terms = request.form.get('agree_terms')
        
        # Validate required fields
        if not store_name or not store_description:
            return jsonify({'error': 'Please fill in all required fields'}), 400
        
        # Get Cloudinary data from form (uploaded by frontend)
        store_logo_public_id = request.form.get('store_logo_public_id')
        store_logo_url = request.form.get('store_logo_url')
        government_id_public_id = request.form.get('government_id_public_id')
        government_id_url = request.form.get('government_id_url')
        
        # Validate Cloudinary data
        if not store_logo_public_id or not store_logo_url:
            return jsonify({'error': 'Store logo upload failed. Please try again.'}), 400
        
        if not government_id_public_id or not government_id_url:
            return jsonify({'error': 'Government ID upload failed. Please try again.'}), 400
        
        # Check if user already has a pending application
        existing = SellerApplication.query.filter_by(
            user_id=session['user_id'],
            status='pending'
        ).first()
        
        if existing:
            # If there's an existing application, clean up the newly uploaded images
            from app.utils.cloudinary_helper import delete_from_cloudinary
            delete_from_cloudinary(store_logo_public_id)
            delete_from_cloudinary(government_id_public_id)
            return jsonify({'error': 'You already have a pending application'}), 400
        
        # Create seller application with Cloudinary data
        application = SellerApplication(
            user_id=session['user_id'],
            store_name=store_name,
            store_description=store_description,
            store_logo_public_id=store_logo_public_id,
            store_logo_url=store_logo_url,
            government_id_public_id=government_id_public_id,
            government_id_url=government_id_url,
            status='pending'
        )
        
        db.session.add(application)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Application submitted successfully! Admin will review your request.'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error submitting seller application: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@templates_bp.route('/seller/application/status')
def seller_application_status():
    """Check the status of a seller's application"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    application = SellerApplication.query.filter_by(
        user_id=session['user_id']
    ).order_by(SellerApplication.submitted_at.desc()).first()
    
    if not application:
        return jsonify({'status': 'none'})
    
    return jsonify({
        'status': application.status,
        'store_name': application.store_name,
        'submitted_at': application.submitted_at.isoformat() if application.submitted_at else None,
        'admin_notes': application.admin_notes
    })



@templates_bp.route('/api/account/<page>')
def account_content(page):
    """Return HTML content for different account pages"""
    try:
        # Get user data if logged in
        user = None
        if session.get('user_id'):
            user = User.query.get(session['user_id'])
        
        if page == 'profile':
            return render_template('account_parts/profile_content.html', 
                                 user=user.to_dict() if user else None)
        elif page == 'orders':
            return render_template('account_parts/orders_content.html', 
                                 user=user.to_dict() if user else None)
        elif page == 'settings':
            return render_template('account_parts/settings_content.html', 
                                 user=user.to_dict() if user else None)
        else:
            return '', 404
            
    except Exception as e:
        print(f"Error loading account page {page}: {str(e)}")
        return f'<div class="error">Error loading content: {str(e)}</div>', 500
# ============================================
# PROFILE MANAGEMENT ROUTES
# ============================================
@templates_bp.route('/api/account/profile/update', methods=['POST'])
def update_profile():
    """Update user profile information with Cloudinary avatar"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        user = User.query.get(session['user_id'])
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # DEBUG: Print what we're receiving
        print("\n" + "="*60)
        print("📝 PROFILE UPDATE REQUEST RECEIVED")
        print(f"👤 User ID: {user.id}")
        print(f"📋 Form data keys: {list(request.form.keys())}")
        
        # Get form data
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        phone = request.form.get('phone', '').strip()
        birthday = request.form.get('birthday', '')
        gender = request.form.get('gender', '')
        
        print(f"📝 Form data: first_name={first_name}, last_name={last_name}, phone={phone}, birthday={birthday}, gender={gender}")
        
        # Update full_name
        if first_name or last_name:
            user.full_name = f"{first_name} {last_name}".strip()
        
        # Update other fields
        if phone:
            user.phone = phone
        if birthday:
            try:
                user.birthday = datetime.strptime(birthday, '%Y-%m-%d').date()
            except:
                pass
        if gender:
            user.gender = gender
        
        # Handle avatar update from Cloudinary
        avatar_public_id = request.form.get('avatar_public_id')
        avatar_url = request.form.get('avatar_url')
        
        if avatar_public_id and avatar_url:
            print(f"📸 Avatar Cloudinary data received: public_id={avatar_public_id}")
            
            # Delete old avatar from Cloudinary if exists
            if user.avatar_public_id:
                from app.utils.cloudinary_helper import delete_from_cloudinary
                delete_from_cloudinary(user.avatar_public_id)
                print(f"🗑️ Deleted old avatar: {user.avatar_public_id}")
            
            # Update user with new Cloudinary data
            user.avatar_public_id = avatar_public_id
            user.avatar_url = avatar_url
            # Keep filename for reference (optional)
            user.avatar_filename = f"avatar_{avatar_public_id}.jpg"
        
        user.updated_at = datetime.utcnow()
        db.session.commit()
        print(f"✅ Database updated for user {user.id}")
        
        # Update session
        session['user_name'] = user.full_name
        
        # Generate the avatar URL for response
        user_dict = user.to_dict()
        print(f"✅ Returning user data with avatar_url: {user_dict.get('avatar_url')}")
        print("="*60 + "\n")
        
        return jsonify({
            'success': True,
            'message': 'Profile updated successfully',
            'user': user_dict
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error updating profile: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@templates_bp.route('/api/account/profile', methods=['GET'])
def get_profile():
    """Get user profile data"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        user = User.query.get(session['user_id'])
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({
            'success': True,
            'user': user.to_dict()
        })
        
    except Exception as e:
        print(f"Error fetching profile: {str(e)}")
        return jsonify({'error': 'Server error'}), 500


@templates_bp.route('/api/account/password/change', methods=['POST'])
def change_password():
    """Change user password"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        user = User.query.get(session['user_id'])
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get form data
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate
        if not all([current_password, new_password, confirm_password]):
            return jsonify({'error': 'All fields are required'}), 400
        
        if new_password != confirm_password:
            return jsonify({'error': 'New passwords do not match'}), 400
        
        if len(new_password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        
        # Verify current password
        if not user.check_password(current_password):
            return jsonify({'error': 'Current password is incorrect'}), 400
        
        # Update password
        user.set_password(new_password)
        user.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Password changed successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error changing password: {str(e)}")
        return jsonify({'error': 'Server error'}), 500

@templates_bp.route('/my-account')
def my_account():
    if not session.get('user_id'):
        return redirect(url_for('templates.login'))

#Get the page parameter from URL (default to 'profile')
    page = request.args.get('page', 'profile')

#Get user data from database
    user = User.query.get(session['user_id'])
    if not user:
        return redirect(url_for('templates.logout'))

#Convert to dict for template
    user_data = user.to_dict()

#Get Mapbox token from environment variables
    mapbox_token = os.getenv('MAPBOX_PUBLIC_TOKEN', '')

#DEBUG: Print token to console to verify it's loaded
    print(f"🗺️ Mapbox token loaded for my-account: {mapbox_token[:15] if mapbox_token else 'NOT FOUND'}...")

#IMPORTANT: Render the template, don't return JSON!
    return render_template('my_account.html', 
                         user=user_data, 
                         active_page=page,
                         initial_page=page,
                         mapbox_token=mapbox_token)  # ✅ Add this line



@templates_bp.route('/api/account/<path:path>')
def catch_api_navigation(path):
    """Redirect any accidental navigation to API URLs back to the proper page"""
    print(f"⚠️ Warning: Someone navigated directly to API URL: /api/account/{path}")
    # Extract the page name
    page = path.split('/')[0]
    if page in ['profile', 'orders', 'settings']:
        return redirect(url_for('templates.my_account', page=page))
    return redirect(url_for('templates.my_account'))

@templates_bp.route('/home')
def home():
    """Customer home page (if you want a separate customer portal)"""
    if 'user_id' not in session:
        return redirect(url_for('templates.login'))
    
    if session.get('role') != 'customer':
        return redirect(url_for('templates.dashboard'))
    
    # Get customer-specific data
    customer_orders = Order.query.filter_by(
        customer_id=session['user_id']
    ).order_by(Order.created_at.desc()).limit(5).all()
    
    return render_template('customer_home.html', 
                         orders=[o.to_dict() for o in customer_orders])

@templates_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Find user by email
        user = User.query.filter_by(email=email).first()
        
        # Check if user exists and password is correct
        if user and user.check_password(password):
            # Set session
            session['user_id'] = user.id
            session['user_name'] = user.full_name
            session['role'] = user.role
            session['email'] = user.email
            
            # Check for redirect URL
            next_url = request.args.get('next')
            if next_url:
                return redirect(next_url)
            
            # Redirect based on role
            if user.role == 'admin':
                return redirect(url_for('templates.admin_users'))
            elif user.role == 'seller':
                return redirect(url_for('templates.seller_products'))
            elif user.role == 'rider':
                return redirect(url_for('templates.rider_dashboard'))
            else:  # customer
                return redirect(url_for('templates.index'))
        else:
            return render_template('login.html', error='Invalid email or password')
    
    return render_template('login.html')

@templates_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            full_name = request.form.get('full_name')
            email = request.form.get('email')
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')
            
            # Validation
            if not all([full_name, email, password, confirm_password]):
                return render_template('register.html', 
                                     error='All fields are required',
                                     form_data=request.form)
            
            if password != confirm_password:
                return render_template('register.html', 
                                     error='Passwords do not match',
                                     form_data=request.form)
            
            if len(password) < 6:
                return render_template('register.html', 
                                     error='Password must be at least 6 characters',
                                     form_data=request.form)
            
            # Check if email exists
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                return render_template('register.html',
                                     error='Email already registered',
                                     form_data=request.form)
            
            # Create new user - ALWAYS as customer
            user = User(
                full_name=full_name.strip(),
                email=email.lower().strip(),
                role='customer',  # Always customer by default
                status='active'
            )
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            # Auto-login after registration
            session['user_id'] = user.id
            session['user_name'] = user.full_name
            session['role'] = user.role
            session['email'] = user.email
            
            # Redirect to home page
            return redirect(url_for('templates.index'))
                
        except Exception as e:
            db.session.rollback()
            print(f"Registration error: {str(e)}")
            return render_template('register.html', 
                                 error=f'Registration failed: {str(e)}',
                                 form_data=request.form)
    
    return render_template('register.html')


@templates_bp.route('/api/account/orders/data')
def orders_data():
    """Return JSON data for orders"""
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session.get('user_id')

    orders = (
        Order.query
        .options(
            joinedload(Order.store),
            joinedload(Order.items).joinedload(OrderItem.product).joinedload(Product.images),
            joinedload(Order.items).joinedload(OrderItem.variant)
        )
        .filter_by(customer_id=user_id)
        .order_by(Order.created_at.desc())
        .all()
    )

    orders_payload = []
    for order in orders:
        order_dict = _serialize_customer_order(order)
        order_dict['date'] = order_dict['created_at']
        orders_payload.append(order_dict)

    return jsonify(orders_payload)

@templates_bp.route('/api/account/orders/<int:order_id>')
def order_details(order_id):
    """Return specific order details"""
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session.get('user_id')
    order = (
        Order.query
        .options(
            joinedload(Order.store),
            joinedload(Order.items).joinedload(OrderItem.product).joinedload(Product.images),
            joinedload(Order.items).joinedload(OrderItem.variant)
        )
        .filter_by(id=order_id, customer_id=user_id)
        .first()
    )

    if not order:
        return jsonify({'error': 'Order not found'}), 404

    order_dict = _serialize_customer_order(order)
    order_dict['date'] = order_dict['created_at']
    return jsonify(order_dict)

@templates_bp.route('/api/account/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    """Cancel an order"""
    if not session.get('user_id'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    user_id = session.get('user_id')
    order = Order.query.filter_by(id=order_id, customer_id=user_id).first()

    if not order:
        return jsonify({'success': False, 'message': 'Order not found'}), 404

    cancellable_statuses = {'pending'}
    if order.status not in cancellable_statuses:
        return jsonify({
            'success': False,
            'message': 'Only pending orders can be cancelled.'
        }), 400

    order.status = 'cancelled'
    order.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'success': True, 'message': 'Order cancelled successfully'})

@templates_bp.route('/orders')
def orders():
    """Display user's orders"""
    if not session.get('user_id'):
        return redirect(url_for('templates.login'))
    
    user_id = session.get('user_id')
    page = request.args.get('page', 1, type=int)
    per_page = 10
    status = request.args.get('status', '')
    
    # Build query
    query = Order.query.filter_by(customer_id=user_id)
    
    if status:
        query = query.filter_by(status=status)
    
    # Get paginated orders
    orders_paginated = query.order_by(Order.created_at.desc()).paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    # Process orders with items
    orders_data = []
    for order in orders_paginated.items:
        order_dict = order.to_dict()
        
        # Get order items
        items = OrderItem.query.filter_by(order_id=order.id).all()
        order_dict['items'] = [item.to_dict() for item in items]
        
        # Get store name
        store = Store.query.get(order.store_id)
        if store:
            order_dict['store_name'] = store.name
            order_dict['store_contact'] = store.contact_number
        
        # Get rider info if assigned
        if order.rider_id:
            rider = Rider.query.get(order.rider_id)
            if rider and rider.user:
                order_dict['rider_name'] = rider.user.full_name
                order_dict['rider_vehicle'] = rider.vehicle_type
        
        orders_data.append(order_dict)
    
    # Calculate order statistics
    total_orders = Order.query.filter_by(customer_id=user_id).count()
    pending_orders = Order.query.filter_by(customer_id=user_id, status='pending').count()
    delivery_orders = Order.query.filter_by(customer_id=user_id, status='on_delivery').count()
    delivered_orders = Order.query.filter_by(customer_id=user_id, status='delivered').count()
    
    return render_template('orders.html',
                         orders=orders_data,
                         total_orders=total_orders,
                         pending_orders=pending_orders,
                         delivery_orders=delivery_orders,
                         delivered_orders=delivered_orders,
                         page=page,
                         total_pages=orders_paginated.pages,
                         status=status)


@templates_bp.route('/category/<path:category_identifier>')
def category(category_identifier):
    """Category page showing all products in a main category"""
    try:
        from app.models import Category
        
        # Try to find by ID first (if it's a number)
        category = None
        if category_identifier.isdigit():
            category = Category.query.get(int(category_identifier))
        
        # If not found by ID or not a number, try by slug
        if not category:
            category = Category.query.filter_by(slug=category_identifier, is_active=True).first()
        
        if not category:
            flash('Category not found', 'error')
            return redirect(url_for('templates.index'))
        
        # Get all products in this main category
        products = Product.query.filter_by(
            main_category_id=category.id,
            is_available=True,
            is_archived=False
        ).join(Store).filter(Store.status == 'active').all()
        
        # Convert products to dict and add store_name
        product_list = []
        for product in products:
            product_dict = product.to_dict()
            product_dict['store_name'] = product.store.name if product.store else 'Unknown Store'
            
            if product.main_category:
                product_dict['main_category'] = {
                    'id': product.main_category.id,
                    'name': product.main_category.name,
                    'slug': product.main_category.slug
                }
            
            if product.store_category:
                product_dict['store_category'] = {
                    'id': product.store_category.id,
                    'name': product.store_category.name,
                    'slug': product.store_category.slug
                }
            
            product_list.append(product_dict)
        
        return render_template('category.html',
                             category=category,
                             products=product_list,
                             category_identifier=category_identifier)
        
    except Exception as e:
        print(f"❌ Error loading category {category_identifier}: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Error loading category', 'error')
        return redirect(url_for('templates.index'))


@templates_bp.route('/contact')
def contact():
    """Contact page"""
    return render_template('contact.html')

@templates_bp.route('/faq')
def faq():
    """FAQ page"""
    return render_template('faq.html')

@templates_bp.route('/shipping')
def shipping():
    """Shipping policy page"""
    return render_template('shipping.html')

@templates_bp.route('/returns')
def returns():
    """Returns policy page"""
    return render_template('returns.html')

@templates_bp.route('/search')
def search():
    query = request.args.get('q', '')
    products = []
    if query:
        raw = Product.query\
            .join(Store, Product.store_id == Store.id)\
            .filter(
                Product.name.ilike(f'%{query}%'),
                Product.is_available == True,
                Product.is_archived == False,
                Store.status == 'active'
            ).all()
        for p in raw:
            pd = p.to_dict()
            pd['store_name'] = p.store.name if p.store else 'Flower Shop'
            products.append(pd)

    return render_template('search.html', query=query, products=products)


@templates_bp.route('/categories')
def categories():
    """All categories page"""
    # Define your categories
    categories_list = [
        {'id': 'flowers', 'name': 'Fresh Flowers', 'icon': 'flower-line', 'count': 42},
        {'id': 'plants', 'name': 'Potted Plants', 'icon': 'plant-line', 'count': 28},
        {'id': 'bouquets', 'name': 'Bouquets', 'icon': 'bouquet-line', 'count': 35},
        {'id': 'succulents', 'name': 'Succulents', 'icon': 'cactus-line', 'count': 19},
    ]
    
    return render_template('categories.html', categories=categories_list)


@templates_bp.route('/products')
def products():
    """All products page for web interface"""
    try:
        products = Product.query.filter_by(is_available=True).all()
        return render_template('products.html', 
                             products=[p.to_dict() for p in products])
    except Exception as e:
        print(f"Error loading products: {str(e)}")
        return render_template('products.html', products=[])
    
@templates_bp.route('/product/<int:product_id>')
def product_detail(product_id):
    """Product detail page with category support"""
    try:
        product = Product.query.get_or_404(product_id)
        store = Store.query.get(product.store_id)
        
        # Get all main categories for the navigation
        from app.models import Category
        main_categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()
        
        # Get related products - same main category
        related_products = Product.query.filter(
            Product.main_category_id == product.main_category_id,
            Product.store_id == product.store_id,
            Product.id != product_id,
            Product.is_available == True,
            Product.is_archived == False,
            Product.stock_quantity > 0
        ).limit(4).all()
        
        # Get add-on products - different main category but same store
        addon_products = []
        if product.main_category_id:
            addon_products = Product.query.filter(
                Product.store_id == product.store_id,
                Product.main_category_id != product.main_category_id,
                Product.id != product_id,
                Product.is_available == True,
                Product.is_archived == False,
                Product.stock_quantity > 0
            ).limit(8).all()
        
        # Convert products to dict format
        product_dict = product.to_dict()
        store_dict = store.to_dict() if store else None
        
        # Add main_category and store_category info to product_dict for template
        if product.main_category:
            product_dict['main_category'] = {
                'id': product.main_category.id,
                'name': product.main_category.name,
                'slug': product.main_category.slug
            }
        
        if product.store_category:
            product_dict['store_category'] = {
                'id': product.store_category.id,
                'name': product.store_category.name,
                'slug': product.store_category.slug
            }
        
        # Debug print
        print(f"\n🔍 PRODUCT DETAIL - ID: {product_id}")
        print(f"  Name: {product.name}")
        print(f"  Main Category: {product.main_category.name if product.main_category else 'None'}")
        print(f"  Store Category: {product.store_category.name if product.store_category else 'None'}")
        print(f"  Categories for nav: {len(main_categories)}")
        print(f"  Related products: {len(related_products)}")
        print(f"  Add-on products: {len(addon_products)}")
        
        return render_template(
            'product_detail.html',
            product=product_dict,
            store=store_dict,
            main_categories=main_categories,  # Pass to base.html for navigation
            related_products=[p.to_dict() for p in related_products],
            addon_products=[p.to_dict() for p in addon_products]
        )
        
    except Exception as e:
        print(f"❌ Error loading product {product_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Product not found', 'error')
        return redirect(url_for('templates.products'))
    
@templates_bp.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('templates.login'))
    return render_template('dashboard.html')

@templates_bp.route('/admin/users')
def admin_users():
    if session.get('role') != 'admin':
        return redirect(url_for('templates.dashboard'))
    return render_template('admin_users.html')

@templates_bp.route('/api/v1/admin/seller-applications')
def get_seller_applications():
    """Get all seller applications with user details"""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    applications = SellerApplication.query.order_by(SellerApplication.submitted_at.desc()).all()
    
    result = []
    for app in applications:
        app_dict = app.to_dict()
        # Add user details
        user = User.query.get(app.user_id)
        if user:
            app_dict['full_name'] = user.full_name
            app_dict['email'] = user.email
            app_dict['phone'] = user.phone
        result.append(app_dict)
    
    return jsonify({'applications': result})



@templates_bp.route('/api/v1/admin/seller-applications/<int:app_id>/approve', methods=['POST'])
def approve_seller_application(app_id):
    """Approve a seller application and convert user to seller"""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        application = SellerApplication.query.get_or_404(app_id)
        user = User.query.get(application.user_id)

        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Update application status
        application.status = 'approved'
        application.reviewed_at = datetime.utcnow()
        application.reviewed_by = session['user_id']

        # Convert user role to seller
        user.role = 'seller'

        # ── KEY FIX: Check if seller already has a store (re-approval case) ──
        existing_store = Store.query.filter_by(seller_id=user.id).first()

        if existing_store:
            # Reactivate the existing store — keeps all products intact
            existing_store.status = 'active'
            existing_store.name = application.store_name
            existing_store.description = application.store_description
            print(f"♻️ Reactivated existing store ID {existing_store.id} for user {user.id}")
        else:
            # First-time approval — create a new store
            store = Store(
                seller_id=user.id,
                name=application.store_name,
                description=application.store_description,
                address='Address pending - please update',
                status='active'
            )
            db.session.add(store)
            print(f"🆕 Created new store for user {user.id}")

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Application approved and seller account activated'
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error approving application: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/v1/admin/seller-applications/<int:app_id>/reject', methods=['POST'])
def reject_seller_application(app_id):
    """Reject a seller application — deactivates store but preserves products"""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json()
        application = SellerApplication.query.get_or_404(app_id)

        application.status = 'rejected'
        application.admin_notes = data.get('admin_notes', '')
        application.reviewed_at = datetime.utcnow()
        application.reviewed_by = session['user_id']

        # ── KEY FIX: Deactivate store instead of ignoring it ──
        # This hides their products from public without deleting anything
        user = User.query.get(application.user_id)
        if user:
            user.role = 'customer'  # Revoke seller role
            existing_store = Store.query.filter_by(seller_id=user.id).first()
            if existing_store:
                existing_store.status = 'inactive'
                print(f"🔒 Deactivated store ID {existing_store.id} for rejected user {user.id}")

        db.session.commit()

        return jsonify({'success': True, 'message': 'Application rejected'})

    except Exception as e:
        db.session.rollback()
        print(f"Error rejecting application: {str(e)}")
        return jsonify({'error': str(e)}), 500

@templates_bp.route('/admin/stores')
def admin_stores():
    if session.get('role') != 'admin':
        return redirect(url_for('templates.dashboard'))
    return render_template('admin_stores.html')

@templates_bp.route('/admin/orders')
def admin_orders():
    if session.get('role') != 'admin':
        return redirect(url_for('templates.dashboard'))
    return render_template('admin_orders.html')

@templates_bp.route('/seller/products')
def seller_products():
    if session.get('role') != 'seller':
        return redirect(url_for('templates.dashboard'))
    
    # Get seller's store
    store = Store.query.filter_by(seller_id=session.get('user_id')).first()
    if not store:
        return render_template('products.html', products=[])
    
    # Get ONLY NON-ARCHIVED products for this store
    products = Product.query.filter_by(
        store_id=store.id,
        is_archived=False  # ← ADD THIS LINE
    ).order_by(Product.created_at.desc()).all()
    
    # FIX: Convert products to dict for template
    product_list = [product.to_dict() for product in products]
    
    return render_template('products.html', products=product_list)

def generate_short_filename(original_filename, product_id, index):
    """Generate a short, safe filename for images"""
    # Get file extension
    if '.' in original_filename:
        ext = original_filename.rsplit('.', 1)[1].lower()
    else:
        ext = 'jpg'  # default
    
    # Create a short unique name using timestamp + random string
    # Format: p{product_id}_{index}_{random}.{ext}
    # Example: p123_0_a1b2c3d4.jpg
    
    # Use last 6 digits of timestamp
    timestamp = str(int(time.time()))[-6:]
    # Use first 8 chars of random UUID
    random_str = uuid.uuid4().hex[:8]
    
    # Short filename: max length around 25-30 chars
    short_filename = f"p{product_id}_{index}_{timestamp}_{random_str}.{ext}"
    
    return short_filename


@templates_bp.route('/seller/products/create', methods=['POST'])
@seller_required
def create_product():
    """Create a new product with Cloudinary images (no local storage)"""
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        # Get seller's store
        store = Store.query.filter_by(seller_id=session.get('user_id')).first()
        if not store:
            return jsonify({'error': 'Store not found. Please create a store first.'}), 404
        
        print("\n" + "="*60)
        print("📝 CREATE PRODUCT REQUEST (Cloudinary Only)")
        print(f"Form keys: {list(request.form.keys())}")
        
        # Import Cloudinary helper
        from app.utils.cloudinary_helper import should_use_cloudinary
        use_cloudinary = should_use_cloudinary()
        
        if not use_cloudinary:
            return jsonify({'error': 'Cloudinary is not configured. Please check your environment variables.'}), 500
        
        # Get form data
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price')
        stock_quantity = request.form.get('stock_quantity')
        
        # ===== UPDATED: Get category fields =====
        main_category_id = request.form.get('main_category_id')
        store_category_id = request.form.get('store_category_id')
        
        is_available = request.form.get('is_available', 'false').lower() == 'true'
        has_variants = request.form.get('has_variants', 'false').lower() == 'true'
        
        print(f"📦 Product data: name={name}, main_category_id={main_category_id}, store_category_id={store_category_id}, has_variants={has_variants}")
        
        # Validate required fields
        if not name or not name.strip():
            return jsonify({'error': 'Product name is required'}), 400
        if not price:
            return jsonify({'error': 'Price is required'}), 400
        if not stock_quantity:
            return jsonify({'error': 'Stock quantity is required'}), 400
        if not main_category_id:
            return jsonify({'error': 'Main category is required'}), 400
        
        # Convert price and stock quantity
        try:
            price_float = float(price)
            if price_float <= 0:
                return jsonify({'error': 'Price must be greater than 0'}), 400
        except ValueError:
            return jsonify({'error': 'Invalid price format'}), 400
        
        try:
            stock_int = int(stock_quantity)
            if stock_int < 0:
                return jsonify({'error': 'Stock quantity cannot be negative'}), 400
        except ValueError:
            return jsonify({'error': 'Invalid stock quantity format'}), 400
        
        # Validate main_category_id exists
        from app.models import Category
        main_category = Category.query.get(main_category_id)
        if not main_category:
            return jsonify({'error': 'Invalid main category'}), 400
        
        # Validate store_category_id if provided
        if store_category_id:
            from app.models import StoreCategory
            store_category = StoreCategory.query.filter_by(
                id=store_category_id,
                store_id=store.id,
                main_category_id=main_category_id
            ).first()
            if not store_category:
                return jsonify({'error': 'Invalid store subcategory'}), 400
        
        # Create new product with category fields
        product = Product(
            store_id=store.id,
            name=name.strip(),
            description=description.strip() if description else None,
            price=price_float,
            stock_quantity=stock_int,
            main_category_id=int(main_category_id),
            store_category_id=int(store_category_id) if store_category_id else None,
            is_available=is_available
        )
        
        db.session.add(product)
        db.session.flush()  # Get product ID
        
        print(f"✅ Product created with ID: {product.id}")
        
        # ===== HANDLE CLOUDINARY IMAGES (ONLY) =====
        cloudinary_images_json = request.form.get('cloudinary_images')
        image_count = 0
        
        if not cloudinary_images_json:
            db.session.rollback()
            return jsonify({'error': 'No images provided. Please upload at least one product image.'}), 400
        
        try:
            cloudinary_images = json.loads(cloudinary_images_json)
            print(f"📸 Received {len(cloudinary_images)} Cloudinary images")
            
            if len(cloudinary_images) == 0:
                db.session.rollback()
                return jsonify({'error': 'At least one product image is required'}), 400
            
            for img_data in cloudinary_images:
                product_image = ProductImage(
                    product_id=product.id,
                    filename=f"cloudinary_{img_data['public_id']}.jpg",
                    public_id=img_data['public_id'],
                    cloudinary_url=img_data['url'],
                    is_primary=img_data.get('is_primary', False),
                    sort_order=img_data.get('sort_order', image_count)
                )
                db.session.add(product_image)
                image_count += 1
                print(f"  ✅ Added Cloudinary image: {img_data['public_id']}")
                
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing cloudinary_images: {e}")
            db.session.rollback()
            return jsonify({'error': 'Invalid image data format'}), 400
        
        # ===== HANDLE VARIANTS =====
        if has_variants:
            variants_json = request.form.get('variants')
            if variants_json:
                try:
                    variants_data = json.loads(variants_json)
                    print(f"🎯 Processing {len(variants_data)} variants")
                    
                    for idx, variant_data in enumerate(variants_data):
                        if variant_data.get('_delete'):
                            continue
                        
                        print(f"  Variant {idx}: {variant_data.get('name')}")
                        
                        variant = ProductVariant(
                            product_id=product.id,
                            name=variant_data.get('name'),
                            price=Decimal(str(variant_data.get('price'))),
                            stock_quantity=int(variant_data.get('stock_quantity', 0)),
                            sku=variant_data.get('sku'),
                            attributes=variant_data.get('attributes'),
                            sort_order=idx,
                            is_available=True
                        )
                        
                        # Handle Cloudinary variant image
                        if variant_data.get('cloudinary_public_id'):
                            variant.image_public_id = variant_data['cloudinary_public_id']
                            variant.image_url = variant_data['cloudinary_url']
                            variant.image_filename = f"variant_{variant_data['cloudinary_public_id']}.jpg"
                            print(f"    📸 Variant with Cloudinary image: {variant_data['cloudinary_public_id']}")
                        
                        db.session.add(variant)
                    
                except json.JSONDecodeError as e:
                    print(f"❌ JSON decode error: {e}")
                    db.session.rollback()
                    return jsonify({'error': 'Invalid variants data'}), 400
                except Exception as e:
                    print(f"❌ Error processing variants: {e}")
                    db.session.rollback()
                    return jsonify({'error': f'Error processing variants: {str(e)}'}), 400
        
        db.session.commit()
        print(f"✅ Product {product.id} created successfully with {image_count} Cloudinary images")
        print("="*60 + "\n")
        
        return jsonify({
            'success': True,
            'message': 'Product created successfully',
            'product': product.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error creating product: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 500
    


@templates_bp.route('/seller/products/<int:product_id>', methods=['GET', 'PUT', 'DELETE'])
@seller_required
def manage_product(product_id):
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        store = Store.query.filter_by(seller_id=session.get('user_id')).first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404

        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            return jsonify({'error': 'Product not found'}), 404

        # ── GET ───────────────────────────────────────────────────────────────
        if request.method == 'GET':
            print(f"\n📖 GET Product {product_id}")
            product_dict = product.to_dict()
            print(f"✅ Returning product with {len(product_dict.get('variants', []))} variants")
            return jsonify({'success': True, 'product': product_dict})

       # ── PUT (UPDATE) ──────────────────────────────────────────────────────
        elif request.method == 'PUT':
            print("\n" + "="*60)
            print(f"📝 UPDATE PRODUCT {product_id} (Cloudinary Only)")
            print(f"Form keys: {list(request.form.keys())}")

            # Import Cloudinary helper
            from app.utils.cloudinary_helper import should_use_cloudinary, delete_from_cloudinary
            use_cloudinary = should_use_cloudinary()
            
            if not use_cloudinary:
                return jsonify({'error': 'Cloudinary is not configured. Please check your environment variables.'}), 500

            # Update basic fields
            if 'name' in request.form:
                product.name = request.form['name'].strip()
            if 'description' in request.form:
                product.description = request.form['description'].strip() or None
            if 'price' in request.form:
                try:
                    product.price = float(request.form['price'])
                except ValueError:
                    return jsonify({'error': 'Invalid price format'}), 400
            if 'stock_quantity' in request.form:
                try:
                    product.stock_quantity = int(request.form['stock_quantity'])
                except ValueError:
                    return jsonify({'error': 'Invalid stock quantity format'}), 400
            
            # ===== UPDATED: Handle category fields =====
            if 'main_category_id' in request.form:
                main_category_id = request.form['main_category_id']
                if main_category_id:
                    from app.models import Category
                    main_category = Category.query.get(main_category_id)
                    if not main_category:
                        return jsonify({'error': 'Invalid main category'}), 400
                    product.main_category_id = int(main_category_id)
            
            if 'store_category_id' in request.form:
                store_category_id = request.form['store_category_id']
                if store_category_id:
                    from app.models import StoreCategory
                    store_category = StoreCategory.query.filter_by(
                        id=store_category_id,
                        store_id=store.id,
                        main_category_id=product.main_category_id
                    ).first()
                    if not store_category:
                        return jsonify({'error': 'Invalid store subcategory'}), 400
                    product.store_category_id = int(store_category_id)
                else:
                    product.store_category_id = None
            
            if 'is_available' in request.form:
                is_avail_str = request.form['is_available']
                product.is_available = is_avail_str.lower() in ['true', '1', 'yes']

            # ===== HANDLE PRODUCT IMAGES (CLOUDINARY ONLY) =====
            
            # Get images to keep/delete
            images_to_keep = []
            images_to_delete = []
            
            if 'images_to_keep' in request.form:
                try:
                    images_to_keep = json.loads(request.form['images_to_keep'])
                    print(f"📌 Images to keep: {images_to_keep}")
                except:
                    pass
            
            if 'images_to_delete' in request.form:
                try:
                    images_to_delete = json.loads(request.form['images_to_delete'])
                    print(f"🗑️ Images to delete: {images_to_delete}")
                except:
                    pass

            # Delete marked images from Cloudinary and database
            for img_id in images_to_delete:
                img = ProductImage.query.filter_by(id=img_id, product_id=product.id).first()
                if img:
                    if img.public_id:
                        delete_from_cloudinary(img.public_id)
                        print(f"  🗑️ Deleted from Cloudinary: {img.public_id}")
                    
                    db.session.delete(img)
                    print(f"  🗑️ Deleted image record {img_id}")

            # Handle new Cloudinary images
            cloudinary_images_json = request.form.get('cloudinary_images')
            if cloudinary_images_json:
                try:
                    cloudinary_images = json.loads(cloudinary_images_json)
                    print(f"📸 Received {len(cloudinary_images)} new Cloudinary images")
                    
                    for img_data in cloudinary_images:
                        product_image = ProductImage(
                            product_id=product.id,
                            filename=f"cloudinary_{img_data['public_id']}.jpg",
                            public_id=img_data['public_id'],
                            cloudinary_url=img_data['url'],
                            is_primary=img_data.get('is_primary', False),
                            sort_order=img_data.get('sort_order', 0)
                        )
                        db.session.add(product_image)
                        print(f"  ✅ Added new Cloudinary image: {img_data['public_id']}")
                            
                except json.JSONDecodeError as e:
                    print(f"❌ Error parsing cloudinary_images: {e}")

            # Handle replacement images
            replacement_images_json = request.form.get('replacement_images')
            if replacement_images_json:
                try:
                    replacement_images = json.loads(replacement_images_json)
                    print(f"🔄 Received {len(replacement_images)} replacement images")
                    
                    for img_data in replacement_images:
                        existing_id = img_data.get('existing_id')
                        if not existing_id:
                            print(f"  ❌ No existing_id in replacement data: {img_data}")
                            continue
                            
                        old_image = ProductImage.query.filter_by(
                            id=existing_id, 
                            product_id=product.id
                        ).first()
                        
                        if old_image:
                            print(f"  Replacing image ID {old_image.id} (public_id: {old_image.public_id})")
                            
                            if old_image.public_id:
                                if delete_from_cloudinary(old_image.public_id):
                                    print(f"    🗑️ Deleted old Cloudinary image: {old_image.public_id}")
                                else:
                                    print(f"    ⚠️ Failed to delete old Cloudinary image: {old_image.public_id}")
                            
                            old_image.public_id = img_data['public_id']
                            old_image.cloudinary_url = img_data['url']
                            old_image.filename = f"cloudinary_{img_data['public_id']}.jpg"
                            old_image.is_primary = img_data.get('is_primary', old_image.is_primary)
                            old_image.sort_order = img_data.get('sort_order', old_image.sort_order)
                            old_image.updated_at = datetime.utcnow()
                            
                            print(f"    ✅ Updated existing image record {old_image.id} with new Cloudinary image: {img_data['public_id']}")
                        else:
                            print(f"    ❌ Could not find existing image with ID: {existing_id}")
                            
                except json.JSONDecodeError as e:
                    print(f"❌ Error parsing replacement_images: {e}")
                except Exception as e:
                    print(f"❌ Error processing replacement images: {e}")

            # ===== HANDLE VARIANTS UPDATE =====
            has_variants = request.form.get('has_variants', 'false').lower() == 'true'
            print(f"🎯 Has variants: {has_variants}")

            if has_variants:
                variants_json = request.form.get('variants')
                if variants_json:
                    try:
                        variants_data = json.loads(variants_json)
                        print(f"📦 Variants data received: {len(variants_data)} variants")

                        kept_variant_ids = []

                        for idx, variant_data in enumerate(variants_data):
                            variant_id = variant_data.get('id')
                            
                            print(f"\n  Variant {idx}:")
                            print(f"    ID: {variant_id}")
                            print(f"    Name: {variant_data.get('name')}")
                            print(f"    Delete: {variant_data.get('_delete')}")
                            print(f"    Remove image: {variant_data.get('_remove_image')}")

                            # Handle deletion
                            if variant_data.get('_delete') and variant_id:
                                variant = ProductVariant.query.filter_by(
                                    id=variant_id, 
                                    product_id=product.id
                                ).first()
                                
                                if variant:
                                    if variant.image_public_id:
                                        delete_from_cloudinary(variant.image_public_id)
                                        print(f"      🗑️ Deleted variant image from Cloudinary")
                                    
                                    db.session.delete(variant)
                                    print(f"    ✅ Deleted variant {variant_id}")
                                continue

                            # Update existing or create new variant
                            if variant_id:
                                # Update existing
                                variant = ProductVariant.query.filter_by(
                                    id=variant_id, 
                                    product_id=product.id
                                ).first()
                                
                                if variant:
                                    variant.name = variant_data.get('name')
                                    variant.price = Decimal(str(variant_data.get('price')))
                                    variant.stock_quantity = int(variant_data.get('stock_quantity', 0))
                                    variant.sku = variant_data.get('sku')
                                    variant.attributes = variant_data.get('attributes')
                                    variant.sort_order = idx
                                    variant.updated_at = datetime.utcnow()
                                    
                                    print(f"    ✅ Updated existing variant {variant_id}")
                                    
                                    # Handle variant image removal
                                    if variant_data.get('_remove_image'):
                                        if variant.image_public_id:
                                            delete_from_cloudinary(variant.image_public_id)
                                            print(f"      🗑️ Removed variant image from Cloudinary")
                                        
                                        variant.image_public_id = None
                                        variant.image_url = None
                                        variant.image_filename = None
                                    
                                    # Handle new Cloudinary image
                                    if variant_data.get('cloudinary_public_id'):
                                        if variant.image_public_id:
                                            delete_from_cloudinary(variant.image_public_id)
                                        
                                        variant.image_public_id = variant_data['cloudinary_public_id']
                                        variant.image_url = variant_data['cloudinary_url']
                                        variant.image_filename = f"variant_{variant_data['cloudinary_public_id']}.jpg"
                                        print(f"      📸 Updated variant with Cloudinary image")
                                    
                                    kept_variant_ids.append(variant_id)
                            else:
                                # Create new variant
                                variant = ProductVariant(
                                    product_id=product.id,
                                    name=variant_data.get('name'),
                                    price=Decimal(str(variant_data.get('price'))),
                                    stock_quantity=int(variant_data.get('stock_quantity', 0)),
                                    sku=variant_data.get('sku'),
                                    attributes=variant_data.get('attributes'),
                                    sort_order=idx,
                                    is_available=True
                                )
                                
                                if variant_data.get('cloudinary_public_id'):
                                    variant.image_public_id = variant_data['cloudinary_public_id']
                                    variant.image_url = variant_data['cloudinary_url']
                                    variant.image_filename = f"variant_{variant_data['cloudinary_public_id']}.jpg"
                                    print(f"      📸 New variant with Cloudinary image")
                                
                                db.session.add(variant)
                                db.session.flush()
                                kept_variant_ids.append(variant.id)
                                print(f"    ✅ Created new variant {variant.id}")

                        # Delete variants that were not included in the update
                        existing_variants = ProductVariant.query.filter_by(
                            product_id=product.id
                        ).all()
                        
                        for existing_variant in existing_variants:
                            if existing_variant.id not in kept_variant_ids:
                                if existing_variant.image_public_id:
                                    delete_from_cloudinary(existing_variant.image_public_id)
                                    print(f"      🗑️ Deleted orphaned variant image from Cloudinary")
                                
                                db.session.delete(existing_variant)
                                print(f"    🗑️ Removed orphaned variant {existing_variant.id}")

                    except json.JSONDecodeError as e:
                        print(f"❌ JSON decode error: {e}")
                        db.session.rollback()
                        return jsonify({'error': 'Invalid variants data'}), 400
            else:
                # If has_variants is false, delete all variants
                print("🗑️ Deleting all variants (has_variants=false)")
                
                for variant in product.variants:
                    if variant.image_public_id:
                        delete_from_cloudinary(variant.image_public_id)
                        print(f"  🗑️ Deleted variant image from Cloudinary")
                    db.session.delete(variant)

            product.updated_at = datetime.utcnow()
            db.session.commit()
            
            print(f"✅ Product {product_id} updated successfully with Cloudinary")
            print("="*60 + "\n")
            
            return jsonify({
                'success': True,
                'message': 'Product updated successfully',
                'product': product.to_dict()
            })

        # ── DELETE ────────────────────────────────────────────────────────────
        elif request.method == 'DELETE':
            print("\n" + "="*60)
            print(f"🗑️ DELETE PRODUCT {product_id}")

            if product.is_archived:
                return jsonify({
                    'success': True,
                    'archived': True,
                    'message': 'Product is already in archive'
                }), 200

            try:
                product.archive(session['user_id'])
                db.session.commit()

                print(f"📦 Product {product_id} archived instead of permanently deleting")
                print("="*60 + "\n")

                return jsonify({
                    'success': True,
                    'archived': True,
                    'message': 'Product moved to archive successfully',
                    'product': product.to_dict()
                }), 200

            except Exception as e:
                db.session.rollback()
                print(f"❌ Error archiving product: {str(e)}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'Failed to archive product: {str(e)}'}), 500

        return jsonify({'error': 'Method not allowed'}), 405

    except Exception as e:
        db.session.rollback()
        print(f"❌ Exception in manage_product: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500



@templates_bp.route('/seller/products/<int:product_id>/availability', methods=['PUT'])
def update_product_availability(product_id):
    """Update just the availability status of a product"""
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        # Get seller's store
        store = Store.query.filter_by(seller_id=session.get('user_id')).first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        data = request.get_json()
        if data is None:
            return jsonify({'error': 'Invalid JSON data'}), 400
            
        is_available = data.get('is_available')
        if is_available is None:
            return jsonify({'error': 'is_available field is required'}), 400
        
        product.is_available = bool(is_available)
        product.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Product {"available" if is_available else "unavailable"}',
            'product': product.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating availability: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500




# ═════════════════════════════════════════════════════════════════════════════
# STOCK REDUCTION AUDIT ENDPOINTS
# ═════════════════════════════════════════════════════════════════════════════

@templates_bp.route('/seller/products/<int:product_id>/reduce-stock', methods=['POST'])
def reduce_product_stock(product_id):
    """
    Record stock reduction with audit trail.
    Handles both main products and variants.
    
    Expected JSON payload:
    {
        "amount": 5,
        "reason": "damage",  # spoilage, damage, defect, other
        "reason_notes": "Damaged during shipping",
        "variant_id": 123  # Optional, only for variants
    }
    """
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = session.get('user_id')
    
    try:
        # Get seller's store
        store = Store.query.filter_by(seller_id=user_id, status='active').first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        # Parse request data
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400
        
        # Validate inputs
        amount = data.get('amount')
        reason = data.get('reason')
        reason_notes = data.get('reason_notes', '')
        variant_id = data.get('variant_id')  # Get variant_id if provided
        
        if not amount:
            return jsonify({'error': 'Reduction amount is required'}), 400
        
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            return jsonify({'error': 'Invalid reduction amount - must be integer'}), 400
        
        if not reason:
            return jsonify({'error': 'Reason for reduction is required'}), 400
        
        if reason not in StockReduction.REASONS:
            return jsonify({
                'error': f'Invalid reason. Must be one of: {", ".join(StockReduction.REASONS)}'
            }), 400
        
        # Find the product first
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        # Handle variant reduction if variant_id is provided
        variant = None
        if variant_id:
            variant = ProductVariant.query.filter_by(id=variant_id, product_id=product.id).first()
            if not variant:
                return jsonify({'error': 'Variant not found'}), 404
            
            # Validate stock
            if amount > variant.stock_quantity:
                return jsonify({'error': f'Cannot reduce by {amount}. Available: {variant.stock_quantity}'}), 400
            
            # Reduce variant stock
            variant.stock_quantity -= amount
            variant.updated_at = datetime.utcnow()
            
            # Create audit entry
            reduction = StockReduction(
                product_id=product.id,
                variant_id=variant.id,
                reduction_amount=amount,
                reason=reason,
                reason_notes=reason_notes,
                reduced_by=user_id
            )
            db.session.add(reduction)
            
            print(f"✅ Variant stock reduction recorded:")
            print(f"   Product: {product.name} (ID: {product.id})")
            print(f"   Variant: {variant.name} (ID: {variant.id})")
            print(f"   Reduced by: {amount} units")
            print(f"   Reason: {reason}")
            print(f"   New variant stock: {variant.stock_quantity}")
            
            # Update product's updated_at timestamp
            product.updated_at = datetime.utcnow()
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Stock reduced by {amount} units for variant {variant.name}',
                'reduction': reduction.to_dict(),
                'product': product.to_dict(),
                'variant': variant.to_dict()
            }), 200
            
        else:
            # Reduce main product stock
            reduction = product.reduce_stock(amount, reason, user_id, reason_notes)
            db.session.commit()
            
            print(f"✅ Main product stock reduction recorded:")
            print(f"   Product: {product.name} (ID: {product.id})")
            print(f"   Reduced by: {amount} units")
            print(f"   Reason: {reason}")
            print(f"   New stock: {product.stock_quantity}")
            
            return jsonify({
                'success': True,
                'message': f'Stock reduced by {amount} units',
                'reduction': reduction.to_dict(),
                'product': product.to_dict()
            }), 200
        
    except ValueError as e:
        db.session.rollback()
        print(f"❌ Validation error: {str(e)}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error reducing stock: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 500
@templates_bp.route('/seller/products/<int:product_id>/stock-history', methods=['GET'])
def get_stock_history(product_id):
    """
    Get audit log of all stock reductions for a product or variant
    """
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = session.get('user_id')
    
    try:
        # Get seller's store
        store = Store.query.filter_by(seller_id=user_id, status='active').first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        # Try to find as a Product first
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        
        # If not found as product, try as variant
        variant = None
        if not product:
            variant = ProductVariant.query.filter_by(id=product_id).first()
            if variant:
                # Get the product this variant belongs to
                product = variant.product
                # Verify the product belongs to this seller's store
                if not product or product.store_id != store.id:
                    return jsonify({'error': 'Product not found'}), 404
            else:
                return jsonify({'error': 'Product not found'}), 404
        
        # Get reductions for main product (where variant_id is NULL)
        main_reductions = StockReduction.query.filter_by(
            product_id=product.id, 
            variant_id=None  # Only main product reductions
        ).order_by(StockReduction.created_at.desc()).all()
        
        # Get reductions for variants (where variant_id is NOT NULL)
        variant_reductions = StockReduction.query.filter(
            StockReduction.product_id == product.id,
            StockReduction.variant_id != None  # Only variant reductions
        ).order_by(StockReduction.created_at.desc()).all()
        
        # Calculate totals for main product
        main_total_reduced = sum(r.reduction_amount for r in main_reductions)
        
        # Calculate totals for variants
        variant_total_reduced = sum(r.reduction_amount for r in variant_reductions)
        
        # Get primary image for main product
        primary_image = None
        if product.images:
            primary_image_obj = next((img for img in product.images if img.is_primary), None)
            if not primary_image_obj:
                primary_image_obj = product.images[0] if product.images else None
            if primary_image_obj:
                primary_image = primary_image_obj.cloudinary_url or primary_image_obj.image_url
        
        # Build main product reductions data
        main_history = []
        for r in main_reductions:
            reduction_data = {
                'id': r.id,
                'product_id': r.product_id,
                'product_name': product.name,
                'product_image': primary_image,
                'reduction_amount': r.reduction_amount,
                'reason': r.reason,
                'reason_notes': r.reason_notes,
                'reduced_by': r.reduced_by,
                'reduced_by_user': r.reducer_user.full_name if r.reducer_user else None,
                'created_at': r.created_at.isoformat() if r.created_at else None,
                'updated_at': r.updated_at.isoformat() if r.updated_at else None
            }
            main_history.append(reduction_data)
        
        # Build variant reductions data
        variant_history = []
        for r in variant_reductions:
            # Get the variant from the variant_id field
            var = ProductVariant.query.filter_by(id=r.variant_id).first() if r.variant_id else None
            if var:
                variant_image = var.image_url  # Get variant's own image
                reduction_data = {
                    'id': r.id,
                    'product_id': r.product_id,
                    'variant_id': var.id,
                    'product_name': f"{product.name} - {var.name}",
                    'product_image': variant_image,  # Use variant image
                    'reduction_amount': r.reduction_amount,
                    'reason': r.reason,
                    'reason_notes': r.reason_notes,
                    'reduced_by': r.reduced_by,
                    'reduced_by_user': r.reducer_user.full_name if r.reducer_user else None,
                    'created_at': r.created_at.isoformat() if r.created_at else None,
                    'updated_at': r.updated_at.isoformat() if r.updated_at else None
                }
                variant_history.append(reduction_data)
            else:
                # Fallback if variant not found (shouldn't happen)
                reduction_data = {
                    'id': r.id,
                    'product_id': r.product_id,
                    'variant_id': r.variant_id,
                    'product_name': f"{product.name} - Variant {r.variant_id}",
                    'product_image': None,
                    'reduction_amount': r.reduction_amount,
                    'reason': r.reason,
                    'reason_notes': r.reason_notes,
                    'reduced_by': r.reduced_by,
                    'reduced_by_user': r.reducer_user.full_name if r.reducer_user else None,
                    'created_at': r.created_at.isoformat() if r.created_at else None,
                    'updated_at': r.updated_at.isoformat() if r.updated_at else None
                }
                variant_history.append(reduction_data)
        
        return jsonify({
            'success': True,
            'product': {
                'id': product.id,
                'name': product.name,
                'image': primary_image,
                'current_stock': product.stock_quantity
            },
            'main_product': {
                'total_reductions': main_total_reduced,
                'reduction_count': len(main_reductions)
            },
            'variants': {
                'total_reductions': variant_total_reduced,
                'reduction_count': len(variant_reductions)
            },
            'stock_history': {
                'main': main_history,
                'variants': variant_history
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Error retrieving stock history: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 500






# Add template filters
@templates_bp.app_template_filter('time_format')
def time_format(value):
    """Format datetime to readable time"""
    if not value:
        return ""
    
    # If value is a string, convert to datetime
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except:
            return value
    
    # Format the time
    return value.strftime('%I:%M %p')  # 12-hour format with AM/PM

@templates_bp.app_template_filter('date_format')
def date_format(value):
    """Format datetime to readable date"""
    if not value:
        return ""
    
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except:
            return value
    
    return value.strftime('%b %d, %Y')  # Feb 07, 2026

@templates_bp.route('/seller/orders')
def seller_orders():
    if session.get('role') != 'seller':
        return redirect(url_for('templates.dashboard'))

    # Get seller's store
    store = Store.query.filter_by(seller_id=session['user_id']).first()
    if not store:
        return redirect(url_for('templates.dashboard'))
    
    # Get orders for this store
    orders = Order.query.filter_by(store_id=store.id)\
                       .order_by(Order.created_at.desc()).all()

    available_riders = Rider.query.filter_by(store_id=store.id, is_active=True)\
                                  .order_by(Rider.created_at.desc()).all()
    
    # Format dates for template
    orders_data = []
    for order in orders:
        order_dict = order.to_dict()
        order_dict['items'] = [item.to_dict() for item in order.items]
        order_dict['items_count'] = sum(item.quantity for item in order.items)
        order_dict['customer_phone'] = order.customer.phone if order.customer else None
        order_dict['payment_proof'] = order.payment_proof
        order_dict['rider_vehicle'] = order.assigned_rider.vehicle_type if order.assigned_rider else None
        
        # ✅ FIX: Add formatted dates
        if order.created_at:
            # Check if created_at is already a datetime object
            if isinstance(order.created_at, datetime):
                order_dict['date_formatted'] = order.created_at.strftime('%Y-%m-%d')
                order_dict['time_formatted'] = order.created_at.strftime('%H:%M')
                order_dict['datetime_formatted'] = order.created_at.strftime('%Y-%m-%d %H:%M')
            else:
                # If it's a string, try to parse it
                try:
                    dt = datetime.fromisoformat(order.created_at.replace('Z', '+00:00'))
                    order_dict['date_formatted'] = dt.strftime('%Y-%m-%d')
                    order_dict['time_formatted'] = dt.strftime('%H:%M')
                    order_dict['datetime_formatted'] = dt.strftime('%Y-%m-%d %H:%M')
                except:
                    order_dict['date_formatted'] = str(order.created_at)
                    order_dict['time_formatted'] = ''
                    order_dict['datetime_formatted'] = str(order.created_at)
        else:
            order_dict['date_formatted'] = ''
            order_dict['time_formatted'] = ''
            order_dict['datetime_formatted'] = ''
        
        orders_data.append(order_dict)

    today = datetime.utcnow().date()
    order_stats = {
        'total': len(orders),
        'today': sum(1 for order in orders if order.created_at and order.created_at.date() == today),
        'pending': sum(1 for order in orders if order.status == 'pending'),
        'payment_review': sum(1 for order in orders if order.payment_status == 'pending_verification'),
        'preparing': sum(1 for order in orders if order.status in ['accepted', 'preparing']),
        'on_delivery': sum(1 for order in orders if order.status == 'on_delivery'),
        'delivered': sum(1 for order in orders if order.status == 'delivered'),
        'cancelled': sum(1 for order in orders if order.status == 'cancelled'),
        'revenue': float(sum((order.total_amount or 0) for order in orders if order.status == 'delivered'))
    }

    riders_data = []
    for rider in available_riders:
        riders_data.append({
            'id': rider.id,
            'name': rider.user.full_name if rider.user else 'Rider',
            'vehicle': rider.vehicle_type,
            'is_active': rider.is_active
        })

    return render_template(
        'seller_orders.html',
        orders=orders_data,
        store=store.to_dict(),
        order_stats=order_stats,
        available_riders=riders_data
    )


def _serialize_seller_order_for_template(order):
    order_dict = order.to_dict()
    order_dict['items'] = [item.to_dict() for item in order.items]
    order_dict['items_count'] = sum(item.quantity for item in order.items)
    order_dict['customer_phone'] = order.customer.phone if order.customer else None
    order_dict['payment_proof'] = order.payment_proof
    order_dict['rider_vehicle'] = order.assigned_rider.vehicle_type if order.assigned_rider else None
    return order_dict


@templates_bp.route('/api/seller/orders/<int:order_id>', methods=['GET'])
def seller_order_details_api(order_id):
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401

    store = Store.query.filter_by(seller_id=session['user_id']).first()
    if not store:
        return jsonify({'error': 'No active store found'}), 404

    order = Order.query.filter_by(id=order_id, store_id=store.id).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    return jsonify(_serialize_seller_order_for_template(order)), 200


@templates_bp.route('/api/seller/orders/<int:order_id>/status', methods=['PUT'])
def seller_order_status_api(order_id):
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401

    store = Store.query.filter_by(seller_id=session['user_id']).first()
    if not store:
        return jsonify({'error': 'No active store found'}), 404

    order = Order.query.filter_by(id=order_id, store_id=store.id).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    data = request.get_json() or {}
    new_status = data.get('status')
    allowed_statuses = {'pending', 'accepted', 'preparing', 'on_delivery', 'delivered', 'cancelled'}

    if new_status not in allowed_statuses:
        return jsonify({'error': 'Invalid status'}), 400

    order.status = new_status
    order.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Order status updated',
        'order': _serialize_seller_order_for_template(order)
    }), 200


@templates_bp.route('/api/seller/orders/<int:order_id>/verify-payment', methods=['PUT'])
def seller_order_verify_payment_api(order_id):
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401

    store = Store.query.filter_by(seller_id=session['user_id']).first()
    if not store:
        return jsonify({'error': 'No active store found'}), 404

    order = Order.query.filter_by(id=order_id, store_id=store.id).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    if not order.payment_proof_url:
        return jsonify({'error': 'No payment proof uploaded'}), 400

    order.payment_status = 'verified'
    if order.status == 'pending':
        order.status = 'accepted'
    order.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Payment verified successfully',
        'order': _serialize_seller_order_for_template(order)
    }), 200

@templates_bp.route('/seller/riders')
def seller_riders():
    if session.get('role') != 'seller':
        return redirect(url_for('templates.dashboard'))
    return render_template('seller_riders.html')



# ─── Helper ───────────────────────────────────────────────────────────────────

def _get_seller_store():
    """Return the active store for the logged-in seller, or None."""
    return (
        Store.query
        .filter_by(seller_id=session['user_id'], status='active')
        .first()
    )

@templates_bp.route('/seller/pos')
@seller_required
def seller_pos():
    """
    Render the POS interface with new category logic.
    Passes all available, in-stock products for the seller's store,
    organized by main categories and store-specific subcategories.
    """
    store = _get_seller_store()

    if not store:
        # Seller has no active store — bounce back with a flash
        flash('Please set up your store first.', 'warning')
        return redirect(url_for('templates.dashboard'))

    # Get all main categories for filtering
    from app.models import Category, StoreCategory
    
    # Get all main categories (global)
    main_categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()
    
    # Get store-specific subcategories for this store
    store_categories = StoreCategory.query.filter_by(
        store_id=store.id,
        is_active=True
    ).order_by(StoreCategory.sort_order).all()
    
    # Fetch all products for this store, ordered by main category then name
    products_query = (
        Product.query
        .filter_by(store_id=store.id, is_archived=False)
        .join(Category, Product.main_category_id == Category.id)
        .order_by(Category.sort_order.asc(), Product.name.asc())
        .all()
    )
    
    # Convert products to serializable format using to_dict() method
    # This will automatically include variants as dictionaries via ProductVariant.to_dict()
    products = []
    for product in products_query:
        product_dict = product.to_dict()
        # Add main category name for filtering
        if product.main_category:
            product_dict['main_category_name'] = product.main_category.name
            product_dict['main_category_slug'] = product.main_category.slug
            product_dict['main_category_id'] = product.main_category.id
        # Add store subcategory info if exists
        if product.store_category:
            product_dict['store_category_name'] = product.store_category.name
            product_dict['store_category_id'] = product.store_category.id
        products.append(product_dict)
    
    # Organize products by main category for easier template access
    products_by_category = {}
    for cat in main_categories:
        cat_products = [p for p in products if p.get('main_category_id') == cat.id]
        if cat_products:
            products_by_category[cat.name] = cat_products
    
    # Group subcategories by main category
    subcategories_by_main = {}
    for sc in store_categories:
        if sc.main_category_id not in subcategories_by_main:
            subcategories_by_main[sc.main_category_id] = []
        subcategories_by_main[sc.main_category_id].append(sc.to_dict())

    return render_template(
        'seller_pos.html',
        store=store,
        products=products,
        main_categories=main_categories,
        store_categories=store_categories,
        products_by_category=products_by_category,
        subcategories_by_main=subcategories_by_main
    )

@templates_bp.route('/seller/pos/order', methods=['POST'])
@seller_required
def pos_create_order():
    """
    Create a POS order and update stock quantities.
    Supports product variants and discounts.
    Returns JSON with the created order id.
    """
    store = _get_seller_store()
    if not store:
        return jsonify({'error': 'No active store found for your account.'}), 403

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Invalid JSON payload.'}), 400

    items_payload = data.get('items', [])
    if not items_payload:
        return jsonify({'error': 'Order must contain at least one item.'}), 400

    # ── Validate every item before touching the DB ────────────────────────────
    validated_items = []
    for entry in items_payload:
        product_id = entry.get('product_id')
        variant_id = entry.get('variant_id')  # May be None
        quantity   = int(entry.get('quantity', 1))
        unit_price = Decimal(str(entry.get('price', 0)))

        if quantity < 1:
            return jsonify({'error': f'Quantity must be at least 1 (product id {product_id}).'}), 400

        # Check if product exists and belongs to store
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            return jsonify({'error': f'Product #{product_id} not found in your store.'}), 404

        if not product.is_available:
            return jsonify({'error': f'"{product.name}" is currently unavailable.'}), 400

        # If variant_id is provided, validate variant
        if variant_id:
            variant = ProductVariant.query.filter_by(id=variant_id, product_id=product_id).first()
            if not variant:
                return jsonify({'error': f'Variant #{variant_id} not found for product "{product.name}".'}), 404
            
            if not variant.is_available:
                return jsonify({'error': f'Variant "{variant.name}" for "{product.name}" is currently unavailable.'}), 400
            
            if variant.stock_quantity < quantity:
                return jsonify({
                    'error': (
                        f'Insufficient stock for "{product.name}" - {variant.name}. '
                        f'Available: {variant.stock_quantity}, requested: {quantity}.'
                    )
                }), 400
        else:
            # Check main product stock
            if product.stock_quantity < quantity:
                return jsonify({
                    'error': (
                        f'Insufficient stock for "{product.name}". '
                        f'Available: {product.stock_quantity}, requested: {quantity}.'
                    )
                }), 400

        validated_items.append({
            'product': product,
            'variant_id': variant_id,
            'quantity': quantity,
            'price': unit_price,
        })

    # ── Create POS order ───────────────────────────────────────────────────────
    customer_name = data.get('customer_name', '').strip()
    customer_contact = data.get('customer_contact')
    payment_method = data.get('payment_method', 'cash')
    amount_given = Decimal(str(data.get('amount_given', 0)))
    change_amount = Decimal(str(data.get('change_amount', 0)))
    
    # ===== HANDLE DISCOUNT =====
    discount = Decimal(str(data.get('discount', 0)))
    if discount < 0:
        return jsonify({'error': 'Discount cannot be negative'}), 400
    # ===========================

    # Calculate subtotal
    subtotal = sum(item['price'] * item['quantity'] for item in validated_items)
    total = subtotal - discount
    
    # Validate total is not negative
    if total < 0:
        return jsonify({'error': 'Discount cannot exceed subtotal'}), 400

    # Create the order with discount
    pos_order = POSOrder(
        store_id=store.id,
        total_amount=total,
        amount_given=amount_given,
        change_amount=change_amount,
        payment_method=payment_method,
        customer_name=customer_name,
        customer_contact=customer_contact,
        discount=discount  # Save the discount
    )
    db.session.add(pos_order)

    # ── Add items and update stock ─────────────────────────────────────────────
    for item in validated_items:
        pos_item = POSOrderItem(
            pos_order=pos_order,
            product_id=item['product'].id,
            variant_id=item['variant_id'],
            quantity=item['quantity'],
            price=item['price']
        )
        db.session.add(pos_item)

        # Update stock based on variant or product
        if item['variant_id']:
            variant = ProductVariant.query.get(item['variant_id'])
            variant.stock_quantity -= item['quantity']
        else:
            item['product'].stock_quantity -= item['quantity']

    db.session.commit()

    return jsonify({
        'success': True,
        'pos_order_id': pos_order.id,
        'message': 'Order processed successfully.'
    }), 201

@templates_bp.route('/api/seller/pos/next-order-id')
@seller_required
def pos_next_order_id():
    store = _get_seller_store()
    if not store:
        return jsonify({'error': 'No active store found'}), 403
    
    last_order = POSOrder.query.filter_by(store_id=store.id).order_by(POSOrder.id.desc()).first()
    next_id = (last_order.id + 1) if last_order else 1000
    
    return jsonify({'next_id': next_id})


@templates_bp.route('/seller/pos/orders')
@seller_required
def pos_orders():
    store = _get_seller_store()
    if not store:
        flash('Please set up your store first.', 'warning')
        return redirect(url_for('templates.dashboard'))

    import pytz
    ph_tz = pytz.timezone('Asia/Manila')
    now_ph = datetime.now(ph_tz)
    today = now_ph.date()
    ph_date = db.func.date(POSOrder.created_at + db.text("INTERVAL '8 hours'"))

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    date_filter = request.args.get('date', 'today')
    payment_filter = request.args.get('payment', 'all')
    search_query = request.args.get('search', '')

    query = POSOrder.query.filter_by(store_id=store.id)

    if date_filter == 'today':
        query = query.filter(ph_date == today)
    elif date_filter == 'yesterday':
        yesterday = today - timedelta(days=1)
        query = query.filter(ph_date == yesterday)
    elif date_filter == 'this_week':
        start_of_week = today - timedelta(days=today.weekday())
        query = query.filter(ph_date >= start_of_week)
    elif date_filter == 'this_month':
        start_of_month = today.replace(day=1)
        query = query.filter(ph_date >= start_of_month)
    elif date_filter == 'custom':
        start_date_str = request.args.get('start_date', '')
        end_date_str = request.args.get('end_date', '')
        if start_date_str:
            try:
                query = query.filter(ph_date >= datetime.strptime(start_date_str, '%Y-%m-%d').date())
            except ValueError:
                pass
        if end_date_str:
            try:
                query = query.filter(ph_date <= datetime.strptime(end_date_str, '%Y-%m-%d').date())
            except ValueError:
                pass

    if payment_filter != 'all':
        query = query.filter_by(payment_method=payment_filter)

    if search_query:
        query = query.filter(
            db.or_(
                POSOrder.customer_name.ilike(f'%{search_query}%'),
                POSOrder.customer_contact.ilike(f'%{search_query}%'),
                POSOrder.id.cast(db.String).ilike(f'%{search_query}%')
            )
        )

    query = query.order_by(POSOrder.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    orders_data = []
    for order in pagination.items:
        d = order.to_dict()
        if order.created_at:
            utc_dt = pytz.utc.localize(order.created_at)
            ph_dt = utc_dt.astimezone(ph_tz)
            d['created_at_date'] = ph_dt.strftime('%Y-%m-%d')
            d['created_at'] = ph_dt.isoformat()
        else:
            d['created_at_date'] = None
        orders_data.append(d)

    summary = {
        'total_orders': POSOrder.query.filter_by(store_id=store.id).count(),
        'total_revenue': float(db.session.query(db.func.sum(POSOrder.total_amount))
            .filter(POSOrder.store_id == store.id).scalar() or 0),
        'cash_orders': POSOrder.query.filter_by(store_id=store.id, payment_method='cash').count(),
        'gcash_orders': POSOrder.query.filter_by(store_id=store.id, payment_method='gcash').count(),
        'card_orders': POSOrder.query.filter_by(store_id=store.id, payment_method='card').count(),
    }

    today_sales = float(db.session.query(db.func.sum(POSOrder.total_amount))
        .filter(POSOrder.store_id == store.id, ph_date == today).scalar() or 0)

    return render_template(
        'seller_pos_orders.html',
        store=store,
        orders=orders_data,
        pagination=pagination,
        summary=summary,
        today_sales=today_sales,
        current_filters={
            'date': date_filter,
            'payment': payment_filter,
            'search': search_query,
            'page': page
        }
    )


@templates_bp.route('/seller/pos/orders/<int:order_id>')
@seller_required
def pos_order_detail(order_id):
    """
    View details of a specific POS order.
    """
    store = _get_seller_store()
    if not store:
        flash('Please set up your store first.', 'warning')
        return redirect(url_for('templates.dashboard'))
    
    order = POSOrder.query.filter_by(id=order_id, store_id=store.id).first_or_404()
    
    return render_template(
        'seller_pos_order_detail.html',
        store=store,
        order=order.to_dict()
    )


@templates_bp.route('/seller/pos/orders/<int:order_id>/void', methods=['POST'])
@seller_required
def pos_void_order(order_id):
    """
    Void a POS order (admin only or within certain time limit).
    This reverses the stock changes.
    """
    store = _get_seller_store()
    if not store:
        return jsonify({'error': 'No active store found'}), 403
    
    order = POSOrder.query.filter_by(id=order_id, store_id=store.id).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    
    # Check if order can be voided (e.g., within 24 hours)
    time_limit = datetime.utcnow() - timedelta(hours=24)
    if order.created_at < time_limit:
        return jsonify({'error': 'Orders older than 24 hours cannot be voided'}), 400
    
    data = request.get_json(silent=True) or {}
    reason = data.get('reason', 'No reason provided')
    
    # Restore stock
    for item in order.items:
        if item.variant_id:
            variant = ProductVariant.query.get(item.variant_id)
            if variant:
                variant.stock_quantity += item.quantity
        else:
            product = Product.query.get(item.product_id)
            if product:
                product.stock_quantity += item.quantity
    
    # Mark order as voided - we'll add a status field if needed
    # For now, we'll just delete it, but better to add a 'status' field to POSOrder
    # order.status = 'voided'  # Add this field to POSOrder model
    
    # Log the void action in a separate table or just delete
    db.session.delete(order)
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Order voided successfully'
    })


# Optional: Add this to your POSOrder model if you want to keep voided orders
"""
Add to POSOrder model:
    status = db.Column(db.String(20), default='active')  # active, voided

Then modify the void function to:
    order.status = 'voided'
    db.session.commit()
"""


@templates_bp.route('/seller/pos/statistics')
@seller_required
def pos_statistics():
    """
    Get POS statistics for the seller's store.
    Returns JSON with sales data for charts.
    """
    store = _get_seller_store()
    if not store:
        return jsonify({'error': 'No active store found'}), 403
    
    # Get date range from query params
    days = request.args.get('days', 7, type=int)
    
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)
    
    # Get daily sales
    daily_sales = db.session.query(
        db.func.date(POSOrder.created_at).label('date'),
        db.func.count(POSOrder.id).label('order_count'),
        db.func.sum(POSOrder.total_amount).label('revenue')
    ).filter(
        POSOrder.store_id == store.id,
        db.func.date(POSOrder.created_at) >= start_date,
        db.func.date(POSOrder.created_at) <= end_date
    ).group_by(
        db.func.date(POSOrder.created_at)
    ).order_by(
        db.func.date(POSOrder.created_at)
    ).all()
    
    # Get payment method breakdown
    payment_breakdown = db.session.query(
        POSOrder.payment_method,
        db.func.count(POSOrder.id).label('count'),
        db.func.sum(POSOrder.total_amount).label('total')
    ).filter(
        POSOrder.store_id == store.id,
        db.func.date(POSOrder.created_at) >= start_date
    ).group_by(
        POSOrder.payment_method
    ).all()
    
    # Get top products
    top_products = db.session.query(
        Product.name,
        db.func.sum(POSOrderItem.quantity).label('total_quantity'),
        db.func.sum(POSOrderItem.quantity * POSOrderItem.price).label('total_revenue')
    ).join(
        POSOrderItem, POSOrderItem.product_id == Product.id
    ).join(
        POSOrder, POSOrder.id == POSOrderItem.pos_order_id
    ).filter(
        POSOrder.store_id == store.id,
        db.func.date(POSOrder.created_at) >= start_date
    ).group_by(
        Product.id
    ).order_by(
        db.desc('total_quantity')
    ).limit(10).all()
    
    return jsonify({
        'daily_sales': [{
            'date': str(row.date),
            'order_count': row.order_count,
            'revenue': float(row.revenue or 0)
        } for row in daily_sales],
        'payment_breakdown': [{
            'method': row.payment_method,
            'count': row.count,
            'total': float(row.total or 0)
        } for row in payment_breakdown],
        'top_products': [{
            'name': row.name,
            'quantity': row.total_quantity,
            'revenue': float(row.total_revenue or 0)
        } for row in top_products]
    })
'''
@templates_bp.route('/seller/pos/orders', methods=['GET'])
@seller_required
def pos_order_history():
    """
    DEPRECATED - Use /api/seller/pos/orders instead
    Keeping this commented out to avoid conflicts
    """
    return jsonify({'error': 'Use /api/seller/pos/orders instead'}), 410


'''



@templates_bp.route('/analytics')
def analytics():
    if 'user_id' not in session:
        return redirect(url_for('templates.login'))
    return render_template('analytics.html')

@templates_bp.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('templates.login'))
    return render_template('profile.html')

@templates_bp.route('/settings')
def settings():
    if 'user_id' not in session:
        return redirect(url_for('templates.login'))
    return render_template('settings.html')

@templates_bp.route('/reports')
def reports():
    if 'user_id' not in session:
        return redirect(url_for('templates.login'))
    return render_template('reports.html')

@templates_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('templates.login'))

@templates_bp.route('/products/<int:product_id>')
def product_details(product_id):
    """Product detail page - updated with new category system"""
    try:
        product = Product.query.get_or_404(product_id)
        store = Store.query.get(product.store_id)
        
        # Get all main categories for the navigation
        from app.models import Category
        main_categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()
        
        # Convert product to dict to include variants with image_url
        product_dict = product.to_dict()
        
        # Add store info to product dict
        if store:
            product_dict['store'] = store.to_dict()
        
        # Add main_category and store_category info to product_dict for template
        if product.main_category:
            product_dict['main_category'] = {
                'id': product.main_category.id,
                'name': product.main_category.name,
                'slug': product.main_category.slug
            }
        
        if product.store_category:
            product_dict['store_category'] = {
                'id': product.store_category.id,
                'name': product.store_category.name,
                'slug': product.store_category.slug
            }
        
        # Add-ons: other products from same store, different main category
        addon_products = Product.query.filter(
            Product.store_id == product.store_id,
            Product.id != product_id,
            Product.is_available == True,
            Product.is_archived == False,
            Product.stock_quantity > 0
        )
        
        # If product has a main category, get products from different categories
        if product.main_category_id:
            addon_products = addon_products.filter(
                Product.main_category_id != product.main_category_id
            )
        
        addon_products = addon_products.limit(8).all()
        
        # Convert addon products to dict
        addon_dicts = []
        for p in addon_products:
            p_dict = p.to_dict()
            if p.main_category:
                p_dict['main_category'] = {
                    'id': p.main_category.id,
                    'name': p.main_category.name,
                    'slug': p.main_category.slug
                }
            addon_dicts.append(p_dict)
        
        # Related: same main category, different products
        related_products = Product.query.filter(
            Product.main_category_id == product.main_category_id,  # FIXED: Use main_category_id instead of category
            Product.id != product_id,
            Product.is_available == True,
            Product.is_archived == False,
            Product.stock_quantity > 0
        ).limit(8).all()
        
        # Convert related products to dict
        related_dicts = []
        for p in related_products:
            p_dict = p.to_dict()
            if p.main_category:
                p_dict['main_category'] = {
                    'id': p.main_category.id,
                    'name': p.main_category.name,
                    'slug': p.main_category.slug
                }
            related_dicts.append(p_dict)
        
        # Debug print
        print(f"\n🔍 PRODUCT DETAILS - ID: {product_id}")
        print(f"  Name: {product.name}")
        print(f"  Main Category: {product.main_category.name if product.main_category else 'None'}")
        print(f"  Store Category: {product.store_category.name if product.store_category else 'None'}")
        print(f"  Add-on products: {len(addon_dicts)}")
        print(f"  Related products: {len(related_dicts)}")
        print(f"  Categories for nav: {len(main_categories)}")
        
        return render_template(
            'product_details.html',  # Note: this template should be updated to use the new category fields
            product=product_dict,
            addon_products=addon_dicts,
            related_products=related_dicts,
            main_categories=main_categories  # Pass to base.html for navigation
        )
        
    except Exception as e:
        print(f"❌ Error loading product {product_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Product not found', 'error')
        return redirect(url_for('templates.products'))


@templates_bp.route('/checkout')
def checkout():
    """Checkout page"""
    if 'user_id' not in session:
        flash('Please login to checkout', 'warning')
        return redirect(url_for('templates.login'))
    
    # Get user's cart
    cart = Cart.query.filter_by(user_id=session['user_id']).first()
    
    return render_template('checkout.html', cart=cart.to_dict() if cart else None)

def get_current_user():
    """Get current user from either session (web) or JWT token (Flutter)"""
    # Check session first (for web)
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            print(f"✅ User authenticated via session: {user.id}")
            return user
    
    # Check JWT token (for Flutter)
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        print(f"🔑 JWT Token received (first 20 chars): {token[:20]}...")
        
        try:
            from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt
            
            # Force verify the JWT
            verify_jwt_in_request()
            
            # Get claims and identity
            claims = get_jwt()
            user_id = get_jwt_identity()
            
            print(f"📋 JWT Claims: {claims}")
            print(f"👤 User ID from token: {user_id}")
            
            if user_id:
                user = User.query.get(int(user_id))
                if user:
                    print(f"✅ User authenticated via JWT: {user.id}")
                    return user
                else:
                    print("❌ User not found for ID from token")
            else:
                print("❌ No user_id in JWT token")
                
        except Exception as e:
            print(f"❌ JWT validation error: {str(e)}")
            # Try to manually decode to see what's in the token
            try:
                import jwt as pyjwt
                from flask import current_app
                
                # Try to decode without verification to see the payload
                unverified = pyjwt.decode(token, options={"verify_signature": False})
                print(f"🔍 Unverified token payload: {unverified}")
                print(f"🔍 Has 'sub' claim: {'sub' in unverified}")
            except Exception as e2:
                print(f"❌ Manual decode also failed: {e2}")
    
    print("❌ No valid authentication found")
    return None

@templates_bp.route('/api/debug/jwt-config', methods=['GET'])
def debug_jwt_config():
    """Debug endpoint to check JWT configuration"""
    from flask import current_app
    from flask_jwt_extended import create_access_token, decode_token
    
    # Check configuration
    config = {
        'JWT_SECRET_KEY': current_app.config.get('JWT_SECRET_KEY', 'NOT SET'),
        'JWT_IDENTITY_CLAIM': current_app.config.get('JWT_IDENTITY_CLAIM', 'NOT SET'),
        'JWT_ACCESS_TOKEN_EXPIRES': str(current_app.config.get('JWT_ACCESS_TOKEN_EXPIRES', 'NOT SET')),
    }
    
    # Create a test token
    test_token = create_access_token(
        identity='999',
        additional_claims={'test': 'value'}
    )
    
    # Decode it to see what's inside
    try:
        decoded = decode_token(test_token)
        token_info = {
            'has_sub': 'sub' in decoded,
            'sub_value': decoded.get('sub'),
            'all_claims': {k: v for k, v in decoded.items() if k not in ['exp', 'iat', 'jti']}
        }
    except Exception as e:
        token_info = {'error': str(e)}
    
    return jsonify({
        'config': config,
        'test_token_preview': test_token[:50] + '...',
        'test_token_info': token_info,
    })

@templates_bp.route('/api/debug/auth', methods=['GET'])
def debug_auth():
    """Debug endpoint to check authentication"""
    user = get_current_user()
    if user:
        return jsonify({
            'authenticated': True,
            'user_id': user.id,
            'method': 'session' if 'user_id' in session else 'jwt'
        })
    else:
        return jsonify({
            'authenticated': False,
            'session_exists': 'user_id' in session,
            'auth_header': request.headers.get('Authorization')
        })
    



@templates_bp.route('/api/cart/items', methods=['POST'])
def add_to_cart():
    """Add item to cart - FIXED to handle variants"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        data = request.get_json()
        product_id = data.get('product_id')
        variant_id = data.get('variant_id')  # ✅ Get variant_id from payload
        quantity = data.get('quantity', 1)
        
        print(f"🛒 Adding to cart - User: {user.id}, Product: {product_id}, Variant: {variant_id}, Quantity: {quantity}")
        
        if not product_id:
            return jsonify({'error': 'Product ID is required'}), 400
        
        # Check if product exists
        product = Product.query.get(product_id)
        if not product:
            print(f"❌ Product not found: {product_id}")
            return jsonify({'error': 'Product not found'}), 404
        
        # If variant_id is provided, check variant exists and has stock
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
        
        if not product.is_available:
            return jsonify({'error': 'Product is not available'}), 400
        
        # Get or create cart
        cart = Cart.query.filter_by(user_id=user.id).first()
        if not cart:
            print(f"🆕 Creating new cart for user: {user.id}")
            cart = Cart(user_id=user.id)
            db.session.add(cart)
            db.session.flush()
        
        # ✅ FIXED: Check if product/variant combination already in cart
        cart_item = CartItem.query.filter_by(
            cart_id=cart.id,
            product_id=product_id,
            variant_id=variant_id  # Include variant_id in the query!
        ).first()
        
        if cart_item:
            # Check total quantity against stock
            if variant:
                if variant.stock_quantity < (cart_item.quantity + quantity):
                    return jsonify({'error': f'Only {variant.stock_quantity} of this variant available total'}), 400
            else:
                if product.stock_quantity < (cart_item.quantity + quantity):
                    return jsonify({'error': f'Only {product.stock_quantity} available total'}), 400
                    
            print(f"🔄 Updating existing cart item from {cart_item.quantity} to {cart_item.quantity + quantity}")
            cart_item.quantity += quantity
        else:
            print(f"➕ Adding new cart item with variant_id: {variant_id}")
            cart_item = CartItem(
                cart_id=cart.id,
                product_id=product_id,
                variant_id=variant_id,  # ✅ Save variant_id!
                quantity=quantity
            )
            db.session.add(cart_item)
        
        db.session.commit()
        
        # ✅ Return the updated cart with proper structure
        cart_dict = cart.to_dict()
        print(f"✅ Item added successfully. Cart now has {len(cart_dict.get('items', []))} items")
        
        return jsonify({
            'success': True,
            'message': 'Item added to cart',
            'cart': cart_dict
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error adding to cart: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/cart', methods=['GET'])
def get_cart():
    """Get cart - FIXED to include variant details and Cloudinary URLs"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        cart = Cart.query.filter_by(user_id=user.id).first()
        if not cart:
            cart = Cart(user_id=user.id)
            db.session.add(cart)
            db.session.commit()
        
        # Filter out archived products from cart
        active_items = []
        removed_count = 0
        
        for item in cart.items:
            if item.product and not item.product.is_archived:
                active_items.append(item)
            else:
                db.session.delete(item)
                removed_count += 1
        
        if removed_count > 0:
            db.session.commit()
        
        # ✅ Build cart data with variant details properly included
        cart_data = {
            'id': cart.id,
            'user_id': cart.user_id,
            'items': [],
            'created_at': cart.created_at.isoformat() if cart.created_at else None,
            'updated_at': cart.updated_at.isoformat() if cart.updated_at else None
        }
        
        total = 0
        for item in active_items:
            # Get product details
            product = item.product
            
            # Get variant details if exists
            variant = None
            if item.variant_id:
                variant = ProductVariant.query.get(item.variant_id)
            
            # Determine price (variant price takes precedence)
            price = float(variant.price) if variant else float(product.price)
            
            # Determine name
            if variant:
                name = f"{variant.name} {product.name}"
            else:
                name = product.name
            
            # Get the full product dictionary (includes all image details)
            product_dict = product.to_dict()
            
            # Determine image URL (variant image takes precedence)
            image_url = None
            if variant and variant.image_url:
                image_url = variant.image_url
            elif product.images:
                primary = next((img for img in product.images if img.is_primary), product.images[0])
                # Use cloudinary_url if available, otherwise fallback to image_url
                image_url = primary.cloudinary_url if primary and primary.cloudinary_url else (
                    primary.image_url if hasattr(primary, 'image_url') else None
                )
            
            # Ensure product images have cloudinary_url in the response
            if 'images' in product_dict:
                for img in product_dict['images']:
                    # Make sure cloudinary_url is included
                    if 'cloudinary_url' not in img and 'image_url' in img:
                        img['cloudinary_url'] = img['image_url']
            
            item_dict = {
                'id': item.id,
                'product_id': product.id,
                'store_id': product.store_id,
                'variant_id': item.variant_id,
                'quantity': item.quantity,
                'is_selected': item.is_selected,
                'product': product_dict,  # Full product dict with all image data
                'store_name': product.store.name if product.store else None,
                'price': price,
                'name': name,
                'image_url': image_url,  # Top-level convenience field
                'subtotal': float(price * item.quantity)
            }
            
            # Add variant details if exists (with full Cloudinary URLs)
            if variant:
                variant_dict = variant.to_dict()
                # Ensure variant image_url is included
                if variant.image_url and 'image_url' not in variant_dict:
                    variant_dict['image_url'] = variant.image_url
                item_dict['variant'] = variant_dict
            
            cart_data['items'].append(item_dict)
            total += item_dict['subtotal']
        
        cart_data['total'] = total
        cart_data['item_count'] = len(cart_data['items'])
        
        # Debug log to verify image URLs
        print(f"\n✅ Cart response for user {user.id}:")
        print(f"   Items: {len(cart_data['items'])}")
        for i, item in enumerate(cart_data['items']):
            print(f"   Item {i}: {item['name']}")
            if item.get('image_url'):
                print(f"      image_url: {item['image_url']}")
            if item['product'].get('images'):
                for j, img in enumerate(item['product']['images']):
                    print(f"      product.images[{j}]: cloudinary_url={img.get('cloudinary_url')}")
        
        return jsonify({
            'success': True,
            'cart': cart_data,
            'removed_count': removed_count,
            'message': f'{removed_count} item(s) removed as they are no longer available' if removed_count else None
        })
        
    except Exception as e:
        print(f"❌ Error getting cart: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@templates_bp.route('/api/cart/items/<int:item_id>', methods=['PUT'])
def update_cart_item(item_id):
    """Update cart item quantity"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        data = request.get_json()
        quantity = data.get('quantity')
        
        print(f"🔄 Updating cart item - User: {user.id}, Item: {item_id}, New Quantity: {quantity}")
        
        if not quantity or quantity < 1:
            return jsonify({'error': 'Invalid quantity'}), 400
        
        cart_item = CartItem.query.get_or_404(item_id)
        
        # Verify ownership
        if cart_item.cart.user_id != user.id:
            print(f"❌ Unauthorized: Item belongs to user {cart_item.cart.user_id}, but request is from {user.id}")
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Check stock
        product = cart_item.product
        if product and product.stock_quantity < quantity:
            return jsonify({'error': f'Only {product.stock_quantity} available'}), 400
        
        cart_item.quantity = quantity
        db.session.commit()
        
        print(f"✅ Cart item updated successfully")
        
        return jsonify({
            'success': True,
            'message': 'Cart updated',
            'cart': cart_item.cart.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error updating cart: {str(e)}")
        return jsonify({'error': str(e)}), 500

@templates_bp.route('/api/cart/items/<int:item_id>', methods=['DELETE'])
def remove_from_cart(item_id):
    """Remove item from cart"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        print(f"🗑️ Removing cart item - User: {user.id}, Item: {item_id}")
        
        cart_item = CartItem.query.get_or_404(item_id)
        
        # Verify ownership
        if cart_item.cart.user_id != user.id:
            print(f"❌ Unauthorized: Item belongs to user {cart_item.cart.user_id}, but request is from {user.id}")
            return jsonify({'error': 'Unauthorized'}), 403
        
        cart = cart_item.cart
        db.session.delete(cart_item)
        db.session.commit()
        
        print(f"✅ Item removed successfully")
        
        return jsonify({
            'success': True,
            'message': 'Item removed from cart',
            'cart': cart.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error removing from cart: {str(e)}")
        return jsonify({'error': str(e)}), 500

@templates_bp.route('/api/cart/clear', methods=['POST'])
def clear_cart():
    """Clear all items from cart"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        print(f"🧹 Clearing cart for user: {user.id}")
        
        cart = Cart.query.filter_by(user_id=user.id).first()
        if cart:
            item_count = CartItem.query.filter_by(cart_id=cart.id).count()
            CartItem.query.filter_by(cart_id=cart.id).delete()
            db.session.commit()
            print(f"✅ Removed {item_count} items from cart")
        else:
            print(f"📭 No cart found for user")
        
        return jsonify({
            'success': True,
            'message': 'Cart cleared'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error clearing cart: {str(e)}")
        return jsonify({'error': str(e)}), 500




'''
@templates_bp.route('/api/product-image/<path:filename>')
def get_resized_product_image(filename):
    """Return a resized version of a product image with proper headers"""
    try:
        # Security: Prevent directory traversal
        if '..' in filename or filename.startswith('/'):
            return jsonify({'error': 'Invalid filename'}), 400
        
        # Construct the full path
        upload_folder = os.path.join(BASE_DIR, 'static', 'uploads', 'products')
        file_path = os.path.join(upload_folder, filename)
        
        # Check if file exists
        if not os.path.exists(file_path):
            print(f"❌ Image not found: {file_path}")
            return jsonify({'error': 'Image not found'}), 404
        
        # Get requested size from query parameters (default 150x150)
        width = request.args.get('w', 150, type=int)
        height = request.args.get('h', 150, type=int)
        
        # Limit maximum size to prevent timeout issues
        width = min(width, 400)  # Reduced from 800 to 400
        height = min(height, 400)  # Reduced from 800 to 400
        
        print(f"🖼️ Serving image: {filename} ({width}x{height})")
        
        # Check if we have a cached resized version
        cache_folder = os.path.join(upload_folder, 'cache')
        os.makedirs(cache_folder, exist_ok=True)
        cache_filename = f"{width}x{height}_{filename}"
        cache_path = os.path.join(cache_folder, cache_filename)
        
        # If cached version exists and is newer than original, serve it
        if os.path.exists(cache_path) and os.path.getmtime(cache_path) > os.path.getmtime(file_path):
            print(f"📦 Serving cached version: {cache_filename}")
            return send_file(
                cache_path,
                mimetype='image/png' if filename.lower().endswith('.png') else 'image/jpeg',
                as_attachment=False,
                download_name=f'thumb_{filename}',
                max_age=86400
            )
        
        # Open and resize image with timeout handling
        try:
            img = Image.open(file_path)
        except Exception as e:
            print(f"❌ Error opening image: {e}")
            return jsonify({'error': f'Cannot open image: {e}'}), 500
        
        # CREAM COLOR (AppColors.warmWhite in hex: #F5EDE6)
        CREAM_BG = (245, 237, 230)  # RGB values for warm white/cream
        
        # Handle PNG with transparency - ADD CREAM BACKGROUND
        if img.mode == 'RGBA':
            # Create cream background
            background = Image.new('RGBA', img.size, CREAM_BG + (255,))
            # Composite the image onto cream background
            background.paste(img, (0, 0), img)
            img = background.convert('RGB')
        elif img.mode in ('RGBA', 'LA') and filename.lower().endswith(('.jpg', '.jpeg')):
            # For JPEG conversion
            background = Image.new('RGB', img.size, CREAM_BG)
            background.paste(img, mask=img.split()[-1])
            img = background
        else:
            img = img.convert('RGB')
        
        # Resize with high-quality algorithm
        img.thumbnail((width, height), Image.Resampling.LANCZOS)
        
        # Save to cache with appropriate format
        if filename.lower().endswith('.jpg') or filename.lower().endswith('.jpeg'):
            format = 'JPEG'
            mimetype = 'image/jpeg'
            img.save(cache_path, format=format, quality=85, optimize=True)
        else:
            format = 'PNG'
            mimetype = 'image/png'
            img.save(cache_path, format=format, optimize=True)
        
        print(f"✅ Image cached: {cache_path} ({os.path.getsize(cache_path)} bytes)")
        
        # Send the cached file
        response = send_file(
            cache_path,
            mimetype=mimetype,
            as_attachment=False,
            download_name=f'thumb_{filename}',
            max_age=86400  # Cache for 24 hours
        )
        
        # Add CORS headers
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Cache-Control'] = 'public, max-age=86400'
        
        return response
        
    except Exception as e:
        print(f"❌ Error resizing image {filename}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
'''
'''
@templates_bp.route('/api/product-image/<path:filename>')
@limiter.limit("100 per minute")
def get_resized_product_image(filename):
    """Return a resized version of a product image with proper headers and security"""
    try:
        # ===== ENHANCED SECURITY: Multiple layers of path validation =====
        from werkzeug.utils import secure_filename
        import os
        import magic  # For MIME type validation (install: pip install python-magic-bin)
        
        # Layer 1: Basic path traversal prevention
        if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
            print(f"❌ Blocked path traversal attempt: {filename}")
            return jsonify({'error': 'Invalid filename'}), 400
        
        # Layer 2: Use secure_filename to get safe basename
        safe_filename = secure_filename(os.path.basename(filename))
        if safe_filename != filename:
            print(f"❌ Filename sanitization changed: {filename} -> {safe_filename}")
            return jsonify({'error': 'Invalid filename characters'}), 400
        
        # Layer 3: Validate file extension
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        ext = safe_filename.rsplit('.', 1)[1].lower() if '.' in safe_filename else ''
        if ext not in allowed_extensions:
            print(f"❌ Blocked invalid extension: {ext}")
            return jsonify({'error': 'Invalid file type'}), 400
        
        # Construct paths
        upload_folder = os.path.join(BASE_DIR, 'static', 'uploads', 'products')
        
        # Layer 4: Path resolution to prevent symlink attacks
        real_upload_folder = os.path.realpath(upload_folder)
        file_path = os.path.join(real_upload_folder, safe_filename)
        real_file_path = os.path.realpath(file_path)
        
        # Layer 5: Verify the resolved path is still within upload folder
        if not real_file_path.startswith(real_upload_folder):
            print(f"❌ Path escape attempt: {real_file_path}")
            return jsonify({'error': 'Access denied'}), 403
        
        # Check if file exists
        if not os.path.exists(real_file_path):
            print(f"❌ Image not found: {safe_filename}")
            return jsonify({'error': 'Image not found'}), 404
        
        # Layer 6: Validate file is actually an image (MIME type check)
        try:
            file_mime = magic.from_file(real_file_path, mime=True)
            if not file_mime.startswith('image/'):
                print(f"❌ Not an image file: {file_mime}")
                return jsonify({'error': 'Invalid image file'}), 400
        except Exception as e:
            print(f"⚠️ MIME check failed: {e}")
            # Fallback to PIL validation
        
        # Get requested size from query parameters
        width = request.args.get('w', 150, type=int)
        height = request.args.get('h', 150, type=int)
        
        # Layer 7: Limit dimensions to prevent DoS
        MAX_DIMENSION = 800
        width = min(max(width, 16), MAX_DIMENSION)  # Min 16px, max 800px
        height = min(max(height, 16), MAX_DIMENSION)
        
        print(f"🖼️ Serving image: {safe_filename} ({width}x{height})")
        
        # Check cache
        cache_folder = os.path.join(real_upload_folder, 'cache')
        os.makedirs(cache_folder, mode=0o755, exist_ok=True)  # Secure permissions
        
        # Layer 8: Sanitize cache filename
        cache_filename = f"{width}x{height}_{safe_filename}"
        cache_filename = secure_filename(cache_filename)
        cache_path = os.path.join(cache_folder, cache_filename)
        
        # Serve cached version if available
        if os.path.exists(cache_path) and os.path.getmtime(cache_path) > os.path.getmtime(real_file_path):
            print(f"📦 Serving cached version: {cache_filename}")
            
            # Layer 9: Validate cached file
            try:
                cache_mime = magic.from_file(cache_path, mime=True)
                if not cache_mime.startswith('image/'):
                    os.remove(cache_path)  # Delete corrupted cache
                    print(f"🗑️ Removed invalid cache: {cache_filename}")
                else:
                    return send_file(
                        cache_path,
                        mimetype=cache_mime,
                        as_attachment=False,
                        download_name=f'thumb_{safe_filename}',
                        max_age=86400
                    )
            except:
                pass  # Proceed to regenerate
        
        # Open and validate image with PIL
        try:
            img = Image.open(real_file_path)
            img.verify()  # Verify it's a valid image
            img = Image.open(real_file_path)  # Reopen after verify
        except Exception as e:
            print(f"❌ Error opening image: {e}")
            return jsonify({'error': 'Corrupted image file'}), 500
        
        # Layer 10: Limit image size to prevent memory DoS
        MAX_PIXELS = 4000 * 4000  # 16 megapixels
        if img.size[0] * img.size[1] > MAX_PIXELS:
            print(f"❌ Image too large: {img.size[0]}x{img.size[1]}")
            return jsonify({'error': 'Image too large'}), 400
        
        # CREAM COLOR for background
        CREAM_BG = (245, 237, 230)
        
        # Handle different image modes
        try:
            if img.mode == 'RGBA':
                # Create cream background
                background = Image.new('RGBA', img.size, CREAM_BG + (255,))
                background.paste(img, (0, 0), img)
                img = background.convert('RGB')
            elif img.mode in ('RGBA', 'LA', 'P'):  # Handle palette images
                img = img.convert('RGBA')
                background = Image.new('RGBA', img.size, CREAM_BG + (255,))
                background.paste(img, (0, 0), img)
                img = background.convert('RGB')
            else:
                img = img.convert('RGB')
        except Exception as e:
            print(f"❌ Error processing image: {e}")
            return jsonify({'error': 'Image processing failed'}), 500
        
        # Resize with high-quality algorithm
        img.thumbnail((width, height), Image.Resampling.LANCZOS)
        
        # Save to cache with secure permissions
        try:
            if ext in ('jpg', 'jpeg'):
                img.save(cache_path, format='JPEG', quality=85, optimize=True)
                mimetype = 'image/jpeg'
            else:
                img.save(cache_path, format='PNG', optimize=True)
                mimetype = 'image/png'
            
            # Set secure file permissions
            os.chmod(cache_path, 0o644)
            
        except Exception as e:
            print(f"❌ Error saving cache: {e}")
            return jsonify({'error': 'Failed to process image'}), 500
        
        print(f"✅ Image cached: {cache_path} ({os.path.getsize(cache_path)} bytes)")
        
        # Send response with security headers
        response = send_file(
            cache_path,
            mimetype=mimetype,
            as_attachment=False,
            download_name=f'thumb_{safe_filename}',
            max_age=86400
        )
        
        # Layer 11: Security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        # Cache control
        response.headers['Cache-Control'] = 'public, max-age=86400, immutable'
        
        # CORS - restrict to your domains in production
        if app.debug:
            response.headers['Access-Control-Allow-Origin'] = '*'
        else:
            # Replace with your actual domains
            response.headers['Access-Control-Allow-Origin'] = 'https://yourdomain.com'
        
        return response
        
    except Exception as e:
        print(f"❌ Error in get_resized_product_image: {e}")
        import traceback
        traceback.print_exc()
        # Don't expose internal errors to client
        return jsonify({'error': 'An error occurred processing the image'}), 500
'''
    

@templates_bp.route('/seller/archive')
@seller_required
def seller_archive():
    """Render the seller archive page"""
    return render_template('seller_archive.html')

'''
@templates_bp.route('/seller/products/<int:product_id>/images/<int:image_id>', methods=['DELETE'])
def delete_product_image(product_id, image_id):
    """Delete a specific product image"""
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        # Get seller's store
        store = Store.query.filter_by(seller_id=session.get('user_id')).first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        image = ProductImage.query.filter_by(id=image_id, product_id=product_id).first()
        if not image:
            return jsonify({'error': 'Image not found'}), 404
        
        # Don't allow deleting the last image
        if len(product.images) <= 1:
            return jsonify({'error': 'Cannot delete the last image of a product'}), 400
        
        # Delete file from filesystem
        upload_path = os.path.join(BASE_DIR, 'static', 'uploads', 'products')
        file_path = os.path.join(upload_path, image.filename)
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # If this was the primary image, make the next image primary
        if image.is_primary and len(product.images) > 1:
            next_image = next((img for img in product.images if img.id != image_id), None)
            if next_image:
                next_image.is_primary = True
        
        db.session.delete(image)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Image deleted successfully',
            'product': product.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting image: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

'''


# ─── REPLACE the existing store_detail route with this ───────────────────────
@templates_bp.route('/stores')
def stores():
    """Redirect /stores back to homepage stores section — stores.html is not needed."""
    return redirect(url_for('templates.index') + '#featured-stores')


@templates_bp.route('/store/<int:store_id>')
def store_detail(store_id):
    """Public store detail page — shows store info + all its active products."""
    try:
        from datetime import timedelta

        store = Store.query.get_or_404(store_id)

        # Only show active stores to the public
        if store.status != 'active':
            flash('This store is not currently available.', 'warning')
            return redirect(url_for('templates.index'))

        # Build store dict
        store_data = store.to_dict()

        # ===== UPDATED: Use Cloudinary URL for logo if available =====
        # Attach logo URL from seller application - prefer Cloudinary URL
        if store.seller_application:
            # Use Cloudinary URL if available
            if store.seller_application.store_logo_url:
                store_data['logo_url'] = store.seller_application.store_logo_url
            # Fallback to local path
            elif store.seller_application.store_logo_path:
                store_data['logo_url'] = f'/static/uploads/seller_logos/{store.seller_application.store_logo_path}'
            else:
                store_data['logo_url'] = None
        else:
            store_data['logo_url'] = None

        # Get active, non-archived products for this store
        products = Product.query \
            .filter_by(
                store_id=store.id,
                is_available=True,
                is_archived=False
            ) \
            .order_by(Product.created_at.desc()) \
            .all()

        product_list = []
        for p in products:
            pd = p.to_dict()
            pd['store_name'] = store.name
            product_list.append(pd)

        # Fetch testimonials for this store (most recent 10)
        testimonials = Testimonial.query \
            .filter_by(store_id=store.id) \
            .order_by(Testimonial.created_at.desc()) \
            .limit(10) \
            .all()

        testimonial_list = [t.to_dict() for t in testimonials]

        # Average rating
        avg_rating = 0.0
        if testimonials:
            avg_rating = round(sum(t.rating for t in testimonials) / len(testimonials), 1)

        now = datetime.utcnow()

        return render_template(
            'store_detail.html',
            store=store_data,
            products=product_list,
            testimonials=testimonial_list,
            avg_rating=avg_rating,
            now=now,
            timedelta=timedelta,
        )

    except Exception as e:
        print(f"Error loading store {store_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Store not found.', 'error')
        return redirect(url_for('templates.index'))


















@templates_bp.route('/seller/store-settings')
@seller_required
def store_settings():
    try:
        store = Store.query.filter_by(seller_id=session['user_id']).first()
        if not store:
            flash('Store not found.', 'error')
            return redirect(url_for('templates.seller_dashboard'))
        
        # Import the laguna_addresses functions
        from app.laguna_addresses import get_municipalities, get_barangays
        
        # Get list of municipalities for the dropdown
        municipalities = get_municipalities()
        
        # FIXED: Process GCash QR codes for template using Cloudinary URL
        gcash_qr_data = []
        if store.gcash_qr_images:
            sorted_qrs = sorted(store.gcash_qr_images, key=lambda x: x.sort_order)
            for qr in sorted_qrs:
                gcash_qr_data.append({
                    'id': qr.id,
                    'filename': qr.filename,
                    'url': qr.cloudinary_url,  # ✅ FIXED: Use Cloudinary URL, not local path
                    'public_id': qr.public_id,
                    'is_primary': qr.is_primary,
                    'sort_order': qr.sort_order
                })
        
        # DEBUG: Print store data
        print("\n" + "="*60)
        print("🔍 STORE SETTINGS PAGE LOADED")
        print(f"Store ID: {store.id}")
        print(f"Store Name: {store.name}")
        print(f"Municipality: {store.municipality}")
        print(f"Barangay: {store.barangay}")
        print(f"Delivery Method: {store.delivery_method}")
        print(f"Has zone_delivery_area: {store.zone_delivery_area is not None}")
        print(f"Has selected_municipalities: {store.selected_municipalities is not None}")
        print(f"Has municipality_delivery_area: {store.municipality_delivery_area is not None}")
        print(f"GCash QR count: {len(gcash_qr_data)}")
        if gcash_qr_data:
            print(f"First QR URL: {gcash_qr_data[0]['url']}")
        print("="*60 + "\n")
        
        return render_template('store_settings.html', 
                             store=store,
                             municipalities=municipalities,
                             get_barangays=get_barangays,
                             gcash_qr_data=gcash_qr_data)
    
    except Exception as e:
        print(f"❌ Error in store_settings: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Error loading page.', 'error')
        return redirect(url_for('templates.seller_dashboard'))


@templates_bp.route('/api/seller/store/settings', methods=['POST'])
@seller_required
def update_store_settings():
    """Update all store settings at once including GCash QR codes with Cloudinary"""
    print("\n" + "="*60)
    print("📥 RECEIVED UPDATE STORE SETTINGS REQUEST")
    
    import json
    
    try:
        store = Store.query.filter_by(seller_id=session['user_id']).first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        # Handle form data
        if request.content_type and 'multipart/form-data' in request.content_type:
            data = request.form
            files = request.files
            print(f"📦 Processing multipart form data with {len(files)} files")
        else:
            data = request.get_json() or {}
            files = {}
            print(f"📦 Processing JSON data")
        
        print(f"📋 Form data keys: {list(data.keys())}")
        
        # ===== BASIC INFO =====
        if 'name' in data:
            store.name = data['name']
        
        # ===== ADDRESS FIELDS =====
        if 'municipality' in data:
            store.municipality = data['municipality']
        if 'barangay' in data:
            store.barangay = data['barangay']
        if 'street' in data:
            store.street = data['street']
        
        # Update full address
        if 'address' in data:
            store.address = data['address']
        else:
            if store.municipality and store.barangay:
                if store.street:
                    store.address = f"{store.street}, Barangay {store.barangay}, {store.municipality}, Laguna"
                else:
                    store.address = f"Barangay {store.barangay}, {store.municipality}, Laguna"
        
        if 'contact_number' in data:
            store.contact_number = data['contact_number']
        if 'description' in data:
            store.description = data['description']
        if 'status' in data:
            store.status = data['status']
        
        # ===== LOCATION FIELDS =====
        if 'latitude' in data and data['latitude']:
            try:
                store.latitude = float(data['latitude'])
            except:
                pass
        if 'longitude' in data and data['longitude']:
            try:
                store.longitude = float(data['longitude'])
            except:
                pass
        if 'formatted_address' in data:
            store.formatted_address = data['formatted_address']
        if 'place_id' in data:
            store.place_id = data['place_id']
        
        # Update PostGIS location
        if store.latitude and store.longitude:
            try:
                from geoalchemy2.shape import from_shape
                from shapely.geometry import Point
                store.location = from_shape(Point(store.longitude, store.latitude), srid=4326)
            except Exception as e:
                print(f"⚠️ Could not update PostGIS location: {e}")
        
        # ===== DELIVERY SETTINGS =====
        old_method = store.delivery_method
        if 'delivery_method' in data:
            store.delivery_method = data['delivery_method']
            print(f"✅ Updated delivery_method from {old_method} to {store.delivery_method}")
        
        if 'delivery_radius_km' in data:
            try:
                store.delivery_radius_km = float(data['delivery_radius_km'])
            except:
                pass
        if 'max_delivery_distance' in data:
            try:
                store.max_delivery_distance = float(data['max_delivery_distance'])
            except:
                pass
        if 'base_delivery_fee' in data:
            try:
                store.base_delivery_fee = float(data['base_delivery_fee'])
            except:
                pass
        if 'delivery_rate_per_km' in data:
            try:
                store.delivery_rate_per_km = float(data['delivery_rate_per_km'])
            except:
                pass
        if 'free_delivery_minimum' in data:
            try:
                store.free_delivery_minimum = float(data['free_delivery_minimum'])
            except:
                pass
        
        # ===== ZONE DELIVERY AREA (always save when provided) =====
        if 'zone_delivery_area' in data:
            zone_value = data['zone_delivery_area']
            if zone_value and zone_value != 'null' and zone_value != 'None':
                try:
                    from geoalchemy2.shape import from_shape
                    from shapely.geometry import shape
                    
                    zone_geojson = json.loads(zone_value)
                    polygon = shape(zone_geojson)
                    store.zone_delivery_area = from_shape(polygon, srid=4326)
                    print(f"✅ Saved zone_delivery_area to database")
                except Exception as e:
                    print(f"⚠️ Error saving zone_delivery_area: {e}")
        
        # ===== MUNICIPALITY SELECTION (always save when provided) =====
        if 'selected_municipalities' in data:
            selected_muni = data['selected_municipalities']
            
            # Parse and save selected municipalities
            if isinstance(selected_muni, str):
                if selected_muni and selected_muni.strip():
                    if selected_muni.strip().startswith('['):
                        try:
                            store.selected_municipalities = json.loads(selected_muni)
                        except:
                            store.selected_municipalities = []
                    elif ',' in selected_muni:
                        store.selected_municipalities = [m.strip() for m in selected_muni.split(',') if m.strip()]
                    else:
                        store.selected_municipalities = [selected_muni.strip()] if selected_muni.strip() else []
                else:
                    store.selected_municipalities = []
            elif isinstance(selected_muni, list):
                store.selected_municipalities = selected_muni
            else:
                store.selected_municipalities = []
            print(f"✅ Saved selected_municipalities: {store.selected_municipalities}")
        
        # ===== MUNICIPALITY DELIVERY AREA (when generated) =====
        if 'municipality_delivery_area' in data:
            muni_value = data['municipality_delivery_area']
            if muni_value and muni_value != 'null' and muni_value != 'None':
                try:
                    from geoalchemy2.shape import from_shape
                    from shapely.geometry import shape
                    
                    muni_geojson = json.loads(muni_value)
                    polygon = shape(muni_geojson)
                    store.municipality_delivery_area = from_shape(polygon, srid=4326)
                    print(f"✅ Saved municipality_delivery_area to database")
                except Exception as e:
                    print(f"⚠️ Error saving municipality_delivery_area: {e}")
        
        # ===== UPDATE ACTIVE DELIVERY AREA BASED ON CURRENT METHOD =====
        store.update_delivery_area_from_method()
        
        # ===== GCASH QR CODE HANDLING WITH CLOUDINARY =====
        print("\n📱 Processing GCash QR codes with Cloudinary...")

        # Get QR IDs to keep and delete
        qr_ids_to_keep = []
        if 'gcash_qr_ids_to_keep' in data:
            keep_str = data['gcash_qr_ids_to_keep']
            if keep_str:
                try:
                    qr_ids_to_keep = json.loads(keep_str)
                except:
                    qr_ids_to_keep = []

        qr_ids_to_delete = []
        if 'gcash_qr_ids_to_delete' in data:
            delete_str = data['gcash_qr_ids_to_delete']
            if delete_str:
                try:
                    qr_ids_to_delete = json.loads(delete_str)
                except:
                    qr_ids_to_delete = []

        # Import Cloudinary helper
        from app.utils.cloudinary_helper import delete_from_cloudinary

        # Delete marked QR codes from Cloudinary and database
        for qr_id in qr_ids_to_delete:
            qr = GCashQR.query.get(qr_id)
            if qr and qr.store_id == store.id:
                # Delete from Cloudinary if public_id exists
                if qr.public_id:
                    delete_from_cloudinary(qr.public_id)
                    print(f"   🗑️ Deleted QR from Cloudinary: {qr.public_id}")
                
                # Delete from database
                db.session.delete(qr)
                print(f"   ✅ Deleted QR record ID: {qr_id}")

        # Process new QR code uploads from Cloudinary
        current_qr_count = GCashQR.query.filter_by(store_id=store.id).count()
        next_sort_order = current_qr_count

        # Look for Cloudinary QR data in form data (sent from frontend after upload)
        qr_index = 0
        while f'gcash_qr_public_id_{qr_index}' in data:
            public_id = data.get(f'gcash_qr_public_id_{qr_index}')
            url = data.get(f'gcash_qr_url_{qr_index}')
            filename = data.get(f'gcash_qr_filename_{qr_index}')
            
            if public_id and url:
                is_primary = (next_sort_order == 0)
                
                new_qr = GCashQR(
                    store_id=store.id,
                    filename=filename or f"gcash_{public_id}.jpg",
                    public_id=public_id,
                    cloudinary_url=url,
                    is_primary=is_primary,
                    sort_order=next_sort_order
                )
                db.session.add(new_qr)
                next_sort_order += 1
                print(f"   ✅ Created new QR record from Cloudinary: {public_id}")
            
            qr_index += 1

        # Also check for file uploads (backward compatibility, but not recommended)
        for key in files:
            if key.startswith('gcash_qr_'):
                file = files[key]
                if file and file.filename:
                    print(f"   ⚠️ Direct file upload detected for {key}. Please use Cloudinary upload instead.")
                    # You could still process it, but better to use Cloudinary
                    # Consider showing a warning to the user

        # Update sort_order for kept QRs
        if qr_ids_to_keep:
            kept_qrs = GCashQR.query.filter(GCashQR.id.in_(qr_ids_to_keep)).all()
            for i, qr in enumerate(kept_qrs):
                qr.sort_order = i
                qr.is_primary = (i == 0)

        # Update GCash instructions
        if 'gcash_instructions' in data:
            store.gcash_instructions = data['gcash_instructions']
        
        store.updated_at = datetime.utcnow()
        db.session.commit()
        
        print("✅ Database commit successful")
        print(f"📊 FINAL STORE DATA AFTER COMMIT:")
        print(f"   delivery_method: {store.delivery_method}")
        print(f"   has zone_delivery_area: {store.zone_delivery_area is not None}")
        print(f"   selected_municipalities: {store.selected_municipalities}")
        print(f"   has municipality_delivery_area: {store.municipality_delivery_area is not None}")
        
        return jsonify({
            'success': True,
            'message': 'Store settings updated successfully',
            'store': store.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ ERROR UPDATING STORE SETTINGS: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
    
@templates_bp.route('/api/seller/store/geocode', methods=['POST'])
@seller_required
def reverse_geocode():
    """Reverse geocode coordinates to get address using Mapbox"""
    print("\n" + "="*60)
    print("📍 REVERSE GEOCODE REQUEST")
    
    try:
        data = request.get_json()
        lat = data.get('latitude')
        lng = data.get('longitude')
        
        print(f"Coordinates: lat={lat}, lng={lng}")
        
        if not lat or not lng:
            print("❌ Missing coordinates")
            return jsonify({'error': 'Latitude and longitude required'}), 400
        
        import requests
        mapbox_token = os.getenv('MAPBOX_PUBLIC_TOKEN')
        
        print(f"Mapbox token exists: {mapbox_token is not None}")
        if mapbox_token:
            print(f"Token preview: {mapbox_token[:10]}...")
        else:
            print("❌ MAPBOX_PUBLIC_TOKEN not found in environment")
            return jsonify({'error': 'Mapbox token not configured'}), 500
        
        url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{lng},{lat}.json"
        params = {
            'access_token': mapbox_token,
            'types': 'address,poi,place,locality',
            'language': 'en',
            'limit': 1
        }
        
        print(f"Calling Mapbox API: {url}")
        
        response = requests.get(url, params=params, timeout=5)
        print(f"Mapbox response status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ Mapbox error: {response.text[:200]}")
            return jsonify({'error': f'Failed to geocode: {response.status_code}'}), 500
        
        data = response.json()
        print(f"Mapbox response keys: {list(data.keys())}")
        
        if data.get('features') and len(data['features']) > 0:
            feature = data['features'][0]
            print(f"✅ Found address: {feature['place_name']}")
            print("="*60 + "\n")
            return jsonify({
                'success': True,
                'address': feature['place_name'],
                'place_id': feature['id']
            })
        else:
            print("❌ No address found for these coordinates")
            print("="*60 + "\n")
            return jsonify({'error': 'No address found'}), 404
            
    except requests.exceptions.Timeout:
        print("❌ Mapbox API timeout")
        return jsonify({'error': 'Mapbox API timeout'}), 500
    except requests.exceptions.RequestException as e:
        print(f"❌ Mapbox request error: {e}")
        return jsonify({'error': f'Mapbox request failed: {str(e)}'}), 500
    except Exception as e:
        print(f"❌ Unexpected error in reverse_geocode: {str(e)}")
        import traceback
        traceback.print_exc()
        print("="*60 + "\n")
        return jsonify({'error': str(e)}), 500
'''
# ADD THIS DEBUG ENDPOINT
@templates_bp.route('/debug/mapbox-config')
def debug_mapbox_config():
    """Debug endpoint to check Mapbox configuration"""
    mapbox_token = os.getenv('MAPBOX_PUBLIC_TOKEN')
    return jsonify({
        'token_exists': mapbox_token is not None,
        'token_preview': mapbox_token[:15] + '...' if mapbox_token else None,
        'token_length': len(mapbox_token) if mapbox_token else 0,
        'env_keys': list(os.environ.keys())  # BE CAREFUL - this exposes all env vars!
    })
'''



@templates_bp.route('/api/laguna/municipalities', methods=['GET'])
def get_laguna_municipalities():
    """Get all municipalities in Laguna"""
    try:
        municipalities = get_municipalities()
        return jsonify({
            'success': True,
            'municipalities': municipalities
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@templates_bp.route('/api/laguna/barangays/<municipality>', methods=['GET'])
def get_municipality_barangays(municipality):
    """Get all barangays for a specific municipality"""
    try:
        barangays = get_barangays(municipality)
        coordinates = get_coordinates(municipality)
        
        return jsonify({
            'success': True,
            'municipality': municipality,
            'barangays': barangays,
            'coordinates': coordinates
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@templates_bp.route('/api/account/addresses', methods=['GET'])
def get_user_addresses():
    """Get all addresses for the logged-in user (supports JWT and sessions)"""
    user_id = get_authenticated_user_id()
    if not user_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        addresses = UserAddress.query.filter_by(user_id=user_id).order_by(
            UserAddress.is_default.desc(),
            UserAddress.created_at.desc()
        ).all()
        
        print(f"✅ Retrieved {len(addresses)} addresses for user {user_id}")
        
        return jsonify({
            'success': True,
            'addresses': [addr.to_dict() for addr in addresses]
        })
    except Exception as e:
        print(f"❌ Error fetching addresses: {str(e)}")
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/account/addresses', methods=['POST'])
def add_user_address():
    """Add a new address for the user (supports JWT and sessions)"""
    user_id = get_authenticated_user_id()
    if not user_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        data = request.get_json()
        
        # Validate required fields
        required = ['municipality', 'barangay', 'address_label', 'latitude', 'longitude']
        for field in required:
            if field not in data or data[field] is None:
                return jsonify({'error': f'{field} is required'}), 400
        
        # Format the complete address
        address_line = format_address(
            data['municipality'],
            data['barangay'],
            data.get('street'),
            data.get('building_details')
        )
        
        # If this is set as default, unset other defaults
        if data.get('is_default'):
            UserAddress.query.filter_by(
                user_id=user_id,
                is_default=True
            ).update({'is_default': False})
        
        # Create new address with EXACT coordinates and place_id from Mapbox
        address = UserAddress(
            user_id=user_id,
            municipality=data['municipality'],
            barangay=data['barangay'],
            street=data.get('street'),
            building_details=data.get('building_details'),
            address_line=address_line,
            latitude=float(data['latitude']),    # EXACT from map
            longitude=float(data['longitude']),  # EXACT from map
            place_id=data.get('place_id'),        # Mapbox place_id (optional)
            address_label=data['address_label'],
            is_default=data.get('is_default', False)
        )
        
        db.session.add(address)
        db.session.commit()
        
        print(f"✅ Address created for user {user_id}: {address_line}")
        
        return jsonify({
            'success': True,
            'message': 'Address added successfully',
            'address': address.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error adding address: {str(e)}")
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/account/addresses/<int:address_id>', methods=['PUT'])
def update_user_address(address_id):
    """Update an existing address (supports JWT and sessions)"""
    user_id = get_authenticated_user_id()
    if not user_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        address = UserAddress.query.filter_by(
            id=address_id,
            user_id=user_id
        ).first()
        
        if not address:
            return jsonify({'error': 'Address not found'}), 404
        
        data = request.get_json()
        
        # Update fields
        if 'municipality' in data:
            address.municipality = data['municipality']
        if 'barangay' in data:
            address.barangay = data['barangay']
        if 'street' in data:
            address.street = data['street']
        if 'building_details' in data:
            address.building_details = data['building_details']
        if 'address_label' in data:
            address.address_label = data['address_label']
        
        # Update EXACT coordinates from Mapbox (if provided)
        if 'latitude' in data and data['latitude'] is not None:
            address.latitude = float(data['latitude'])
        if 'longitude' in data and data['longitude'] is not None:
            address.longitude = float(data['longitude'])
        
        # Update place_id (if provided)
        if 'place_id' in data:
            address.place_id = data['place_id']
        
        # Reformat address line
        address.address_line = format_address(
            address.municipality,
            address.barangay,
            address.street,
            address.building_details
        )
        
        # Handle default status
        if data.get('is_default'):
            UserAddress.query.filter_by(
                user_id=user_id,
                is_default=True
            ).filter(UserAddress.id != address_id).update({'is_default': False})
            address.is_default = True
        elif 'is_default' in data:
            address.is_default = False
        
        address.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Address updated successfully',
            'address': address.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating address: {str(e)}")
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/account/addresses/<int:address_id>', methods=['DELETE'])
def delete_user_address(address_id):
    """Delete an address (supports JWT and sessions)"""
    user_id = get_authenticated_user_id()
    if not user_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        address = UserAddress.query.filter_by(
            id=address_id,
            user_id=user_id
        ).first()
        
        if not address:
            return jsonify({'error': 'Address not found'}), 404
        
        # If this was the default, make another address default
        if address.is_default:
            next_address = UserAddress.query.filter_by(
                user_id=user_id
            ).filter(UserAddress.id != address_id).first()
            
            if next_address:
                next_address.is_default = True
        
        db.session.delete(address)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Address deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting address: {str(e)}")
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/account/addresses/<int:address_id>/set-default', methods=['POST'])
def set_default_address(address_id):
    """Set an address as default (supports JWT and sessions)"""
    user_id = get_authenticated_user_id()
    if not user_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        address = UserAddress.query.filter_by(
            id=address_id,
            user_id=user_id
        ).first()
        
        if not address:
            return jsonify({'error': 'Address not found'}), 404
        
        # Unset all other defaults
        UserAddress.query.filter_by(
            user_id=user_id,
            is_default=True
        ).update({'is_default': False})
        
        # Set this one as default
        address.is_default = True
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Default address updated',
            'address': address.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500






# ===== MUNICIPALITY BOUNDARY ENDPOINTS =====
@templates_bp.route('/api/municipality-boundaries', methods=['GET'])
def get_municipality_boundaries():
    """Get all municipality boundaries as GeoJSON FeatureCollection"""
    try:
        # Check if the MunicipalityBoundary model exists
        from app.models import MunicipalityBoundary
        
        # Optional: filter by province
        province = request.args.get('province', 'Laguna')
        
        query = MunicipalityBoundary.query
        if province:
            query = query.filter(MunicipalityBoundary.province.ilike(f'%{province}%'))
        
        municipalities = query.order_by(MunicipalityBoundary.name).all()
        
        features = [m.to_geojson() for m in municipalities]
        
        return jsonify({
            'type': 'FeatureCollection',
            'features': features,
            'count': len(features)
        })
    except ImportError:
        return jsonify({'error': 'MunicipalityBoundary model not found'}), 500
    except Exception as e:
        print(f"Error getting boundaries: {e}")
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/municipality/check-contiguity', methods=['POST'])
def check_municipality_contiguity():
    """Check if a list of municipalities are contiguous"""
    try:
        from app.models import MunicipalityBoundary
        from geoalchemy2.functions import ST_Touches
        
        data = request.get_json()
        municipalities = data.get('municipalities', [])
        province = data.get('province', 'Laguna')
        
        if not municipalities:
            return jsonify({'contiguous': True, 'message': 'No municipalities selected'})
        
        if len(municipalities) <= 1:
            return jsonify({'contiguous': True, 'message': 'Single municipality is always contiguous'})
        
        # Get all municipality boundaries for the selected names
        boundaries = MunicipalityBoundary.query.filter(
            MunicipalityBoundary.name.in_(municipalities),
            MunicipalityBoundary.province.ilike(f'%{province}%')
        ).all()
        
        if len(boundaries) != len(municipalities):
            return jsonify({
                'contiguous': False, 
                'error': 'Some municipalities not found in database'
            }), 404
        
        # Create name to id mapping
        name_to_boundary = {b.name: b for b in boundaries}
        
        # BFS to check connectivity
        visited = set()
        queue = [municipalities[0]]
        visited.add(municipalities[0])
        
        while queue:
            current = queue.pop(0)
            current_boundary = name_to_boundary[current]
            
            # Find all neighbors that are in our list and not visited
            for neighbor_name in municipalities:
                if neighbor_name in visited:
                    continue
                
                neighbor_boundary = name_to_boundary[neighbor_name]
                
                # Check if they touch using SQL
                from app.extensions import db
                result = db.session.query(
                    ST_Touches(current_boundary.boundary, neighbor_boundary.boundary)
                ).scalar()
                
                if result:
                    visited.add(neighbor_name)
                    queue.append(neighbor_name)
        
        is_contiguous = len(visited) == len(municipalities)
        
        return jsonify({
            'contiguous': is_contiguous,
            'selected_count': len(municipalities),
            'connected_count': len(visited),
            'message': 'Municipalities are contiguous' if is_contiguous else 'Municipalities are not contiguous'
        })
        
    except ImportError:
        return jsonify({'error': 'MunicipalityBoundary model not found'}), 500
    except Exception as e:
        print(f"Error checking contiguity: {e}")
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/municipality/merge-boundaries', methods=['POST'])
def merge_municipality_boundaries():
    """Merge multiple municipality boundaries into one MultiPolygon"""
    try:
        from app.models import MunicipalityBoundary
        from sqlalchemy import text
        
        data = request.get_json()
        municipalities = data.get('municipalities', [])
        province = data.get('province', 'Laguna')
        
        if not municipalities:
            return jsonify({'error': 'No municipalities provided'}), 400
        
        # Use PostGIS ST_Union to merge boundaries
        placeholders = ','.join([f"'{m}'" for m in municipalities])
        query = text(f"""
            SELECT ST_AsGeoJSON(ST_Union(boundary)) as geometry
            FROM municipality_boundaries
            WHERE name IN ({placeholders})
            AND province ILIKE :province
        """)
        
        from app.extensions import db
        result = db.session.execute(query, {'province': f'%{province}%'}).fetchone()
        
        if not result or not result[0]:
            return jsonify({'error': 'Could not merge boundaries'}), 404
        
        import json
        geometry = json.loads(result[0])
        
        return jsonify({
            'success': True,
            'type': 'Feature',
            'geometry': geometry,
            'municipalities': municipalities
        })
        
    except ImportError:
        return jsonify({'error': 'MunicipalityBoundary model not found'}), 500
    except Exception as e:
        print(f"Error merging boundaries: {e}")
        return jsonify({'error': str(e)}), 500

























# ===== PRODUCT VARIANT ROUTES =====
@templates_bp.route('/api/seller/products/<int:product_id>/variants', methods=['GET'])
@seller_required
def get_product_variants(product_id):
    """Get all variants for a product"""
    try:
        store = Store.query.filter_by(seller_id=session['user_id']).first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        variants = [v.to_dict() for v in product.variants]
        
        return jsonify({
            'success': True,
            'variants': variants
        })
        
    except Exception as e:
        print(f"Error getting variants: {str(e)}")
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/seller/variants/<int:variant_id>', methods=['GET'])
@seller_required
def get_variant(variant_id):
    """Get a single variant by ID"""
    try:
        store = Store.query.filter_by(seller_id=session['user_id']).first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        variant = ProductVariant.query.get(variant_id)
        if not variant:
            return jsonify({'error': 'Variant not found'}), 404
        
        # Verify product belongs to seller's store
        if variant.product.store_id != store.id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        return jsonify({
            'success': True,
            'variant': variant.to_dict()
        })
        
    except Exception as e:
        print(f"Error getting variant: {str(e)}")
        return jsonify({'error': str(e)}), 500

@templates_bp.route('/api/seller/variants/create', methods=['POST'])
@seller_required
def create_variant():
    """Create a new product variant"""
    print("\n" + "="*60)
    print("📥 CREATE VARIANT REQUEST RECEIVED")
    
    try:
        store = Store.query.filter_by(seller_id=session['user_id']).first()
        if not store:
            print("❌ Store not found")
            return jsonify({'error': 'Store not found'}), 404
        
        # Debug: Print all form data
        print(f"📋 Form data keys: {list(request.form.keys())}")
        print(f"📋 Form data values:")
        for key in request.form.keys():
            print(f"   {key}: {request.form.get(key)}")
        
        print(f"📎 Files: {list(request.files.keys())}")
        
        product_id = request.form.get('product_id')
        if not product_id:
            print("❌ Product ID is missing")
            return jsonify({'error': 'Product ID is required'}), 400
        
        try:
            product_id = int(product_id)
        except ValueError:
            print(f"❌ Invalid product_id format: {product_id}")
            return jsonify({'error': 'Invalid product ID format'}), 400
        
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            print(f"❌ Product {product_id} not found in store {store.id}")
            return jsonify({'error': 'Product not found'}), 404
        
        name = request.form.get('name')
        price = request.form.get('price')
        stock_quantity = request.form.get('stock_quantity')
        
        print(f"📝 Variant data - Name: {name}, Price: {price}, Stock: {stock_quantity}")
        
        if not name:
            print("❌ Name is missing")
            return jsonify({'error': 'Variant name is required'}), 400
        if not price:
            print("❌ Price is missing")
            return jsonify({'error': 'Price is required'}), 400
        if not stock_quantity:
            print("❌ Stock quantity is missing")
            return jsonify({'error': 'Stock quantity is required'}), 400
        
        try:
            price_float = float(price)
            if price_float < 0:
                print(f"❌ Price cannot be negative: {price_float}")
                return jsonify({'error': 'Price cannot be negative'}), 400
        except ValueError as e:
            print(f"❌ Invalid price format: {price} - {e}")
            return jsonify({'error': 'Invalid price format'}), 400
        
        try:
            stock_int = int(stock_quantity)
            if stock_int < 0:
                print(f"❌ Stock cannot be negative: {stock_int}")
                return jsonify({'error': 'Stock quantity cannot be negative'}), 400
        except ValueError as e:
            print(f"❌ Invalid stock format: {stock_quantity} - {e}")
            return jsonify({'error': 'Invalid stock quantity format'}), 400
        
        # Parse attributes JSON if provided
        attributes = None
        attributes_str = request.form.get('attributes')
        if attributes_str:
            print(f"📋 Attributes string: {attributes_str}")
            try:
                attributes = json.loads(attributes_str)
                print(f"✅ Parsed attributes: {attributes}")
            except json.JSONDecodeError as e:
                print(f"❌ Invalid attributes JSON: {e}")
                return jsonify({'error': 'Invalid attributes JSON'}), 400
        
        # Handle variant image upload
        image_filename = None
        if 'image' in request.files:
            file = request.files['image']
            print(f"📸 Image file received: {file.filename if file.filename else 'None'}")
            
            if file and file.filename and allowed_file(file.filename):
                # Create variant images directory if it doesn't exist
                variant_upload_path = os.path.join(BASE_DIR, 'static', 'uploads', 'product_variants')
                os.makedirs(variant_upload_path, exist_ok=True)
                
                # Generate filename
                ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
                timestamp = str(int(time.time()))[-6:]
                random_str = uuid.uuid4().hex[:8]
                image_filename = f"v{product_id}_{timestamp}_{random_str}.{ext}"
                
                filepath = os.path.join(variant_upload_path, image_filename)
                file.save(filepath)
                print(f"✅ Saved variant image: {image_filename}")
            else:
                print(f"⚠️ Invalid file or not allowed: {file.filename if file.filename else 'No file'}")
        
        # Get max sort order
        max_sort = db.session.query(db.func.max(ProductVariant.sort_order)).filter_by(product_id=product.id).scalar() or 0
        print(f"📊 Max sort order: {max_sort}, new sort order: {max_sort + 1}")
        
        is_available = request.form.get('is_available', 'true').lower()
        print(f"🔘 is_available: {is_available}")
        
        variant = ProductVariant(
            product_id=product.id,
            name=name.strip(),
            price=price_float,
            stock_quantity=stock_int,
            sku=request.form.get('sku') or None,
            image_filename=image_filename,
            attributes=attributes,
            sort_order=max_sort + 1,
            is_available=is_available == 'true'
        )
        
        db.session.add(variant)
        db.session.commit()
        
        print(f"✅ Variant created successfully with ID: {variant.id}")
        print("="*60 + "\n")
        
        return jsonify({
            'success': True,
            'message': 'Variant created successfully',
            'variant': variant.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error creating variant: {str(e)}")
        import traceback
        traceback.print_exc()
        print("="*60 + "\n")
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/seller/variants/<int:variant_id>', methods=['PUT'])
@seller_required
def update_variant(variant_id):
    """Update a product variant"""
    try:
        store = Store.query.filter_by(seller_id=session['user_id']).first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        variant = ProductVariant.query.get(variant_id)
        if not variant:
            return jsonify({'error': 'Variant not found'}), 404
        
        # Verify product belongs to seller's store
        if variant.product.store_id != store.id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Update fields
        if request.form.get('name'):
            variant.name = request.form.get('name').strip()
        
        if request.form.get('price'):
            try:
                variant.price = float(request.form.get('price'))
            except ValueError:
                return jsonify({'error': 'Invalid price format'}), 400
        
        if request.form.get('stock_quantity'):
            try:
                variant.stock_quantity = int(request.form.get('stock_quantity'))
            except ValueError:
                return jsonify({'error': 'Invalid stock quantity format'}), 400
        
        if request.form.get('sku') is not None:
            variant.sku = request.form.get('sku') or None
        
        if request.form.get('attributes'):
            try:
                variant.attributes = json.loads(request.form.get('attributes'))
            except:
                return jsonify({'error': 'Invalid attributes JSON'}), 400
        elif 'attributes' in request.form:
            variant.attributes = None
        
        if request.form.get('is_available') is not None:
            variant.is_available = request.form.get('is_available').lower() == 'true'
        
        # Handle variant image upload
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename):
                # Delete old image if exists
                if variant.image_filename:
                    old_path = os.path.join(BASE_DIR, 'static', 'uploads', 'product_variants', variant.image_filename)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                
                # Save new image
                variant_upload_path = os.path.join(BASE_DIR, 'static', 'uploads', 'product_variants')
                os.makedirs(variant_upload_path, exist_ok=True)
                
                ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
                timestamp = str(int(time.time()))[-6:]
                random_str = uuid.uuid4().hex[:8]
                image_filename = f"v{variant.product_id}_{timestamp}_{random_str}.{ext}"
                
                filepath = os.path.join(variant_upload_path, image_filename)
                file.save(filepath)
                variant.image_filename = image_filename
                print(f"📸 Updated variant image: {image_filename}")
        
        variant.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Variant updated successfully',
            'variant': variant.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating variant: {str(e)}")
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/seller/variants/<int:variant_id>', methods=['DELETE'])
@seller_required
def delete_variant(variant_id):
    """Delete a product variant"""
    try:
        store = Store.query.filter_by(seller_id=session['user_id']).first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        variant = ProductVariant.query.get(variant_id)
        if not variant:
            return jsonify({'error': 'Variant not found'}), 404
        
        # Verify product belongs to seller's store
        if variant.product.store_id != store.id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Check if variant is in any carts or orders
        cart_count = CartItem.query.filter_by(variant_id=variant_id).count()
        order_count = OrderItem.query.filter_by(variant_id=variant_id).count()
        pos_count = POSOrderItem.query.filter_by(variant_id=variant_id).count()
        
        if cart_count > 0 or order_count > 0 or pos_count > 0:
            return jsonify({
                'error': f'Cannot delete. Variant is in {cart_count} carts and {order_count + pos_count} orders.'
            }), 400
        
        # Delete image file if exists
        if variant.image_filename:
            image_path = os.path.join(BASE_DIR, 'static', 'uploads', 'product_variants', variant.image_filename)
            if os.path.exists(image_path):
                os.remove(image_path)
        
        db.session.delete(variant)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Variant deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting variant: {str(e)}")
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/seller/variants/reorder', methods=['POST'])
@seller_required
def reorder_variants():
    """Reorder variants for a product"""
    try:
        store = Store.query.filter_by(seller_id=session['user_id']).first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        data = request.get_json()
        product_id = data.get('product_id')
        variant_order = data.get('variant_order', [])  # List of variant IDs in desired order
        
        if not product_id or not variant_order:
            return jsonify({'error': 'Product ID and variant order required'}), 400
        
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        for index, variant_id in enumerate(variant_order):
            variant = ProductVariant.query.get(variant_id)
            if variant and variant.product_id == product.id:
                variant.sort_order = index
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Variants reordered successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error reordering variants: {str(e)}")
        return jsonify({'error': str(e)}), 500
    



@templates_bp.route('/seller/products/add')
@seller_required
def add_product_page():
    """Render the add/edit product page"""
    product_id = request.args.get('edit')
    is_edit = bool(product_id)
    product = None
    
    # ===== ADD THIS: Get all main categories =====
    from app.models import Category
    main_categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()
    # =============================================
    
    if is_edit:
        # Convert product_id to integer
        try:
            product_id = int(product_id)
        except (TypeError, ValueError):
            flash('Invalid product ID', 'error')
            return redirect(url_for('templates.seller_products'))
        
        store = _get_seller_store()
        if not store:
            flash('Store not found', 'error')
            return redirect(url_for('templates.seller_products'))
        
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            flash('Product not found', 'error')
            return redirect(url_for('templates.seller_products'))
    
    return render_template('add_product.html', 
                         is_edit=is_edit, 
                         product=product,
                         main_categories=main_categories)  # ← Pass to template








@templates_bp.route('/api/store/<int:store_id>/gcash-qrs', methods=['GET'])
def get_store_gcash_qrs(store_id):
    """Get GCash QR codes for a store (for checkout page)"""
    try:
        store = Store.query.get_or_404(store_id)
        
        # Build QR code URLs
        qr_codes = []
        if store.gcash_qr_codes:
            qr_codes_list = store.gcash_qr_codes
            if isinstance(qr_codes_list, str):
                try:
                    qr_codes_list = json.loads(qr_codes_list)
                except:
                    qr_codes_list = []
            
            for i, filename in enumerate(qr_codes_list):
                if filename:
                    qr_codes.append({
                        'url': f'/static/uploads/gcash_qr/{filename}',
                        'is_primary': (i == 0)
                    })
        
        return jsonify({
            'success': True,
            'qr_codes': qr_codes,
            'instructions': store.gcash_instructions
        })
        
    except Exception as e:
        print(f"Error getting GCash QR codes: {str(e)}")
        return jsonify({'error': str(e)}), 500
    



@templates_bp.route('/api/seller/store/gcash-qr/<path:filename>', methods=['DELETE'])
@seller_required
def delete_gcash_qr(filename):
    """Delete a specific GCash QR code"""
    try:
        store = Store.query.filter_by(seller_id=session['user_id']).first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        # Security: Prevent directory traversal
        if '..' in filename or filename.startswith('/'):
            return jsonify({'error': 'Invalid filename'}), 400
        
        # Check if QR code exists in store's list
        qr_codes = store.gcash_qr_codes or []
        if isinstance(qr_codes, str):
            try:
                qr_codes = json.loads(qr_codes)
            except:
                qr_codes = []
        
        if filename not in qr_codes:
            return jsonify({'error': 'QR code not found'}), 404
        
        # Delete file
        gcash_upload_path = os.path.join(BASE_DIR, 'static', 'uploads', 'gcash_qr')
        file_path = os.path.join(gcash_upload_path, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"🗑️ Deleted QR code file: {filename}")
        
        # Remove from list
        qr_codes.remove(filename)
        store.gcash_qr_codes = qr_codes
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'QR code deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting QR code: {str(e)}")
        return jsonify({'error': str(e)}), 500
    


@templates_bp.route('/seller/products/images-count', methods=['POST'])
@seller_required
def get_products_image_count():
    """Get total Cloudinary image count for selected products"""
    try:
        store = Store.query.filter_by(seller_id=session.get('user_id')).first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        data = request.get_json()
        product_ids = data.get('product_ids', [])
        
        if not product_ids:
            return jsonify({'total_images': 0})
        
        total_images = 0
        
        for product_id in product_ids:
            product = Product.query.filter_by(id=product_id, store_id=store.id).first()
            if product:
                # Count product images
                total_images += len(product.images)
                
                # Count variant images
                for variant in product.variants:
                    if variant.image_public_id:
                        total_images += 1
        
        return jsonify({'total_images': total_images})
        
    except Exception as e:
        print(f"Error counting images: {e}")
        return jsonify({'error': str(e)}), 500
    
@templates_bp.route('/api/v1/cloudinary/upload', methods=['POST', 'OPTIONS'])
def cloudinary_upload():
    """Upload an image directly to Cloudinary and return the result
    Supports both sellers and customers (customers can upload avatars, sellers can upload products)
    """
    # Handle preflight OPTIONS request for CORS
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, X-CSRFToken, X-Requested-With')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response
    
    try:
        # Log the request for debugging
        print("\n" + "="*60)
        print("📤 CLOUDINARY UPLOAD REQUEST RECEIVED")
        print(f"Session user_id: {session.get('user_id')}")
        print(f"Session role: {session.get('role')}")
        print(f"Content Type: {request.content_type}")
        print(f"Files keys: {list(request.files.keys())}")
        print(f"Form keys: {list(request.form.keys())}")
        
        # Check if user is authenticated (any role can upload)
        if 'user_id' not in session:
            print("❌ User not authenticated")
            return jsonify({
                'success': False, 
                'error': 'Not authenticated. Please log in first.'
            }), 401
        
        # Get the user to verify they exist
        user = User.query.get(session['user_id'])
        if not user:
            print(f"❌ User {session['user_id']} not found in database")
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        # Check if file exists
        if 'file' not in request.files:
            print("❌ No file in request")
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        if not file or not file.filename:
            print("❌ Empty file")
            return jsonify({'success': False, 'error': 'Empty file'}), 400
        
        folder = request.form.get('folder', 'e-flowers/temp')
        print(f"📁 Folder: {folder}")
        print(f"📄 Filename: {file.filename}")
        print(f"📄 File size: {file.tell()} bytes")
        
        # Validate file type
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        if '.' in file.filename:
            ext = file.filename.rsplit('.', 1)[1].lower()
            if ext not in allowed_extensions:
                print(f"❌ Invalid file extension: {ext}")
                return jsonify({
                    'success': False, 
                    'error': f'Invalid file type. Allowed: {", ".join(allowed_extensions)}'
                }), 400
        
        # Validate file size (max 10MB)
        file.seek(0, 2)  # Seek to end
        file_size = file.tell()
        file.seek(0)  # Reset to beginning
        max_size = 10 * 1024 * 1024  # 10MB
        
        if file_size > max_size:
            print(f"❌ File too large: {file_size} bytes")
            return jsonify({
                'success': False, 
                'error': f'File too large. Maximum size is 10MB.'
            }), 400
        
        # Import Cloudinary helper
        from app.utils.cloudinary_helper import upload_to_cloudinary, should_use_cloudinary
        
        # Check if Cloudinary is configured
        if not should_use_cloudinary():
            print("❌ Cloudinary not configured")
            return jsonify({
                'success': False, 
                'error': 'Cloudinary is not configured. Please contact support.'
            }), 500
        
        # Upload to Cloudinary
        print("⏫ Uploading to Cloudinary...")
        result = upload_to_cloudinary(file, folder)
        
        if result['success']:
            print(f"✅ Upload successful: {result['public_id']}")
            print(f"🔗 URL: {result['url']}")
            print(f"📊 Format: {result.get('format')}, Size: {result.get('width')}x{result.get('height')}")
            
            response = jsonify({
                'success': True,
                'public_id': result['public_id'],
                'url': result['url'],
                'format': result.get('format'),
                'width': result.get('width'),
                'height': result.get('height'),
                'bytes': result.get('bytes')
            })
            
            # Add CORS headers for development
            response.headers.add('Access-Control-Allow-Origin', '*')
            return response
        else:
            print(f"❌ Upload failed: {result.get('error', 'Unknown error')}")
            return jsonify({
                'success': False, 
                'error': result.get('error', 'Upload failed')
            }), 500
            
    except Exception as e:
        print(f"❌ Cloudinary upload error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False, 
            'error': f'Server error: {str(e)}'
        }), 500


















'''

@templates_bp.route('/api/seller/pos/next-order-id', methods=['GET'])
@seller_required
def get_next_pos_order_id():
    """Get the next available POS order ID"""
    store = _get_seller_store()
    if not store:
        return jsonify({'error': 'No active store.'}), 403
    
    # Get the latest order
    latest_order = POSOrder.query.filter_by(store_id=store.id).order_by(POSOrder.id.desc()).first()
    
    if latest_order:
        next_id = latest_order.id + 1
    else:
        next_id = 1  # Start from 1 if no orders exist
    
    return jsonify({'next_id': next_id})
'''



'''
@templates_bp.route('/seller/pos/orders')
@seller_required
def seller_pos_orders():
    """Render the POS orders history page"""
    store = _get_seller_store()
    if not store:
        return redirect(url_for('templates.dashboard'))
    
    return render_template('seller_pos_orders.html', store=store)
'''
@templates_bp.route('/api/seller/pos/orders/<int:order_id>', methods=['GET'])
@seller_required
def pos_order_detail_api(order_id):
    store = _get_seller_store()
    if not store:
        return jsonify({'error': 'No active store found'}), 403
    
    try:
        order = POSOrder.query.filter_by(id=order_id, store_id=store.id).first()
        if not order:
            return jsonify({'error': 'Order not found'}), 404
        
        items = []
        subtotal = 0
        for item in order.items:
            product_name = 'Unknown Product'
            if item.product:
                product_name = item.product.name
            if item.variant_id and item.variant:
                product_name = f"{product_name} - {item.variant.name}"
            item_subtotal = float(item.price * item.quantity)
            subtotal += item_subtotal
            items.append({
                'id': item.id,
                'product_id': item.product_id,
                'variant_id': item.variant_id,
                'product_name': product_name,
                'quantity': item.quantity,
                'unit_price': float(item.price),
                'subtotal': item_subtotal
            })

        # created_at is stored as PH local time (naive datetime), NOT UTC.
        # Just label it with +08:00 offset directly — no UTC conversion needed.
        created_at_iso = None
        created_at_date = None
        if order.created_at:
            created_at_iso  = order.created_at.strftime('%Y-%m-%dT%H:%M:%S+00:00')
            created_at_date = order.created_at.strftime('%Y-%m-%d')

        return jsonify({
            'id': order.id,
            'created_at': created_at_iso,
            'created_at_date': created_at_date,
            'customer_name': order.customer_name or 'Walk-in',
            'customer_contact': order.customer_contact,
            'payment_method': order.payment_method or 'cash',
            'amount_given': float(order.amount_given) if order.amount_given else 0,
            'change_amount': float(order.change_amount) if order.change_amount else 0,
            'total_amount': float(order.total_amount) if order.total_amount else 0,
            'subtotal': subtotal,
            'discount': float(order.discount or 0),
            'items': items,
            'item_count': len(items)
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@templates_bp.route('/api/seller/pos/orders', methods=['GET'])
@seller_required
def pos_order_history_api():
    """API endpoint to get POS orders data (returns JSON)"""
    store = _get_seller_store()
    if not store:
        return jsonify({'error': 'No active store.'}), 403

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    date_filter = request.args.get('date', 'this_week')
    payment_filter = request.args.get('payment', 'all')
    search_query = request.args.get('search', '')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = POSOrder.query.filter_by(store_id=store.id)

    # ── Date filtering ────────────────────────────────────────────────────────
    # created_at is stored as PH local time (naive datetime), NOT UTC.
    # So we compare directly using PH local date boundaries — no UTC conversion.
    import pytz
    ph_tz = pytz.timezone('Asia/Manila')
    today_ph = datetime.now(ph_tz).date()

    if date_filter == 'today':
        start = datetime(today_ph.year, today_ph.month, today_ph.day, 0, 0, 0)
        end   = datetime(today_ph.year, today_ph.month, today_ph.day, 23, 59, 59)
        query = query.filter(POSOrder.created_at >= start, POSOrder.created_at <= end)

    elif date_filter == 'yesterday':
        yesterday = today_ph - timedelta(days=1)
        start = datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0)
        end   = datetime(yesterday.year, yesterday.month, yesterday.day, 23, 59, 59)
        query = query.filter(POSOrder.created_at >= start, POSOrder.created_at <= end)

    elif date_filter == 'this_week':
        start_of_week = today_ph - timedelta(days=today_ph.weekday())  # Monday
        start = datetime(start_of_week.year, start_of_week.month, start_of_week.day, 0, 0, 0)
        query = query.filter(POSOrder.created_at >= start)

    elif date_filter == 'this_month':
        start_of_month = today_ph.replace(day=1)
        start = datetime(start_of_month.year, start_of_month.month, start_of_month.day, 0, 0, 0)
        query = query.filter(POSOrder.created_at >= start)

    elif date_filter == 'custom' and start_date and end_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').replace(hour=0, minute=0, second=0)
            end   = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            query = query.filter(POSOrder.created_at >= start, POSOrder.created_at <= end)
        except ValueError:
            pass

    # ── Payment filter ────────────────────────────────────────────────────────
    if payment_filter != 'all':
        query = query.filter_by(payment_method=payment_filter)

    # ── Search filter ─────────────────────────────────────────────────────────
    if search_query:
        query = query.filter(
            db.or_(
                POSOrder.customer_name.ilike(f'%{search_query}%'),
                POSOrder.customer_contact.ilike(f'%{search_query}%'),
                db.cast(POSOrder.id, db.String).ilike(f'%{search_query}%')
            )
        )

    # ── Paginate ──────────────────────────────────────────────────────────────
    pagination = query.order_by(POSOrder.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # ── Serialize ─────────────────────────────────────────────────────────────
    # created_at is stored as PH local time, so we just label it with +08:00
    # offset directly — no UTC conversion needed.
    orders = []
    for o in pagination.items:
        subtotal   = sum(float(item.price * item.quantity) for item in o.items)
        item_count = sum(item.quantity for item in o.items)

        if o.created_at:
            created_at_iso  = o.created_at.strftime('%Y-%m-%dT%H:%M:%S+00:00')
            created_at_date = o.created_at.strftime('%Y-%m-%d')
        else:
            created_at_iso  = None
            created_at_date = None

        orders.append({
            'id':             o.id,
            'created_at':     created_at_iso,
            'created_at_date': created_at_date,
            'customer_name':  o.customer_name or 'Walk-in',
            'customer_contact': o.customer_contact,
            'item_count':     item_count,
            'subtotal':       float(subtotal),
            'discount':       float(o.discount or 0),
            'total_amount':   float(o.total_amount) if o.total_amount else 0,
            'amount_given':   float(o.amount_given) if o.amount_given else 0,
            'change_amount':  float(o.change_amount) if o.change_amount else 0,
            'payment_method': o.payment_method or 'cash'
        })

    return jsonify({
        'orders':       orders,
        'total':        pagination.total,
        'pages':        pagination.pages,
        'current_page': pagination.page,
        'has_next':     pagination.has_next,
        'has_prev':     pagination.has_prev,
    })


@templates_bp.route('/seller/pos/orders')
@seller_required
def seller_pos_orders():
    """Render the POS orders history page - JS loads data via API"""
    store = _get_seller_store()
    if not store:
        flash('Please set up your store first.', 'warning')
        return redirect(url_for('templates.dashboard'))
    
    return render_template('seller_pos_orders.html', store=store)



























@templates_bp.route('/store/<int:store_id>/category/<int:category_id>')
def store_category(store_id, category_id):
    """View products in a store-specific subcategory"""
    from app.models import Store, StoreCategory, Product
    
    store = Store.query.get_or_404(store_id)
    category = StoreCategory.query.get_or_404(category_id)
    
    # Verify category belongs to store
    if category.store_id != store_id:
        os.abort(404)
    
    products = Product.query.filter_by(
        store_id=store_id,
        store_category_id=category_id,
        is_archived=False,
        is_available=True
    ).all()
    
    return render_template('store_category.html',
                         store=store,
                         category=category,
                         products=products)


@templates_bp.route('/api/store/categories', methods=['GET'])
@seller_required
def get_store_categories():
    """Get store-specific subcategories for a main category"""
    main_category_id = request.args.get('main_category_id')
    store = _get_seller_store()
    
    if not store:
        return jsonify({'success': False, 'error': 'Store not found'}), 404
    
    if not main_category_id:
        return jsonify({'success': False, 'error': 'Main category ID required'}), 400
    
    from app.models import StoreCategory
    
    categories = StoreCategory.query.filter_by(
        store_id=store.id,
        main_category_id=main_category_id,
        is_active=True
    ).order_by(StoreCategory.sort_order).all()
    
    return jsonify({
        'success': True,
        'categories': [cat.to_dict() for cat in categories]
    })


@templates_bp.route('/api/store/categories/create', methods=['POST'])
@seller_required
def create_store_category():
    """Create a new store-specific subcategory"""
    data = request.get_json()
    store = _get_seller_store()
    
    if not store:
        return jsonify({'success': False, 'error': 'Store not found'}), 404
    
    main_category_id = data.get('main_category_id')
    name = data.get('name', '').strip()
    description = data.get('description', '').strip()
    
    if not main_category_id:
        return jsonify({'success': False, 'error': 'Main category ID required'}), 400
    
    if not name:
        return jsonify({'success': False, 'error': 'Subcategory name required'}), 400
    
    from app.models import StoreCategory, Category
    
    # Verify main category exists
    main_category = Category.query.get(main_category_id)
    if not main_category:
        return jsonify({'success': False, 'error': 'Main category not found'}), 404
    
    # Check if subcategory already exists for this store
    existing = StoreCategory.query.filter_by(
        store_id=store.id,
        name=name
    ).first()
    
    if existing:
        return jsonify({'success': False, 'error': 'Subcategory already exists'}), 400
    
    # Create slug
    import re
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    slug = f"{slug}-{store.id}"
    
    subcategory = StoreCategory(
        store_id=store.id,
        main_category_id=main_category_id,
        name=name,
        slug=slug,
        description=description
    )
    
    db.session.add(subcategory)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'category': subcategory.to_dict()
    })
