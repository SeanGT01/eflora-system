from flask import Flask, render_template
from flask_cors import CORS
import os
import mimetypes

# Import extensions from the new extensions module
from app.extensions import db, migrate, jwt

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
    # ADD MAPBOX TOKEN TO APP CONFIG (if not already there)
    # ====================================================
    # Make sure MAPBOX_PUBLIC_TOKEN is set in your .env file
    # and loaded in config.py
    if 'MAPBOX_PUBLIC_TOKEN' not in app.config:
        # Fallback to environment variable
        app.config['MAPBOX_PUBLIC_TOKEN'] = os.getenv('MAPBOX_PUBLIC_TOKEN', '')
    
    print(f"🗺️ Mapbox token loaded: {app.config['MAPBOX_PUBLIC_TOKEN'][:15] if app.config['MAPBOX_PUBLIC_TOKEN'] else 'NOT FOUND'}...")
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    
    # ====================================================
    # ADD JWT USER LOADER CALLBACK
    # ====================================================
    @jwt.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_data):
        """
        This callback is used to load a user from the database
        based on the identity in the JWT.
        It handles both 'sub' and 'user_id' claims.
        """
        # Try to get identity from 'sub' claim first (standard)
        identity = jwt_data.get('sub')
        
        # If no 'sub', try 'user_id' (for backward compatibility)
        if identity is None:
            identity = jwt_data.get('user_id')
            if identity is not None:
                print(f"🔑 Using 'user_id' claim instead of 'sub'")
        
        if identity is not None:
            # Convert to int if it's a string (for database lookup)
            if isinstance(identity, str) and identity.isdigit():
                identity = int(identity)
            elif isinstance(identity, str):
                print(f"⚠️ Identity is string but not numeric: {identity}")
            
            print(f"🔍 Looking up user with identity: {identity}")
            
            # Import here to avoid circular imports
            from app.models import User
            user = User.query.get(identity)
            
            if user:
                print(f"✅ User found: {user.id} - {user.email}")
                return user
            else:
                print(f"❌ User not found for identity: {identity}")
        else:
            print("❌ No valid identity found in token")
            print(f"📋 Available claims: {list(jwt_data.keys())}")
        
        return None
    
    # FIXED: CORS for both API and static routes
    CORS(app, 
         resources={
             r"/api/*": {"origins": "*"},
             r"/static/*": {"origins": "*"}  # Important for images
         },
         allow_headers=["Content-Type", "Authorization"],
         expose_headers=["Authorization", "Content-Type"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
    
    # Create upload folders
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Create seller application upload folders
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'seller_logos'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'govt_ids'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'products'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'avatars'), exist_ok=True)
    
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
        """Make Mapbox token available to all templates"""
        return dict(mapbox_public_token=app.config.get('MAPBOX_PUBLIC_TOKEN', ''))
    
    # Add response headers for all static files
    @app.after_request
    def add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
        return response
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return render_template('404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return render_template('500.html'), 500
    
    return app