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
    app.config['WTF_CSRF_CHECK_DEFAULT'] = False  # Don't check all requests by default
    app.config['WTF_CSRF_SSL_STRICT'] = False if app.debug else True
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # 1 hour
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
    csrf.init_app(app)  # Initialize CSRF with the app
    limiter.init_app(app)
    
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
    
    # Create upload folders
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'seller_logos'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'govt_ids'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'products'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'avatars'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'gcash_qr'), exist_ok=True)
    
    # Import models here to ensure they're registered with SQLAlchemy
    from app import models
    
    # Register blueprints
    from app.auth import auth_bp
    from app.admin import admin_bp
    from app.seller import seller_bp
    from app.customer import customer_bp
    from app.rider import rider_bp
    from app.templates_routes import templates_bp
    from app.bg_removal import bg_removal_bp  
    from app.archive_routes import archive_bp
    
    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
    app.register_blueprint(admin_bp, url_prefix='/api/v1/admin')
    app.register_blueprint(seller_bp, url_prefix='/api/v1/seller')
    app.register_blueprint(customer_bp, url_prefix='/api/v1/customer')
    app.register_blueprint(rider_bp, url_prefix='/api/v1/rider')
    app.register_blueprint(templates_bp)
    app.register_blueprint(bg_removal_bp)
    app.register_blueprint(archive_bp)
    
    # Set session secret key
    app.secret_key = app.config['SECRET_KEY']
    
    # ====================================================
    # ADD MAPBOX TO TEMPLATE CONTEXT
    # ====================================================
    @app.context_processor
    def inject_mapbox_token():
        return dict(mapbox_public_token=app.config.get('MAPBOX_PUBLIC_TOKEN', ''))
    
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
    # CSRF PROTECTION - ADD THIS BACK!
    # ====================================================
    @app.before_request
    def csrf_protect():
        """Protect state-changing methods with CSRF"""
        # Define routes that should be exempt from CSRF protection
        exempt_routes = [
            '/webhook',  # Example webhook
            '/api/public/endpoint',  # Public API endpoints
        ]
        
        # Skip CSRF for exempt routes
        if request.path in exempt_routes:
            return
            
        # Skip CSRF for GET, HEAD, OPTIONS, TRACE methods
        if request.method in ["GET", "HEAD", "OPTIONS", "TRACE"]:
            return
            
        # Skip CSRF check for API routes (they use JWT)
        if request.path.startswith('/api/'):
            return
            
        # For all other state-changing requests, check CSRF token
        try:
            csrf.protect()
        except Exception as e:
            # Log the error but don't expose details
            app.logger.error(f"CSRF protection error: {str(e)}")
            return jsonify({'error': 'CSRF token missing or invalid'}), 400
    
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