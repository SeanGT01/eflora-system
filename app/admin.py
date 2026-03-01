from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import User, Store, Order, Product, Rider, OrderAnalytics
from sqlalchemy import func, extract
from datetime import datetime, timedelta

admin_bp = Blueprint('admin', __name__)

def admin_required(fn):
    @jwt_required()
    def decorated_function(*args, **kwargs):
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.role != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        
        return fn(*args, **kwargs)
    
    # IMPORTANT: Preserve the original function's name
    decorated_function.__name__ = fn.__name__
    return decorated_function

@admin_bp.route('/dashboard', methods=['GET'])
@admin_required
def get_dashboard():
    # Total counts
    total_users = User.query.count()
    total_sellers = User.query.filter_by(role='seller').count()
    total_stores = Store.query.count()
    total_orders = Order.query.count()
    total_riders = Rider.query.count()
    
    # Recent orders
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()
    
    # Store status counts
    pending_stores = Store.query.filter_by(status='pending').count()
    active_stores = Store.query.filter_by(status='active').count()
    
    # Revenue (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    revenue_data = db.session.query(
        func.date(Order.created_at).label('date'),
        func.sum(Order.total_amount).label('revenue')
    ).filter(
        Order.created_at >= thirty_days_ago,
        Order.status == 'delivered'
    ).group_by(func.date(Order.created_at)).all()
    
    return jsonify({
        'stats': {
            'total_users': total_users,
            'total_sellers': total_sellers,
            'total_stores': total_stores,
            'total_orders': total_orders,
            'total_riders': total_riders,
            'pending_stores': pending_stores,
            'active_stores': active_stores
        },
        'recent_orders': [order.to_dict() for order in recent_orders],
        'revenue_data': [
            {'date': row.date.isoformat(), 'revenue': float(row.revenue or 0)}
            for row in revenue_data
        ]
    }), 200

@admin_bp.route('/users', methods=['GET'])
@admin_required
def get_users():
    role = request.args.get('role')
    status = request.args.get('status')
    
    query = User.query
    
    if role:
        query = query.filter_by(role=role)
    if status:
        query = query.filter_by(status=status)
    
    users = query.order_by(User.created_at.desc()).all()
    
    return jsonify({'users': [user.to_dict() for user in users]}), 200

@admin_bp.route('/users/<int:user_id>/status', methods=['PUT'])
@admin_required
def update_user_status(user_id):
    data = request.get_json()
    status = data.get('status')
    
    if status not in ['pending', 'active', 'suspended', 'inactive']:
        return jsonify({'error': 'Invalid status'}), 400
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    user.status = status
    user.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({'message': 'User status updated', 'user': user.to_dict()}), 200

@admin_bp.route('/stores', methods=['GET'])
@admin_required
def get_stores():
    status = request.args.get('status')
    
    query = Store.query
    
    if status:
        query = query.filter_by(status=status)
    
    stores = query.order_by(Store.created_at.desc()).all()
    
    # Include seller info
    store_data = []
    for store in stores:
        store_dict = store.to_dict()
        store_dict['seller'] = store.seller.to_dict() if store.seller else None
        store_data.append(store_dict)
    
    return jsonify({'stores': store_data}), 200

@admin_bp.route('/stores/<int:store_id>/status', methods=['PUT'])
@admin_required
def update_store_status(store_id):
    data = request.get_json()
    status = data.get('status')
    
    if status not in ['pending', 'active', 'suspended', 'inactive']:
        return jsonify({'error': 'Invalid status'}), 400
    
    store = Store.query.get(store_id)
    if not store:
        return jsonify({'error': 'Store not found'}), 404
    
    store.status = status
    store.updated_at = datetime.utcnow()
    db.session.commit()
    
    # Activate seller if store is approved
    if status == 'active' and store.seller:
        store.seller.status = 'active'
        db.session.commit()
    
    return jsonify({'message': 'Store status updated', 'store': store.to_dict()}), 200

@admin_bp.route('/orders', methods=['GET'])
@admin_required
def get_all_orders():
    status = request.args.get('status')
    store_id = request.args.get('store_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = Order.query
    
    if status:
        query = query.filter_by(status=status)
    if store_id:
        query = query.filter_by(store_id=store_id)
    if start_date:
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        query = query.filter(Order.created_at >= start)
    if end_date:
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        query = query.filter(Order.created_at <= end)
    
    orders = query.order_by(Order.created_at.desc()).all()
    
    return jsonify({'orders': [order.to_dict() for order in orders]}), 200

@admin_bp.route('/analytics', methods=['GET'])
@admin_required
def get_analytics():
    period = request.args.get('period', 'month')  # day, week, month, year
    
    now = datetime.utcnow()
    
    if period == 'day':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        group_by = func.date(Order.created_at)
    elif period == 'week':
        start_date = now - timedelta(days=7)
        group_by = func.date(Order.created_at)
    elif period == 'month':
        start_date = now - timedelta(days=30)
        group_by = func.date(Order.created_at)
    else:  # year
        start_date = now - timedelta(days=365)
        group_by = func.date_trunc('month', Order.created_at)
    
    # Revenue trend
    revenue_trend = db.session.query(
        group_by.label('period'),
        func.count(Order.id).label('order_count'),
        func.sum(Order.total_amount).label('revenue')
    ).filter(
        Order.created_at >= start_date,
        Order.status == 'delivered'
    ).group_by(group_by).order_by(group_by).all()
    
    # Order status distribution
    status_distribution = db.session.query(
        Order.status,
        func.count(Order.id).label('count')
    ).filter(Order.created_at >= start_date).group_by(Order.status).all()
    
    # Top stores
    top_stores = db.session.query(
        Store.name,
        func.count(Order.id).label('order_count'),
        func.sum(Order.total_amount).label('revenue')
    ).join(Order, Store.id == Order.store_id).filter(
        Order.created_at >= start_date,
        Order.status == 'delivered'
    ).group_by(Store.id, Store.name).order_by(func.sum(Order.total_amount).desc()).limit(10).all()
    
    return jsonify({
        'revenue_trend': [
            {
                'period': row.period.isoformat() if hasattr(row.period, 'isoformat') else str(row.period),
                'order_count': row.order_count,
                'revenue': float(row.revenue or 0)
            }
            for row in revenue_trend
        ],
        'status_distribution': [
            {'status': row.status, 'count': row.count}
            for row in status_distribution
        ],
        'top_stores': [
            {
                'store_name': row.name,
                'order_count': row.order_count,
                'revenue': float(row.revenue or 0)
            }
            for row in top_stores
        ]
    }), 200