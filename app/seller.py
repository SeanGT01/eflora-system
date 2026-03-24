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

def serialize_seller_order(order):
    order_dict = order.to_dict()
    order_dict['items'] = [item.to_dict() for item in order.items]
    order_dict['items_count'] = sum(item.quantity for item in order.items)
    order_dict['customer_phone'] = order.customer.phone if order.customer else None
    order_dict['payment_proof'] = order.payment_proof
    order_dict['rider_vehicle'] = order.assigned_rider.vehicle_type if order.assigned_rider else None
    return order_dict


@seller_bp.route('/orders', methods=['GET'])
@seller_required
def get_orders():
    user_id = get_jwt_identity()
    store = get_seller_store(user_id)
    
    if not store:
        return jsonify({'error': 'No active store found'}), 404
    
    status = request.args.get('status')
    payment_status = request.args.get('payment_status')
    
    query = Order.query.filter_by(store_id=store.id)
    if status:
        query = query.filter_by(status=status)
    if payment_status:
        query = query.filter_by(payment_status=payment_status)
    
    orders = query.order_by(Order.created_at.desc()).all()
    
    return jsonify({
        'success': True,
        'orders': [serialize_seller_order(order) for order in orders]
    }), 200


@seller_bp.route('/orders/<int:order_id>', methods=['GET'])
@seller_required
def get_order(order_id):
    user_id = get_jwt_identity()
    store = get_seller_store(user_id)
    
    if not store:
        return jsonify({'error': 'No active store found'}), 404
    
    order = Order.query.filter_by(id=order_id, store_id=store.id).first_or_404()
    return jsonify(serialize_seller_order(order)), 200


@seller_bp.route('/orders/<int:order_id>/items', methods=['GET'])
@seller_required
def get_order_items(order_id):
    user_id = get_jwt_identity()
    store = get_seller_store(user_id)
    
    if not store:
        return jsonify({'error': 'No active store found'}), 404
    
    order = Order.query.filter_by(id=order_id, store_id=store.id).first_or_404()
    return jsonify([item.to_dict() for item in order.items]), 200


@seller_bp.route('/orders/<int:order_id>/status', methods=['PUT'])
@seller_required
def update_order_status(order_id):
    user_id = get_jwt_identity()
    store = get_seller_store(user_id)
    
    if not store:
        return jsonify({'error': 'No active store found'}), 404
    
    order = Order.query.filter_by(id=order_id, store_id=store.id).first_or_404()
    data = request.get_json() or {}
    new_status = data.get('status')
    
    allowed_statuses = {'pending', 'accepted', 'preparing', 'on_delivery', 'delivered', 'cancelled'}
    if new_status not in allowed_statuses:
        return jsonify({'error': 'Invalid status'}), 400
    
    order.status = new_status
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Order status updated',
        'order': serialize_seller_order(order)
    }), 200


@seller_bp.route('/orders/<int:order_id>/verify-payment', methods=['PUT'])
@seller_required
def verify_order_payment(order_id):
    user_id = get_jwt_identity()
    store = get_seller_store(user_id)
    
    if not store:
        return jsonify({'error': 'No active store found'}), 404
    
    order = Order.query.filter_by(id=order_id, store_id=store.id).first_or_404()
    if not order.payment_proof_url:
        return jsonify({'error': 'No payment proof uploaded'}), 400
    
    order.payment_status = 'verified'
    if order.status == 'pending':
        order.status = 'accepted'
    order.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Payment verified successfully',
        'order': serialize_seller_order(order)
    }), 200
