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

    # =============================
    # JWT Configuration - ADD THESE LINES
    # =============================
    # Make JWT validation more flexible
    JWT_DECODE_OPTIONS = {
        'verify_sub': False,      # Don't verify the 'sub' claim exists
        'verify_aud': False,       # Don't verify audience
        'verify_iat': True,        # Verify issued at
        'require_exp': True,       # Require expiration
        'verify_exp': True,        # Verify expiration
        'verify_nbf': False,       # Don't verify not before
        'verify_iss': False,       # Don't verify issuer
        'require_sub': False,      # Don't require 'sub' claim
    }
    
    # Allow both 'sub' and 'user_id' as identity claims
    JWT_IDENTITY_CLAIM = 'sub'     # Keep as sub for standard compliance
    
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)

    # =============================
    # Database
    # =============================
    # Priority:
    # 1. DATABASE_URL from .env
    # 2. fallback to SQLite (easy local dev)
    DATABASE_URL = os.getenv("DATABASE_URL")

    if DATABASE_URL:
        SQLALCHEMY_DATABASE_URI = DATABASE_URL
    else:
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(basedir, 'dev.db')}"

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # =============================
    # File Uploads
    # =============================
    UPLOAD_FOLDER = os.path.join(basedir, "static", "uploads")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf"}
    
    # =============================
    # Seller Application Upload Paths
    # =============================
    SELLER_LOGO_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "seller_logos")
    SELLER_ID_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, "govt_ids")

    # =============================
    # API
    # =============================
    API_PREFIX = "/api/v1"

    # =============================
    # PostGIS
    # =============================
    POSTGIS_VERSION = (3, 3, 0)


# =================================
# Environments
# =================================

class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


# =================================
# THIS is what __init__.py imports
# =================================

config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig
}