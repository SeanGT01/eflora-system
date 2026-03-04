from app.extensions import db
from geoalchemy2 import Geometry
from sqlalchemy import event
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import os
from decimal import Decimal

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

class Store(db.Model):
    __tablename__ = 'stores'
    
    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.Text, nullable=False)  # Full formatted address (kept for backward compatibility)
    
    # ===== NEW ADDRESS FIELDS FOR DROPDOWN SELECTION =====
    municipality = db.Column(db.String(100), nullable=True)  # Municipality/City
    barangay = db.Column(db.String(100), nullable=True)      # Barangay
    street = db.Column(db.String(200), nullable=True)        # Street/Building details
    # ====================================================
    
    contact_number = db.Column(db.String(20))
    description = db.Column(db.Text)
    delivery_area = db.Column(Geometry('POLYGON', srid=4326))
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
    # Delivery method preference
    delivery_method = db.Column(db.String(20), default='radius')  # 'radius', 'zone', or 'municipality'
    
    # NEW: Store selected municipalities for municipality delivery mode
    selected_municipalities = db.Column(db.JSON, nullable=True)  # Stores array of selected municipality names
    
    # Delivery pricing configuration
    base_delivery_fee = db.Column(db.Numeric(10, 2), default=50.00)
    delivery_rate_per_km = db.Column(db.Numeric(10, 2), default=20.00)
    free_delivery_minimum = db.Column(db.Numeric(10, 2), default=500.00)
    max_delivery_distance = db.Column(db.Float, default=15.0)
    
    # Store coordinates (simple floats for easy calculations)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    
    # Formatted address from reverse geocoding
    formatted_address = db.Column(db.String(500), nullable=True)
    place_id = db.Column(db.String(100), nullable=True)
    # ==================================
    
    # Relationships
    products = db.relationship('Product', backref='store', lazy=True, cascade='all, delete-orphan')
    riders = db.relationship('Rider', backref='store', lazy=True)
    orders = db.relationship('Order', backref='store', lazy=True)
    pos_orders = db.relationship('POSOrder', backref='store', lazy=True)
    testimonials = db.relationship('Testimonial', backref='store', lazy=True)
    analytics = db.relationship('OrderAnalytics', backref='store', lazy=True)
    
    # FIXED: Relationships for seller approval - unique backref names
    seller_application = db.relationship('SellerApplication', foreign_keys=[seller_application_id], backref='approved_store_record', lazy=True)
    approved_by_user = db.relationship('User', foreign_keys=[approved_by], backref='stores_approved', lazy=True)
    
    def calculate_delivery_fee(self, distance_km, subtotal):
        """Calculate delivery fee based on distance and order subtotal"""
        from decimal import Decimal
        
        # Free delivery for orders above threshold
        if subtotal >= self.free_delivery_minimum:
            return Decimal('0')
        
        # Calculate fee: base fee + (distance * rate per km)
        fee = Decimal(str(self.base_delivery_fee or 0)) + \
              (Decimal(str(self.delivery_rate_per_km or 0)) * Decimal(str(distance_km)))
        
        # Ensure minimum fee
        min_fee = Decimal('30.00')
        if fee < min_fee:
            fee = min_fee
        
        return fee
    
    def can_deliver_to(self, customer_lat, customer_lng):
        """Check if customer is within delivery area based on selected method"""
        if self.delivery_method == 'zone' and self.delivery_area:
            # Use custom zone
            from geoalchemy2.functions import ST_Contains
            from geoalchemy2.shape import from_shape
            from shapely.geometry import Point
            
            point = from_shape(Point(customer_lng, customer_lat), srid=4326)
            result = db.session.query(ST_Contains(self.delivery_area, point)).scalar()
            return bool(result)
        elif self.delivery_method == 'municipality' and self.selected_municipalities:
            # Use municipality boundaries - this would need a spatial query
            # For now, we'll use a simplified check
            from app.laguna_addresses import get_coordinates
            # This is a placeholder - you'd need to implement proper boundary checking
            return True
        else:
            # Use radius method (default)
            distance = self.calculate_distance(customer_lat, customer_lng)
            return distance <= self.delivery_radius_km
    
    def calculate_distance(self, lat2, lng2):
        """Calculate distance between store and customer (Haversine formula)"""
        from math import radians, sin, cos, sqrt, atan2
        
        if not self.latitude or not self.longitude:
            return float('inf')
        
        # Convert to radians
        lat1, lng1 = radians(self.latitude), radians(self.longitude)
        lat2, lng2 = radians(lat2), radians(lng2)
        
        # Haversine formula
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
        # Earth radius in kilometers (6371 km)
        return 6371 * c
    
    def to_dict(self):
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
            
            # NEW ADDRESS FIELDS
            'municipality': self.municipality,
            'barangay': self.barangay,
            'street': self.street,
            
            # Mapbox fields
            'delivery_method': self.delivery_method,
            'selected_municipalities': self.selected_municipalities,  # NEW
            'base_delivery_fee': float(self.base_delivery_fee or 0),
            'delivery_rate_per_km': float(self.delivery_rate_per_km or 0),
            'free_delivery_minimum': float(self.free_delivery_minimum or 0),
            'max_delivery_distance': self.max_delivery_distance,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'formatted_address': self.formatted_address,
            'place_id': self.place_id
        }


