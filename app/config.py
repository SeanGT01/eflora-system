import os
from datetime import timedelta
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    # =============================
    # Security
    # =============================
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "jwt-secret-key")
    JWT_IDENTITY_CLAIM = "sub"
    MAPBOX_PUBLIC_TOKEN = os.getenv('MAPBOX_PUBLIC_TOKEN', '')
    APP_BASE_URL = os.getenv('APP_BASE_URL', '')

    # =============================
    # JWT Configuration
    # =============================
    JWT_DECODE_OPTIONS = {
        'verify_sub': False,
        'verify_aud': False,
        'verify_iat': True,
        'require_exp': True,
        'verify_exp': True,
        'verify_nbf': False,
        'verify_iss': False,
        'require_sub': False,
    }
    
    JWT_IDENTITY_CLAIM = 'sub'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)

    # =============================
    # Database
    # =============================
    DATABASE_URL = os.getenv("DATABASE_URL")

    if DATABASE_URL:
        SQLALCHEMY_DATABASE_URI = DATABASE_URL
    else:
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(basedir, 'dev.db')}"

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # =============================
    # File Uploads (Local - Fallback)
    # =============================
    UPLOAD_FOLDER = os.path.join(basedir, "static", "uploads")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "pdf"}
    
    # Local upload subfolders
    SELLER_LOGO_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "seller_logos")
    SELLER_ID_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "govt_ids")
    AVATAR_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "avatars")
    PRODUCT_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "products")
    PRODUCT_VARIANT_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "product_variants")
    GCASH_QR_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "gcash_qr")
    PAYMENT_PROOF_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "payments")

    # =============================
    # CLOUDINARY CONFIGURATION
    # =============================
    CLOUDINARY_CLOUD_NAME = os.getenv('CLOUDINARY_CLOUD_NAME')
    CLOUDINARY_API_KEY = os.getenv('CLOUDINARY_API_KEY')
    CLOUDINARY_API_SECRET = os.getenv('CLOUDINARY_API_SECRET')
    
    # Cloudinary folders for different image types
    CLOUDINARY_FOLDERS = {
        'avatar': 'e-flowers/avatars',
        'product': 'e-flowers/products',
        'product_variant': 'e-flowers/product-variants',
        'seller_logo': 'e-flowers/seller-logos',
        'govt_id': 'e-flowers/govt-ids',
        'gcash_qr': 'e-flowers/gcash-qr',
        'payment_proof': 'e-flowers/payments',
        'store_logo': 'e-flowers/store-logos',
        'category_image': 'e-flowers/categories',
        'testimonial': 'e-flowers/testimonials'
    }
    
    # Cloudinary transformation presets
    CLOUDINARY_PRESETS = {
        'avatar': {
            'width': 300,
            'height': 300,
            'crop': 'fill',
            'gravity': 'face',
            'quality': 'auto',
            'fetch_format': 'auto'
        },
        'product': {
            'width': 800,
            'height': 800,
            'crop': 'limit',
            'quality': 'auto',
            'fetch_format': 'auto'
        },
        'product_thumbnail': {
            'width': 300,
            'height': 300,
            'crop': 'fill',
            'quality': 'auto',
            'fetch_format': 'auto'
        },
        'gcash_qr': {
            'width': 500,
            'height': 500,
            'crop': 'limit',
            'quality': 'auto',
            'fetch_format': 'auto'
        },
        'govt_id': {
            'width': 1000,
            'height': 1000,
            'crop': 'limit',
            'quality': 'auto',
            'fetch_format': 'auto'
        }
    }
    
    # Whether to use Cloudinary in development
    # Set to False to use local uploads during development
    USE_CLOUDINARY_IN_DEV = os.getenv('USE_CLOUDINARY_IN_DEV', 'False').lower() == 'true'

    # =============================
    # API
    # =============================
    API_PREFIX = "/api/v1"

    # =============================
    # PostGIS
    # =============================
    POSTGIS_VERSION = (3, 3, 0)

    # =============================
    # Email / SMTP (Flask-Mail)
    # =============================
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USE_SSL = os.getenv('MAIL_USE_SSL', 'False').lower() == 'true'
    MAIL_USERNAME = os.getenv('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', '')  # Gmail App Password
    # IMPORTANT: MAIL_DEFAULT_SENDER MUST match MAIL_USERNAME for Gmail SMTP (DMARC alignment)
    # For production, use SendGrid instead (set SENDGRID_API_KEY)
    _mail_default = os.getenv('MAIL_DEFAULT_SENDER')
    if _mail_default:
        MAIL_DEFAULT_SENDER = _mail_default
    elif os.getenv('MAIL_USERNAME'):
        MAIL_DEFAULT_SENDER = os.getenv('MAIL_USERNAME')  # Gmail requires this match
    else:
        MAIL_DEFAULT_SENDER = 'noreply@eflowers.com'
    
    # SendGrid API (preferred for production)
    SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY', '')


# =================================
# Environments
# =================================

class DevelopmentConfig(Config):
    DEBUG = True
    # In development, you can choose to use local files or Cloudinary
    # Set this in your .env file


class ProductionConfig(Config):
    DEBUG = False
    # In production, always use Cloudinary
    USE_CLOUDINARY_IN_DEV = True  # This will be overridden but ensures Cloudinary is used


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    # Use local files in testing
    USE_CLOUDINARY_IN_DEV = False


# =================================
# THIS is what __init__.py imports
# =================================

config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig
}