from app.extensions import db
from geoalchemy2 import Geometry
from sqlalchemy import event
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import os
from decimal import Decimal
from sqlalchemy.dialects.postgresql import JSON
import cloudinary
import cloudinary.utils
import pytz


# Philippines timezone (UTC+8)
PHT = pytz.timezone('Asia/Manila')

def to_pht_iso(dt):
    """Convert UTC datetime to Philippines timezone ISO string"""
    if not dt:
        return None
    if dt.tzinfo is None:
        # Assume UTC if no timezone info
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(PHT).isoformat()


class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin, seller, rider, customer
    status = db.Column(db.String(20), default='pending')
    
    # Profile fields
    phone = db.Column(db.String(20), nullable=True)
    birthday = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(20), nullable=True)  # male, female, other, prefer_not_to_say
    
    # ===== CLOUDINARY FIELDS (NO LOCAL FALLBACK) =====
    avatar_filename = db.Column(db.String(255), nullable=True)  # Original filename (metadata only)
    avatar_public_id = db.Column(db.String(255), nullable=True)  # Cloudinary public ID
    avatar_url = db.Column(db.String(500), nullable=True)  # Full Cloudinary URL
    # =================================================
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    stores = db.relationship('Store', backref='seller', lazy=True, foreign_keys='Store.seller_id')
    customer_orders = db.relationship('Order', backref='customer', lazy=True, foreign_keys='Order.customer_id')
    testimonials = db.relationship('Testimonial', backref='customer', lazy=True)
    addresses = db.relationship('UserAddress', backref='user', lazy=True, cascade='all, delete-orphan')
    
    # Seller application relationships
    seller_applications = db.relationship('SellerApplication', foreign_keys='SellerApplication.user_id', back_populates='applicant', lazy=True)
    reviewed_seller_applications = db.relationship('SellerApplication', foreign_keys='SellerApplication.reviewed_by', back_populates='reviewer', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    @property
    def avatar_image_url(self):
        """Get Cloudinary URL - no local fallback"""
        return self.avatar_url
    
    def get_avatar_transformed(self, width=None, height=None, crop='fill'):
        """Generate transformed avatar URL"""
        if not self.avatar_public_id:
            return None
            
        transformations = {}
        if width:
            transformations['width'] = width
        if height:
            transformations['height'] = height
        if crop:
            transformations['crop'] = crop
            
        url, _ = cloudinary.utils.cloudinary_url(
            self.avatar_public_id,
            **transformations,
            secure=True
        )
        return url
    
    def to_dict(self):
        # Split on last space: everything before = first name, last word = last name
        _name_parts = self.full_name.rsplit(' ', 1) if ' ' in self.full_name else [self.full_name]
        return {
            'id': self.id,
            'full_name': self.full_name,
            'first_name': _name_parts[0] if len(_name_parts) > 0 else self.full_name,
            'last_name': _name_parts[1] if len(_name_parts) > 1 else '',
            'email': self.email,
            'role': self.role,
            'status': self.status,
            'phone': self.phone,
            'birthday': self.birthday.isoformat() if self.birthday else None,
            'gender': self.gender,
            'avatar_url': self.avatar_url,  # Cloudinary only
            'avatar_thumbnail': self.get_avatar_transformed(width=100, height=100),
            'avatar_public_id': self.avatar_public_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


# ═════════════════════════════════════════════════════════════════════════════
# GCASH QR CODE MODEL
# ═════════════════════════════════════════════════════════════════════════════
class GCashQR(db.Model):
    __tablename__ = 'gcash_qrs'
    
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id', ondelete='CASCADE'), nullable=False)
    
    # ===== CLOUDINARY FIELDS (NO LOCAL FALLBACK) =====
    filename = db.Column(db.String(255), nullable=False)  # Original filename (metadata only)
    public_id = db.Column(db.String(255), nullable=False)  # Cloudinary public ID - REQUIRED
    cloudinary_url = db.Column(db.String(500), nullable=False)  # Full Cloudinary URL - REQUIRED
    # =================================================
    
    is_primary = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    store = db.relationship('Store', back_populates='gcash_qr_images')
    
    @property
    def url(self):
        """Get Cloudinary URL - no local fallback"""
        return self.cloudinary_url
    
    def to_dict(self):
        return {
            'id': self.id,
            'store_id': self.store_id,
            'filename': self.filename,
            'public_id': self.public_id,
            'url': self.cloudinary_url,  # Cloudinary only
            'is_primary': self.is_primary,
            'sort_order': self.sort_order,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Store(db.Model):
    __tablename__ = 'stores'
    
    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.Text, nullable=False)
    
    # ===== ADDRESS FIELDS FOR DROPDOWN SELECTION =====
    municipality = db.Column(db.String(100), nullable=True)
    barangay = db.Column(db.String(100), nullable=True)
    street = db.Column(db.String(200), nullable=True)
    # ====================================================
    
    contact_number = db.Column(db.String(20))
    description = db.Column(db.Text)
    
    # Current active delivery area (changes based on selected method)
    delivery_area = db.Column(Geometry('POLYGON', srid=4326))
    
    # ===== STORAGE FOR ALL DELIVERY METHODS =====
    # Store the drawn zone polygon (when in zone mode)
    zone_delivery_area = db.Column(Geometry('POLYGON', srid=4326), nullable=True)
    
    # Store the municipality selection (when in municipality mode)
    selected_municipalities = db.Column(db.JSON, nullable=True)
    
    # Store the generated municipality polygon (for quick queries)
    municipality_delivery_area = db.Column(Geometry('MULTIPOLYGON', srid=4326), nullable=True)
    # =============================================
    
    # Radius settings (always stored)
    delivery_radius_km = db.Column(db.Float, default=5.0)
    
    location = db.Column(Geometry('POINT', srid=4326))
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Seller application tracking fields
    seller_application_id = db.Column(db.Integer, db.ForeignKey('seller_applications.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # ===== MAPBOX DELIVERY FIELDS =====
    delivery_method = db.Column(db.String(20), default='radius')
    base_delivery_fee = db.Column(db.Numeric(10, 2), default=50.00)
    delivery_rate_per_km = db.Column(db.Numeric(10, 2), default=20.00)
    free_delivery_minimum = db.Column(db.Numeric(10, 2), default=500.00)
    max_delivery_distance = db.Column(db.Float, default=15.0)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    formatted_address = db.Column(db.String(500), nullable=True)
    place_id = db.Column(db.String(100), nullable=True)
    # ==================================
    
    # ===== GCASH INSTRUCTIONS =====
    gcash_instructions = db.Column(db.Text, nullable=True)
    # ==================================
    
    # ===== STORE SCHEDULE =====
    # JSON format: {"schedules": [{"days": ["monday","tuesday",...], "open": "07:00", "close": "12:00"}, ...], "slot_duration": 2}
    store_schedule = db.Column(db.JSON, nullable=True)
    # ==================================
    
    # Relationships
    products = db.relationship('Product', backref='store', lazy=True, cascade='all, delete-orphan')
    riders = db.relationship('Rider', backref='store', lazy=True)
    orders = db.relationship('Order', backref='store', lazy=True)
    pos_orders = db.relationship('POSOrder', backref='store', lazy=True)
    testimonials = db.relationship('Testimonial', backref='store', lazy=True)
    analytics = db.relationship('OrderAnalytics', backref='store', lazy=True)
    
    # GCash QR relationship
    gcash_qr_images = db.relationship('GCashQR', back_populates='store', 
                                      cascade='all, delete-orphan', 
                                      order_by='GCashQR.sort_order')
    
    seller_application = db.relationship('SellerApplication', foreign_keys=[seller_application_id], backref='approved_store_record', lazy=True)
    approved_by_user = db.relationship('User', foreign_keys=[approved_by], backref='stores_approved', lazy=True)
    
    @property
    def logo_url(self):
        """Get store logo from seller application - Cloudinary only"""
        if self.seller_application:
            return self.seller_application.store_logo_url
        return None
    
    def calculate_delivery_fee(self, distance_km, subtotal):
        """Calculate delivery fee based on distance and order subtotal"""
        if subtotal >= self.free_delivery_minimum:
            return Decimal('0')
        
        fee = Decimal(str(self.base_delivery_fee or 0)) + \
              (Decimal(str(self.delivery_rate_per_km or 0)) * Decimal(str(distance_km)))
        
        min_fee = Decimal('30.00')
        if fee < min_fee:
            fee = min_fee
        
        return fee
    
    def generate_radius_polygon(self):
        """Generate a circular polygon around the store location based on delivery radius"""
        if not self.latitude or not self.longitude or not self.delivery_radius_km:
            return None
        
        try:
            from shapely.geometry import Point
            import math
            
            # Create a point at store location
            center = Point(self.longitude, self.latitude)
            
            # Convert radius from km to degrees (approximate)
            # 1 degree of latitude ≈ 111 km
            radius_degrees = self.delivery_radius_km / 111.0
            
            # Create a circle by buffering the point
            circle = center.buffer(radius_degrees)
            
            return circle
            
        except Exception as e:
            print(f"⚠️ Error generating radius polygon: {e}")
            return None
    
    def update_delivery_area_from_method(self):
        """Update the active delivery_area based on the current delivery_method"""
        if self.delivery_method == 'radius':
            # Generate fresh radius polygon
            circle = self.generate_radius_polygon()
            if circle:
                from geoalchemy2.shape import from_shape
                self.delivery_area = from_shape(circle, srid=4326)
                
        elif self.delivery_method == 'zone':
            # Use the saved zone polygon
            self.delivery_area = self.zone_delivery_area
            
        elif self.delivery_method == 'municipality':
            # Use the saved municipality polygon
            self.delivery_area = self.municipality_delivery_area
    
    def can_deliver_to(self, customer_lat, customer_lng):
        """Check if customer is within delivery area based on selected method"""
        if not self.delivery_area:
            return False
            
        from geoalchemy2.functions import ST_Contains
        from geoalchemy2.shape import from_shape
        from shapely.geometry import Point
        
        point = from_shape(Point(customer_lng, customer_lat), srid=4326)
        result = db.session.query(ST_Contains(self.delivery_area, point)).scalar()
        return bool(result)
    
    def calculate_distance(self, lat2, lng2):
        """Calculate distance between store and customer (Haversine formula)"""
        from math import radians, sin, cos, sqrt, atan2
        
        if not self.latitude or not self.longitude:
            return float('inf')
        
        lat1, lng1 = radians(self.latitude), radians(self.longitude)
        lat2, lng2 = radians(lat2), radians(lng2)
        
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
        return 6371 * c
    
    def to_dict(self):
        # Generate current radius GeoJSON if in radius mode
        radius_geojson = None
        if self.delivery_method == 'radius' and self.latitude and self.longitude:
            circle = self.generate_radius_polygon()
            if circle:
                from shapely.geometry import mapping
                import json
                radius_geojson = json.dumps(mapping(circle))
        
        # Convert zone_delivery_area to GeoJSON if it exists
        zone_geojson = None
        if self.zone_delivery_area:
            try:
                from shapely import wkb
                from shapely.geometry import mapping
                import json
                
                if hasattr(self.zone_delivery_area, 'data'):
                    wkb_bytes = bytes(self.zone_delivery_area.data)
                else:
                    wkb_bytes = bytes.fromhex(self.zone_delivery_area)
                
                geometry = wkb.loads(wkb_bytes)
                zone_geojson = json.dumps(mapping(geometry))
            except:
                pass
        
        # Convert municipality_delivery_area to GeoJSON if it exists
        municipality_geojson = None
        if self.municipality_delivery_area:
            try:
                from shapely import wkb
                from shapely.geometry import mapping
                import json
                
                if hasattr(self.municipality_delivery_area, 'data'):
                    wkb_bytes = bytes(self.municipality_delivery_area.data)
                else:
                    wkb_bytes = bytes.fromhex(self.municipality_delivery_area)
                
                geometry = wkb.loads(wkb_bytes)
                municipality_geojson = json.dumps(mapping(geometry))
            except:
                pass
        
        return {
            'id': self.id,
            'name': self.name,
            'address': self.address,
            'seller_id': self.seller_id,
            'delivery_radius_km': self.delivery_radius_km,
            'status': self.status,
            'contact_number': self.contact_number,
            'description': self.description,
            'logo_url': self.logo_url,  # Cloudinary only
            'seller_application_id': self.seller_application_id,
            'approved_at': self.approved_at.isoformat() if self.approved_at else None,
            'municipality': self.municipality,
            'barangay': self.barangay,
            'street': self.street,
            'delivery_method': self.delivery_method,
            'selected_municipalities': self.selected_municipalities,
            'base_delivery_fee': float(self.base_delivery_fee or 0),
            'delivery_rate_per_km': float(self.delivery_rate_per_km or 0),
            'free_delivery_minimum': float(self.free_delivery_minimum or 0),
            'max_delivery_distance': self.max_delivery_distance,
            'created_at': self.created_at,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'formatted_address': self.formatted_address,
            'place_id': self.place_id,
            # Delivery area data for all methods
            'radius_geojson': radius_geojson,
            'zone_geojson': zone_geojson,
            'municipality_geojson': municipality_geojson,
            'current_delivery_geojson': self._get_current_delivery_geojson(),
            # GCash fields
            'gcash_qr_codes': [qr.to_dict() for qr in self.gcash_qr_images],
            'gcash_instructions': self.gcash_instructions,
            # Store schedule
            'store_schedule': self.store_schedule
        }
    
    def _get_current_delivery_geojson(self):
        """Get GeoJSON for the current active delivery area"""
        if not self.delivery_area:
            return None
        
        try:
            from shapely import wkb
            from shapely.geometry import mapping
            import json
            
            if hasattr(self.delivery_area, 'data'):
                wkb_bytes = bytes(self.delivery_area.data)
            else:
                wkb_bytes = bytes.fromhex(self.delivery_area)
            
            geometry = wkb.loads(wkb_bytes)
            return json.dumps(mapping(geometry))
        except:
            return None


class SellerApplication(db.Model):
    __tablename__ = 'seller_applications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    store_name = db.Column(db.String(100), nullable=False)
    store_description = db.Column(db.Text)
    
    # ===== CLOUDINARY FIELDS (NO LOCAL FALLBACK) =====
    store_logo_path = db.Column(db.String(500), nullable=True)  # Deprecated - keep for backward compatibility
    store_logo_public_id = db.Column(db.String(255), nullable=True)  # Cloudinary public ID
    store_logo_url = db.Column(db.String(500), nullable=True)  # Cloudinary URL
    
    government_id_path = db.Column(db.String(500), nullable=True)  # Deprecated - keep for backward compatibility
    government_id_public_id = db.Column(db.String(255), nullable=True)  # Cloudinary public ID
    government_id_url = db.Column(db.String(500), nullable=True)  # Cloudinary URL
    # =================================================
    
    status = db.Column(db.String(20), default='pending')
    admin_notes = db.Column(db.Text)
    rejection_details = db.Column(JSON, nullable=True)  # Per-field rejection: {"store_name": {"rejected": true, "reason": "..."}, ...}
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    applicant = db.relationship('User', foreign_keys=[user_id], back_populates='seller_applications')
    reviewer = db.relationship('User', foreign_keys=[reviewed_by], back_populates='reviewed_seller_applications')
    
    @property
    def store_logo(self):
        """Get Cloudinary URL - no local fallback"""
        return self.store_logo_url
    
    @property
    def government_id(self):
        """Get Cloudinary URL - no local fallback"""
        return self.government_id_url
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'full_name': self.applicant.full_name if self.applicant else None,
            'email': self.applicant.email if self.applicant else None,
            'phone': self.applicant.phone if self.applicant else None,
            'store_name': self.store_name,
            'store_description': self.store_description,
            'store_logo_url': self.store_logo_url,  # Cloudinary only
            'store_logo_public_id': self.store_logo_public_id,
            'government_id_url': self.government_id_url,  # Cloudinary only
            'government_id_public_id': self.government_id_public_id,
            'status': self.status,
            'admin_notes': self.admin_notes,
            'rejection_details': self.rejection_details,
            'submitted_at': self.submitted_at.isoformat() if self.submitted_at else None,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            'reviewer_name': self.reviewer.full_name if self.reviewer else None
        }


class Notification(db.Model):
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), nullable=False)  # seller_app_approved, seller_app_rejected, etc.
    reference_id = db.Column(db.Integer, nullable=True)  # ID of related entity
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('notifications', lazy=True))
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'message': self.message,
            'type': self.type,
            'reference_id': self.reference_id,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Rider(db.Model):
    __tablename__ = 'riders'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False)
    vehicle_type = db.Column(db.String(50))
    license_plate = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = db.relationship('User', backref='rider_profile', lazy=True)
    orders = db.relationship('Order', backref='assigned_rider', lazy=True)
    locations = db.relationship('RiderLocation', backref='rider', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'store_id': self.store_id,
            'full_name': self.user.full_name if self.user else None,
            'email': self.user.email if self.user else None,
            'avatar_url': self.user.avatar_url if self.user else None,  # Cloudinary only
            'vehicle_type': self.vehicle_type,
            'license_plate': self.license_plate,
            'is_active': self.is_active
        }