class SellerApplication(db.Model):
    __tablename__ = 'seller_applications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Store Information
    store_name = db.Column(db.String(100), nullable=False)
    store_description = db.Column(db.Text)
    store_logo_path = db.Column(db.String(500))  # Path to uploaded logo
    
    # Documents
    government_id_path = db.Column(db.String(500))  # Path to uploaded ID
    
    # Status and Tracking
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    admin_notes = db.Column(db.Text)  # Notes from admin about rejection/approval
    
    # Timestamps
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Relationships
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
    
    # Relationships
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
    order_items = db.relationship('OrderItem', backref='product', lazy=True)
    pos_order_items = db.relationship('POSOrderItem', backref='product', lazy=True)
    
    # Relationship for archived_by
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
            
            # Mapbox fields
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
    quantity = db.Column(db.Integer, default=1)
    price = db.Column(db.Numeric(10, 2))
    
    def to_dict(self):
        product = self.product
        primary_image = None
        if product and product.images:
            primary_image = next((img for img in product.images if img.is_primary), product.images[0])
        
        return {
            'id': self.id,
            'order_id': self.order_id,
            'product_id': self.product_id,
            'quantity': self.quantity,
            'price': float(self.price) if self.price else 0,
            'total': float(self.quantity * self.price) if self.price else 0,
            'product_name': product.name if product else None,
            'product_image': primary_image.filename if primary_image else None
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
    quantity = db.Column(db.Integer, default=1)
    price = db.Column(db.Numeric(10, 2))
    
    def to_dict(self):
        product = self.product
        primary_image = None
        if product and product.images:
            primary_image = next((img for img in product.images if img.is_primary), product.images[0])
            
        return {
            'id': self.id,
            'pos_order_id': self.pos_order_id,
            'product_id': self.product_id,
            'quantity': self.quantity,
            'price': float(self.price) if self.price else 0,
            'total': float(self.quantity * self.price) if self.price else 0,
            'product_name': product.name if product else None,
            'product_image': primary_image.filename if primary_image else None
        }


class Testimonial(db.Model):
    __tablename__ = 'testimonials'
    
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'))
    rating = db.Column(db.Integer, nullable=False)  # 1-5
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


# Event listener to update analytics
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
    quantity = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    product = db.relationship('Product', backref=db.backref('cart_items', lazy='dynamic', passive_deletes=True))
    
    @property
    def subtotal(self):
        return self.product.price * self.quantity if self.product else 0
    
    def to_dict(self):
        return {
            'id': self.id,
            'cart_id': self.cart_id,
            'product_id': self.product_id,
            'product': self.product.to_dict() if self.product else None,
            'quantity': self.quantity,
            'subtotal': float(self.subtotal),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    __table_args__ = (
        db.UniqueConstraint('cart_id', 'product_id', name='unique_cart_product'),
    )


class UserAddress(db.Model):
    __tablename__ = 'user_addresses'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Laguna-specific address fields
    municipality = db.Column(db.String(100), nullable=False)  # Municipality/City
    barangay = db.Column(db.String(100), nullable=False)
    street = db.Column(db.String(200), nullable=True)  # Optional street name/number
    building_details = db.Column(db.String(200), nullable=True)  # House/Unit number, landmarks
    
    # Full formatted address
    address_line = db.Column(db.String(500), nullable=False)
    
    # Coordinates (can be approximate for barangay center)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    
    # Mapbox reference (optional)
    place_id = db.Column(db.String(100), nullable=True)
    
    # Address type/label
    address_label = db.Column(db.String(50), default='Home')  # Home, Work, Other
    
    # Is this the default address?
    is_default = db.Column(db.Boolean, default=False)
    
    # Timestamps
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


# ===== NEW: Municipality Boundaries Table for Delivery Zones =====
class MunicipalityBoundary(db.Model):
    __tablename__ = 'municipality_boundaries'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    province = db.Column(db.String(100), nullable=True, index=True)
    region = db.Column(db.String(100), nullable=True)
    psgc_code = db.Column(db.String(20), nullable=True, index=True)  # Philippine Standard Geographic Code
    
    # The actual boundary geometry (MultiPolygon for islands or discontinuous areas)
    boundary = db.Column(Geometry('MULTIPOLYGON', srid=4326), nullable=False)
    
    # Optional: bounding box for quick filtering
    min_lat = db.Column(db.Float, nullable=True)
    max_lat = db.Column(db.Float, nullable=True)
    min_lng = db.Column(db.Float, nullable=True)
    max_lng = db.Column(db.Float, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_geojson(self):
        """Convert to GeoJSON feature"""
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
        """
        Find municipalities that share a border with the given municipality
        Uses spatial ST_Touches function
        """
        from sqlalchemy import func
        from geoalchemy2.functions import ST_Touches
        
        query = MunicipalityBoundary.query.filter_by(name=municipality_name)
        if province:
            query = query.filter_by(province=province)
        
        municipality = query.first()
        if not municipality:
            return []
        
        # Find all boundaries that touch this municipality
        adjacent_query = MunicipalityBoundary.query.filter(
            ST_Touches(MunicipalityBoundary.boundary, municipality.boundary)
        )
        
        # Filter by same province if specified
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
        """Get all municipalities in a province"""
        return MunicipalityBoundary.query.filter_by(province=province).order_by(MunicipalityBoundary.name).all()
    
    @staticmethod
    def find_containing_municipality(lat, lng, province=None):
        """
        Find which municipality contains the given point
        Uses spatial ST_Contains function
        """
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