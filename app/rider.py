from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import User, Rider, Order, OrderItem, RiderLocation, Store, Product
from datetime import datetime, timedelta
from sqlalchemy import func
from app.utils.report_service import period_range
from sqlalchemy.orm import joinedload, selectinload
from app.utils.cloudinary_helper import upload_delivery_proof

rider_bp = Blueprint('rider', __name__)

# Customer confirmation moves delivered → completed; both count as fulfilled deliveries.
_DELIVERED_STATUSES = ('delivered', 'completed')

# Maximum simultaneous active deliveries per rider to prevent overload (1 at a time)
MAX_RIDER_ACTIVE_DELIVERIES = 1


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
    
    # Today's stats (Philippine calendar day)
    today_start, today_end, _ = period_range('today')
    fulfill_at = func.coalesce(Order.delivered_at, Order.updated_at, Order.created_at)
    
    today_orders = Order.query.filter(
        Order.rider_id == rider.id,
        db.or_(
            db.and_(Order.created_at >= today_start, Order.created_at < today_end),
            db.and_(fulfill_at >= today_start, fulfill_at < today_end),
            Order.status.in_(['on_delivery', 'accepted', 'preparing', 'done_preparing'])
        )
    ).count()
    
    # Count delivered + completed (customer-confirmed) using fulfillment date.
    today_delivered = Order.query.filter(
        Order.rider_id == rider.id,
        Order.status.in_(_DELIVERED_STATUSES),
        fulfill_at >= today_start,
        fulfill_at < today_end,
    ).count()

    today_custom_orders = Order.query.filter(
        Order.rider_id == rider.id,
        db.or_(Order.order_type == 'custom_chat', Order.custom_ticket_id.isnot(None)),
        db.or_(
            db.and_(Order.created_at >= today_start, Order.created_at < today_end),
            db.and_(fulfill_at >= today_start, fulfill_at < today_end),
            Order.status.in_(['on_delivery', 'accepted', 'preparing', 'done_preparing'])
        )
    ).count()

    custom_orders = Order.query.filter(
        Order.rider_id == rider.id,
        db.or_(Order.order_type == 'custom_chat', Order.custom_ticket_id.isnot(None))
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
            'today_delivered': today_delivered,
            'today_custom_orders': today_custom_orders,
            'custom_orders': custom_orders,
        },
        'current_order': None,
        'recent_orders': []
    }
    
    if current_order:
        from app.utils.phone_bind import attach_order_customer_contact
        co = current_order.to_dict()
        co['items'] = [item.to_dict() for item in current_order.items]
        attach_order_customer_contact(co, current_order.customer)
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
    
    base_query = (
        Order.query
        .options(
            selectinload(Order.items).selectinload(OrderItem.addons),
            selectinload(Order.items).joinedload(OrderItem.product).selectinload(Product.images),
            joinedload(Order.customer),
            joinedload(Order.store),
        )
        .filter(Order.rider_id == rider.id)
    )

    if status == 'delivered':
        # Completed tab: rider-delivered and customer-confirmed orders.
        orders = (
            base_query
            .filter(Order.status.in_(_DELIVERED_STATUSES))
            .order_by(Order.created_at.desc())
            .all()
        )
    else:
        orders = (
            base_query
            .filter_by(status=status)
            .order_by(Order.created_at.desc())
            .all()
        )
    
    order_data = []
    for order in orders:
        from app.utils.phone_bind import attach_order_customer_contact
        order_dict = order.to_dict()
        order_dict['items'] = [item.to_dict() for item in order.items]
        order_dict['customer_name'] = order.customer.full_name if order.customer else None
        attach_order_customer_contact(order_dict, order.customer)
        order_dict['delivery_address'] = order.delivery_address
        # Include store coordinates for map routing
        if order.store:
            order_dict['store_latitude'] = order.store.latitude
            order_dict['store_longitude'] = order.store.longitude
            order_dict['store_address'] = order.store.address
        order_data.append(order_dict)
    
    return jsonify({'orders': order_data}), 200

