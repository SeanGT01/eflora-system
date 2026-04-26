# app/seller.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models import User, Store, Product, Order, Rider, POSOrder, OrderAnalytics, Testimonial, OrderItem, RiderOTP
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
    
    allowed_statuses = {'pending', 'accepted', 'preparing', 'done_preparing', 'on_delivery', 'delivered', 'cancelled'}
    if new_status not in allowed_statuses:
        return jsonify({'error': 'Invalid status'}), 400
    
    order.set_status(new_status)
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
        order.set_status('accepted')
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Payment verified successfully',
        'order': serialize_seller_order(order)
    }), 200


# ═══════════════════════════════════════════════════════════════════════════════
# RIDER MANAGEMENT ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@seller_bp.route('/riders', methods=['GET'])
@seller_required
def get_riders():
    """Get all riders for the seller's store"""
    user_id = get_jwt_identity()
    store = get_seller_store(user_id)
    if not store:
        return jsonify({'error': 'No active store found'}), 404
    
    riders = Rider.query.filter_by(store_id=store.id).all()
    
    riders_data = []
    for rider in riders:
        rider_dict = rider.to_dict()
        total_deliveries = Order.query.filter_by(
            rider_id=rider.id, status='delivered'
        ).count()
        active_delivery = Order.query.filter(
            Order.rider_id == rider.id,
            Order.status.in_(['on_delivery', 'accepted', 'preparing'])
        ).first()
        rider_dict['total_deliveries'] = total_deliveries
        rider_dict['has_active_delivery'] = active_delivery is not None
        rider_dict['active_order_id'] = active_delivery.id if active_delivery else None
        riders_data.append(rider_dict)
    
    pending_otps = RiderOTP.query.filter_by(
        store_id=store.id,
        is_verified=False
    ).filter(RiderOTP.expires_at > datetime.utcnow()).all()
    
    return jsonify({
        'success': True,
        'riders': riders_data,
        'pending_invitations': [otp.to_dict() for otp in pending_otps],
        'stats': {
            'total': len(riders),
            'active': sum(1 for r in riders if r.is_active),
            'inactive': sum(1 for r in riders if not r.is_active)
        }
    }), 200


@seller_bp.route('/riders', methods=['POST'])
@seller_required
def invite_rider():
    """Invite a new rider — sends a 6-digit OTP to their email for verification"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    store = get_seller_store(user_id)
    if not store:
        return jsonify({'error': 'No active store found'}), 404
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400
    
    email = (data.get('email') or '').lower().strip()
    full_name = (data.get('full_name') or '').strip()
    phone = (data.get('phone') or '').strip()
    vehicle_type = data.get('vehicle_type', '')
    license_plate = (data.get('license_plate') or '').strip()
    
    if not email or not full_name:
        return jsonify({'error': 'Email and full name are required'}), 400
    
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        existing_rider = Rider.query.filter_by(
            user_id=existing_user.id, store_id=store.id
        ).first()
        if existing_rider:
            return jsonify({'error': 'This email is already registered as a rider for your store'}), 409
    
    existing_otp = RiderOTP.query.filter_by(
        email=email, store_id=store.id, is_verified=False
    ).filter(RiderOTP.expires_at > datetime.utcnow()).first()
    
    if existing_otp:
        return jsonify({'error': 'An invitation is already pending for this email.'}), 409
    
    from app.utils.email_helper import generate_otp_code, send_rider_otp_email
    otp_code = generate_otp_code()
    
    rider_otp = RiderOTP(
        email=email,
        verification_token=otp_code,
        rider_data={
            'full_name': full_name,
            'phone': phone,
            'vehicle_type': vehicle_type,
            'license_plate': license_plate
        },
        store_id=store.id,
        created_by=user_id,
        expires_at=datetime.utcnow() + timedelta(minutes=10)
    )
    db.session.add(rider_otp)
    db.session.commit()
    
    email_sent = send_rider_otp_email(
        recipient_email=email,
        otp_code=otp_code,
        store_name=store.name,
        seller_name=user.full_name
    )
    
    if not email_sent:
        return jsonify({'error': 'Failed to send OTP email.'}), 500
    
    return jsonify({
        'success': True,
        'message': f'OTP sent to {email}. Ask the rider for the 6-digit code.',
        'otp_id': rider_otp.id
    }), 201


@seller_bp.route('/riders/resend-invitation', methods=['POST'])
@seller_required
def resend_rider_invitation():
    """Resend OTP for a pending rider invitation"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    store = get_seller_store(user_id)
    if not store:
        return jsonify({'error': 'No active store found'}), 404
    
    data = request.get_json()
    otp_id = data.get('otp_id')
    
    if not otp_id:
        return jsonify({'error': 'Invitation ID is required'}), 400
    
    rider_otp = RiderOTP.query.filter_by(
        id=otp_id, store_id=store.id, is_verified=False
    ).first()
    
    if not rider_otp:
        return jsonify({'error': 'Invitation not found'}), 404
    
    from app.utils.email_helper import generate_otp_code, send_rider_otp_email
    new_otp = generate_otp_code()
    rider_otp.verification_token = new_otp
    rider_otp.expires_at = datetime.utcnow() + timedelta(minutes=10)
    db.session.commit()
    
    email_sent = send_rider_otp_email(
        recipient_email=rider_otp.email,
        otp_code=new_otp,
        store_name=store.name,
        seller_name=user.full_name
    )
    
    if not email_sent:
        return jsonify({'error': 'Failed to resend OTP email'}), 500
    
    return jsonify({
        'success': True,
        'message': f'New OTP sent to {rider_otp.email}'
    }), 200


