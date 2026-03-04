# app/templates_routes.py - FIXED VERSION
from datetime import datetime
from flask import Blueprint, app, flash, make_response, render_template, jsonify, request, session, redirect, url_for, current_app
from app.archive_routes import get_seller_store
from app.models import MunicipalityBoundary, OrderItem, User, Store, Rider, Product, Order, SellerApplication, Cart, CartItem, ProductImage, POSOrder, POSOrderItem, Testimonial, MunicipalityBoundary
from app.extensions import db
import os
from werkzeug.utils import secure_filename
from functools import wraps
from decimal import Decimal
import uuid
import time
import jwt
from PIL import Image
import io
from flask import send_file
from app.laguna_addresses import get_municipalities, get_barangays, get_coordinates, format_address, LAGUNA_ADDRESSES
from app.models import UserAddress

templates_bp = Blueprint('templates', __name__)

# Define upload folder relative to the app root
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'products')

# Or if you want it at the project root (where your app folder is)
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..'))
UPLOAD_FOLDER_ALT = os.path.join(PROJECT_ROOT, 'uploads', 'products')


# Configure upload folder
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


    
@templates_bp.route('/')
def index():
    """Show the e-commerce landing page to everyone"""
    try:
        # Get products for the landing page - only from active stores with stock
        products = Product.query\
            .join(Store, Product.store_id == Store.id)\
            .filter(
                Product.is_archived == False,
                Product.is_available == True,
                Store.status == 'active',
                Product.stock_quantity > 0
            )\
            .order_by(Product.created_at.desc())\
            .limit(8)\
            .all()
        
        print("=== DEBUGGING PRODUCTS ===")
        print(f"Raw products count: {len(products)}")
        for p in products:
            print(f"Product ID: {p.id}, Name: {p.name}, Store ID: {p.store_id}, Store: {p.store.name if p.store else 'None'}")
        
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
        
        print(f"\nFinal product_list count: {len(product_list)}")
        print(f"Final store_list count: {len(store_list)}")
        print("=== END DEBUG ===\n")
        
        categories = [
            {'id': 'flowers', 'name': 'Fresh Flowers', 'icon': 'flower-line'},
            {'id': 'plants', 'name': 'Potted Plants', 'icon': 'plant-line'},
            {'id': 'bouquets', 'name': 'Bouquets', 'icon': 'bouquet-line'},
            {'id': 'succulents', 'name': 'Succulents', 'icon': 'cactus-line'},
        ]
        
        return render_template(
            'index.html',
            products=product_list,
            stores=store_list,
            categories=categories
        )
    except Exception as e:
        print(f"ERROR loading landing page: {str(e)}")
        import traceback
        traceback.print_exc()
        return render_template('index.html', 
                             products=[], 
                             stores=[], 
                             categories=[])
    


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
            
            # Delete images
            from app.templates_routes import BASE_DIR
            upload_path = os.path.join(BASE_DIR, 'static', 'uploads', 'products')
            for image in product.images:
                image_path = os.path.join(upload_path, image.filename)
                if os.path.exists(image_path):
                    os.remove(image_path)
            
            db.session.delete(product)
            db.session.commit()
            return jsonify({
                'success': True,
                'message': 'Product permanently deleted'
            }), 200
            
        else:  # cancel
            return jsonify({
                'success': True,
                'message': 'Action cancelled'
            }), 200
            
    except Exception as e:
        db.session.rollback()
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

def generate_short_filename(original_filename, product_id, index):
    """Generate a short, safe filename for images"""
    if '.' in original_filename:
        ext = original_filename.rsplit('.', 1)[1].lower()
    else:
        ext = 'jpg'
    
    timestamp = str(int(time.time()))[-6:]
    random_str = uuid.uuid4().hex[:8]
    short_filename = f"p{product_id}_{index}_{timestamp}_{random_str}.{ext}"
    return short_filename
    


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