def _parse_order_time_priority(order_dict):
    """
    Extracts a chronological sort key (date_str, start_minutes) for an order.
    Orders with earlier requested dates and earlier start windows are delivered first.
    """
    date_val = str(order_dict.get('requested_delivery_date') or '').strip()
    if not date_val:
        date_val = '0000-00-00'
    
    time_slot = order_dict.get('requested_delivery_time')
    start_min = 720  # default midday if no window specified
    if time_slot:
        from app.utils.store_schedule import parse_slot_interval_minutes
        parsed = parse_slot_interval_minutes(time_slot)
        if parsed:
            start_min = parsed[0]
            
    return (date_val, start_min)


def optimize_rider_itinerary(orders_data, store_lat=None, store_lng=None):
    """
    Arranges available orders into an optimal delivery itinerary.
    Prioritizes:
    1. Requested delivery date & start time window (customer preferred time).
    2. Geographic distance from the store / previous stop (Nearest Neighbor TSP).
    
    Annotates each order with:
    - itinerary_sequence (1, 2, 3...)
    - is_recommended_first (True for stop 1)
    - leg_distance_km (distance from previous stop or store)
    - cumulative_distance_km (total route distance up to this stop)
    """
    if not orders_data:
        return []

    from app.map_utils import calculate_distance

    # Group into time buckets so delivery window deadlines are strictly respected
    buckets = {}
    for od in orders_data:
        key = _parse_order_time_priority(od)
        buckets.setdefault(key, []).append(od)

    sorted_keys = sorted(buckets.keys())

    optimized = []
    current_lat = store_lat
    current_lng = store_lng
    cumulative_dist = 0.0

    for bucket_key in sorted_keys:
        bucket_orders = list(buckets[bucket_key])
        
        while bucket_orders:
            best_idx = 0
            best_dist = None
            
            for idx, cand in enumerate(bucket_orders):
                cand_lat = cand.get('customer_latitude')
                cand_lng = cand.get('customer_longitude')
                
                if current_lat is not None and current_lng is not None and cand_lat is not None and cand_lng is not None:
                    try:
                        d = calculate_distance(current_lat, current_lng, cand_lat, cand_lng)
                    except Exception:
                        d = 9999.0
                else:
                    d = 9999.0
                    
                if best_dist is None or d < best_dist:
                    best_dist = d
                    best_idx = idx

            chosen = bucket_orders.pop(best_idx)
            leg_dist = best_dist if (best_dist is not None and best_dist < 9000.0) else (chosen.get('distance_from_store_km') or 0.0)
            cumulative_dist += leg_dist

            chosen['leg_distance_km'] = round(leg_dist, 2)
            chosen['cumulative_distance_km'] = round(cumulative_dist, 2)

            # Advance current position to this stop
            c_lat = chosen.get('customer_latitude')
            c_lng = chosen.get('customer_longitude')
            if c_lat is not None and c_lng is not None:
                current_lat = c_lat
                current_lng = c_lng

            optimized.append(chosen)

    # Assign 1-indexed itinerary sequence numbers and recommendation flag
    for i, od in enumerate(optimized):
        od['itinerary_sequence'] = i + 1
        od['is_recommended_first'] = (i == 0)

    return optimized


