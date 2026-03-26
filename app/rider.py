from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import User, Rider, Order, RiderLocation, Store
from datetime import datetime
from sqlalchemy import func

rider_bp = Blueprint('rider', __name__)

def rider_required(fn):
    @jwt_required()
    def decorated_function(*args, **kwargs):
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.role != 'rider':
            return jsonify({'error': 'Rider access required'}), 403
        
        return fn(*args, **kwargs)
    
    decorated_function.__name__ = fn.__name__
    return decorated_function

def get_rider_profile(user_id):
    rider = Rider.query.filter_by(user_id=user_id, is_active=True).first()
    return rider

@rider_bp.route('/dashboard', methods=['GET'])
@rider_required
def rider_dashboard():
    user_id = get_jwt_identity()
    rider = get_rider_profile(user_id)
    
    if not rider:
        return jsonify({'error': 'Rider profile not found'}), 404
    
    # Today's stats
    today = datetime.utcnow().date()
    
    today_orders = Order.query.filter(
        Order.rider_id == rider.id,
        func.date(Order.created_at) == today
    ).count()
    
    today_delivered = Order.query.filter(
        Order.rider_id == rider.id,
        func.date(Order.created_at) == today,
        Order.status == 'delivered'
    ).count()
    
    # Current active delivery
    current_order = Order.query.filter_by(
        rider_id=rider.id,
        status='on_delivery'
    ).first()
    
    # Recent deliveries
    recent_orders = Order.query.filter_by(rider_id=rider.id).order_by(
        Order.updated_at.desc()
    ).limit(10).all()
    
    dashboard_data = {
        'rider': rider.to_dict(),
        'stats': {
            'today_orders': today_orders,
            'today_delivered': today_delivered
        },
        'current_order': None,
        'recent_orders': []
    }
    
    if current_order:
        co = current_order.to_dict()
        co['items'] = [item.to_dict() for item in current_order.items]
        co['customer_contact'] = current_order.customer.phone if current_order.customer and hasattr(current_order.customer, 'phone') else None
        if current_order.store:
            co['store_latitude'] = current_order.store.latitude
            co['store_longitude'] = current_order.store.longitude
            co['store_address'] = current_order.store.address
        dashboard_data['current_order'] = co
    
    for order in recent_orders:
        od = order.to_dict()
        od['items'] = [item.to_dict() for item in order.items]
        if order.store:
            od['store_latitude'] = order.store.latitude
            od['store_longitude'] = order.store.longitude
            od['store_address'] = order.store.address
        dashboard_data['recent_orders'].append(od)
    
    return jsonify(dashboard_data), 200

@rider_bp.route('/orders', methods=['GET'])
@rider_required
def get_assigned_orders():
    user_id = get_jwt_identity()
    rider = get_rider_profile(user_id)
    
    if not rider:
        return jsonify({'error': 'Rider profile not found'}), 404
    
    status = request.args.get('status', 'on_delivery')
    
    orders = Order.query.filter_by(
        rider_id=rider.id,
        status=status
    ).order_by(Order.created_at.desc()).all()
    
    order_data = []
    for order in orders:
        order_dict = order.to_dict()
        order_dict['items'] = [item.to_dict() for item in order.items]
        order_dict['customer_name'] = order.customer.full_name if order.customer else None
        order_dict['customer_contact'] = order.customer.phone if hasattr(order.customer, 'phone') else None
        order_dict['delivery_address'] = order.delivery_address
        # Include store coordinates for map routing
        if order.store:
            order_dict['store_latitude'] = order.store.latitude
            order_dict['store_longitude'] = order.store.longitude
            order_dict['store_address'] = order.store.address
        order_data.append(order_dict)
    
    return jsonify({'orders': order_data}), 200