@seller_bp.route('/riders/verify-otp', methods=['POST'])
@seller_required
def verify_rider_otp():
    """Seller verifies the OTP from the rider, creates the account with a default password"""
    user_id = get_jwt_identity()
    store = get_seller_store(user_id)
    if not store:
        return jsonify({'error': 'No active store found'}), 404
    
    data = request.get_json()
    otp_id = data.get('otp_id')
    otp_code = (data.get('otp_code') or '').strip()
    
    if not otp_id or not otp_code:
        return jsonify({'error': 'OTP ID and code are required'}), 400
    
    rider_otp = RiderOTP.query.filter_by(
        id=otp_id, store_id=store.id, is_verified=False
    ).first()
    
    if not rider_otp:
        return jsonify({'error': 'Invitation not found'}), 404
    
    if rider_otp.is_expired():
        return jsonify({'error': 'OTP has expired. Please resend a new one.'}), 400
    
    if rider_otp.verification_token != otp_code:
        return jsonify({'error': 'Invalid OTP code. Please try again.'}), 400
    
    # OTP is correct — create the rider account with a default password
    from app.utils.email_helper import generate_default_password, send_rider_credentials_email
    
    rider_data = rider_otp.rider_data
    default_password = generate_default_password()
    
    # Find or create the User
    user_account = User.query.filter_by(email=rider_otp.email).first()
    
    if not user_account:
        user_account = User(
            full_name=rider_data['full_name'],
            email=rider_otp.email,
            phone=rider_data.get('phone'),
            role='rider',
            status='active'
        )
        user_account.set_password(default_password)
        db.session.add(user_account)
        db.session.flush()
    else:
        user_account.set_password(default_password)
        user_account.status = 'active'
    
    # Create Rider record if not exists
    existing_rider = Rider.query.filter_by(
        user_id=user_account.id, store_id=store.id
    ).first()
    
    if not existing_rider:
        new_rider = Rider(
            user_id=user_account.id,
            store_id=store.id,
            vehicle_type=rider_data.get('vehicle_type', ''),
            license_plate=rider_data.get('license_plate', ''),
            is_active=True
        )
        db.session.add(new_rider)
    
    # Mark OTP as verified and delete it
    rider_otp.is_verified = True
    db.session.delete(rider_otp)
    db.session.commit()
    
    # Send credentials email to the rider
    send_rider_credentials_email(
        recipient_email=rider_otp.email,
        full_name=rider_data['full_name'],
        default_password=default_password,
        store_name=store.name
    )
    
    return jsonify({
        'success': True,
        'message': f'Rider account created for {rider_data["full_name"]}! Credentials sent to {rider_otp.email}.'
    }), 201


