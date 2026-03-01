# app/seller.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models import User, Store, Product, Order, Rider, POSOrder, OrderAnalytics, Testimonial
from sqlalchemy import func
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename

seller_bp = Blueprint('seller', __name__)

# Use functools.wraps to preserve function names
from functools import wraps

def seller_required(f):
    @wraps(f)
    @jwt_required()
    def decorated(*args, **kwargs):
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.role != 'seller':
            return jsonify({'error': 'Seller access required'}), 403
        
        return f(*args, **kwargs)
    return decorated

def get_seller_store(user_id):
    store = Store.query.filter_by(seller_id=user_id, status='active').first()
    return store

@seller_bp.route('/dashboard', methods=['GET'])
@seller_required
def seller_dashboard():
    user_id = get_jwt_identity()
    store = get_seller_store(user_id)
    
    if not store:
        return jsonify({'error': 'No active store found'}), 404
    
    # Today's stats
    today = datetime.utcnow().date()
    
    today_orders = Order.query.filter(
        Order.store_id == store.id,
        func.date(Order.created_at) == today
    ).count()
    
    today_revenue_result = db.session.query(func.sum(Order.total_amount)).filter(
        Order.store_id == store.id,
        func.date(Order.created_at) == today,
        Order.status == 'delivered'
    ).first()
    today_revenue = float(today_revenue_result[0] or 0)
    
    # Total stats
    total_orders = Order.query.filter_by(store_id=store.id).count()
    pending_orders = Order.query.filter_by(store_id=store.id, status='pending').count()
    
    # Recent orders
    recent_orders = Order.query.filter_by(store_id=store.id).order_by(
        Order.created_at.desc()
    ).limit(10).all()
    
    # Top products
    top_products = db.session.query(
        Product.name,
        func.sum(OrderItem.quantity).label('total_sold')
    ).join(OrderItem, Product.id == OrderItem.product_id).join(
        Order, OrderItem.order_id == Order.id
    ).filter(
        Order.store_id == store.id,
        Order.created_at >= datetime.utcnow() - timedelta(days=30)
    ).group_by(Product.id, Product.name).order_by(
        func.sum(OrderItem.quantity).desc()
    ).limit(5).all()
    
    return jsonify({
        'store': store.to_dict(),
        'stats': {
            'today_orders': today_orders,
            'today_revenue': today_revenue,
            'total_orders': total_orders,
            'pending_orders': pending_orders
        },
        'recent_orders': [order.to_dict() for order in recent_orders],
        'top_products': [
            {'product_name': row.name, 'total_sold': row.total_sold}
            for row in top_products
        ]
    }), 200

@seller_bp.route('/products', methods=['GET'])
@seller_required
def get_products():
    user_id = get_jwt_identity()
    store = get_seller_store(user_id)
    
    if not store:
        return jsonify({'error': 'No active store found'}), 404
    
    products = Product.query.filter_by(store_id=store.id).order_by(
        Product.created_at.desc()
    ).all()
    
    return jsonify({'products': [product.to_dict() for product in products]}), 200

@seller_bp.route('/products', methods=['POST'])
@seller_required
def create_product():
    user_id = get_jwt_identity()
    store = get_seller_store(user_id)
    
    if not store:
        return jsonify({'error': 'No active store found'}), 404
    
    data = request.form
    
    # Simple product creation without image for now
    product = Product(
        store_id=store.id,
        name=data.get('name', 'New Product'),
        description=data.get('description', ''),
        price=float(data.get('price', 0)),
        stock_quantity=int(data.get('stock_quantity', 0)),
        category=data.get('category', 'flowers'),
        is_available=data.get('is_available', 'true').lower() == 'true'
    )
    
    db.session.add(product)
    db.session.commit()
    
    return jsonify({'message': 'Product created', 'product': product.to_dict()}), 201

# Add more routes as needed, but keep the @wraps decorator pattern

# Import OrderItem at the top if not already
from app.models import OrderItem