@rider_bp.route('/orders/available', methods=['GET'])
@rider_required
def get_available_orders():
    user_id = get_jwt_identity()
    rider = get_rider_profile(user_id)
    
    if not rider:
        return jsonify({'error': 'Rider profile not found'}), 404
    
    # Get orders from rider's store that are ready for pickup (accepted or done_preparing) and not assigned
    orders = Order.query.filter(
        Order.store_id == rider.store_id,
        Order.status.in_(['accepted', 'done_preparing']),
        Order.rider_id.is_(None)
    ).order_by(Order.created_at).all()
    
    order_data = []
    for order in orders:
        order_dict = order.to_dict()
        order_dict['items'] = [item.to_dict() for item in order.items]
        order_dict['customer_name'] = order.customer.full_name if order.customer else None
        order_dict['delivery_address'] = order.delivery_address
        
        # Include store coordinates for map routing
        store = Store.query.get(rider.store_id)
        if store:
            order_dict['store_latitude'] = store.latitude
            order_dict['store_longitude'] = store.longitude
            order_dict['store_address'] = store.address

        # Calculate distance from store to delivery location
        store = Store.query.get(rider.store_id)
        try:
            if store and store.location and order.delivery_location:
                from app.map_utils import calculate_distance
                distance = calculate_distance(
                    store.location.x, store.location.y,
                    order.delivery_location.x, order.delivery_location.y
                )
                order_dict['distance_from_store_km'] = round(distance, 2)
        except (AttributeError, TypeError):
            # Location extraction failed, skip distance calculation
            pass
        
        order_data.append(order_dict)
    
    return jsonify({'orders': order_data}), 200

@rider_bp.route('/orders/<int:order_id>/accept', methods=['POST'])
@rider_required
def accept_order(order_id):
    user_id = get_jwt_identity()
    rider = get_rider_profile(user_id)
    
    if not rider:
        return jsonify({'error': 'Rider profile not found'}), 404
    
    order = Order.query.get(order_id)
    if not order or order.store_id != rider.store_id:
        return jsonify({'error': 'Order not found'}), 404
    
    if order.status not in ('accepted', 'done_preparing') or order.rider_id is not None:
        return jsonify({'error': 'Order cannot be accepted'}), 400
    
    order.rider_id = rider.id
    order.status = 'on_delivery'
    order.updated_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({
        'message': 'Order accepted',
        'order': order.to_dict()
    }), 200

@rider_bp.route('/orders/<int:order_id>/update-status', methods=['PUT'])
@rider_required
def update_order_status(order_id):
    user_id = get_jwt_identity()
    rider = get_rider_profile(user_id)
    
    order = Order.query.get(order_id)
    if not order or order.rider_id != rider.id:
        return jsonify({'error': 'Order not found'}), 404
    
    data = request.get_json()
    new_status = data.get('status')
    
    if new_status not in ['on_delivery', 'delivered']:
        return jsonify({'error': 'Invalid status'}), 400
    
    order.status = new_status
    order.updated_at = datetime.utcnow()
    
    # If delivered, update payment status if proof exists
    if new_status == 'delivered' and order.payment_proof:
        order.payment_status = 'verified'
    
    db.session.commit()
    
    return jsonify({
        'message': f'Order marked as {new_status}',
        'order': order.to_dict()
    }), 200

@rider_bp.route('/location', methods=['POST'])
@rider_required
def update_location():
    user_id = get_jwt_identity()
    rider = get_rider_profile(user_id)
    
    if not rider:
        return jsonify({'error': 'Rider profile not found'}), 404
    
    data = request.get_json()
    lat = data.get('lat')
    lng = data.get('lng')
    order_id = data.get('order_id')
    
    if not lat or not lng:
        return jsonify({'error': 'Missing coordinates'}), 400
    
    # Create location record
    location = RiderLocation(
        rider_id=rider.id,
        order_id=order_id,
        location=f'POINT({lng} {lat})'
    )
    
    db.session.add(location)
    db.session.commit()
    
    # Also send to Firebase for real-time tracking (optional)
    # firebase_update(rider.id, order_id, lat, lng)
    
    return jsonify({
        'message': 'Location updated',
        'location': {
            'lat': lat,
            'lng': lng,
            'timestamp': location.timestamp.isoformat()
        }
    }), 200