# NEW: Seller Application Routes
@templates_bp.route('/seller/apply', methods=['POST'])
def seller_apply():
    """Handle seller application form submission"""
    if 'user_id' not in session:
        return jsonify({'error': 'Please login first'}), 401
    
    try:
        # Get the user from database (optional, just to verify they exist)
        user = User.query.get(session['user_id'])
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get form data - NO name fields!
        store_name = request.form.get('store_name')
        store_description = request.form.get('store_description')
        
        # Validate required fields
        if not store_name or not store_description:
            return jsonify({'error': 'Please fill in all required fields'}), 400
        
        # Check if user already has a pending application
        existing = SellerApplication.query.filter_by(
            user_id=session['user_id'],
            status='pending'
        ).first()
        
        if existing:
            return jsonify({'error': 'You already have a pending application'}), 400
        
        # Handle store logo upload
        store_logo_filename = None
        if 'store_logo' in request.files:
            file = request.files['store_logo']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # Add timestamp to make filename unique
                import time
                timestamp = str(int(time.time()))
                store_logo_filename = f"{timestamp}_{filename}"
                
                # Get upload path from config
                upload_path = current_app.config['SELLER_LOGO_UPLOAD_FOLDER']
                os.makedirs(upload_path, exist_ok=True)
                
                # Save file
                filepath = os.path.join(upload_path, store_logo_filename)
                file.save(filepath)
        
        # Handle government ID upload
        govt_id_filename = None
        if 'government_id' in request.files:
            file = request.files['government_id']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # Add timestamp to make filename unique
                import time
                timestamp = str(int(time.time()))
                govt_id_filename = f"{timestamp}_{filename}"
                
                # Get upload path from config
                upload_path = current_app.config['SELLER_ID_UPLOAD_FOLDER']
                os.makedirs(upload_path, exist_ok=True)
                
                # Save file
                filepath = os.path.join(upload_path, govt_id_filename)
                file.save(filepath)
        
        # Create seller application - NO name fields!
        application = SellerApplication(
            user_id=session['user_id'],
            # first_name and last_name are GONE!
            store_name=store_name,
            store_description=store_description,
            store_logo_path=store_logo_filename,
            government_id_path=govt_id_filename,
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
    """Update user profile information"""
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
        print(f"📎 File keys: {list(request.files.keys())}")
        
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
        
        # Handle avatar upload
        if 'avatar' in request.files:
            file = request.files['avatar']
            print(f"📸 Avatar file received: {file.filename}")
            print(f"📸 Content type: {file.content_type}")
            
            # Check file size
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)  # Reset file pointer
            print(f"📸 File size: {file_size} bytes ({file_size/1024:.2f} KB)")
            
            # Check file extension
            if file.filename:
                file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'none'
                print(f"📸 File extension: {file_ext}")
                print(f"📸 Allowed extensions: {ALLOWED_EXTENSIONS}")
                print(f"📸 Is allowed: {file_ext in ALLOWED_EXTENSIONS}")
            
            if file and file.filename and allowed_file(file.filename):
                print(f"✅ File is allowed, processing...")
                
                filename = secure_filename(file.filename)
                print(f"🔒 Secure filename: {filename}")
                
                # Add timestamp to make filename unique
                import time
                timestamp = str(int(time.time()))
                avatar_filename = f"{timestamp}_{filename}"
                print(f"🏷️ Final filename: {avatar_filename}")
                
                # Use config UPLOAD_FOLDER
                upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'avatars')
                print(f"📁 Upload path from config: {upload_path}")
                print(f"📁 Config UPLOAD_FOLDER: {current_app.config['UPLOAD_FOLDER']}")
                
                # Make sure directory exists
                os.makedirs(upload_path, exist_ok=True)
                print(f"✅ Ensured directory exists: {os.path.exists(upload_path)}")
                
                # Save file
                filepath = os.path.join(upload_path, avatar_filename)
                print(f"💾 Saving to: {filepath}")
                file.save(filepath)
                
                # Check if file was saved
                if os.path.exists(filepath):
                    saved_size = os.path.getsize(filepath)
                    print(f"✅ File saved successfully! Size: {saved_size} bytes")
                    print(f"📁 Absolute path: {os.path.abspath(filepath)}")
                    
                    # List directory contents
                    print(f"📁 Files in avatars folder:")
                    try:
                        files = os.listdir(upload_path)
                        for f in files[-5:]:  # Show last 5 files
                            f_size = os.path.getsize(os.path.join(upload_path, f))
                            print(f"   - {f} ({f_size} bytes)")
                    except Exception as e:
                        print(f"   Error listing directory: {e}")
                else:
                    print(f"❌ File not found after save!")
                
                # Delete old avatar if exists
                if user.avatar_filename:
                    old_path = os.path.join(upload_path, user.avatar_filename)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                        print(f"🗑️ Deleted old avatar: {old_path}")
                
                user.avatar_filename = avatar_filename
                print(f"✅ Updated user.avatar_filename to: {avatar_filename}")
            else:
                print(f"❌ Invalid file or not allowed")
                if file:
                    print(f"   File exists: {bool(file)}")
                    print(f"   Filename exists: {bool(file.filename)}")
                    if file.filename:
                        print(f"   Extension: {file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'none'}")
                        print(f"   Allowed: {allowed_file(file.filename)}")
        else:
            print("📭 No avatar file in request")
        
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
    
    # Get the page parameter from URL (default to 'profile')
    page = request.args.get('page', 'profile')
    
    # Get user data from database
    user = User.query.get(session['user_id'])
    if not user:
        return redirect(url_for('templates.logout'))
    
    # Convert to dict for template
    user_data = user.to_dict()
    
    # Get Mapbox token from environment variables
    mapbox_token = os.getenv('MAPBOX_PUBLIC_TOKEN', '')
    
    # DEBUG: Print token to console to verify it's loaded
    print(f"🗺️ Mapbox token loaded for my-account: {mapbox_token[:15] if mapbox_token else 'NOT FOUND'}...")
    
    # IMPORTANT: Render the template, don't return JSON!
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
    # Example data - replace with actual database query
    orders = [
        {
            'id': 1,
            'order_number': 'ORD-001',
            'date': '2024-01-15',
            'total': 2499.99,
            'status': 'delivered',
            'items': [
                {'name': 'Rose Bouquet', 'store_name': 'Floral Dreams', 'quantity': 1, 'price': 1499.99},
                {'name': 'Vase', 'store_name': 'Floral Dreams', 'quantity': 1, 'price': 1000.00}
            ]
        },
        {
            'id': 2,
            'order_number': 'ORD-002',
            'date': '2024-01-10',
            'total': 899.99,
            'status': 'processing',
            'items': [
                {'name': 'Tulips', 'store_name': 'Garden Delights', 'quantity': 2, 'price': 449.99}
            ]
        }
    ]
    return jsonify(orders)