@rider_bp.route('/orders/available', methods=['GET'])
@rider_required
def get_available_orders():
    user_id = get_jwt_identity()
    rider = get_rider_profile(user_id)
    
    if not rider:
        return jsonify({'error': 'Rider profile not found'}), 404
    
    # Get orders from rider's store that are ready for pickup (accepted or done_preparing) and not assigned
    orders = (
        Order.query
        .options(
            selectinload(Order.items).selectinload(OrderItem.addons),
            selectinload(Order.items).joinedload(OrderItem.product).selectinload(Product.images),
            joinedload(Order.customer),
            joinedload(Order.store),
        )
        .filter(
            Order.store_id == rider.store_id,
            Order.status.in_(['accepted', 'preparing', 'done_preparing']),
            Order.rider_id.is_(None),
            db.or_(Order.fulfillment_type == 'delivery', Order.fulfillment_type.is_(None))
        )
        .order_by(Order.created_at)
        .all()
    )
    
    store = Store.query.get(rider.store_id)
    store_lat = None
    store_lng = None
    if store:
        store_lat = float(store.latitude) if store.latitude is not None else (float(store.location.y) if store.location else None)
        store_lng = float(store.longitude) if store.longitude is not None else (float(store.location.x) if store.location else None)

    order_data = []
    for order in orders:
        from app.utils.phone_bind import attach_order_customer_contact
        order_dict = order.to_dict()
        order_dict['items'] = [item.to_dict() for item in order.items]
        order_dict['customer_name'] = order.customer.full_name if order.customer else None
        attach_order_customer_contact(order_dict, order.customer)
        order_dict['delivery_address'] = order.delivery_address
        
        # Include store coordinates for map routing
        if store:
            order_dict['store_latitude'] = store_lat
            order_dict['store_longitude'] = store_lng
            order_dict['store_address'] = store.address
            order_dict['store_name'] = store.name

        # Extract or fallback customer coordinates
        cust_lat = order_dict.get('customer_latitude')
        cust_lng = order_dict.get('customer_longitude')
        if (cust_lat is None or cust_lng is None) and order.delivery_location:
            try:
                cust_lat = float(order.delivery_location.y)
                cust_lng = float(order.delivery_location.x)
                order_dict['customer_latitude'] = cust_lat
                order_dict['customer_longitude'] = cust_lng
            except Exception:
                pass

        # Calculate distance from store to delivery location
        if store_lat is not None and store_lng is not None and cust_lat is not None and cust_lng is not None:
            try:
                from app.map_utils import calculate_distance
                distance = calculate_distance(store_lat, store_lng, cust_lat, cust_lng)
                order_dict['distance_from_store_km'] = round(distance, 2)
            except (AttributeError, TypeError, Exception):
                pass
        
        order_data.append(order_dict)

    # Sort and structure orders into an optimal delivery itinerary
    optimized_orders = optimize_rider_itinerary(order_data, store_lat=store_lat, store_lng=store_lng)
        
    active_deliveries_count = Order.query.filter_by(
        rider_id=rider.id,
        status='on_delivery'
    ).count()

    total_route_distance = round(sum(o.get('leg_distance_km', 0.0) for o in optimized_orders), 2)

    return jsonify({
        'orders': optimized_orders,
        'itinerary_summary': {
            'total_stops': len(optimized_orders),
            'total_distance_km': total_route_distance,
            'store_latitude': store_lat,
            'store_longitude': store_lng,
            'store_name': store.name if store else 'Store',
        },
        'active_deliveries_count': active_deliveries_count,
        'max_active_deliveries': MAX_RIDER_ACTIVE_DELIVERIES,
        'can_accept_more': active_deliveries_count < MAX_RIDER_ACTIVE_DELIVERIES
    }), 200

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
    
    if order.status not in ('accepted', 'preparing', 'done_preparing') or order.rider_id is not None:
        return jsonify({'error': 'Order cannot be accepted'}), 400

    if getattr(order, 'fulfillment_type', '') == 'pickup':
        return jsonify({'error': 'Store pickup orders cannot be accepted by riders'}), 400

    # Rider workload guardrail: limit to 1 active delivery at a time
    active_deliveries = Order.query.filter(
        Order.rider_id == rider.id,
        Order.status == 'on_delivery'
    ).count()
    if active_deliveries >= MAX_RIDER_ACTIVE_DELIVERIES:
        return jsonify({
            'error': f'Active delivery limit reached ({active_deliveries}/{MAX_RIDER_ACTIVE_DELIVERIES}). Please deliver your ongoing order before accepting another.'
        }), 400
    
    order.rider_id = rider.id
    order.set_status('on_delivery')
    
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
    
    if not rider:
        return jsonify({'error': 'Rider profile not found'}), 404
    
    order = Order.query.get(order_id)
    if not order or order.rider_id != rider.id:
        return jsonify({'error': 'Order not found'}), 404
    
    data = request.get_json()
    new_status = data.get('status')
    
    if new_status not in ['on_delivery', 'delivered']:
        return jsonify({'error': 'Invalid status'}), 400
    
    order.set_status(new_status)
    
    # If delivered, update payment status if proof exists
    if new_status == 'delivered' and order.payment_proof:
        order.payment_status = 'verified'
    
    db.session.commit()
    
    return jsonify({
        'message': f'Order marked as {new_status}',
        'order': order.to_dict()
    }), 200

