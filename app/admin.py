from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import User, Store, Order, Product, Rider, OrderAnalytics, SellerApplication, Notification
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


# ══════════════════════════════════════════════════════════════════════════
# SELLER APPLICATIONS
# ══════════════════════════════════════════════════════════════════════════

@admin_bp.route('/seller-applications', methods=['GET'])
@admin_required
def get_seller_applications():
    status = request.args.get('status')
    query = SellerApplication.query
    if status:
        query = query.filter_by(status=status)
    applications = query.order_by(SellerApplication.submitted_at.desc()).all()
    return jsonify({'applications': [app.to_dict() for app in applications]}), 200


@admin_bp.route('/seller-applications/<int:app_id>', methods=['GET'])
@admin_required
def get_seller_application(app_id):
    application = SellerApplication.query.get(app_id)
    if not application:
        return jsonify({'error': 'Application not found'}), 404
    return jsonify({'application': application.to_dict()}), 200


@admin_bp.route('/seller-applications/<int:app_id>/approve', methods=['POST'])
@admin_required
def approve_seller_application(app_id):
    application = SellerApplication.query.get(app_id)
    if not application:
        return jsonify({'error': 'Application not found'}), 404
    if application.status != 'pending':
        return jsonify({'error': f'Application is already {application.status}'}), 400

    admin_id = get_jwt_identity()
    data = request.get_json() or {}

    # Update application status
    application.status = 'approved'
    application.admin_notes = data.get('admin_notes', '')
    application.rejection_details = None
    application.reviewed_at = datetime.utcnow()
    application.reviewed_by = admin_id

    # Upgrade user role to seller
    user = application.applicant
    user.role = 'seller'
    user.status = 'active'

    # Create the store
    store = Store(
        seller_id=user.id,
        name=application.store_name,
        address='To be updated',
        description=application.store_description,
        seller_application_id=application.id,
        status='active',
        approved_at=datetime.utcnow(),
        approved_by=admin_id,
    )
    db.session.add(store)

    # Create notification for the applicant
    notification = Notification(
        user_id=user.id,
        title='Seller Application Approved',
        message=f'Congratulations! Your seller application for "{application.store_name}" has been approved. You can now start selling on E-FLOWERS.',
        type='seller_app_approved',
        reference_id=application.id,
    )
    db.session.add(notification)

    db.session.commit()
    return jsonify({'success': True, 'message': 'Application approved', 'application': application.to_dict()}), 200


@admin_bp.route('/seller-applications/<int:app_id>/reject', methods=['POST'])
@admin_required
def reject_seller_application(app_id):
    application = SellerApplication.query.get(app_id)
    if not application:
        return jsonify({'error': 'Application not found'}), 404
    if application.status != 'pending':
        return jsonify({'error': f'Application is already {application.status}'}), 400

    admin_id = get_jwt_identity()
    data = request.get_json() or {}
    admin_notes = data.get('admin_notes', '')
    rejection_details = data.get('rejection_details')  # Per-field rejection dict

    if not admin_notes and not rejection_details:
        return jsonify({'error': 'Please provide a rejection reason'}), 400

    application.status = 'rejected'
    application.admin_notes = admin_notes
    application.rejection_details = rejection_details
    application.reviewed_at = datetime.utcnow()
    application.reviewed_by = admin_id

    # Build rejection message for notification
    rejected_fields = []
    if rejection_details:
        for field, info in rejection_details.items():
            if info.get('rejected'):
                label = field.replace('_', ' ').title()
                rejected_fields.append(f"- {label}: {info.get('reason', 'No reason given')}")

    rejection_msg = f'Your seller application for "{application.store_name}" has been rejected.'
    if rejected_fields:
        rejection_msg += '\n\nRejected items:\n' + '\n'.join(rejected_fields)
    rejection_msg += '\n\nYou may update the rejected items and resubmit your application.'

    notification = Notification(
        user_id=application.user_id,
        title='Seller Application Rejected',
        message=rejection_msg,
        type='seller_app_rejected',
        reference_id=application.id,
    )
    db.session.add(notification)

    db.session.commit()
    return jsonify({'success': True, 'message': 'Application rejected', 'application': application.to_dict()}), 200