class Category(db.Model):
    """Global main categories (same for all stores)"""
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)  # e.g., "Bouquets"
    slug = db.Column(db.String(50), unique=True, nullable=False)  # URL-friendly: "bouquets"
    description = db.Column(db.Text, nullable=True)
    icon = db.Column(db.String(50), nullable=True)  # FontAwesome icon class
    image_url = db.Column(db.String(500), nullable=True)  # Category image (Cloudinary)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    store_subcategories = db.relationship('StoreCategory', back_populates='main_category', lazy=True)
    products = db.relationship('Product', back_populates='main_category', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'description': self.description,
            'icon': self.icon,
            'image_url': self.image_url,
            'sort_order': self.sort_order,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class StoreCategory(db.Model):
    """Store-specific subcategories"""
    __tablename__ = 'store_categories'
    
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id', ondelete='CASCADE'), nullable=False)
    main_category_id = db.Column(db.Integer, db.ForeignKey('categories.id', ondelete='CASCADE'), nullable=False)
    
    name = db.Column(db.String(100), nullable=False)  # e.g., "Crochet Bouquets"
    slug = db.Column(db.String(100), nullable=False)  # Store-specific slug
    description = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(500), nullable=True)  # Cloudinary URL for subcategory image
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    
    # Custom attributes (JSON field for store-specific settings)
    custom_attributes = db.Column(db.JSON, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    store = db.relationship('Store', backref=db.backref('custom_categories', lazy=True))
    main_category = db.relationship('Category', back_populates='store_subcategories')
    products = db.relationship('Product', back_populates='store_category', lazy=True)
    
    __table_args__ = (
        db.UniqueConstraint('store_id', 'slug', name='unique_store_category_slug'),
        db.UniqueConstraint('store_id', 'name', name='unique_store_category_name'),
    )
    
    @property
    def full_path(self):
        """Get full category path e.g., 'Bouquets > Crochet Bouquets'"""
        return f"{self.main_category.name} > {self.name}"
    
    def to_dict(self, include_products=False):
        data = {
            'id': self.id,
            'store_id': self.store_id,
            'main_category_id': self.main_category_id,
            'main_category_name': self.main_category.name,
            'main_category_slug': self.main_category.slug,
            'main_category_icon': self.main_category.icon,
            'name': self.name,
            'slug': self.slug,
            'description': self.description,
            'image_url': self.image_url,
            'sort_order': self.sort_order,
            'is_active': self.is_active,
            'full_path': self.full_path,
            'product_count': len(self.products) if not include_products else None,
            'custom_attributes': self.custom_attributes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
        
        if include_products:
            data['products'] = [p.to_dict() for p in self.products]
        
        return data


class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False)
    
    # Category relationships
    main_category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    store_category_id = db.Column(db.Integer, db.ForeignKey('store_categories.id'), nullable=True)
    
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    special_price = db.Column(db.Numeric(10, 2), nullable=True)  # Sale / discounted price
    stock_quantity = db.Column(db.Integer, default=0)
    is_available = db.Column(db.Boolean, default=True)
    
    # Archive fields
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    archived_at = db.Column(db.DateTime, nullable=True)
    archived_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    main_category = db.relationship('Category', back_populates='products')
    store_category = db.relationship('StoreCategory', back_populates='products')
    images = db.relationship('ProductImage', back_populates='product', lazy=True, cascade='all, delete-orphan', order_by='ProductImage.sort_order')
    variants = db.relationship('ProductVariant', back_populates='product', lazy=True, cascade='all, delete-orphan', order_by='ProductVariant.sort_order')
    order_items = db.relationship('OrderItem', backref='product', lazy=True)
    pos_order_items = db.relationship('POSOrderItem', back_populates='product', lazy=True)
    archived_by_user = db.relationship('User', foreign_keys=[archived_by], backref='archived_products')
    stock_reductions = db.relationship('StockReduction', back_populates='product', lazy=True, cascade='all, delete-orphan')
    
    @property
    def effective_price(self):
        """The price customers actually pay (special_price if set, else price)."""
        if self.special_price and self.special_price < self.price:
            return float(self.special_price)
        return float(self.price)

    @property
    def discount_pct(self):
        """Integer discount percentage, or None when no special price is active."""
        if self.special_price and self.special_price < self.price and float(self.price) > 0:
            return round((1 - float(self.special_price) / float(self.price)) * 100)
        return None

    @property
    def category_path(self):
        """Get full category path e.g., 'Bouquets > Crochet Bouquets'"""
        if not self.main_category:
            return 'Uncategorized'
        if self.store_category:
            return self.store_category.full_path
        return self.main_category.name

    @property
    def category_display(self):
        """Get display name with subcategory if available"""
        if not self.main_category:
            return 'Uncategorized'
        if self.store_category:
            return f"{self.main_category.name} / {self.store_category.name}"
        return self.main_category.name
    
    def archive(self, user_id):
        """Move product to archive"""
        self.is_archived = True
        self.is_available = False
        self.archived_at = datetime.utcnow()
        self.archived_by = user_id
    
    def restore(self):
        """Restore product from archive"""
        self.is_archived = False
        self.is_available = True
        self.archived_at = None
        self.archived_by = None
    
    def reduce_stock(self, amount, reason, user_id, reason_notes=None, variant=None):
        """
        Reduce stock with audit trail.
        
        Args:
            amount (int): Number of units to reduce
            reason (str): Reason for reduction (spoilage, damage, defect, other, pos_sale)
            user_id (int): ID of user making the reduction
            reason_notes (str): Optional additional context
            variant (ProductVariant, optional): If reducing variant stock
            
        Returns:
            StockReduction: The created reduction record
            
        Raises:
            ValueError: If amount is invalid or exceeds available stock
        """
        if amount <= 0:
            raise ValueError("Reduction amount must be positive")
        
        if variant:
            # Reduce variant stock
            if amount > variant.stock_quantity:
                raise ValueError(f"Cannot reduce by {amount}. Available: {variant.stock_quantity}")
            
            variant.stock_quantity -= amount
            variant.updated_at = datetime.utcnow()
            
            reduction = StockReduction(
                product_id=self.id,
                variant_id=variant.id,
                reduction_amount=amount,
                reason=reason,
                reason_notes=reason_notes,
                reduced_by=user_id
            )
        else:
            # Reduce main product stock
            if amount > self.stock_quantity:
                raise ValueError(f"Cannot reduce by {amount}. Available: {self.stock_quantity}")
            
            self.stock_quantity -= amount
            
            reduction = StockReduction(
                product_id=self.id,
                variant_id=None,
                reduction_amount=amount,
                reason=reason,
                reason_notes=reason_notes,
                reduced_by=user_id
            )
        
        db.session.add(reduction)
        return reduction
    
    def delete_with_cloudinary(self):
        """Delete product and all associated Cloudinary images"""
        from app.utils.cloudinary_helper import delete_from_cloudinary
        
        for image in self.images:
            if image.public_id:
                delete_from_cloudinary(image.public_id)
        
        for variant in self.variants:
            if variant.image_public_id:
                delete_from_cloudinary(variant.image_public_id)
        
        db.session.delete(self)
    
    def to_dict(self):
        sorted_images = sorted(self.images, key=lambda x: x.sort_order)
        primary_image = next((img for img in sorted_images if img.is_primary), sorted_images[0] if sorted_images else None)
        
        sorted_variants = sorted(self.variants, key=lambda v: v.sort_order)
        
        data = {
            'id': self.id,
            'store_id': self.store_id,
            'store_name': self.store.name if self.store else 'Unknown Store',
            'name': self.name,
            'description': self.description,
            'price': float(self.price) if self.price else 0,
            'special_price': float(self.special_price) if self.special_price else None,
            'effective_price': self.effective_price,
            'discount_pct': self.discount_pct,
            'stock_quantity': self.stock_quantity,
            
                        # Main category info (with safe fallbacks)
            'main_category_id': self.main_category_id,
            'main_category_name': self.main_category.name if self.main_category else 'Uncategorized',
            'main_category_slug': self.main_category.slug if self.main_category else None,
            'main_category_icon': self.main_category.icon if self.main_category else None,

            # Store subcategory info (if any)
            'store_category_id': self.store_category_id,
            'store_category_name': self.store_category.name if self.store_category else None,
            'store_category_slug': self.store_category.slug if self.store_category else None,

            # Combined category info (with safe fallbacks)
            'category_path': self.category_path if self.main_category else 'Uncategorized',
            'category_display': self.category_display if self.main_category else 'Uncategorized',
            
            'image_url': primary_image.image_url if primary_image else None,
            'thumbnail_url': primary_image.get_transformed_url(width=200, height=200) if primary_image else None,
            'images': [img.to_dict() for img in sorted_images],
            'is_available': self.is_available,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'is_archived': self.is_archived,
            'archived_at': self.archived_at.isoformat() if self.archived_at else None,
            'archived_by': self.archived_by,
            
            # Variant support
            'has_variants': len(self.variants) > 0,
            'variants': [variant.to_dict() for variant in sorted_variants]
        }
        
        return data


class ProductImage(db.Model):
    __tablename__ = 'product_images'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    
    # ===== CLOUDINARY FIELDS (NO LOCAL FALLBACK) =====
    filename = db.Column(db.String(255), nullable=False)  # Original filename (metadata only)
    public_id = db.Column(db.String(255), nullable=False, unique=True)  # Cloudinary public ID - REQUIRED
    cloudinary_url = db.Column(db.String(500), nullable=False)  # Full Cloudinary URL - REQUIRED
    cloudinary_format = db.Column(db.String(10), nullable=True)  # Store format for transformations
    cloudinary_version = db.Column(db.String(20), nullable=True)  # Store version for cache busting
    # =================================================
    
    is_primary = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    product = db.relationship('Product', back_populates='images')
    
    @property
    def image_url(self):
        """Get Cloudinary URL - no local fallback"""
        return self.cloudinary_url
    
    def get_transformed_url(self, width=None, height=None, crop='fill'):
        """Generate transformed URL on the fly"""
        if not self.public_id:
            return None
            
        transformations = {}
        if width:
            transformations['width'] = width
        if height:
            transformations['height'] = height
        if crop:
            transformations['crop'] = crop
            
        url, _ = cloudinary.utils.cloudinary_url(
            self.public_id,
            **transformations,
            secure=True,
            version=self.cloudinary_version
        )
        return url
    
    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'filename': self.filename,
            'public_id': self.public_id,
            'image_url': self.image_url,
            'thumbnail_url': self.get_transformed_url(width=200, height=200),
            'medium_url': self.get_transformed_url(width=400, height=400),
            'large_url': self.get_transformed_url(width=800, height=800),
            'is_primary': self.is_primary,
            'sort_order': self.sort_order,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ═════════════════════════════════════════════════════════════════════════════
# PRODUCT VARIANT MODEL
# ═════════════════════════════════════════════════════════════════════════════
class ProductVariant(db.Model):
    __tablename__ = 'product_variants'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    
    # Variant details
    name = db.Column(db.String(100), nullable=False)  # e.g., "Small", "Red Rose", "12 Stems"
    price = db.Column(db.Numeric(10, 2), nullable=False)  # Variant-specific price
    special_price = db.Column(db.Numeric(10, 2), nullable=True)  # Sale / discounted price
    stock_quantity = db.Column(db.Integer, default=0)
    sku = db.Column(db.String(50), nullable=True)  # Stock Keeping Unit
    
    # ===== CLOUDINARY FIELDS (NO LOCAL FALLBACK) =====
    image_filename = db.Column(db.String(255), nullable=True)  # Original filename (metadata only)
    image_public_id = db.Column(db.String(255), nullable=True)  # Cloudinary public ID
    image_url = db.Column(db.String(500), nullable=True)  # Cloudinary URL
    image_format = db.Column(db.String(10), nullable=True)  # Format for transformations
    # =================================================
    
    # Variant attributes (can be used for filtering/display)
    # e.g., {"color": "red", "size": "small", "stems": 12}
    attributes = db.Column(db.JSON, nullable=True)
    
    # Display order
    sort_order = db.Column(db.Integer, default=0)
    
    # Availability
    is_available = db.Column(db.Boolean, default=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    product = db.relationship('Product', back_populates='variants')
    
    @property
    def effective_price(self):
        if self.special_price and self.special_price < self.price:
            return float(self.special_price)
        return float(self.price)

    @property
    def discount_pct(self):
        if self.special_price and self.special_price < self.price and float(self.price) > 0:
            return round((1 - float(self.special_price) / float(self.price)) * 100)
        return None

    @property
    def image(self):
        """Get Cloudinary URL - no local fallback"""
        return self.image_url
    
    def get_transformed_url(self, width=None, height=None, crop='fill'):
        """Generate transformed variant image URL"""
        if not self.image_public_id:
            return None
            
        transformations = {}
        if width:
            transformations['width'] = width
        if height:
            transformations['height'] = height
        if crop:
            transformations['crop'] = crop
            
        url, _ = cloudinary.utils.cloudinary_url(
            self.image_public_id,
            **transformations,
            secure=True
        )
        return url
    
    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'name': self.name,
            'price': float(self.price) if self.price else 0,
            'special_price': float(self.special_price) if self.special_price else None,
            'effective_price': self.effective_price,
            'discount_pct': self.discount_pct,
            'stock_quantity': self.stock_quantity,
            'sku': self.sku,
            'image_url': self.image_url,  # Cloudinary only
            'image_thumbnail': self.get_transformed_url(width=100, height=100),
            'image_public_id': self.image_public_id,
            'attributes': self.attributes,
            'sort_order': self.sort_order,
            'is_available': self.is_available,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


# ═════════════════════════════════════════════════════════════════════════════
# STOCK REDUCTION AUDIT MODEL
# ═════════════════════════════════════════════════════════════════════════════
# ═════════════════════════════════════════════════════════════════════════════
# STOCK REDUCTION AUDIT MODEL
# ═════════════════════════════════════════════════════════════════════════════
class StockReduction(db.Model):
    """Audit log for all stock reductions with reason tracking"""
    __tablename__ = 'stock_reductions'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id', ondelete='SET NULL'), nullable=True)
    reduction_amount = db.Column(db.Integer, nullable=False)
    
    # Reason for reduction
    reason = db.Column(db.String(50), nullable=False)  # spoilage, damage, defect, other, pos_sale
    reason_notes = db.Column(db.Text, nullable=True)   # Additional context
    
    # Who made the reduction
    reduced_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    product = db.relationship('Product', back_populates='stock_reductions')
    variant = db.relationship('ProductVariant', backref='stock_reductions', foreign_keys=[variant_id])
    reducer_user = db.relationship('User', backref='stock_reductions_made', foreign_keys=[reduced_by])
    
    # Valid reasons
    REASONS = ['spoilage', 'damage', 'defect', 'other', 'pos_sale', 'found_stock', 'receiving_error', 'restock']
    
    def to_dict(self):
        # Get product image (prefer primary, then first image)
        product_image = None
        if self.product and self.product.images:
            primary_image = next((img for img in self.product.images if img.is_primary), None)
            product_image = primary_image or self.product.images[0]
        
        # Get variant info and variant image URL
        variant_info = None
        variant_image_url = None  # ADD THIS VARIABLE
        if self.variant:
            variant_info = {
                'id': self.variant.id,
                'name': self.variant.name,
                'stock_before': self.variant.stock_quantity + self.reduction_amount if self.variant else None,
                'stock_after': self.variant.stock_quantity if self.variant else None
            }
            # ADD THIS - Get the variant's own image URL
            if self.variant.image_url:
                variant_image_url = self.variant.image_url
        
        return {
            'id': self.id,
            'product_id': self.product_id,
            'product_name': self.product.name if self.product else None,
            'product_image': product_image.image_url if product_image else None,
            'variant_id': self.variant_id,
            'variant_info': variant_info,
            'variant_image_url': variant_image_url,  # ADD THIS LINE
            'reduction_amount': self.reduction_amount,
            'reason': self.reason,
            'reason_notes': self.reason_notes,
            'reduced_by': self.reduced_by,
            'reduced_by_user': self.reducer_user.full_name if self.reducer_user else None,
            'reducer_name': self.reducer_user.full_name if self.reducer_user else None,
            'reducer_email': self.reducer_user.email if self.reducer_user else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class Order(db.Model):
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False)
    rider_id = db.Column(db.Integer, db.ForeignKey('riders.id'))
    
    order_type = db.Column(db.String(20), default='online')
    status = db.Column(db.String(20), default='pending')
    
    # Financial breakdown
    subtotal_amount = db.Column(db.Numeric(10, 2), default=0)
    delivery_fee = db.Column(db.Numeric(10, 2), default=0)
    distance_km = db.Column(db.Float)
    total_amount = db.Column(db.Numeric(10, 2))
    
    payment_method = db.Column(db.String(50), default='gcash')
    payment_status = db.Column(db.String(20), default='pending')
    
    # ===== CLOUDINARY FIELDS (NO LOCAL FALLBACK) =====
    payment_proof = db.Column(db.String(255), nullable=True)  # Original filename (metadata only)
    payment_proof_public_id = db.Column(db.String(255), nullable=True)  # Cloudinary public ID
    payment_proof_url = db.Column(db.String(500), nullable=True)  # Cloudinary URL
    # =================================================
    
    # Delivery information
    delivery_location = db.Column(Geometry('POINT', srid=4326))
    delivery_address = db.Column(db.Text)
    delivery_notes = db.Column(db.Text)
    requested_delivery_date = db.Column(db.Date, nullable=True)  # Format: YYYY-MM-DD
    requested_delivery_time = db.Column(db.String(50), nullable=True)  # Format: "8:00 AM - 12:00 PM"
    
    # ===== MAPBOX CUSTOMER FIELDS =====
    customer_latitude = db.Column(db.Float, nullable=True)
    customer_longitude = db.Column(db.Float, nullable=True)
    mapbox_place_id = db.Column(db.String(100), nullable=True)
    # ==================================
    
    # ===== DELIVERY PROOF FIELDS (NO LOCAL FALLBACK) =====
    delivery_proof = db.Column(db.String(255), nullable=True)  # Original filename (metadata only)
    delivery_proof_public_id = db.Column(db.String(255), nullable=True)  # Cloudinary public ID
    delivery_proof_url = db.Column(db.String(500), nullable=True)  # Cloudinary URL
    
    # Second delivery proof
    delivery_proof_2 = db.Column(db.String(255), nullable=True)  # Original filename (metadata only)
    delivery_proof_2_public_id = db.Column(db.String(255), nullable=True)  # Cloudinary public ID
    delivery_proof_2_url = db.Column(db.String(500), nullable=True)  # Cloudinary URL
    # ======================================================
    
    # Status timestamps for timeline tracking
    pending_at = db.Column(db.DateTime, default=datetime.utcnow)  # When order was created
    accepted_at = db.Column(db.DateTime, nullable=True)  # When seller verifies payment receipt
    preparing_at = db.Column(db.DateTime, nullable=True)  # Same time as accepted_at
    done_preparing_at = db.Column(db.DateTime, nullable=True)  # When seller clicks done preparing
    confirmed_at = db.Column(db.DateTime, nullable=True)  # When rider accepts the order
    on_delivery_at = db.Column(db.DateTime, nullable=True)  # DEPRECATED - use confirmed_at
    delivered_at = db.Column(db.DateTime, nullable=True)  # When rider submits proofs and marks delivered
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')
    
    @property
    def payment_proof_image(self):
        """Get Cloudinary URL - no local fallback"""
        return self.payment_proof_url
    
    def compute_total(self):
        subtotal = Decimal(self.subtotal_amount or 0)
        delivery = Decimal(self.delivery_fee or 0)
        self.total_amount = subtotal + delivery

    def set_status(self, new_status):
        """Update order status and record the timestamp for timeline tracking.
        
        Timeline mapping:
        - pending_at: order created
        - accepted_at: seller verifies payment receipt
        - preparing_at: same as accepted_at (set together)
        - done_preparing_at: seller clicks done preparing
        - confirmed_at: rider accepts the order
        - delivered_at: rider submits proofs and marks delivered
        """
        self.status = new_status
        now = datetime.utcnow()
        timestamp_map = {
            'pending': 'pending_at',
            'done_preparing': 'done_preparing_at',
            'delivered': 'delivered_at',
        }
        field = timestamp_map.get(new_status)
        if field and getattr(self, field) is None:
            setattr(self, field, now)
        
        # accepted: set both accepted_at and preparing_at together
        if new_status == 'accepted':
            if self.accepted_at is None:
                self.accepted_at = now
            if self.preparing_at is None:
                self.preparing_at = now
        
        # preparing: also set accepted_at and preparing_at (web verify-payment goes straight to preparing)
        if new_status == 'preparing':
            if self.accepted_at is None:
                self.accepted_at = now
            if self.preparing_at is None:
                self.preparing_at = now
        
        # on_delivery (rider accepts): set confirmed_at
        if new_status == 'on_delivery':
            if self.confirmed_at is None:
                self.confirmed_at = now
        
        self.updated_at = now
    
    def to_dict(self):
        return {
            'id': self.id,
            'customer_id': self.customer_id,
            'store_id': self.store_id,
            'rider_id': self.rider_id,
            'order_type': self.order_type,
            'status': self.status,
            'subtotal_amount': float(self.subtotal_amount or 0),
            'delivery_fee': float(self.delivery_fee or 0),
            'distance_km': self.distance_km,
            'total_amount': float(self.total_amount or 0),
            'payment_method': self.payment_method,
            'payment_status': self.payment_status,
            'payment_proof_url': self.payment_proof_url,  # Cloudinary only
            'payment_proof_public_id': self.payment_proof_public_id,
            'delivery_address': self.delivery_address,
            'delivery_notes': self.delivery_notes,
            'delivery_proof_url': self.delivery_proof_url,  # Cloudinary only
            'delivery_proof_public_id': self.delivery_proof_public_id,
            'delivery_proof_2_url': self.delivery_proof_2_url,  # Cloudinary only
            'delivery_proof_2_public_id': self.delivery_proof_2_public_id,
            'requested_delivery_date': self.requested_delivery_date.isoformat() if self.requested_delivery_date else None,
            'requested_delivery_time': self.requested_delivery_time,
            'customer_latitude': self.customer_latitude,
            'customer_longitude': self.customer_longitude,
            'mapbox_place_id': self.mapbox_place_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'pending_at': self.pending_at.isoformat() if self.pending_at else None,
            'accepted_at': self.accepted_at.isoformat() if self.accepted_at else None,
            'preparing_at': self.preparing_at.isoformat() if self.preparing_at else None,
            'done_preparing_at': self.done_preparing_at.isoformat() if self.done_preparing_at else None,
            'confirmed_at': self.confirmed_at.isoformat() if self.confirmed_at else None,
            'delivered_at': self.delivered_at.isoformat() if self.delivered_at else None,
            'customer_name': self.customer.full_name if self.customer else None,
            'customer_avatar': self.customer.avatar_url if self.customer else None,  # Cloudinary only
            'store_name': self.store.name if self.store else None,
            'store_logo': self.store.logo_url if self.store else None,  # Cloudinary only
            'rider_name': self.assigned_rider.user.full_name if self.assigned_rider and self.assigned_rider.user else None
        }


class OrderItem(db.Model):
    __tablename__ = 'order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id', ondelete='SET NULL'), nullable=True)
    quantity = db.Column(db.Integer, default=1)
    price = db.Column(db.Numeric(10, 2))
    
    variant = db.relationship('ProductVariant', backref='order_items', lazy=True)
    
    @property
    def product_image(self):
        """Get the appropriate product image (variant or main) - Cloudinary only"""
        if self.variant and self.variant.image_url:
            return self.variant.image_url
        elif self.product and self.product.images:
            primary = next((img for img in self.product.images if img.is_primary), self.product.images[0] if self.product.images else None)
            return primary.image_url if primary else None
        return None
    
    def to_dict(self):
        product = self.product
        variant_name = None
        
        if self.variant:
            variant_name = self.variant.name
        
        return {
            'id': self.id,
            'order_id': self.order_id,
            'product_id': self.product_id,
            'variant_id': self.variant_id,
            'variant_name': variant_name,
            'quantity': self.quantity,
            'price': float(self.price) if self.price else 0,
            'total': float(self.quantity * self.price) if self.price else 0,
            'product_name': product.name if product else None,
            'product_image_url': self.product_image  # Cloudinary only
        }