@templates_bp.route('/api/account/orders/<int:order_id>')
def order_details(order_id):
    """Return specific order details"""
    # Replace with actual database query
    order = {
        'id': order_id,
        'order_number': f'ORD-{order_id:03d}',
        'date': '2024-01-15',
        'total': 2499.99,
        'status': 'delivered',
        'items': [
            {'name': 'Rose Bouquet', 'store_name': 'Floral Dreams', 'quantity': 1, 'price': 1499.99},
            {'name': 'Vase', 'store_name': 'Floral Dreams', 'quantity': 1, 'price': 1000.00}
        ]
    }
    return jsonify(order)

@templates_bp.route('/api/account/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    """Cancel an order"""
    # Add your cancellation logic here
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




@templates_bp.route('/category/<category_id>')
def category(category_id):
    """Category page for web interface"""
    products = Product.query.filter_by(
        category=category_id, 
        is_available=True
    ).all()
    
    # Convert products to dict and add store_name
    product_list = []
    for product in products:
        product_dict = product.to_dict()
        # Add store name to each product
        if product.store:
            product_dict['store_name'] = product.store.name
            product_dict['store_id'] = product.store.id  # Optional: if you want to link to store
        else:
            product_dict['store_name'] = 'Unknown Store'
            product_dict['store_id'] = None
        product_list.append(product_dict)
    
    return render_template('category.html',
                         category_id=category_id,
                         products=product_list)


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
    """Product detail page"""
    try:
        product = Product.query.get_or_404(product_id)
        store = Store.query.get(product.store_id)
        
        # Get related products
        related_products = Product.query.filter(
            Product.store_id == product.store_id,
            Product.id != product_id,
            Product.is_available == True
        ).limit(4).all()
        
        return render_template('product_detail.html',
                             product=product.to_dict(),
                             store=store.to_dict() if store else None,
                             related_products=[p.to_dict() for p in related_products])
    except Exception as e:
        print(f"Error loading product {product_id}: {str(e)}")
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
def create_product():
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        # Get seller's store
        store = Store.query.filter_by(seller_id=session.get('user_id')).first()
        if not store:
            return jsonify({'error': 'Store not found. Please create a store first.'}), 404
        
        # Get form data
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price')
        stock_quantity = request.form.get('stock_quantity')
        category = request.form.get('category')
        
        # Validate required fields
        if not name or not name.strip():
            return jsonify({'error': 'Product name is required'}), 400
        if not price:
            return jsonify({'error': 'Price is required'}), 400
        if not stock_quantity:
            return jsonify({'error': 'Stock quantity is required'}), 400
        if not category:
            return jsonify({'error': 'Category is required'}), 400
        
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
        
        # Create new product first (without images)
        product = Product(
            store_id=store.id,
            name=name.strip(),
            description=description.strip() if description else None,
            price=price_float,
            stock_quantity=stock_int,
            category=category,
            is_available=True
        )
        
        db.session.add(product)
        db.session.flush()  # Get product ID without committing yet
        
        # Handle multiple image uploads
        image_filenames = []
        upload_path = os.path.join(BASE_DIR, 'static', 'uploads', 'products')
        os.makedirs(upload_path, exist_ok=True)
        
        # Look for image fields (image_0, image_1, image_2, etc.)
        for key in request.files:
            if key.startswith('image_'):
                file = request.files[key]
                if file and file.filename and allowed_file(file.filename):
                    # FIXED: Generate SHORT filename instead of long one
                    short_filename = generate_short_filename(
                        file.filename, 
                        product.id, 
                        len(image_filenames)
                    )
                    
                    # Save file with short name
                    filepath = os.path.join(upload_path, short_filename)
                    file.save(filepath)
                    
                    # Determine if this is the primary image (first one)
                    is_primary = (len(image_filenames) == 0)
                    
                    # Create ProductImage record with short filename
                    product_image = ProductImage(
                        product_id=product.id,
                        filename=short_filename,
                        is_primary=is_primary,
                        sort_order=len(image_filenames)
                    )
                    db.session.add(product_image)
                    image_filenames.append(short_filename)
                    
                    print(f"📸 Saved image: {short_filename}")
        
        # Validate at least one image was uploaded
        if not image_filenames:
            db.session.rollback()
            return jsonify({'error': 'At least one product image is required'}), 400
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Product created successfully',
            'product': product.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error creating product: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 500
    

@templates_bp.route('/seller/products/<int:product_id>', methods=['GET', 'PUT', 'DELETE'])
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
            return jsonify({'product': product.to_dict()})

        # ── PUT (UPDATE) ──────────────────────────────────────────────────────
        elif request.method == 'PUT':

            # FormData (includes file uploads)
            if request.content_type and 'multipart/form-data' in request.content_type:
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
                if 'category' in request.form:
                    product.category = request.form['category']
                if 'is_available' in request.form:
                    product.is_available = request.form['is_available'].lower() == 'true'

                # Add new images (keep existing ones)
                upload_path = os.path.join(BASE_DIR, 'static', 'uploads', 'products')
                os.makedirs(upload_path, exist_ok=True)
                current_images = ProductImage.query.filter_by(product_id=product.id).all()
                next_sort_order = len(current_images)
                new_filenames = []

                for key in request.files:
                    if key.startswith('image_'):
                        file = request.files[key]
                        if file and file.filename and allowed_file(file.filename):
                            short_filename = generate_short_filename(
                                file.filename, product.id, next_sort_order
                            )
                            file.save(os.path.join(upload_path, short_filename))
                            is_primary = (len(current_images) == 0 and len(new_filenames) == 0)
                            db.session.add(ProductImage(
                                product_id=product.id,
                                filename=short_filename,
                                is_primary=is_primary,
                                sort_order=next_sort_order
                            ))
                            new_filenames.append(short_filename)
                            next_sort_order += 1
                            print(f"📸 Added image to product {product.id}: {short_filename}")

                product.updated_at = datetime.utcnow()
                db.session.commit()
                return jsonify({
                    'success': True,
                    'message': 'Product updated successfully',
                    'product': product.to_dict()
                })

            # JSON (no files)
            else:
                data = request.get_json() or {}
                if 'name' in data:
                    product.name = data['name'].strip()
                if 'description' in data:
                    product.description = data['description'].strip() if data['description'] else None
                if 'price' in data:
                    try:
                        product.price = float(data['price'])
                    except ValueError:
                        return jsonify({'error': 'Invalid price format'}), 400
                if 'stock_quantity' in data:
                    try:
                        product.stock_quantity = int(data['stock_quantity'])
                    except ValueError:
                        return jsonify({'error': 'Invalid stock quantity format'}), 400
                if 'category' in data:
                    product.category = data['category']
                if 'is_available' in data:
                    if isinstance(data['is_available'], bool):
                        product.is_available = data['is_available']
                    else:
                        product.is_available = str(data['is_available']).lower() == 'true'

                product.updated_at = datetime.utcnow()
                db.session.commit()
                return jsonify({
                    'success': True,
                    'message': 'Product updated successfully',
                    'product': product.to_dict()
                })

        # ── DELETE ────────────────────────────────────────────────────────────
        elif request.method == 'DELETE':
            carts_with_product = CartItem.query.filter_by(product_id=product_id).count()

            # Always show the choice dialog — never auto-delete
            return jsonify({
                'success':      True,
                'needs_choice': True,
                'message':      'Choose action:',
                'product':      product.to_dict(),
                'in_carts':     carts_with_product,
            }), 200

        return jsonify({'error': 'Method not allowed'}), 405

    except Exception as e:
        db.session.rollback()
        print(f"DEBUG: Exception in manage_product: {str(e)}")
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
    
    # Format dates for template
    orders_data = []
    for order in orders:
        order_dict = order.to_dict()
        
        # Add formatted dates
        if order.created_at:
            order_dict['date_formatted'] = order.created_at.strftime('%Y-%m-%d')
            order_dict['time_formatted'] = order.created_at.strftime('%H:%M')
            order_dict['datetime_formatted'] = order.created_at.strftime('%Y-%m-%d %H:%M')
        else:
            order_dict['date_formatted'] = ''
            order_dict['time_formatted'] = ''
            order_dict['datetime_formatted'] = ''
        
        orders_data.append(order_dict)
    
    return render_template('seller_orders.html', orders=orders_data, store=store.to_dict())

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


def _get_primary_image(product):
    """Return the URL path for the primary (or first) product image."""
    if not product.images:
        return None
    primary = next((img for img in product.images if img.is_primary), None)
    img = primary or product.images[0]
    return f'/static/uploads/products/{img.filename}'


@templates_bp.route('/seller/pos')
@seller_required
def seller_pos():
    """
    Render the POS interface.
    Passes all available, in-stock products for the seller's store.
    """
    store = _get_seller_store()

    if not store:
        # Seller has no active store — bounce back with a flash
        return redirect(url_for('templates.dashboard'))

    # Fetch all products for this store, ordered by category then name
    products = (
        Product.query
        .filter_by(store_id=store.id)
        .order_by(Product.category.asc(), Product.name.asc())
        .all()
    )

    return render_template(
        'seller_pos.html',
        store=store,
        products=products,
    )


# ═════════════════════════════════════════════════════════════════════════════
# ROUTE 2 — CREATE POS ORDER
# POST /seller/pos/order
# Body (JSON):
#   {
#     "customer_name":    "Maria Santos",   // optional
#     "customer_contact": "09171234567",    // optional
#     "payment_method":   "cash",           // cash | gcash | card
#     "discount":         50.00,            // optional, default 0
#     "items": [
#       { "product_id": 3, "quantity": 2, "price": 250.00 },
#       ...
#     ]
#   }
# ═════════════════════════════════════════════════════════════════════════════

@templates_bp.route('/seller/pos/order', methods=['POST'])
@seller_required
def pos_create_order():
    """
    Create a POS order and update stock quantities.
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
        quantity   = int(entry.get('quantity', 1))
        unit_price = Decimal(str(entry.get('price', 0)))

        if quantity < 1:
            return jsonify({'error': f'Quantity must be at least 1 (product id {product_id}).'}), 400

        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            return jsonify({'error': f'Product #{product_id} not found in your store.'}), 404

        if not product.is_available:
            return jsonify({'error': f'"{product.name}" is currently unavailable.'}), 400

        if product.stock_quantity < quantity:
            return jsonify({
                'error': (
                    f'Insufficient stock for "{product.name}". '
                    f'Available: {product.stock_quantity}, requested: {quantity}.'
                )
            }), 400

        validated_items.append({
            'product':  product,
            'quantity': quantity,
            'price':    unit_price,
        })

    # ── Calculate totals ──────────────────────────────────────────────────────
    subtotal = sum(v['price'] * v['quantity'] for v in validated_items)
    discount = Decimal(str(data.get('discount', 0) or 0))
    if discount < 0:
        discount = Decimal('0')
    total_amount = max(Decimal('0'), subtotal - discount)

    # ── Persist everything in a transaction ───────────────────────────────────
    try:
        # 1. Create POSOrder
        order = POSOrder(
            store_id        = store.id,
            total_amount    = total_amount,
            customer_name   = data.get('customer_name') or None,
            customer_contact= data.get('customer_contact') or None,
        )
        db.session.add(order)
        db.session.flush()   # get order.id before adding items

        # 2. Create POSOrderItems + deduct stock
        for v in validated_items:
            item = POSOrderItem(
                pos_order_id = order.id,
                product_id   = v['product'].id,
                quantity     = v['quantity'],
                price        = v['price'],
            )
            db.session.add(item)

            # Deduct stock
            v['product'].stock_quantity -= v['quantity']

        # 3. Commit
        db.session.commit()

        return jsonify({
            'success':      True,
            'pos_order_id': order.id,
            'total_amount': float(total_amount),
            'message':      'Order created successfully.',
        }), 201

    except Exception as e:
        db.session.rollback()
        print(f'[POS] Order creation error: {e}')
        return jsonify({'error': 'Failed to save order. Please try again.'}), 500


# ═════════════════════════════════════════════════════════════════════════════
# ROUTE 3 — GET POS ORDER HISTORY (optional, for a history panel)
# GET /seller/pos/orders?page=1&per_page=20
# ═════════════════════════════════════════════════════════════════════════════

@templates_bp.route('/seller/pos/orders', methods=['GET'])
@seller_required
def pos_order_history():
    """
    Return a paginated list of POS orders for the seller's store.
    Useful for a history sidebar or analytics.
    """
    store = _get_seller_store()
    if not store:
        return jsonify({'error': 'No active store.'}), 403

    page     = request.args.get('page',     1,  type=int)
    per_page = request.args.get('per_page', 20, type=int)
    per_page = min(per_page, 100)   # cap at 100

    pagination = (
        POSOrder.query
        .filter_by(store_id=store.id)
        .order_by(POSOrder.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    orders = []
    for o in pagination.items:
        orders.append({
            'id':              o.id,
            'total_amount':    float(o.total_amount) if o.total_amount else 0,
            'customer_name':   o.customer_name or 'Walk-in',
            'customer_contact':o.customer_contact,
            'item_count':      sum(i.quantity for i in o.items),
            'created_at':      o.created_at.strftime('%b %d, %Y %I:%M %p') if o.created_at else '—',
        })

    return jsonify({
        'orders':       orders,
        'total':        pagination.total,
        'pages':        pagination.pages,
        'current_page': pagination.page,
        'has_next':     pagination.has_next,
        'has_prev':     pagination.has_prev,
    })


# ═════════════════════════════════════════════════════════════════════════════
# ROUTE 4 — GET SINGLE POS ORDER DETAIL
# GET /seller/pos/orders/<int:order_id>
# ═════════════════════════════════════════════════════════════════════════════

@templates_bp.route('/seller/pos/orders/<int:order_id>', methods=['GET'])
@seller_required
def pos_order_detail(order_id):
    """
    Return full detail for a single POS order (for receipt reprinting).
    Only accessible by the store owner.
    """
    store = _get_seller_store()
    if not store:
        return jsonify({'error': 'No active store.'}), 403

    order = POSOrder.query.filter_by(id=order_id, store_id=store.id).first()
    if not order:
        return jsonify({'error': 'Order not found.'}), 404

    items = []
    for i in order.items:
        product   = i.product
        img_url   = _get_primary_image(product) if product else None
        items.append({
            'product_id':   i.product_id,
            'product_name': product.name if product else '(deleted)',
            'quantity':     i.quantity,
            'unit_price':   float(i.price) if i.price else 0,
            'subtotal':     float(i.price * i.quantity) if i.price else 0,
            'image_url':    img_url,
        })

    return jsonify({
        'id':               order.id,
        'store_id':         order.store_id,
        'total_amount':     float(order.total_amount) if order.total_amount else 0,
        'customer_name':    order.customer_name or 'Walk-in',
        'customer_contact': order.customer_contact,
        'items':            items,
        'created_at':       order.created_at.isoformat() if order.created_at else None,
    })



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
    product = Product.query.get_or_404(product_id)
    # Add-ons: other products from same store, different category
    addon_products = Product.query.filter(
        Product.store_id == product.store_id,
        Product.id != product_id,
        Product.is_available == True,
        Product.stock_quantity > 0
    ).limit(8).all()
    # Related: same category, different store or same store
    related_products = Product.query.filter(
        Product.category == product.category,
        Product.id != product_id,
        Product.is_available == True
    ).limit(8).all()
    return render_template('product_details.html',
        product=product,
        addon_products=addon_products,
        related_products=related_products)



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
    



@templates_bp.route('/api/cart', methods=['GET'])
def get_cart():
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
                # Automatically remove archived products from cart
                db.session.delete(item)
                removed_count += 1
        
        if removed_count > 0:
            db.session.commit()
        
        # Build cart with only active items
        cart_data = cart.to_dict()
        
        return jsonify({
            'success': True,
            'cart': cart_data,
            'removed_count': removed_count,
            'message': f'{removed_count} item(s) removed as they are no longer available' if removed_count else None
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@templates_bp.route('/api/cart/items', methods=['POST'])
def add_to_cart():
    """Add item to cart"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        data = request.get_json()
        product_id = data.get('product_id')
        quantity = data.get('quantity', 1)
        
        print(f"🛒 Adding to cart - User: {user.id}, Product: {product_id}, Quantity: {quantity}")
        
        if not product_id:
            return jsonify({'error': 'Product ID is required'}), 400
        
        # Check if product exists and has stock
        product = Product.query.get(product_id)
        if not product:
            print(f"❌ Product not found: {product_id}")
            return jsonify({'error': 'Product not found'}), 404
        
        print(f"📦 Product: {product.name}, Stock: {product.stock_quantity}, Available: {product.is_available}")
        
        if not product.is_available:
            return jsonify({'error': 'Product is not available'}), 400
        
        if product.stock_quantity < quantity:
            return jsonify({'error': f'Only {product.stock_quantity} available'}), 400
        
        # Get or create cart
        cart = Cart.query.filter_by(user_id=user.id).first()
        if not cart:
            print(f"🆕 Creating new cart for user: {user.id}")
            cart = Cart(user_id=user.id)
            db.session.add(cart)
            db.session.flush()
        
        # Check if product already in cart
        cart_item = CartItem.query.filter_by(
            cart_id=cart.id,
            product_id=product_id
        ).first()
        
        if cart_item:
            # Check total quantity against stock
            if product.stock_quantity < (cart_item.quantity + quantity):
                return jsonify({'error': f'Only {product.stock_quantity} available total'}), 400
            print(f"🔄 Updating existing cart item from {cart_item.quantity} to {cart_item.quantity + quantity}")
            cart_item.quantity += quantity
        else:
            print(f"➕ Adding new cart item")
            cart_item = CartItem(
                cart_id=cart.id,
                product_id=product_id,
                quantity=quantity
            )
            db.session.add(cart_item)
        
        db.session.commit()
        
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





@templates_bp.route('/debug/check-image/<path:filename>', methods=['GET'])
def debug_check_image(filename):
    """Check if an image file exists and return its info"""
    from os.path import exists, join, getsize
    from datetime import datetime
    
    try:
        # Construct the full path to the image
        image_path = join(BASE_DIR, 'static', 'uploads', 'products', filename)
        
        if exists(image_path):
            file_size = getsize(image_path)
            modified_time = datetime.fromtimestamp(os.path.getmtime(image_path))
            
            return jsonify({
                'exists': True,
                'filename': filename,
                'path': image_path,
                'size_bytes': file_size,
                'size_kb': round(file_size / 1024, 2),
                'modified': modified_time.isoformat(),
                'url': f'/static/uploads/products/{filename}'
            })
        else:
            # Try to list directory contents for debugging
            upload_dir = join(BASE_DIR, 'static', 'uploads', 'products')
            files = []
            if exists(upload_dir):
                files = os.listdir(upload_dir)[:10]  # First 10 files
            
            return jsonify({
                'exists': False,
                'filename': filename,
                'path': image_path,
                'directory_exists': exists(upload_dir),
                'sample_files': files
            }), 404
            
    except Exception as e:
        return jsonify({
            'error': str(e),
            'filename': filename
        }), 500
    

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

@templates_bp.route('/debug/images', methods=['GET'])
def debug_images():
    """Debug endpoint to list all product images"""
    try:
        upload_folder = os.path.join(BASE_DIR, 'static', 'uploads', 'products')
        if not os.path.exists(upload_folder):
            return jsonify({'error': 'Upload folder not found'}), 404
        
        files = os.listdir(upload_folder)
        
        # Get file details
        images = []
        for f in files:
            file_path = os.path.join(upload_folder, f)
            if os.path.isfile(file_path):
                images.append({
                    'filename': f,
                    'size': os.path.getsize(file_path),
                    'exists': True
                })
        
        # Check the specific images from your logs
        target_images = ['p3_1_008392_c059e330.png', 'p4_1_008377_8f751b4b.png', 'p5_1_008348_61d580a4.png']
        missing = []
        for img in target_images:
            if img not in files:
                missing.append(img)
        
        return jsonify({
            'total_images': len(images),
            'images': images[:20],  # First 20 images
            'missing_targets': missing,
            'upload_folder': upload_folder
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/debug/product-images/<int:product_id>', methods=['GET'])
def debug_product_images(product_id):
    """Debug endpoint to check all images for a product"""
    try:
        product = Product.query.get_or_404(product_id)
        
        result = {
            'product_id': product.id,
            'product_name': product.name,
            'images': []
        }
        
        upload_folder = os.path.join(BASE_DIR, 'static', 'uploads', 'products')
        
        for img in product.images:
            file_path = os.path.join(upload_folder, img.filename)
            file_exists = os.path.exists(file_path)
            
            result['images'].append({
                'id': img.id,
                'filename': img.filename,
                'is_primary': img.is_primary,
                'file_exists': file_exists,
                'file_size': os.path.getsize(file_path) if file_exists else None,
                'url': f'/static/uploads/products/{img.filename}',
                'resized_url': f'/api/product-image/{img.filename}?w=800&h=800'
            })
        
        # Also list all files in the upload folder for comparison
        if os.path.exists(upload_folder):
            all_files = os.listdir(upload_folder)
            result['all_files_in_folder'] = all_files[:20]  # First 20 files
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    

@templates_bp.route('/seller/archive')
@seller_required
def seller_archive():
    """Render the seller archive page"""
    return render_template('seller_archive.html')


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
    



@templates_bp.route('/debug/check-avatar/<filename>')
def debug_check_avatar(filename):
    """Check if avatar file exists and return its URL"""
    from flask import url_for
    import os
    
    # Check using config path
    upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'avatars')
    file_path = os.path.join(upload_path, filename)
    file_exists = os.path.exists(file_path)
    
    # Generate the URL that should work
    static_url = url_for('static', filename=f'uploads/avatars/{filename}', _external=True)
    
    return jsonify({
        'filename': filename,
        'upload_path': upload_path,
        'file_path': file_path,
        'file_exists': file_exists,
        'file_size': os.path.getsize(file_path) if file_exists else None,
        'static_url': static_url,
        'static_url_relative': f'/static/uploads/avatars/{filename}'
    })


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
            return redirect(url_for('templates.index'))  # ✅ FIXED: was url_for('templates.store_detail') — missing store_id

        # Build store dict
        store_data = store.to_dict()

        # Attach logo URL from seller application
        if store.seller_application and store.seller_application.store_logo_path:
            store_data['logo_url'] = f'/static/uploads/seller_logos/{store.seller_application.store_logo_path}'
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
        return redirect(url_for('templates.index'))  # ✅ FIXED: was url_for('templates.store_detail') — would crash again
    




























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
        
        # Convert delivery_area from WKB to GeoJSON for display
        delivery_geojson = None
        if store.delivery_area:
            try:
                import json
                from shapely import wkb
                from shapely.geometry import mapping
                
                # Convert WKB hex to geometry
                if hasattr(store.delivery_area, 'data'):
                    wkb_bytes = bytes(store.delivery_area.data)
                else:
                    wkb_bytes = bytes.fromhex(store.delivery_area)
                
                geometry = wkb.loads(wkb_bytes)
                
                # Convert to GeoJSON
                geojson_dict = mapping(geometry)
                delivery_geojson = json.dumps(geojson_dict)
                print(f"✅ Converted WKB to GeoJSON for display")
            except Exception as e:
                print(f"⚠️ Could not convert delivery_area to GeoJSON: {e}")
                import traceback
                traceback.print_exc()
        
        # DEBUG: Print store data including new fields
        print("\n" + "="*60)
        print("🔍 STORE SETTINGS PAGE LOADED")
        print(f"Store ID: {store.id}")
        print(f"Store Name: {store.name}")
        print(f"Municipality: {store.municipality}")
        print(f"Barangay: {store.barangay}")
        print(f"Street: {store.street}")
        print(f"Has latitude: {store.latitude is not None}")
        print(f"Has longitude: {store.longitude is not None}")
        print(f"Has formatted_address: {store.formatted_address is not None}")
        print(f"Has delivery_area: {store.delivery_area is not None}")
        print(f"Has delivery_geojson: {delivery_geojson is not None}")
        print("="*60 + "\n")
        
        return render_template('store_settings.html', 
                             store=store,
                             municipalities=municipalities,
                             get_barangays=get_barangays,
                             delivery_geojson=delivery_geojson)
    
    except Exception as e:
        print(f"❌ Error in store_settings: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Error loading page.', 'error')
        return redirect(url_for('templates.seller_dashboard'))
    
    
@templates_bp.route('/api/seller/store/settings', methods=['POST'])
@seller_required
def update_store_settings():
    """Update all store settings at once"""
    print("\n" + "="*60)
    print("📥 RECEIVED UPDATE STORE SETTINGS REQUEST")
    
    try:
        data = request.get_json()
        print(f"📦 Received data keys: {list(data.keys())}")
        
        # DEBUG: Print the exact value of selected_municipalities
        if 'selected_municipalities' in data:
            print(f"🏙️ selected_municipalities value: {data['selected_municipalities']}")
            print(f"🏙️ selected_municipalities type: {type(data['selected_municipalities'])}")
            print(f"🏙️ selected_municipalities length: {len(data['selected_municipalities']) if data['selected_municipalities'] else 0}")
        else:
            print("🏙️ selected_municipalities NOT in data")
        
        # Get seller's store
        store = Store.query.filter_by(seller_id=session['user_id']).first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        # Store the original delivery area to check if it changed
        original_delivery_area = store.delivery_area
        
        # NEW: Delivery method preference
        if 'delivery_method' in data:
            store.delivery_method = data['delivery_method']
            print(f"✅ Updated delivery_method to: {store.delivery_method}")
        
        # Update basic info
        if 'name' in data:
            store.name = data['name']
        
        # ===== NEW: Update address fields =====
        if 'municipality' in data:
            store.municipality = data['municipality']
            print(f"✅ Updated municipality to: {store.municipality}")
        
        if 'barangay' in data:
            store.barangay = data['barangay']
            print(f"✅ Updated barangay to: {store.barangay}")
        
        if 'street' in data:
            store.street = data['street']
            print(f"✅ Updated street to: {store.street}")
        
        # Update the full address field (for backward compatibility)
        if 'address' in data:
            store.address = data['address']
            print(f"✅ Updated full address")
        else:
            # Construct address from components if not provided
            if store.municipality and store.barangay:
                if store.street:
                    store.address = f"{store.street}, Barangay {store.barangay}, {store.municipality}, Laguna"
                else:
                    store.address = f"Barangay {store.barangay}, {store.municipality}, Laguna"
                print(f"✅ Constructed full address: {store.address}")
        
        if 'contact_number' in data:
            store.contact_number = data['contact_number']
        if 'description' in data:
            store.description = data['description']
        if 'status' in data:
            store.status = data['status']
        
        # Update location
        if 'latitude' in data and data['latitude']:
            store.latitude = data['latitude']
        if 'longitude' in data and data['longitude']:
            store.longitude = data['longitude']
        if 'formatted_address' in data:
            store.formatted_address = data['formatted_address']
        if 'place_id' in data:
            store.place_id = data['place_id']
        
        # Update PostGIS geometry for store location
        if store.latitude and store.longitude:
            try:
                from geoalchemy2.shape import from_shape
                from shapely.geometry import Point
                store.location = from_shape(Point(store.longitude, store.latitude), srid=4326)
                print("✅ Updated PostGIS location")
            except Exception as e:
                print(f"⚠️ Could not update PostGIS location: {e}")
        
        # Update delivery settings
        if 'delivery_radius_km' in data:
            store.delivery_radius_km = data['delivery_radius_km']
        if 'max_delivery_distance' in data:
            store.max_delivery_distance = data['max_delivery_distance']
        if 'base_delivery_fee' in data:
            store.base_delivery_fee = data['base_delivery_fee']
        if 'delivery_rate_per_km' in data:
            store.delivery_rate_per_km = data['delivery_rate_per_km']
        if 'free_delivery_minimum' in data:
            store.free_delivery_minimum = data['free_delivery_minimum']
        
        # ===== CRITICAL FIX: Update selected municipalities =====
        if 'selected_municipalities' in data:
            # Always update, even if it's an empty array
            store.selected_municipalities = data['selected_municipalities']
            print(f"✅ Updated selected_municipalities to: {store.selected_municipalities}")
        else:
            print(f"⚠️ selected_municipalities not in data, keeping existing: {store.selected_municipalities}")
        
        # ===== FIXED: Update delivery zone with preservation logic =====
        # Check for explicit clear flag first
        if 'clear_delivery_zone' in data and data['clear_delivery_zone']:
            # Explicitly clearing the zone
            store.delivery_area = None
            print("✅ Cleared delivery zone (explicit)")
        elif 'delivery_area' in data:
            if data['delivery_area'] and data['delivery_area'] is not None:
                try:
                    import json
                    from geoalchemy2.shape import from_shape
                    from shapely.geometry import shape
                    
                    print(f"🔄 Processing delivery_area...")
                    
                    # Parse the GeoJSON
                    zone_geojson = json.loads(data['delivery_area'])
                    print(f"✅ Parsed GeoJSON: {type(zone_geojson)}")
                    print(f"✅ GeoJSON type: {zone_geojson.get('type')}")
                    
                    # Convert to Shapely geometry
                    polygon = shape(zone_geojson)
                    print(f"✅ Created Shapely polygon with {len(polygon.exterior.coords)} points")
                    
                    # Save to PostGIS
                    store.delivery_area = from_shape(polygon, srid=4326)
                    print(f"✅ Saved delivery zone to database")
                    
                except json.JSONDecodeError as e:
                    print(f"❌ JSON decode error: {e}")
                except Exception as e:
                    print(f"⚠️ Error saving delivery zone: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                # delivery_area is present but empty/null - only clear if it was explicitly intended
                # Check if this is a radius mode save by looking at delivery_method
                if 'delivery_method' in data and data['delivery_method'] == 'radius':
                    # In radius mode, preserve existing zone data
                    if original_delivery_area:
                        print(f"⚠️ Radius mode save - preserving existing delivery zone")
                        # Keep the original delivery area
                        store.delivery_area = original_delivery_area
                    else:
                        print(f"ℹ️ No existing delivery zone to preserve")
                else:
                    # Not in radius mode and no zone data - only clear if we're sure
                    print(f"⚠️ Received empty delivery_area, but preserving existing zone to be safe")
                    # Uncomment the next line ONLY if you want to allow clearing without explicit flag
                    # store.delivery_area = None
        
        store.updated_at = datetime.utcnow()
        db.session.commit()
        
        print("✅ Database commit successful")
        print(f"📊 FINAL STORE DATA AFTER COMMIT:")
        print(f"   delivery_method: {store.delivery_method}")
        print(f"   selected_municipalities: {store.selected_municipalities}")
        print(f"   type: {type(store.selected_municipalities)}")
        
        # Verify the zone was saved
        if store.delivery_area:
            print(f"✅ Verified: delivery_area is now set in database")
        else:
            print(f"ℹ️ Note: delivery_area is None after save")
        
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
    """Get all addresses for the logged-in user"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        addresses = UserAddress.query.filter_by(user_id=session['user_id']).order_by(
            UserAddress.is_default.desc(),
            UserAddress.created_at.desc()
        ).all()
        
        return jsonify({
            'success': True,
            'addresses': [addr.to_dict() for addr in addresses]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/account/addresses', methods=['POST'])
def add_user_address():
    """Add a new address for the user"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        data = request.get_json()
        
        # Validate required fields - including place_id (optional)
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
                user_id=session['user_id'],
                is_default=True
            ).update({'is_default': False})
        
        # Create new address with EXACT coordinates and place_id from Mapbox
        address = UserAddress(
            user_id=session['user_id'],
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
    """Update an existing address"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        address = UserAddress.query.filter_by(
            id=address_id,
            user_id=session['user_id']
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
                user_id=session['user_id'],
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
    """Delete an address"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        address = UserAddress.query.filter_by(
            id=address_id,
            user_id=session['user_id']
        ).first()
        
        if not address:
            return jsonify({'error': 'Address not found'}), 404
        
        # If this was the default, make another address default
        if address.is_default:
            next_address = UserAddress.query.filter_by(
                user_id=session['user_id']
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
    """Set an address as default"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        address = UserAddress.query.filter_by(
            id=address_id,
            user_id=session['user_id']
        ).first()
        
        if not address:
            return jsonify({'error': 'Address not found'}), 404
        
        # Unset all other defaults
        UserAddress.query.filter_by(
            user_id=session['user_id'],
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