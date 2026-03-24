from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import os
import mimetypes

# Import extensions from the new extensions module
from app.extensions import db, migrate, jwt

# ====================================================
# ADD CSRF AND RATE LIMITING IMPORTS
# ====================================================
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# ====================================================
# ADD CLOUDINARY IMPORTS
# ====================================================
import cloudinary
import cloudinary.uploader
import cloudinary.api

# Initialize extensions at module level
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
    strategy="fixed-window"
)

def create_app(config_class='default'):
    app = Flask(__name__)
    
    # Ensure PNG files have correct MIME type
    mimetypes.add_type('image/png', '.png')
    mimetypes.add_type('image/jpeg', '.jpg')
    mimetypes.add_type('image/jpeg', '.jpeg')
    mimetypes.add_type('image/gif', '.gif')
    mimetypes.add_type('image/webp', '.webp')
    
    # Load configuration
    from app.config import config
    app.config.from_object(config[config_class])
    
    # ====================================================
    # ADD MAPBOX TOKEN TO APP CONFIG
    # ====================================================
    if 'MAPBOX_PUBLIC_TOKEN' not in app.config:
        app.config['MAPBOX_PUBLIC_TOKEN'] = os.getenv('MAPBOX_PUBLIC_TOKEN', '')
    
    # ====================================================
    # CSRF CONFIGURATION
    # ====================================================
    app.config['WTF_CSRF_ENABLED'] = True
    app.config['WTF_CSRF_CHECK_DEFAULT'] = False
    app.config['WTF_CSRF_SSL_STRICT'] = False if app.debug else True
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600
    app.config['SECRET_KEY'] = app.config.get('SECRET_KEY', os.urandom(24))
    app.config['WTF_CSRF_SECRET_KEY'] = app.config.get('SECRET_KEY')
    
    # ====================================================
    # SESSION SECURITY CONFIGURATION
    # ====================================================
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = not app.debug
    app.config['REMEMBER_COOKIE_HTTPONLY'] = True
    app.config['REMEMBER_COOKIE_SECURE'] = not app.debug
    app.config['REMEMBER_COOKIE_DURATION'] = 86400 * 30
    
    print(f"🗺️ Mapbox token loaded: {app.config['MAPBOX_PUBLIC_TOKEN'][:15] if app.config['MAPBOX_PUBLIC_TOKEN'] else 'NOT FOUND'}...")
    
    # ====================================================
    # INITIALIZE EXTENSIONS WITH APP
    # ====================================================
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    
    # ====================================================
    # INITIALIZE CLOUDINARY
    # ====================================================
    if app.config.get('CLOUDINARY_CLOUD_NAME') and \
       app.config.get('CLOUDINARY_API_KEY') and \
       app.config.get('CLOUDINARY_API_SECRET'):
        
        cloudinary.config(
            cloud_name=app.config['CLOUDINARY_CLOUD_NAME'],
            api_key=app.config['CLOUDINARY_API_KEY'],
            api_secret=app.config['CLOUDINARY_API_SECRET'],
            secure=True
        )
        app.logger.info("✅ Cloudinary configured successfully")
        
        # Test Cloudinary connection
        try:
            cloudinary.api.ping()
            app.logger.info("✅ Cloudinary connection test passed")
        except Exception as e:
            app.logger.warning(f"⚠️ Cloudinary connection test failed: {e}")
    else:
        app.logger.warning("⚠️ Cloudinary credentials not found - using local file storage")
    
    # ====================================================
    # ADD JWT USER LOADER CALLBACK
    # ====================================================
    @jwt.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_data):
        identity = jwt_data.get('sub') or jwt_data.get('user_id')
        if identity:
            if isinstance(identity, str) and identity.isdigit():
                identity = int(identity)
            from app.models import User
            return User.query.get(identity)
        return None
    
    # ====================================================
    # CORS CONFIGURATION
    # ====================================================
    CORS(app, 
         resources={
             r"/api/*": {"origins": "*"},
             r"/static/*": {"origins": "*"}
         },
         allow_headers=["Content-Type", "Authorization", "X-CSRFToken"],
         expose_headers=["Authorization", "Content-Type"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
         supports_credentials=True)
    
    # Create upload folders (still needed for local fallback)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'seller_logos'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'govt_ids'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'products'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'avatars'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'gcash_qr'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'payments'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'product_variants'), exist_ok=True)
    
    # Import models here to ensure they're registered with SQLAlchemy
    from app import models
    
    # ====================================================
    # REGISTER BLUEPRINTS (INCLUDING CLOUDINARY)
    # ====================================================
    from app.auth import auth_bp
    from app.admin import admin_bp
    from app.seller import seller_bp
    from app.customer import customer_bp
    from app.rider import rider_bp
    from app.templates_routes import templates_bp
    from app.bg_removal import bg_removal_bp  
    from app.archive_routes import archive_bp
    from app.cloudinary_routes import cloudinary_bp  # Import Cloudinary blueprint
    from app.checkout_routes import checkout_bp  # Import Checkout blueprint
    from app.payment_verification_routes import payment_verification_bp  # Seller payment verification
    
    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
    app.register_blueprint(admin_bp, url_prefix='/api/v1/admin')
    app.register_blueprint(seller_bp, url_prefix='/api/v1/seller')
    app.register_blueprint(customer_bp, url_prefix='/api/v1/customer')
    app.register_blueprint(rider_bp, url_prefix='/api/v1/rider')
    app.register_blueprint(templates_bp)
    app.register_blueprint(bg_removal_bp)
    app.register_blueprint(archive_bp)
    app.register_blueprint(cloudinary_bp, url_prefix='/api/v1/cloudinary')  # Register Cloudinary blueprint
    app.register_blueprint(checkout_bp, url_prefix='/api/v1/checkout')
    app.register_blueprint(payment_verification_bp)  # Register Payment Verification blueprint
    
    # Set session secret key
    app.secret_key = app.config['SECRET_KEY']
    
    # ====================================================
    # ADD MAPBOX TO TEMPLATE CONTEXT
    # ====================================================
    @app.context_processor
    def inject_mapbox_token():
        return dict(mapbox_public_token=app.config.get('MAPBOX_PUBLIC_TOKEN', ''))
    
    # ====================================================
    # ADD CLOUDINARY UTILITIES TO TEMPLATE CONTEXT
    # ====================================================
    @app.context_processor
    def inject_cloudinary_utils():
        def get_cloudinary_url(public_id, transformation=None):
            """Generate Cloudinary URL with optional transformations"""
            if not public_id:
                return None
            try:
                if transformation:
                    return cloudinary.CloudinaryImage(public_id).build_url(**transformation)
                return cloudinary.CloudinaryImage(public_id).build_url()
            except Exception as e:
                app.logger.error(f"Error generating Cloudinary URL: {e}")
                return None
        
        def get_optimized_image(public_id, preset='product'):
            """Get optimized image URL using presets"""
            if not public_id:
                return None
            try:
                preset_config = app.config.get('CLOUDINARY_PRESETS', {}).get(preset, {})
                return cloudinary.CloudinaryImage(public_id).build_url(**preset_config)
            except Exception as e:
                app.logger.error(f"Error generating optimized image: {e}")
                return None
        
        def cloudinary_enabled():
            """Check if Cloudinary is enabled and configured"""
            return bool(app.config.get('CLOUDINARY_CLOUD_NAME'))
        
        return dict(
            get_cloudinary_url=get_cloudinary_url,
            get_optimized_image=get_optimized_image,
            cloudinary_enabled=cloudinary_enabled,
            cloudinary_folders=app.config.get('CLOUDINARY_FOLDERS', {})
        )
    
    # ====================================================
    # ADD SECURITY HEADERS TO ALL RESPONSES
    # ====================================================
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        if not app.debug:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        return response
    
    # ====================================================
    # CSRF PROTECTION
    # ====================================================
    @app.before_request
    def csrf_protect():
        """Protect state-changing methods with CSRF"""
        exempt_routes = [
            '/webhook',
            '/api/public/endpoint',
        ]
        
        if request.path in exempt_routes:
            return
            
        if request.method in ["GET", "HEAD", "OPTIONS", "TRACE"]:
            return
            
        if request.path.startswith('/api/'):
            return
            
        try:
            csrf.protect()
        except Exception as e:
            app.logger.error(f"CSRF protection error: {str(e)}")
            return jsonify({'error': 'CSRF token missing or invalid'}), 400
    
    # ====================================================
    # DEBUG: PRINT ALL REGISTERED ROUTES
    # ====================================================
    print("\n" + "="*60)
    print("📋 REGISTERED BLUEPRINTS AND ROUTES:")
    print("="*60)
    for rule in app.url_map.iter_rules():
        if 'cloudinary' in str(rule):
            print(f"   ✅ {rule}")
        elif 'api' in str(rule):
            print(f"      {rule}")
    print("="*60 + "\n")
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return render_template('404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return render_template('500.html'), 500
    
    @app.errorhandler(429)
    def ratelimit_handler(error):
        return jsonify({
            'error': 'Rate limit exceeded',
            'message': 'Too many requests. Please try again later.'
        }), 429
    
    return app

# Make extensions available for import from app
__all__ = ['db', 'migrate', 'jwt', 'csrf', 'limiter', 'create_app']