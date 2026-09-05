"""Self-serve customer account deletion (anonymize + purge personal data)."""
from __future__ import annotations

import secrets
import time
from datetime import datetime

from flask import jsonify

from sqlalchemy import or_

from app.extensions import db
from app.models import (
    Cart,
    Conversation,
    CustomerOTP,
    Notification,
    Order,
    PasswordResetOTP,
    SavedReport,
    User,
    UserAddress,
    WishlistItem,
)

ACTIVE_ORDER_STATUSES = (
    'pending',
    'accepted',
    'preparing',
    'done_preparing',
    'confirmed',
    'on_delivery',
)

ANON_ADDRESS = 'Removed after account deletion'


def _active_orders(user_id):
    return Order.query.filter(
        Order.customer_id == user_id,
        Order.status.in_(ACTIVE_ORDER_STATUSES),
    ).all()


def delete_customer_account(user, password, confirmation=None):
    """
    Returns a Flask (response, status) tuple.
    Keeps order/payment/review rows for sellers; strips personal data.
    """
    if not user:
        return jsonify({'success': False, 'error': 'User not found.'}), 404

    role = (user.role or '').strip().lower()
    if role != 'customer':
        return jsonify({
            'success': False,
            'error': 'Only customer accounts can be deleted here. Contact support for seller or rider accounts.',
        }), 403

    if (user.status or '').strip().lower() == 'deleted':
        return jsonify({'success': False, 'error': 'This account is already deleted.'}), 400

    if (confirmation or '').strip().upper() != 'DELETE':
        return jsonify({'success': False, 'error': 'Type DELETE to confirm.'}), 400

    if not password or not user.check_password(password):
        return jsonify({'success': False, 'error': 'Password is incorrect.'}), 400

    blocking = _active_orders(user.id)
    if blocking:
        return jsonify({
            'success': False,
            'error': (
                'You still have an order being prepared or delivered. '
                'Wait until it is completed or cancelled, then try again.'
            ),
            'error_code': 'active_orders',
            'active_order_count': len(blocking),
        }), 409

    now = datetime.utcnow()
    uid = user.id
    old_email = user.email

    for order in Order.query.filter_by(customer_id=uid).all():
        order.delivery_address = ANON_ADDRESS
        order.delivery_notes = None
        order.customer_latitude = None
        order.customer_longitude = None
        order.mapbox_place_id = None
        order.delivery_location = None

    UserAddress.query.filter_by(user_id=uid).delete(synchronize_session=False)
    WishlistItem.query.filter_by(user_id=uid).delete(synchronize_session=False)
    Notification.query.filter_by(user_id=uid).delete(synchronize_session=False)
    SavedReport.query.filter_by(user_id=uid).delete(synchronize_session=False)

    cart = Cart.query.filter_by(user_id=uid).first()
    if cart:
        db.session.delete(cart)

    for conv in Conversation.query.filter_by(customer_id=uid).all():
        conv.customer_deleted_at = now
        conv.customer_unread = 0
        conv.last_message_text = '[Account deleted]'

    bind_key = f'phonebind.{uid}@otp.eflora.internal'
    CustomerOTP.query.filter(
        or_(CustomerOTP.email == old_email, CustomerOTP.email == bind_key)
    ).delete(synchronize_session=False)
    if old_email:
        PasswordResetOTP.query.filter_by(email=old_email).delete(synchronize_session=False)

    if user.avatar_public_id:
        try:
            import cloudinary.uploader
            cloudinary.uploader.destroy(user.avatar_public_id, invalidate=True)
        except Exception:
            pass

    user.full_name = 'Deleted User'
    user.email = f'deleted_{uid}_{int(time.time())}@deleted.eflora.internal'
    user.phone = None
    user.birthday = None
    user.gender = None
    user.avatar_filename = None
    user.avatar_public_id = None
    user.avatar_url = None
    user.status = 'deleted'
    user.role = 'customer'
    user.set_password(secrets.token_urlsafe(48))
    user.updated_at = now

    db.session.commit()
    return jsonify({
        'success': True,
        'message': 'Your account has been deleted.',
    }), 200
