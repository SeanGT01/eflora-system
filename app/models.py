from app.extensions import db
from geoalchemy2 import Geometry
from sqlalchemy import event
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import os
from decimal import Decimal
from sqlalchemy.dialects.postgresql import JSON


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
    avatar_filename = db.Column(db.String(255), nullable=True)  # Path to profile picture
    
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
    
    def to_dict(self):
        return {
            'id': self.id,
            'full_name': self.full_name,
            'first_name': self.full_name.split()[0] if ' ' in self.full_name else self.full_name,
            'last_name': self.full_name.split()[1] if ' ' in self.full_name and len(self.full_name.split()) > 1 else '',
            'email': self.email,
            'role': self.role,
            'status': self.status,
            'phone': self.phone,
            'birthday': self.birthday.isoformat() if self.birthday else None,
            'gender': self.gender,
            'avatar_url': f'/static/uploads/avatars/{self.avatar_filename}' if self.avatar_filename else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


# ═════════════════════════════════════════════════════════════════════════════
# GCASH QR CODE MODEL (NEW)
# ═════════════════════════════════════════════════════════════════════════════
class GCashQR(db.Model):
    __tablename__ = 'gcash_qrs'
    
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id', ondelete='CASCADE'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    is_primary = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    store = db.relationship('Store', back_populates='gcash_qr_images')
    
    def to_dict(self):
        return {
            'id': self.id,
            'store_id': self.store_id,
            'filename': self.filename,
            'url': f'/static/uploads/gcash_qr/{self.filename}',
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
            'logo_path': self.seller_application.store_logo_path if self.seller_application else None,
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
            'gcash_instructions': self.gcash_instructions
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
    store_logo_path = db.Column(db.String(500))
    government_id_path = db.Column(db.String(500))
    status = db.Column(db.String(20), default='pending')
    admin_notes = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    applicant = db.relationship('User', foreign_keys=[user_id], back_populates='seller_applications')
    reviewer = db.relationship('User', foreign_keys=[reviewed_by], back_populates='reviewed_seller_applications')
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'full_name': self.applicant.full_name if self.applicant else None,
            'store_name': self.store_name,
            'store_description': self.store_description,
            'store_logo_url': f'/static/uploads/seller_logos/{self.store_logo_path}' if self.store_logo_path else None,
            'government_id_url': f'/static/uploads/govt_ids/{self.government_id_path}' if self.government_id_path else None,
            'status': self.status,
            'admin_notes': self.admin_notes,
            'submitted_at': self.submitted_at.isoformat() if self.submitted_at else None,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            'reviewer_name': self.reviewer.full_name if self.reviewer else None
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
            'vehicle_type': self.vehicle_type,
            'license_plate': self.license_plate,
            'is_active': self.is_active
        }


class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    stock_quantity = db.Column(db.Integer, default=0)
    category = db.Column(db.String(50))
    is_available = db.Column(db.Boolean, default=True)
    
    # Archive fields
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    archived_at = db.Column(db.DateTime, nullable=True)
    archived_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    images = db.relationship('ProductImage', back_populates='product', lazy=True, cascade='all, delete-orphan', order_by='ProductImage.sort_order')
    variants = db.relationship('ProductVariant', back_populates='product', lazy=True, cascade='all, delete-orphan', order_by='ProductVariant.sort_order')
    order_items = db.relationship('OrderItem', backref='product', lazy=True)
    pos_order_items = db.relationship('POSOrderItem', backref='product', lazy=True)
    archived_by_user = db.relationship('User', foreign_keys=[archived_by], backref='archived_products')
    
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
    
    def to_dict(self):
        sorted_images = sorted(self.images, key=lambda x: x.sort_order)
        primary_image = next((img for img in sorted_images if img.is_primary), sorted_images[0] if sorted_images else None)
        
        # Sort variants by sort_order
        sorted_variants = sorted(self.variants, key=lambda v: v.sort_order)
        
        data = {
            'id': self.id,
            'store_id': self.store_id,
            'name': self.name,
            'description': self.description,
            'price': float(self.price) if self.price else 0,
            'stock_quantity': self.stock_quantity,
            'category': self.category,
            'image_url': f'/static/uploads/products/{primary_image.filename}' if primary_image else None,
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
    filename = db.Column(db.String(255), nullable=False)
    is_primary = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    product = db.relationship('Product', back_populates='images')
    
    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'filename': self.filename,
            'image_url': f'/static/uploads/products/{self.filename}',
            'is_primary': self.is_primary,
            'sort_order': self.sort_order
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
    stock_quantity = db.Column(db.Integer, default=0)
    sku = db.Column(db.String(50), nullable=True)  # Stock Keeping Unit
    
    # Variant image (optional - if not provided, uses product's main image)
    image_filename = db.Column(db.String(255), nullable=True)
    
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
    
    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'name': self.name,
            'price': float(self.price) if self.price else 0,
            'stock_quantity': self.stock_quantity,
            'sku': self.sku,
            'image_url': f'/static/uploads/product_variants/{self.image_filename}' if self.image_filename else None,
            'attributes': self.attributes,
            'sort_order': self.sort_order,
            'is_available': self.is_available,
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
    payment_proof = db.Column(db.String(255))
    
    # Delivery information
    delivery_location = db.Column(Geometry('POINT', srid=4326))
    delivery_address = db.Column(db.Text)
    delivery_notes = db.Column(db.Text)
    
    # ===== MAPBOX CUSTOMER FIELDS =====
    customer_latitude = db.Column(db.Float, nullable=True)
    customer_longitude = db.Column(db.Float, nullable=True)
    mapbox_place_id = db.Column(db.String(100), nullable=True)
    # ==================================
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')
    
    def compute_total(self):
        subtotal = Decimal(self.subtotal_amount or 0)
        delivery = Decimal(self.delivery_fee or 0)
        self.total_amount = subtotal + delivery
    
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
            'payment_proof_url': f'/static/uploads/payments/{self.payment_proof}' if self.payment_proof else None,
            'delivery_address': self.delivery_address,
            'delivery_notes': self.delivery_notes,
            'customer_latitude': self.customer_latitude,
            'customer_longitude': self.customer_longitude,
            'mapbox_place_id': self.mapbox_place_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'customer_name': self.customer.full_name if self.customer else None,
            'store_name': self.store.name if self.store else None,
            'rider_name': self.assigned_rider.user.full_name 
                if self.assigned_rider and self.assigned_rider.user else None
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
    
    def to_dict(self):
        product = self.product
        primary_image = None
        if product and product.images:
            primary_image = next((img for img in product.images if img.is_primary), product.images[0])
        
        # Use variant image if variant is selected
        image_filename = primary_image.filename if primary_image else None
        variant_name = None
        
        if self.variant:
            if self.variant.image_filename:
                image_filename = self.variant.image_filename
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
            'product_image': image_filename
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
    customer_name = db.Column(db.String(100))
    customer_contact = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    items = db.relationship('POSOrderItem', backref='pos_order', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'store_id': self.store_id,
            'total_amount': float(self.total_amount) if self.total_amount else 0,
            'customer_name': self.customer_name,
            'customer_contact': self.customer_contact,
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
    
    variant = db.relationship('ProductVariant', backref='pos_order_items', lazy=True)
    
    def to_dict(self):
        product = self.product
        primary_image = None
        if product and product.images:
            primary_image = next((img for img in product.images if img.is_primary), product.images[0])
        
        # Use variant image if variant is selected
        image_filename = primary_image.filename if primary_image else None
        variant_name = None
        
        if self.variant:
            if self.variant.image_filename:
                image_filename = self.variant.image_filename
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
            'product_image': image_filename
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
            'created_at': self.created_at.isoformat() if self.created_at else None
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
        
        analytics.completed_orders += 1
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
        return {
            'id': self.id,
            'user_id': self.user_id,
            'items': items_list,
            'total': sum(item['subtotal'] for item in items_list),
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    product = db.relationship('Product', backref=db.backref('cart_items', lazy='dynamic', passive_deletes=True))
    variant = db.relationship('ProductVariant', backref='cart_items', lazy=True)
    
    @property
    def subtotal(self):
        # Use variant price if variant is selected, otherwise product price
        if self.variant:
            return self.variant.price * self.quantity
        return self.product.price * self.quantity if self.product else 0
    
    def to_dict(self):
        product_dict = self.product.to_dict() if self.product else None
        variant_dict = self.variant.to_dict() if self.variant else None
        
        return {
            'id': self.id,
            'cart_id': self.cart_id,
            'product_id': self.product_id,
            'variant_id': self.variant_id,
            'product': product_dict,
            'variant': variant_dict,
            'quantity': self.quantity,
            'subtotal': float(self.subtotal),
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