@seller_bp.route('/riders/<int:rider_id>', methods=['GET'])
@seller_required
def get_rider(rider_id):
    """Get a single rider's details"""
    user_id = get_jwt_identity()
    store = get_seller_store(user_id)
    if not store:
        return jsonify({'error': 'No active store found'}), 404
    
    rider = Rider.query.filter_by(id=rider_id, store_id=store.id).first_or_404()
    rider_dict = rider.to_dict()
    
    total_deliveries = Order.query.filter_by(rider_id=rider.id, status='delivered').count()
    recent_orders = Order.query.filter_by(rider_id=rider.id).order_by(
        Order.created_at.desc()
    ).limit(10).all()
    
    rider_dict['total_deliveries'] = total_deliveries
    rider_dict['recent_orders'] = [o.to_dict() for o in recent_orders]
    
    return jsonify({'success': True, 'rider': rider_dict}), 200


@seller_bp.route('/riders/<int:rider_id>', methods=['PUT'])
@seller_required
def update_rider(rider_id):
    """Update rider info (vehicle, license plate, active status)"""
    user_id = get_jwt_identity()
    store = get_seller_store(user_id)
    if not store:
        return jsonify({'error': 'No active store found'}), 404
    
    rider = Rider.query.filter_by(id=rider_id, store_id=store.id).first_or_404()
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400
    
    if 'vehicle_type' in data:
        rider.vehicle_type = data['vehicle_type']
    if 'license_plate' in data:
        rider.license_plate = data['license_plate']
    if 'is_active' in data:
        rider.is_active = bool(data['is_active'])
    
    if rider.user:
        if 'full_name' in data:
            rider.user.full_name = data['full_name']
        if 'phone' in data:
            rider.user.phone = data['phone']
    
    rider.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Rider updated successfully',
        'rider': rider.to_dict()
    }), 200


@seller_bp.route('/riders/<int:rider_id>/status', methods=['PUT'])
@seller_required
def update_rider_status(rider_id):
    """Toggle rider active/inactive"""
    user_id = get_jwt_identity()
    store = get_seller_store(user_id)
    if not store:
        return jsonify({'error': 'No active store found'}), 404
    
    rider = Rider.query.filter_by(id=rider_id, store_id=store.id).first_or_404()
    data = request.get_json()
    
    is_active = data.get('is_active')
    if is_active is not None:
        rider.is_active = bool(is_active)
        if rider.is_active:
            rider.is_archived = False
    
    rider.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Rider {"activated" if rider.is_active else "deactivated"}',
        'rider': rider.to_dict()
    }), 200


@seller_bp.route('/riders/<int:rider_id>', methods=['DELETE'])
@seller_required
def delete_rider(rider_id):
    """Archive a rider (soft delete)"""
    user_id = get_jwt_identity()
    store = get_seller_store(user_id)
    if not store:
        return jsonify({'error': 'No active store found'}), 404
    
    rider = Rider.query.filter_by(id=rider_id, store_id=store.id).first_or_404()
    
    active_delivery = Order.query.filter(
        Order.rider_id == rider.id,
        Order.status.in_(['on_delivery', 'accepted', 'preparing'])
    ).first()
    
    if active_delivery:
        return jsonify({'error': 'Cannot remove rider with active deliveries'}), 400
    
    rider.is_active = False
    rider.is_archived = True
    rider.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Rider archived successfully (set to inactive)',
        'rider': rider.to_dict(),
        'archived': True
    }), 200


@seller_bp.route('/riders/cancel-invitation', methods=['POST'])
@seller_required
def cancel_rider_invitation():
    """Cancel a pending rider invitation"""
    user_id = get_jwt_identity()
    store = get_seller_store(user_id)
    if not store:
        return jsonify({'error': 'No active store found'}), 404
    
    data = request.get_json()
    otp_id = data.get('otp_id')
    
    if not otp_id:
        return jsonify({'error': 'OTP ID is required'}), 400
    
    rider_otp = RiderOTP.query.filter_by(
        id=otp_id, store_id=store.id, is_verified=False
    ).first()
    
    if not rider_otp:
        return jsonify({'error': 'Invitation not found'}), 404
    
    db.session.delete(rider_otp)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Invitation cancelled'
    }), 200