@rider_bp.route('/location/history', methods=['GET'])
@rider_required
def get_location_history():
    user_id = get_jwt_identity()
    rider = get_rider_profile(user_id)
    
    if not rider:
        return jsonify({'error': 'Rider profile not found'}), 404
    
    order_id = request.args.get('order_id')
    hours = int(request.args.get('hours', 24))
    
    query = RiderLocation.query.filter_by(rider_id=rider.id)
    
    if order_id:
        query = query.filter_by(order_id=order_id)
    
    # Get locations from last X hours
    time_threshold = datetime.utcnow() - datetime.timedelta(hours=hours)
    query = query.filter(RiderLocation.timestamp >= time_threshold)
    
    locations = query.order_by(RiderLocation.timestamp.desc()).all()
    
    location_data = []
    for loc in locations:
        location_data.append({
            'id': loc.id,
            'order_id': loc.order_id,
            'lat': loc.location.x,
            'lng': loc.location.y,
            'timestamp': loc.timestamp.isoformat()
        })
    
    return jsonify({'locations': location_data}), 200

@rider_bp.route('/stats', methods=['GET'])
@rider_required
def get_rider_stats():
    user_id = get_jwt_identity()
    rider = get_rider_profile(user_id)
    
    if not rider:
        return jsonify({'error': 'Rider profile not found'}), 404
    
    # Weekly stats
    week_ago = datetime.utcnow() - datetime.timedelta(days=7)
    
    weekly_deliveries = Order.query.filter(
        Order.rider_id == rider.id,
        Order.status == 'delivered',
        Order.updated_at >= week_ago
    ).count()
    
    # Monthly stats
    month_ago = datetime.utcnow() - datetime.timedelta(days=30)
    
    monthly_deliveries = Order.query.filter(
        Order.rider_id == rider.id,
        Order.status == 'delivered',
        Order.updated_at >= month_ago
    ).count()
    
    # Average delivery time (for delivered orders)
    avg_delivery_time = db.session.query(
        func.avg(func.extract('epoch', Order.updated_at - Order.created_at) / 60)
    ).filter(
        Order.rider_id == rider.id,
        Order.status == 'delivered'
    ).scalar()
    
    # Total deliveries
    total_deliveries = Order.query.filter_by(
        rider_id=rider.id,
        status='delivered'
    ).count()
    
    return jsonify({
        'stats': {
            'weekly_deliveries': weekly_deliveries,
            'monthly_deliveries': monthly_deliveries,
            'total_deliveries': total_deliveries,
            'avg_delivery_time_minutes': round(float(avg_delivery_time or 0), 1)
        }
    }), 200

@rider_bp.route('/profile', methods=['GET'])
@rider_required
def get_rider_profile_info():
    user_id = get_jwt_identity()
    rider = get_rider_profile(user_id)
    
    if not rider:
        return jsonify({'error': 'Rider profile not found'}), 404
    
    profile_data = rider.to_dict()
    profile_data['store_name'] = rider.store.name if rider.store else None
    
    return jsonify({'profile': profile_data}), 200

@rider_bp.route('/profile', methods=['PUT'])
@rider_required
def update_rider_profile():
    user_id = get_jwt_identity()
    rider = get_rider_profile(user_id)
    
    if not rider:
        return jsonify({'error': 'Rider profile not found'}), 404
    
    data = request.get_json()
    
    # Update rider info
    if 'vehicle_type' in data:
        rider.vehicle_type = data['vehicle_type']
    if 'license_plate' in data:
        rider.license_plate = data['license_plate']
    if 'is_active' in data:
        rider.is_active = data['is_active']
    
    # Update user info
    user = User.query.get(user_id)
    if 'full_name' in data and user:
        user.full_name = data['full_name']
    
    rider.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'message': 'Profile updated',
        'profile': rider.to_dict()
    }), 200