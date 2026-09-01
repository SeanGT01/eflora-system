from flask import Blueprint, request, jsonify, session
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
from app import db
from app.models import User, Store, Order, Product, Rider, OrderAnalytics, SellerApplication, Notification
from sqlalchemy import func, text
from datetime import datetime, timedelta
from app.utils.report_service import period_range, pht_sql_date

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


def _is_session_admin():
    """Website admin UI uses Flask session cookies (not JWT)."""
    user_id = session.get('user_id')
    role = (session.get('role') or '').strip().lower()
    if user_id and role == 'admin':
        return True
    if not user_id:
        return False
    user = User.query.get(user_id)
    if user and (user.role or '').strip().lower() == 'admin':
        session['role'] = 'admin'
        return True
    return False


def _is_jwt_admin():
    try:
        verify_jwt_in_request(optional=True)
        user_id = get_jwt_identity()
        if user_id is None or user_id == '':
            return False
        user = User.query.get(int(str(user_id).strip()))
        return bool(user and (user.role or '').strip().lower() == 'admin')
    except Exception:
        return False


def admin_session_or_jwt_required(fn):
    """Allow either website session admin or JWT admin API clients."""
    def decorated_function(*args, **kwargs):
        if _is_session_admin() or _is_jwt_admin():
            return fn(*args, **kwargs)
        return jsonify({'error': 'Unauthorized'}), 401

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
    
    # Revenue (last 30 Philippine calendar days)
    import pytz
    today_pht = datetime.now(pytz.timezone('Asia/Manila')).date()
    thirty_start, thirty_end, _ = period_range(
        'custom',
        custom_from=(today_pht - timedelta(days=29)).isoformat(),
        custom_to=today_pht.isoformat(),
    )
    day = pht_sql_date(Order.created_at)
    revenue_data = db.session.query(
        day.label('date'),
        func.sum(Order.total_amount).label('revenue')
    ).filter(
        Order.created_at >= thirty_start,
        Order.created_at < thirty_end,
        Order.status == 'delivered'
    ).group_by(day).all()
    
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
@admin_session_or_jwt_required
def update_store_status(store_id):
    """
    Update store status.
    Used by the website admin Stores page (session cookie) and JWT admin clients.
    This route is registered on admin_bp at /api/v1/admin/... and must accept
    session auth — otherwise the browser UI gets 401 (no JWT).
    """
    data = request.get_json(silent=True) or {}
    status = (data.get('status') or '').strip().lower()
    if status == 'inactive':
        status = 'suspended'

    if status not in ['pending', 'active', 'suspended']:
        return jsonify({'error': 'Invalid status. Use pending, active, or suspended.'}), 400

    store = Store.query.get(store_id)
    if not store:
        return jsonify({'error': 'Store not found'}), 404

    store.status = status
    store.updated_at = datetime.utcnow()

    # Activate seller if store is approved
    if status == 'active' and store.seller and (store.seller.status or '').lower() != 'active':
        store.seller.status = 'active'

    try:
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Store status updated',
            'status': store.status,
            'store': store.to_dict(),
        }), 200
    except Exception as ex:
        db.session.rollback()
        return jsonify({'error': f'Could not update status: {ex}'}), 500

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
    day = pht_sql_date(Order.created_at)

    if period == 'day':
        start_date, end_date, _ = period_range('today')
        group_by = day
    elif period == 'week':
        start_date, end_date, _ = period_range('week')
        group_by = day
    elif period == 'year':
        start_date, end_date, _ = period_range('year')
        group_by = func.date_trunc(
            'month', Order.created_at + text("INTERVAL '8 hours'")
        )
    else:  # month
        start_date, end_date, _ = period_range('month')
        group_by = day

    # Revenue trend
    revenue_trend = db.session.query(
        group_by.label('period'),
        func.count(Order.id).label('order_count'),
        func.sum(Order.total_amount).label('revenue')
    ).filter(
        Order.created_at >= start_date,
        Order.created_at < end_date,
        Order.status == 'delivered'
    ).group_by(group_by).order_by(group_by).all()
    
    # Order status distribution
    status_distribution = db.session.query(
        Order.status,
        func.count(Order.id).label('count')
    ).filter(
        Order.created_at >= start_date,
        Order.created_at < end_date,
    ).group_by(Order.status).all()
    
    # Top stores
    top_stores = db.session.query(
        Store.name,
        func.count(Order.id).label('order_count'),
        func.sum(Order.total_amount).label('revenue')
    ).join(Order, Store.id == Order.store_id).filter(
        Order.created_at >= start_date,
        Order.created_at < end_date,
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
    if application.status not in ('pending', 'resubmitted'):
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
        address='',
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
        message=f'Congratulations! Your seller application for "{application.store_name}" has been approved. You can now start selling on E-FLORA.',
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
    if application.status not in ('pending', 'resubmitted'):
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

    user = User.query.get(application.user_id)
    if user:
        src = application.application_source or 'customer_account'
        if src != 'seller_portal':
            user.role = 'customer'
        st = Store.query.filter_by(seller_id=user.id).first()
        if st:
            st.status = 'inactive'

    db.session.commit()
    return jsonify({'success': True, 'message': 'Application rejected', 'application': application.to_dict()}), 200