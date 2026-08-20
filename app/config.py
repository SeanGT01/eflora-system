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
    SEND_FILE_MAX_AGE_DEFAULT = 86400
    # Railway/proxy Postgres closes idle sockets; ping + recycle + TCP keepalives
    # avoid "server closed the connection unexpectedly" on the next request.
    if DATABASE_URL and str(DATABASE_URL).startswith(('postgres://', 'postgresql://')):
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_pre_ping': True,
            'pool_recycle': 180,
            'pool_size': 5,
            'max_overflow': 10,
            'pool_reset_on_return': 'rollback',
            'connect_args': {
                'connect_timeout': 10,
                'keepalives': 1,
                'keepalives_idle': 30,
                'keepalives_interval': 10,
                'keepalives_count': 5,
            },
        }

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
    # IMPORTANT: Upload-time transforms permanently rewrite the stored asset.
    # Keep product uploads large; resize on delivery (URL transforms) instead.
    CLOUDINARY_PRESETS = {
        'avatar': {
            'width': 400,
            'height': 400,
            'crop': 'fill',
            'gravity': 'face',
            'quality': 'auto:good',
            'fetch_format': 'auto'
        },
        'product': {
            # Soft ceiling only — do not downscale typical phone/camera photos hard
            'width': 2500,
            'height': 2500,
            'crop': 'limit',
            'quality': 'auto:best',
        },
        'product_thumbnail': {
            # Used only for on-demand URL transforms, not for permanent uploads
            'width': 400,
            'height': 400,
            'crop': 'fill',
            'quality': 'auto:good',
            'fetch_format': 'auto'
        },
        'gcash_qr': {
            'width': 1000,
            'height': 1000,
            'crop': 'limit',
            'quality': 'auto:best',
        },
        'govt_id': {
            'width': 2000,
            'height': 2000,
            'crop': 'limit',
            'quality': 'auto:best',
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
    # Email - Gmail OAuth2
    # =============================
    # Gmail OAuth2 configuration for sending verification & OTP emails
    # See generate_gmail_oauth_token.py for setup instructions
    GMAIL_REFRESH_TOKEN = os.getenv('GMAIL_REFRESH_TOKEN', '')
    GMAIL_CLIENT_ID = os.getenv('GMAIL_CLIENT_ID', '')
    GMAIL_CLIENT_SECRET = os.getenv('GMAIL_CLIENT_SECRET', '')
    GMAIL_SENDER_EMAIL = os.getenv('GMAIL_SENDER_EMAIL', 'eflowers.verification@gmail.com')
    
    # Email identity for sending via Gmail OAuth2
    _mail_default = os.getenv('MAIL_DEFAULT_SENDER')
    if _mail_default:
        MAIL_DEFAULT_SENDER = _mail_default
    else:
        MAIL_DEFAULT_SENDER = GMAIL_SENDER_EMAIL if GMAIL_SENDER_EMAIL else 'noreply@eflowers.com'

    # =============================
    # iProg SMS (OTP via PH mobile)
    # =============================
    IPROG_API_TOKEN = os.getenv('IPROG_API_TOKEN', '')
    IPROG_SMS_BASE_URL = os.getenv('IPROG_SMS_BASE_URL', 'https://sms.iprogtech.com/api/v1')


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