class RiderLocation(db.Model):
    __tablename__ = 'rider_locations'
    
    id = db.Column(db.Integer, primary_key=True)
    rider_id = db.Column(db.Integer, db.ForeignKey('riders.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'))
    location = db.Column(Geometry('POINT', srid=4326), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'rider_id': self.rider_id,
            'order_id': self.order_id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }

class POSOrder(db.Model):
    __tablename__ = 'pos_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False)
    total_amount = db.Column(db.Numeric(10, 2))
    
    # ===== NEW FIELDS FOR CASH MANAGEMENT =====
    amount_given = db.Column(db.Numeric(10, 2), nullable=True)  # Amount customer paid
    change_amount = db.Column(db.Numeric(10, 2), nullable=True)  # Change returned to customer
    payment_method = db.Column(db.String(20), default='cash')  # cash, gcash, card
    # ==========================================
    
    # ===== NEW DISCOUNT FIELD =====
    discount = db.Column(db.Numeric(10, 2), default=0.00, nullable=True)  # Discount amount
    # ==============================
    
    customer_name = db.Column(db.String(100))
    customer_contact = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # FIXED: Use back_populates instead of backref
    items = db.relationship('POSOrderItem', back_populates='pos_order', lazy=True, cascade='all, delete-orphan')
    
    @property
    def subtotal(self):
        """Calculate subtotal from items"""
        return sum(item.price * item.quantity for item in self.items) if self.items else 0
    
    def to_dict(self):
        subtotal = float(self.subtotal)
        discount = float(self.discount or 0)
        total = float(self.total_amount or 0)
        
        return {
            'id': self.id,
            'store_id': self.store_id,
            'subtotal': subtotal,
            'discount': discount,
            'total_amount': total,
            'amount_given': float(self.amount_given) if self.amount_given else 0,
            'change_amount': float(self.change_amount) if self.change_amount else 0,
            'payment_method': self.payment_method or 'cash',
            'customer_name': self.customer_name,
            'customer_contact': self.customer_contact,
            'items': [item.to_dict() for item in self.items],
            'item_count': len(self.items),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class POSOrderItem(db.Model):
    __tablename__ = 'pos_order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    pos_order_id = db.Column(db.Integer, db.ForeignKey('pos_orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id', ondelete='SET NULL'), nullable=True)
    quantity = db.Column(db.Integer, default=1)
    price = db.Column(db.Numeric(10, 2))
    
    # FIXED: Use back_populates to match the relationship in POSOrder
    pos_order = db.relationship('POSOrder', back_populates='items', lazy=True)
    
    # FIXED: Use back_populates for product (matches the relationship in Product)
    product = db.relationship('Product', back_populates='pos_order_items', lazy=True)
    
    # This one can stay as backref since it's a simple one-way relationship
    variant = db.relationship('ProductVariant', backref='pos_order_items', lazy=True)
    
    @property
    def product_image(self):
        """Get the appropriate product image (variant or main) - Cloudinary only"""
        if self.variant and self.variant.image_url:
            return self.variant.image_url
        elif self.product and self.product.images:
            primary = next((img for img in self.product.images if img.is_primary), self.product.images[0] if self.product.images else None)
            return primary.image_url if primary else None
        return None
    
    def to_dict(self):
        product = self.product
        variant_name = None
        
        if self.variant:
            variant_name = self.variant.name
        
        return {
            'id': self.id,
            'pos_order_id': self.pos_order_id,
            'product_id': self.product_id,
            'variant_id': self.variant_id,
            'variant_name': variant_name,
            'quantity': self.quantity,
            'price': float(self.price) if self.price else 0,
            'total': float(self.quantity * self.price) if self.price else 0,
            'product_name': product.name if product else None,
            'product_image_url': self.product_image,  # Cloudinary only
            # ADD THESE LINES - Category information
            'main_category_name': product.main_category.name if product and product.main_category else None,
            'main_category_id': product.main_category_id if product else None,
            'subcategory_name': product.store_category.name if product and product.store_category else None,
            'subcategory_id': product.store_category_id if product else None
        }


class Testimonial(db.Model):
    __tablename__ = 'testimonials'
    
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'))
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'customer_id': self.customer_id,
            'store_id': self.store_id,
            'order_id': self.order_id,
            'rating': self.rating,
            'comment': self.comment,
            'customer_name': self.customer.full_name if self.customer else None,
            'customer_avatar': self.customer.avatar_url if self.customer else None,  # Cloudinary only
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ProductRating(db.Model):
    """Per-product rating submitted by customers after order delivery."""
    __tablename__ = 'product_ratings'
    
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id', ondelete='SET NULL'), nullable=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    order_item_id = db.Column(db.Integer, db.ForeignKey('order_items.id', ondelete='SET NULL'), nullable=True)
    rating = db.Column(db.Integer, nullable=False)  # 1-5 stars
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    customer = db.relationship('User', backref=db.backref('product_ratings', lazy='dynamic'))
    product = db.relationship('Product', backref=db.backref('ratings', lazy='dynamic'))
    variant = db.relationship('ProductVariant', backref=db.backref('ratings', lazy='dynamic'))
    order = db.relationship('Order', backref=db.backref('product_ratings', lazy='dynamic'))
    order_item = db.relationship('OrderItem', backref=db.backref('rating', uselist=False))
    
    __table_args__ = (
        db.UniqueConstraint('customer_id', 'order_item_id', name='unique_customer_order_item_rating'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'customer_id': self.customer_id,
            'product_id': self.product_id,
            'variant_id': self.variant_id,
            'order_id': self.order_id,
            'order_item_id': self.order_item_id,
            'rating': self.rating,
            'comment': self.comment,
            'customer_name': self.customer.full_name if self.customer else None,
            'customer_avatar': self.customer.avatar_url if self.customer else None,
            'variant_name': self.variant.name if self.variant else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class OrderAnalytics(db.Model):
    __tablename__ = 'order_analytics'
    
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False)
    total_orders = db.Column(db.Integer, default=0)
    completed_orders = db.Column(db.Integer, default=0)
    total_revenue = db.Column(db.Numeric(12, 2), default=0)
    date = db.Column(db.Date, default=datetime.utcnow().date)
    
    def to_dict(self):
        return {
            'id': self.id,
            'store_id': self.store_id,
            'total_orders': self.total_orders,
            'completed_orders': self.completed_orders,
            'total_revenue': float(self.total_revenue) if self.total_revenue else 0,
            'date': self.date.isoformat() if self.date else None
        }


@event.listens_for(Order.status, 'set')
def update_analytics(target, value, oldvalue, initiator):
    if value == 'delivered' and oldvalue != 'delivered':
        from app import db
        from datetime import date
        
        today = date.today()
        analytics = OrderAnalytics.query.filter_by(
            store_id=target.store_id, 
            date=today
        ).first()
        
        if not analytics:
            analytics = OrderAnalytics(store_id=target.store_id, date=today)
            db.session.add(analytics)
        
        # Fix: Handle None values (from existing NULL records in database)
        analytics.completed_orders = (analytics.completed_orders or 0) + 1
        if target.total_amount:
            analytics.total_revenue = (analytics.total_revenue or 0) + target.total_amount


class Cart(db.Model):
    __tablename__ = 'carts'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('cart', uselist=False, cascade='all, delete-orphan'))
    items = db.relationship('CartItem', backref='cart', lazy='dynamic', cascade='all, delete-orphan')
    
    def to_dict(self):
        items_list = [item.to_dict() for item in self.items.all()]
        
        # Group items by store
        stores_dict = {}
        for item in items_list:
            if item['product']:
                store_id = item['product']['store_id']
                store_name = item['product'].get('store').get('name') if item['product'].get('store') else f'Store {store_id}'
                
                if store_id not in stores_dict:
                    stores_dict[store_id] = {
                        'store_id': store_id,
                        'store_name': store_name,
                        'items': [],
                        'subtotal': 0,
                        'item_count': 0
                    }
                
                stores_dict[store_id]['items'].append(item)
                stores_dict[store_id]['item_count'] += item['quantity']
                if item['is_selected']:
                    stores_dict[store_id]['subtotal'] += item['subtotal']
        
        stores_list = list(stores_dict.values())
        
        # Calculate selected total (only selected items)
        selected_total = sum(item['subtotal'] for item in items_list if item['is_selected'])
        
        return {
            'id': self.id,
            'user_id': self.user_id,
            'items': items_list,
            'stores': stores_list,  # Grouped by store
            'total': sum(item['subtotal'] for item in items_list),  # All items
            'selected_total': selected_total,  # Only selected items
            'item_count': sum(item['quantity'] for item in items_list),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class CartItem(db.Model):
    __tablename__ = 'cart_items'
    
    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.Integer, db.ForeignKey('carts.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id', ondelete='CASCADE'), nullable=True)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    is_selected = db.Column(db.Boolean, default=True)  # Checkbox for checkout selection
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    product = db.relationship('Product', backref=db.backref('cart_items', lazy='dynamic', passive_deletes=True))
    variant = db.relationship('ProductVariant', backref='cart_items', lazy=True)
    
    @property
    def subtotal(self):
        # Use effective sale-aware price (variant takes precedence)
        if self.variant:
            return self.variant.effective_price * self.quantity
        return self.product.effective_price * self.quantity if self.product else 0
    
    @property
    def item_image(self):
        """Get the appropriate image for cart display - Cloudinary only"""
        if self.variant and self.variant.image_url:
            return self.variant.image_url
        elif self.product and self.product.images:
            primary = next((img for img in self.product.images if img.is_primary), self.product.images[0] if self.product.images else None)
            return primary.image_url if primary else None
        return None
    
    def to_dict(self):
        product_dict = self.product.to_dict() if self.product else None
        variant_dict = self.variant.to_dict() if self.variant else None
        
        # Extract store name from product
        store_name = 'Unknown Store'
        if self.product and self.product.store:
            store_name = self.product.store.name
        
        # Resolve effective (sale-aware) price and sale metadata for Flutter
        if self.variant:
            effective = float(self.variant.effective_price)
            original  = float(self.variant.price)
            disc_pct  = self.variant.discount_pct
        elif self.product:
            effective = float(self.product.effective_price)
            original  = float(self.product.price)
            disc_pct  = self.product.discount_pct
        else:
            effective = 0.0
            original  = 0.0
            disc_pct  = None

        return {
            'id': self.id,
            'cart_id': self.cart_id,
            'product_id': self.product_id,
            'variant_id': self.variant_id,
            'store_id': self.product.store_id if self.product else None,
            'store_name': store_name,
            'product': product_dict,
            'variant': variant_dict,
            'quantity': self.quantity,
            'is_selected': self.is_selected,
            'subtotal': float(self.subtotal),
            'image_url': self.item_image,
            # Top-level price fields consumed by Flutter CartItem.fromJson
            'price': effective,
            'original_price': original if disc_pct else None,
            'discount_pct': disc_pct,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    __table_args__ = (
        db.UniqueConstraint('cart_id', 'product_id', 'variant_id', name='unique_cart_product_variant'),
    )


class UserAddress(db.Model):
    __tablename__ = 'user_addresses'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    municipality = db.Column(db.String(100), nullable=False)
    barangay = db.Column(db.String(100), nullable=False)
    street = db.Column(db.String(200), nullable=True)
    building_details = db.Column(db.String(200), nullable=True)
    address_line = db.Column(db.String(500), nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    place_id = db.Column(db.String(100), nullable=True)
    address_label = db.Column(db.String(50), default='Home')
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'municipality': self.municipality,
            'barangay': self.barangay,
            'street': self.street,
            'building_details': self.building_details,
            'address_line': self.address_line,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'place_id': self.place_id,
            'address_label': self.address_label,
            'is_default': self.is_default,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class RiderOTP(db.Model):
    """Email verification for rider account creation"""
    __tablename__ = 'rider_otps'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False, index=True)
    verification_token = db.Column(db.String(64), nullable=False, unique=True, index=True)
    rider_data = db.Column(db.JSON, nullable=False)  # Stores pending rider info
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Seller who initiated
    is_verified = db.Column(db.Boolean, default=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    store = db.relationship('Store', backref='rider_otps')
    creator = db.relationship('User', backref='created_rider_otps')
    
    def is_expired(self):
        return datetime.utcnow() > self.expires_at
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'store_id': self.store_id,
            'is_verified': self.is_verified,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class CustomerOTP(db.Model):
    """Email verification for customer self-registration.

    Mirrors the rider OTP design but is initiated by the prospective customer.
    The OTP itself is stored as a salted hash (never plaintext); the pending
    registration payload (full_name, password_hash, phone) lives in
    `customer_data` until verification succeeds and a real `User` row is created.
    """
    __tablename__ = 'customer_otps'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False, unique=True, index=True)
    otp_hash = db.Column(db.String(255), nullable=False)
    customer_data = db.Column(db.JSON, nullable=False)  # {full_name, password_hash, phone}
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    attempts = db.Column(db.Integer, default=0, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    last_sent_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    verified_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def is_expired(self):
        return datetime.utcnow() > self.expires_at

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'is_verified': self.is_verified,
            'attempts': self.attempts,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'verified_at': self.verified_at.isoformat() if self.verified_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class MunicipalityBoundary(db.Model):
    __tablename__ = 'municipality_boundaries'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    province = db.Column(db.String(100), nullable=True, index=True)
    region = db.Column(db.String(100), nullable=True)
    psgc_code = db.Column(db.String(20), nullable=True, index=True)
    boundary = db.Column(Geometry('MULTIPOLYGON', srid=4326), nullable=False)
    min_lat = db.Column(db.Float, nullable=True)
    max_lat = db.Column(db.Float, nullable=True)
    min_lng = db.Column(db.Float, nullable=True)
    max_lng = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_geojson(self):
        from geoalchemy2.shape import to_shape
        from shapely.geometry import mapping
        
        geom = to_shape(self.boundary)
        return {
            'type': 'Feature',
            'properties': {
                'id': self.id,
                'name': self.name,
                'province': self.province,
                'region': self.region,
                'psgc': self.psgc_code
            },
            'geometry': mapping(geom)
        }
    
    @staticmethod
    def get_adjacent_municipalities(municipality_name, province=None):
        from sqlalchemy import func
        from geoalchemy2.functions import ST_Touches
        
        query = MunicipalityBoundary.query.filter_by(name=municipality_name)
        if province:
            query = query.filter_by(province=province)
        
        municipality = query.first()
        if not municipality:
            return []
        
        adjacent_query = MunicipalityBoundary.query.filter(
            ST_Touches(MunicipalityBoundary.boundary, municipality.boundary)
        )
        
        if province:
            adjacent_query = adjacent_query.filter_by(province=province)
        
        adjacent = adjacent_query.all()
        
        return [{
            'id': m.id,
            'name': m.name,
            'province': m.province
        } for m in adjacent]
    
    @staticmethod
    def get_municipalities_in_province(province):
        return MunicipalityBoundary.query.filter_by(province=province).order_by(MunicipalityBoundary.name).all()
    
    @staticmethod
    def find_containing_municipality(lat, lng, province=None):
        from geoalchemy2.functions import ST_Contains
        from geoalchemy2.shape import from_shape
        from shapely.geometry import Point
        
        point = from_shape(Point(lng, lat), srid=4326)
        
        query = MunicipalityBoundary.query.filter(ST_Contains(MunicipalityBoundary.boundary, point))
        if province:
            query = query.filter_by(province=province)
        
        return query.first()
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'province': self.province,
            'region': self.region,
            'psgc_code': self.psgc_code,
            'bounds': {
                'min_lat': self.min_lat,
                'max_lat': self.max_lat,
                'min_lng': self.min_lng,
                'max_lng': self.max_lng
            } if self.min_lat else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ═════════════════════════════════════════════════════════════════════════════
# CHAT / MESSAGING MODELS
# ═════════════════════════════════════════════════════════════════════════════

class Conversation(db.Model):
    """A chat conversation between a customer and a seller (store)."""
    __tablename__ = 'conversations'

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False)

    # Denormalized last-message data for fast inbox queries
    last_message_text = db.Column(db.Text, nullable=True)
    last_message_at = db.Column(db.DateTime, nullable=True)
    last_sender_id = db.Column(db.Integer, nullable=True)

    # Per-participant unread counters
    customer_unread = db.Column(db.Integer, default=0)
    seller_unread = db.Column(db.Integer, default=0)

    # Soft-delete per participant (allows "delete conversation" without affecting the other side)
    customer_deleted_at = db.Column(db.DateTime, nullable=True)
    seller_deleted_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    customer = db.relationship('User', foreign_keys=[customer_id], backref=db.backref('customer_conversations', lazy='dynamic'))
    seller = db.relationship('User', foreign_keys=[seller_id], backref=db.backref('seller_conversations', lazy='dynamic'))
    store = db.relationship('Store', backref=db.backref('conversations', lazy='dynamic'))
    messages = db.relationship('ChatMessage', back_populates='conversation', lazy='dynamic',
                               cascade='all, delete-orphan', order_by='ChatMessage.created_at')

    __table_args__ = (
        db.UniqueConstraint('customer_id', 'store_id', name='unique_customer_store_conversation'),
    )

    def unread_for(self, user_id):
        if user_id == self.customer_id:
            return self.customer_unread
        return self.seller_unread

    def to_dict(self, current_user_id=None):
        # Determine the "other" participant relative to current user
        if current_user_id == self.customer_id:
            other = self.seller
            unread = self.customer_unread
        else:
            other = self.customer
            unread = self.seller_unread

        return {
            'id': self.id,
            'customer_id': self.customer_id,
            'seller_id': self.seller_id,
            'store_id': self.store_id,
            'store_name': self.store.name if self.store else None,
            'store_logo': self.store.logo_url if self.store else None,
            'other_user': {
                'id': other.id,
                'full_name': other.full_name,
                'avatar_url': other.avatar_url,
                'role': other.role,
            } if other else None,
            'last_message_text': self.last_message_text,
            'last_message_at': to_pht_iso(self.last_message_at),
            'last_sender_id': self.last_sender_id,
            'unread_count': unread,
            'created_at': to_pht_iso(self.created_at),
            'updated_at': to_pht_iso(self.updated_at),
        }


class ChatMessage(db.Model):
    """A single message inside a conversation."""
    __tablename__ = 'chat_messages'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Content
    message_type = db.Column(db.String(20), default='text')  # text, image
    text = db.Column(db.Text, nullable=True)

    # Image attachment (Cloudinary)
    image_url = db.Column(db.String(500), nullable=True)
    image_public_id = db.Column(db.String(255), nullable=True)

    # Reply
    reply_to_id = db.Column(db.Integer, db.ForeignKey('chat_messages.id'), nullable=True)

    # Soft delete
    is_deleted = db.Column(db.Boolean, default=False)

    # Read receipt
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    conversation = db.relationship('Conversation', back_populates='messages')
    sender = db.relationship('User', backref=db.backref('sent_messages', lazy='dynamic'))
    reply_to = db.relationship('ChatMessage', remote_side='ChatMessage.id', uselist=False)

    def to_dict(self):
        d = {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'sender_id': self.sender_id,
            'sender_name': self.sender.full_name if self.sender else None,
            'sender_avatar': self.sender.avatar_url if self.sender else None,
            'message_type': self.message_type,
            'is_deleted': self.is_deleted or False,
            'is_read': self.is_read,
            'read_at': to_pht_iso(self.read_at),
            'created_at': to_pht_iso(self.created_at),
            'reply_to_id': self.reply_to_id,
            'reply_to_text': None,
            'reply_to_sender_name': None,
        }
        if self.is_deleted:
            d['text'] = None
            d['image_url'] = None
            d['image_public_id'] = None
        else:
            d['text'] = self.text
            d['image_url'] = self.image_url
            d['image_public_id'] = self.image_public_id
        if self.reply_to_id and self.reply_to:
            d['reply_to_text'] = self.reply_to.text if not self.reply_to.is_deleted else None
            d['reply_to_sender_name'] = self.reply_to.sender.full_name if self.reply_to.sender else None
        return d