# app/payment_verification_routes.py
"""
Seller endpoints for verifying customer payment proofs
- View pending payment proofs
- Accept/reject payment
- Transition order to 'accepted' status
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt, verify_jwt_in_request
from functools import wraps
from app.models import Order, Store, User
from app.extensions import db
from datetime import datetime

payment_verification_bp = Blueprint('payment_verification', __name__, url_prefix='/api/v1/seller/payments')

def seller_only(f):
    """Decorator: JWT required + must be seller role + must own the store."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            verify_jwt_in_request()
            claims = get_jwt()
            user_id = get_jwt_identity()
            
            if not user_id:
                return jsonify({'error': 'Invalid token'}), 401
                
            if claims.get('role') != 'seller':
                return jsonify({'error': 'Seller access required'}), 403
                
            return f(*args, **kwargs)
        except Exception as e:
            print(f"❌ JWT Error: {str(e)}")
            return jsonify({'error': 'Authentication failed'}), 401
    return wrapper


# ══════════════════════════════════════════════════════════════════════════
# VIEW PENDING PAYMENT PROOFS
# ══════════════════════════════════════════════════════════════════════════

@payment_verification_bp.route('/pending', methods=['GET'])
@seller_only
def get_pending_payment_proofs():
    """
    Get all pending payment proofs for seller's stores.
    Seller can see orders from their stores that have pending payment verification.
    """
    try:
        user_id = get_jwt_identity()
        
        # Get all stores for this seller
        stores = Store.query.filter_by(seller_id=user_id).all()
        if not stores:
            return jsonify({'proofs': []}), 200
        
        store_ids = [store.id for store in stores]
        
        # Get orders with pending payment verification from these stores
        orders = Order.query.filter(
            Order.store_id.in_(store_ids),
            Order.payment_method == 'gcash',
            Order.payment_status == 'pending_verification',
            Order.payment_proof_url.isnot(None)
        ).order_by(Order.created_at.desc()).all()
        
        proofs = []
        for order in orders:
            customer = order.customer
            store = order.store
            
            proof_data = {
                'id': order.id,
                'order_id': order.id,
                'customer_id': customer.id,
                'customer_name': customer.full_name,
                'customer_phone': customer.phone,
                'customer_avatar': customer.avatar_url,
                'store_id': store.id,
                'store_name': store.name,
                'amount': float(order.total_amount),
                'subtotal': float(order.subtotal_amount),
                'delivery_fee': float(order.delivery_fee),
                'payment_proof_url': order.payment_proof_url,
                'payment_proof_public_id': order.payment_proof_public_id,
                'proof_submitted_at': order.created_at.isoformat() if order.created_at else None,
                'items_count': len(order.items),
                'items': [
                    {
                        'product_name': item.product.name if item.product else 'Unknown',
                        'variant_name': item.variant.name if item.variant else None,
                        'quantity': item.quantity,
                        'price': float(item.price),
                        'subtotal': float(item.quantity * item.price)
                    }
                    for item in order.items
                ]
            }
            proofs.append(proof_data)
        
        print(f"✅ Found {len(proofs)} pending payment proofs for seller {user_id}")
        
        return jsonify({
            'success': True,
            'count': len(proofs),
            'proofs': proofs
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching pending proofs: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════════════════
# VERIFY / REJECT PAYMENT
# ══════════════════════════════════════════════════════════════════════════

@payment_verification_bp.route('/order/<int:order_id>/verify', methods=['POST'])
@seller_only
def verify_payment(order_id):
    """
    Accept and verify a payment proof.
    Updates:
    - payment_status: pending_verification → verified
    - order.status: pending → accepted
    Triggers order workflow continuation.
    """
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}
        verification_notes = data.get('notes', '')
        
        # Get order
        order = Order.query.get_or_404(order_id)
        
        # Verify seller owns this store
        store = Store.query.filter_by(id=order.store_id, seller_id=user_id).first()
        if not store:
            return jsonify({'error': 'Unauthorized - You do not own this store'}), 403
        
        # Verify order has pending payment
        if order.payment_status != 'pending_verification':
            return jsonify({
                'error': f'Invalid order state. Current status: {order.payment_status}'
            }), 400
        
        if not order.payment_proof_url:
            return jsonify({'error': 'No payment proof to verify'}), 400
        
        # Update order
        order.payment_status = 'verified'
        order.set_status('accepted')  # Accept order - ready for rider pickup
        
        db.session.commit()
        
        print(f"✅ Payment verified for order #{order_id} - Status: {order.status}")
        
        return jsonify({
            'success': True,
            'message': 'Payment verified. Order accepted.',
            'order': {
                'id': order.id,
                'status': order.status,
                'payment_status': order.payment_status,
                'updated_at': order.updated_at.isoformat()
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error verifying payment: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@payment_verification_bp.route('/order/<int:order_id>/reject', methods=['POST'])
@seller_only
def reject_payment(order_id):
    """
    Reject a payment proof.
    Customer must resubmit payment proof.
    Updates:
    - payment_status: pending_verification → pending
    - Optionally: add rejection reason for customer feedback
    """
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}
        rejection_reason = data.get('reason', 'Payment proof does not match transaction')
        
        # Get order
        order = Order.query.get_or_404(order_id)
        
        # Verify seller owns this store
        store = Store.query.filter_by(id=order.store_id, seller_id=user_id).first()
        if not store:
            return jsonify({'error': 'Unauthorized - You do not own this store'}), 403
        
        # Verify order has pending payment
        if order.payment_status != 'pending_verification':
            return jsonify({
                'error': f'Invalid order state. Current status: {order.payment_status}'
            }), 400
        
        # Update order - back to pending (customer needs to resubmit)
        order.payment_status = 'pending'
        order.updated_at = datetime.utcnow()
        
        # Optional: Store rejection reason in a new field
        # (Add to Order model if needed: rejection_reason, rejected_at, rejected_by)
        
        db.session.commit()
        
        print(f"✅ Payment rejected for order #{order_id} - Reason: {rejection_reason}")
        
        # TODO: Send notification to customer about rejection
        
        return jsonify({
            'success': True,
            'message': 'Payment proof rejected. Customer can resubmit.',
            'rejection_reason': rejection_reason,
            'order': {
                'id': order.id,
                'status': order.status,
                'payment_status': order.payment_status,
                'updated_at': order.updated_at.isoformat()
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error rejecting payment: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════════════════
# PAYMENT STATISTICS & DASHBOARD
# ══════════════════════════════════════════════════════════════════════════

@payment_verification_bp.route('/summary', methods=['GET'])
@seller_only
def get_payment_summary():
    """
    Get payment statistics for seller dashboard.
    Shows counts of pending, verified, failed payments.
    """
    try:
        user_id = get_jwt_identity()
        
        # Get all stores for this seller
        stores = Store.query.filter_by(seller_id=user_id).all()
        if not stores:
            return jsonify({
                'pending': 0,
                'verified': 0,
                'total_verified_amount': 0.0,
                'pending_verification_count': 0
            }), 200
        
        store_ids = [store.id for store in stores]
        
        # Count orders by payment status
        pending_count = Order.query.filter(
            Order.store_id.in_(store_ids),
            Order.payment_status == 'pending'
        ).count()
        
        pending_verification_count = Order.query.filter(
            Order.store_id.in_(store_ids),
            Order.payment_status == 'pending_verification'
        ).count()
        
        verified_orders = Order.query.filter(
            Order.store_id.in_(store_ids),
            Order.payment_status == 'verified'
        ).all()
        
        verified_count = len(verified_orders)
        total_verified_amount = sum(float(o.total_amount or 0) for o in verified_orders)
        
        return jsonify({
            'success': True,
            'pending': pending_count,
            'pending_verification': pending_verification_count,
            'verified': verified_count,
            'total_verified_amount': total_verified_amount,
            'stores_count': len(stores)
        }), 200
        
    except Exception as e:
        print(f"❌ Error getting payment summary: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════════════════
# PAYMENT HISTORY
# ══════════════════════════════════════════════════════════════════════════

@payment_verification_bp.route('/history', methods=['GET'])
@seller_only
def get_payment_history():
    """
    Get payment history for seller.
    Shows all payments (pending, verified, rejected).
    """
    try:
        user_id = get_jwt_identity()
        status_filter = request.args.get('status', 'verified')  # pending, verified, pending_verification
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        
        # Get all stores for this seller
        stores = Store.query.filter_by(seller_id=user_id).all()
        if not stores:
            return jsonify({
                'history': [],
                'total': 0,
                'page': page,
                'pages': 0
            }), 200
        
        store_ids = [store.id for store in stores]
        
        # Query orders
        query = Order.query.filter(
            Order.store_id.in_(store_ids),
            Order.payment_method == 'gcash'
        )
        
        if status_filter:
            query = query.filter_by(payment_status=status_filter)
        
        paginated = query.order_by(Order.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        history = []
        for order in paginated.items:
            history.append({
                'id': order.id,
                'customer_name': order.customer.full_name if order.customer else 'Unknown',
                'customer_phone': order.customer.phone if order.customer else None,
                'amount': float(order.total_amount),
                'payment_status': order.payment_status,
                'order_status': order.status,
                'created_at': order.created_at.isoformat() if order.created_at else None,
                'has_proof': bool(order.payment_proof_url)
            })
        
        return jsonify({
            'success': True,
            'history': history,
            'total': paginated.total,
            'page': paginated.page,
            'pages': paginated.pages,
            'has_next': paginated.has_next
        }), 200
        
    except Exception as e:
        print(f"❌ Error getting payment history: {str(e)}")
        return jsonify({'error': str(e)}), 500