@rider_bp.route('/orders/<int:order_id>/upload-delivery-proof', methods=['POST'])
@rider_required
def upload_delivery_proof_handler(order_id):
    user_id = get_jwt_identity()
    rider = get_rider_profile(user_id)
    
    if not rider:
        return jsonify({'success': False, 'error': 'Rider profile not found'}), 404
    
    order = Order.query.get(order_id)
    if not order or order.rider_id != rider.id:
        return jsonify({'success': False, 'error': 'Order not found'}), 404
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    
    # Get proof index (1 or 2)
    proof_index = request.form.get('proof_index', '1')
    if proof_index not in ['1', '2']:
        return jsonify({'success': False, 'error': 'Invalid proof_index. Must be 1 or 2'}), 400
    
    # Upload to Cloudinary
    result = upload_delivery_proof(file, order_id)
    
    if not result['success']:
        return jsonify({'success': False, 'error': result.get('error', 'Upload failed')}), 500
    
    # Save delivery proof metadata to order
    if proof_index == '1':
        order.delivery_proof = file.filename
        order.delivery_proof_public_id = result['public_id']
        order.delivery_proof_url = result['url']
    else:  # proof_index == '2'
        order.delivery_proof_2 = file.filename
        order.delivery_proof_2_public_id = result['public_id']
        order.delivery_proof_2_url = result['url']
    
    order.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Delivery proof {proof_index} uploaded successfully',
        'public_id': result['public_id'],
        'url': result['url'],
        'proof_index': proof_index,
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
    time_threshold = datetime.utcnow() - timedelta(hours=hours)
    query = query.filter(RiderLocation.timestamp >= time_threshold)
    
    locations = query.order_by(RiderLocation.timestamp.desc()).all()
    
    location_data = []
    for loc in locations:
        from geoalchemy2.shape import to_shape
        point = to_shape(loc.location)
        location_data.append({
            'id': loc.id,
            'order_id': loc.order_id,
            'lat': float(point.y),
            'lng': float(point.x),
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
    week_ago = datetime.utcnow() - timedelta(days=7)
    
    weekly_deliveries = Order.query.filter(
        Order.rider_id == rider.id,
        Order.status.in_(_DELIVERED_STATUSES),
        func.coalesce(Order.delivered_at, Order.updated_at) >= week_ago
    ).count()
    
    # Monthly stats
    month_ago = datetime.utcnow() - timedelta(days=30)
    
    monthly_deliveries = Order.query.filter(
        Order.rider_id == rider.id,
        Order.status.in_(_DELIVERED_STATUSES),
        func.coalesce(Order.delivered_at, Order.updated_at) >= month_ago
    ).count()
    
    # Average time from rider accepting the order (confirmed_at) until delivered_at.
    # Using created_at→updated_at was wrong: that includes payment wait, seller prep,
    # and any later row updates — not the rider's trip.
    avg_delivery_time = db.session.query(
        func.avg(func.extract('epoch', Order.delivered_at - Order.confirmed_at) / 60.0)
    ).filter(
        Order.rider_id == rider.id,
        Order.status.in_(_DELIVERED_STATUSES),
        Order.delivered_at.isnot(None),
        Order.confirmed_at.isnot(None),
    ).scalar()
    
    # Total deliveries
    total_deliveries = Order.query.filter(
        Order.rider_id == rider.id,
        Order.status.in_(_DELIVERED_STATUSES),
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
        from app.utils.validators import normalize_ph_license_plate
        plate, plate_err = normalize_ph_license_plate(data.get('license_plate'))
        if plate_err:
            return jsonify({'error': plate_err}), 400
        rider.license_plate = plate
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