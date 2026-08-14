"""
Chat / Messaging API Routes
Real-time-ready REST endpoints for the e-Flora chat feature.
Supports both Flask session auth (website) and JWT auth (mobile app).
"""

from flask import Blueprint, request, jsonify, session, g
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
from datetime import datetime, timedelta
from functools import wraps
import pytz

from sqlalchemy import case, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import User, Store, Conversation, ChatMessage, Rider, Order, OrderItem, Product

import cloudinary
import cloudinary.uploader

chat_bp = Blueprint('chat', __name__)

# Philippines timezone
PHT = pytz.timezone('Asia/Manila')

def pht_now():
    """Get current time in Philippines timezone (UTC+8)"""
    return datetime.now(PHT)


def _to_pht(dt):
    """Normalize naive/aware datetimes to Asia/Manila for safe comparisons.

    Naive values are treated as UTC (same convention as models.to_pht_iso).
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(PHT)


# ═══════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════

def chat_auth_required(fn):
    """
    Decorator that supports BOTH Flask session auth (website) and JWT auth (mobile).
    Sets g.chat_user_id on success.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        # 1) Try Flask session first (website users)
        if session.get('user_id'):
            g.chat_user_id = session['user_id']
            return fn(*args, **kwargs)

        # 2) Try JWT token (mobile app / chat widget with session-bridge token)
        try:
            verify_jwt_in_request()
            identity = get_jwt_identity()
            g.chat_user_id = int(identity) if isinstance(identity, str) else identity
            return fn(*args, **kwargs)
        except Exception:
            pass

        return jsonify({'error': 'Authentication required'}), 401
    return wrapper


def _current_user():
    """Return the authenticated User object."""
    uid = getattr(g, 'chat_user_id', None)
    if uid:
        return User.query.get(uid)
    return None


def _admin_user_ids():
    return [row[0] for row in db.session.query(User.id).filter_by(role='admin').all()]


def _can_access_conversation(user, convo):
    if not user or not convo:
        return False
    if user.id in (convo.customer_id, convo.seller_id):
        return True
    # Any admin can access support threads bound to an admin account
    if user.role == 'admin':
        seller = User.query.get(convo.seller_id)
        return bool(seller and seller.role == 'admin')
    return False


_ACTIVE_RIDER_ORDER_STATUSES = (
    'accepted',
    'preparing',
    'done_preparing',
    'confirmed',
    'picked_up',
    'on_delivery',
    'out_for_delivery',
)


def _build_order_chat_context(order):
    """Compact order summary for rider↔customer chat headers."""
    if not order:
        return None

    items = []
    for item in (order.items or []):
        items.append({
            'id': item.id,
            'name': item.product.name if item.product else 'Product',
            'variant_name': item.variant.name if item.variant else None,
            'quantity': item.quantity or 1,
            'price': float(item.price or 0),
            'total': float((item.quantity or 0) * float(item.price or 0)),
            'image_url': item.product_image,
        })

    return {
        'order_id': order.id,
        'order_number': f'ORD-{order.id:05d}',
        'status': order.status,
        'store_name': order.store.name if order.store else None,
        'total_amount': float(order.total_amount or 0),
        'subtotal_amount': float(order.subtotal_amount or 0),
        'delivery_fee': float(order.delivery_fee or 0),
        'item_count': len(items),
        'items': items,
    }


def _resolve_order_for_rider_conversation(convo, preferred_order_id=None):
    """Find the order that this rider↔customer thread is about."""
    if not convo:
        return None

    rider = Rider.query.filter_by(user_id=convo.seller_id, is_archived=False).first()
    if not rider:
        rider = Rider.query.filter_by(user_id=convo.seller_id).first()
    if not rider:
        return None

    base = (
        Order.query.options(
            joinedload(Order.items).joinedload(OrderItem.product).joinedload(Product.images),
            joinedload(Order.items).joinedload(OrderItem.variant),
            joinedload(Order.store),
        )
        .filter_by(
            customer_id=convo.customer_id,
            store_id=convo.store_id,
            rider_id=rider.id,
        )
    )

    if preferred_order_id:
        preferred = base.filter_by(id=preferred_order_id).first()
        if preferred:
            return preferred

    active = (
        base.filter(Order.status.in_(_ACTIVE_RIDER_ORDER_STATUSES))
        .order_by(Order.updated_at.desc(), Order.id.desc())
        .first()
    )
    if active:
        return active

    return base.order_by(Order.created_at.desc(), Order.id.desc()).first()


def _conversation_payload(convo, user, preferred_order_id=None):
    """Serialize conversation and attach rider order context when applicable."""
    data = convo.to_dict(current_user_id=user.id if user else None)
    order = _resolve_order_for_rider_conversation(convo, preferred_order_id)
    if order:
        data['is_rider_thread'] = True
        data['order_context'] = _build_order_chat_context(order)
    else:
        data['is_rider_thread'] = False
        data['order_context'] = None
    return data


def _maybe_notify_seller_new_chat(convo, user, preview_text):
    """Notify store seller when a customer sends a message on a store thread."""
    try:
        if not convo or not user:
            return
        if user.id != convo.customer_id:
            return
        if not convo.store_id:
            return

        store = Store.query.get(convo.store_id)
        if not store or store.seller_id != convo.seller_id:
            # Rider / support / admin threads — skip
            return

        snippet = (preview_text or '').strip()
        if len(snippet) > 120:
            snippet = snippet[:117] + '...'
        customer_name = (user.full_name or 'Customer').strip() or 'Customer'
        from app.utils.seller_notifications import notify_store_seller
        notify_store_seller(
            store_id=convo.store_id,
            seller_id=store.seller_id,
            title='New chat message',
            message=f'{customer_name}: {snippet}' if snippet else f'{customer_name} sent a message.',
            type='new_chat',
            reference_id=convo.id,
        )
    except Exception:
        pass


def _support_store_for_chat(customer_id, admin_user_id=None):
    """
    Pick a store_id for a new support thread.

    Uniqueness is (customer_id, store_id, seller_id), so only stores already used
    with this admin (seller_id) are blocked — not every store the customer has
    ever messaged.
    """
    collide_filter = [Conversation.customer_id == customer_id]
    if admin_user_id:
        collide_filter.append(Conversation.seller_id == admin_user_id)
    else:
        admin_ids = _admin_user_ids()
        if admin_ids:
            collide_filter.append(Conversation.seller_id.in_(admin_ids))

    used_store_ids = {
        row[0]
        for row in db.session.query(Conversation.store_id).filter(*collide_filter).all()
    }

    candidates = []
    if admin_user_id:
        candidates.extend(
            Store.query.filter_by(seller_id=admin_user_id).order_by(Store.id.asc()).all()
        )
    candidates.extend(
        Store.query.filter(Store.name.ilike('%support%')).order_by(Store.id.asc()).all()
    )
    candidates.extend(Store.query.order_by(Store.id.asc()).all())

    seen = set()
    for store in candidates:
        if not store or store.id in seen:
            continue
        seen.add(store.id)
        if store.id not in used_store_ids:
            return store
    return None


def _bump_other_unread(convo, sender_id):
    """Atomically increment the recipient unread counter."""
    if sender_id == convo.customer_id:
        Conversation.query.filter_by(id=convo.id).update(
            {Conversation.seller_unread: func.coalesce(Conversation.seller_unread, 0) + 1},
            synchronize_session=False,
        )
        if convo.seller_deleted_at:
            convo.seller_deleted_at = None
    else:
        Conversation.query.filter_by(id=convo.id).update(
            {Conversation.customer_unread: func.coalesce(Conversation.customer_unread, 0) + 1},
            synchronize_session=False,
        )
        if convo.customer_deleted_at:
            convo.customer_deleted_at = None


def _refresh_conversation_preview(convo):
    """Rebuild denormalized last-message fields from the latest visible message."""
    latest = (
        ChatMessage.query
        .filter_by(conversation_id=convo.id, is_deleted=False)
        .order_by(ChatMessage.created_at.desc())
        .first()
    )
    if not latest:
        convo.last_message_text = None
        convo.last_message_at = None
        convo.last_sender_id = None
        return
    if latest.message_type == 'image':
        preview = (latest.text[:200] if latest.text else '[Image]')
    else:
        preview = (latest.text[:200] if latest.text else None)
    convo.last_message_text = preview
    convo.last_message_at = latest.created_at
    convo.last_sender_id = latest.sender_id


# ═══════════════════════════════════════════════════════════════════════
# CONVERSATIONS
# ═══════════════════════════════════════════════════════════════════════

@chat_bp.route('/conversations', methods=['GET'])
@chat_auth_required
def list_conversations():
    """
    GET /api/v1/chat/conversations
    Returns all conversations for the current user (customer or seller).
    Admins also see support threads owned by any admin account.
    """
    user = _current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    if user.role == 'admin':
        admin_ids = _admin_user_ids() or [user.id]
        convos = Conversation.query.filter(
            or_(
                db.and_(
                    Conversation.customer_id == user.id,
                    Conversation.customer_deleted_at.is_(None),
                ),
                db.and_(
                    Conversation.seller_id.in_(admin_ids),
                    Conversation.seller_deleted_at.is_(None),
                ),
            )
        ).order_by(Conversation.last_message_at.desc().nullslast()).options(
            joinedload(Conversation.customer),
            joinedload(Conversation.seller),
            joinedload(Conversation.store),
        ).all()
    else:
        convos = Conversation.query.filter(
            or_(
                db.and_(
                    Conversation.customer_id == user.id,
                    Conversation.customer_deleted_at.is_(None),
                ),
                db.and_(
                    Conversation.seller_id == user.id,
                    Conversation.seller_deleted_at.is_(None),
                ),
            )
        ).order_by(Conversation.last_message_at.desc().nullslast()).options(
            joinedload(Conversation.customer),
            joinedload(Conversation.seller),
            joinedload(Conversation.store),
        ).all()

    return jsonify({
        'conversations': [c.to_dict(current_user_id=user.id) for c in convos]
    }), 200


@chat_bp.route('/conversations/rider-order', methods=['POST'])
@chat_auth_required
def create_or_get_rider_conversation():
    """
    POST /api/v1/chat/conversations/rider-order
    Body: { "order_id": <int> }

    Opens (or creates) the private rider↔customer thread for an assigned order.
    Allowed for:
      - the assigned rider
      - the customer who placed the order (once a rider is assigned)
    """
    user = _current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    data = request.get_json(silent=True) or {}
    order_id = data.get('order_id')
    if not order_id:
        return jsonify({'error': 'order_id is required'}), 400

    order = Order.query.get(order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    if not order.rider_id:
        return jsonify({'error': 'No rider assigned to this order yet'}), 400

    assigned_rider = Rider.query.get(order.rider_id)
    if not assigned_rider or not assigned_rider.user_id:
        return jsonify({'error': 'Rider profile not found'}), 404

    rider_user_id = assigned_rider.user_id

    if user.role == 'rider':
        my_rider = Rider.query.filter_by(user_id=user.id, is_archived=False).first()
        if not my_rider:
            return jsonify({'error': 'Rider profile not found'}), 404
        if order.rider_id != my_rider.id:
            return jsonify({'error': 'Order is not assigned to this rider'}), 403
    elif user.role == 'customer':
        if order.customer_id != user.id:
            return jsonify({'error': 'Access denied'}), 403
    else:
        return jsonify({'error': 'Only the customer or assigned rider can open this chat'}), 403

    store = Store.query.get(order.store_id)
    if not store:
        return jsonify({'error': 'Store not found'}), 404

    convo = Conversation.query.filter_by(
        customer_id=order.customer_id,
        store_id=order.store_id,
        seller_id=rider_user_id,
    ).first()
    if convo:
        payload = _conversation_payload(convo, user, preferred_order_id=order.id)
        return jsonify({'conversation': payload, 'order_context': payload.get('order_context')}), 200

    convo = Conversation(
        customer_id=order.customer_id,
        seller_id=rider_user_id,  # private rider-customer thread
        store_id=order.store_id,
    )
    db.session.add(convo)
    db.session.commit()
    payload = _conversation_payload(convo, user, preferred_order_id=order.id)
    return jsonify({'conversation': payload, 'order_context': payload.get('order_context')}), 201


@chat_bp.route('/conversations', methods=['POST'])
@chat_auth_required
def create_or_get_conversation():
    """
    POST /api/v1/chat/conversations
    Body: { "store_id": <int> }
    Creates a new conversation with the given store or returns the existing one.
    Customers only.
    """
    user = _current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    if user.role != 'customer':
        return jsonify({'error': 'Only customers can start a store chat'}), 403

    data = request.get_json(silent=True) or {}
    store_id = data.get('store_id')
    if not store_id:
        return jsonify({'error': 'store_id is required'}), 400

    store = Store.query.get(store_id)
    if not store:
        return jsonify({'error': 'Store not found'}), 404

    # Don't let a seller message their own store
    if user.id == store.seller_id:
        return jsonify({'error': 'Cannot message your own store'}), 400

    # Find existing or create new
    convo = Conversation.query.filter_by(
        customer_id=user.id,
        store_id=store.id,
        seller_id=store.seller_id
    ).first()
    if convo:
        # Un-delete for the customer if they previously deleted it
        if convo.customer_deleted_at:
            convo.customer_deleted_at = None
            db.session.commit()
        return jsonify({'conversation': convo.to_dict(current_user_id=user.id)}), 200

    convo = Conversation(
        customer_id=user.id,
        seller_id=store.seller_id,
        store_id=store.id,
    )
    db.session.add(convo)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        convo = Conversation.query.filter_by(
            customer_id=user.id,
            store_id=store.id,
            seller_id=store.seller_id
        ).first()
        if not convo:
            return jsonify({'error': 'Could not open conversation'}), 500
        return jsonify({'conversation': convo.to_dict(current_user_id=user.id)}), 200

    return jsonify({'conversation': convo.to_dict(current_user_id=user.id)}), 201


@chat_bp.route('/conversations/support', methods=['POST'])
@chat_auth_required
def create_or_get_support_conversation():
    """
    POST /api/v1/chat/conversations/support
    Creates (or returns) a conversation between the current user and an admin account.
    """
    user = _current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    if user.role == 'admin':
        return jsonify({'error': 'Admins already receive support chats in their inbox.'}), 400

    admin_user = User.query.filter_by(role='admin').order_by(User.id.asc()).first()
    if not admin_user:
        return jsonify({'error': 'No admin account available for support.'}), 503

    # First priority: reuse an existing thread with this admin.
    convo = (
        Conversation.query
        .filter_by(customer_id=user.id, seller_id=admin_user.id)
        .order_by(Conversation.updated_at.desc())
        .first()
    )
    if convo:
        changed = False
        if convo.customer_deleted_at:
            convo.customer_deleted_at = None
            changed = True
        if changed:
            db.session.commit()
        return jsonify({'conversation': convo.to_dict(current_user_id=user.id)}), 200

    support_store = _support_store_for_chat(user.id, admin_user.id)
    if not support_store:
        return jsonify({'error': 'No available support slot. Please contact admin directly.'}), 503

    convo = Conversation(
        customer_id=user.id,
        seller_id=admin_user.id,
        store_id=support_store.id,
        last_message_text='Support thread opened',
        last_message_at=pht_now(),
        last_sender_id=user.id,
    )
    db.session.add(convo)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = (
            Conversation.query
            .filter_by(customer_id=user.id, seller_id=admin_user.id)
            .order_by(Conversation.updated_at.desc())
            .first()
        )
        if not existing:
            return jsonify({'error': 'Could not open support conversation'}), 500
        return jsonify({'conversation': existing.to_dict(current_user_id=user.id)}), 200

    return jsonify({'conversation': convo.to_dict(current_user_id=user.id)}), 201


@chat_bp.route('/conversations/<int:convo_id>', methods=['GET'])
@chat_auth_required
def get_conversation(convo_id):
    """
    GET /api/v1/chat/conversations/<id>
    Returns conversation details (header info).
    Optional query: order_id — prefer that order for rider-thread context.
    """
    user = _current_user()
    convo = Conversation.query.get_or_404(convo_id)

    if not _can_access_conversation(user, convo):
        return jsonify({'error': 'Access denied'}), 403

    preferred_order_id = request.args.get('order_id', type=int)
    payload = _conversation_payload(convo, user, preferred_order_id=preferred_order_id)
    return jsonify({'conversation': payload, 'order_context': payload.get('order_context')}), 200


@chat_bp.route('/conversations/<int:convo_id>', methods=['DELETE'])
@chat_auth_required
def delete_conversation(convo_id):
    """
    DELETE /api/v1/chat/conversations/<id>
    Soft-deletes the conversation for the current user only.
    """
    user = _current_user()
    convo = Conversation.query.get_or_404(convo_id)

    if not _can_access_conversation(user, convo):
        return jsonify({'error': 'Access denied'}), 403

    now = pht_now()
    if user.id == convo.customer_id:
        convo.customer_deleted_at = now
    else:
        convo.seller_deleted_at = now

    db.session.commit()
    return jsonify({'message': 'Conversation deleted'}), 200


# ═══════════════════════════════════════════════════════════════════════
# MESSAGES
# ═══════════════════════════════════════════════════════════════════════

@chat_bp.route('/conversations/<int:convo_id>/messages', methods=['GET'])
@chat_auth_required
def get_messages(convo_id):
    """
    GET /api/v1/chat/conversations/<id>/messages?page=1&per_page=30
    Returns paginated message history (newest first).
    """
    user = _current_user()
    convo = Conversation.query.get_or_404(convo_id)

    if not _can_access_conversation(user, convo):
        return jsonify({'error': 'Access denied'}), 403

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 30, type=int), 100)

    pagination = ChatMessage.query.filter_by(conversation_id=convo_id) \
        .order_by(ChatMessage.created_at.desc()) \
        .paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'messages': [m.to_dict() for m in reversed(pagination.items)],  # chronological
        'page': pagination.page,
        'per_page': per_page,
        'total': pagination.total,
        'pages': pagination.pages,
        'has_next': pagination.has_next,
    }), 200


@chat_bp.route('/conversations/<int:convo_id>/messages', methods=['POST'])
@chat_auth_required
def send_message(convo_id):
    """
    POST /api/v1/chat/conversations/<id>/messages
    Body: { "text": "Hello!", "message_type": "text" }
    Sends a text message.
    """
    user = _current_user()
    convo = Conversation.query.get_or_404(convo_id)

    if not _can_access_conversation(user, convo):
        return jsonify({'error': 'Access denied'}), 403

    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    msg_type = data.get('message_type', 'text')

    if msg_type == 'text' and not text:
        return jsonify({'error': 'Message text is required'}), 400

    reply_to_id = data.get('reply_to_id')
    if reply_to_id is not None:
        reply_to_id = int(reply_to_id)
        # Verify the replied-to message exists in this conversation
        replied = ChatMessage.query.filter_by(id=reply_to_id, conversation_id=convo.id).first()
        if not replied:
            reply_to_id = None

    msg = ChatMessage(
        conversation_id=convo.id,
        sender_id=user.id,
        message_type=msg_type,
        text=text if text else None,
        reply_to_id=reply_to_id,
    )
    db.session.add(msg)

    # Update conversation denormalized fields
    now = pht_now()
    convo.last_message_text = text[:200] if text else '[Image]'
    convo.last_message_at = now
    convo.last_sender_id = user.id
    convo.updated_at = now

    # Increment unread for the OTHER participant (atomic)
    _bump_other_unread(convo, user.id)

    _maybe_notify_seller_new_chat(convo, user, text or '[Image]')

    db.session.commit()

    return jsonify({'message': msg.to_dict()}), 201


@chat_bp.route('/conversations/<int:convo_id>/messages/image', methods=['POST'])
@chat_auth_required
def send_image_message(convo_id):
    """
    POST /api/v1/chat/conversations/<id>/messages/image
    Multipart form: file=<image>, text=<optional caption>
    Uploads an image to Cloudinary and sends it as a chat message.
    """
    user = _current_user()
    convo = Conversation.query.get_or_404(convo_id)

    if not _can_access_conversation(user, convo):
        return jsonify({'error': 'Access denied'}), 403

    if 'file' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'Empty file'}), 400

    # Validate file type
    allowed = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed:
        return jsonify({'error': f'File type .{ext} not allowed'}), 400

    try:
        result = cloudinary.uploader.upload(
            file,
            folder='e-flowers/chat',
            resource_type='image',
            transformation=[{'width': 1200, 'height': 1200, 'crop': 'limit'}]
        )
    except Exception as e:
        return jsonify({'error': f'Image upload failed: {str(e)}'}), 500

    caption = (request.form.get('text') or '').strip()

    msg = ChatMessage(
        conversation_id=convo.id,
        sender_id=user.id,
        message_type='image',
        text=caption if caption else None,
        image_url=result['secure_url'],
        image_public_id=result['public_id'],
    )
    db.session.add(msg)

    now = pht_now()
    convo.last_message_text = caption[:200] if caption else '[Image]'
    convo.last_message_at = now
    convo.last_sender_id = user.id
    convo.updated_at = now

    _bump_other_unread(convo, user.id)

    _maybe_notify_seller_new_chat(convo, user, caption if caption else '[Image]')

    db.session.commit()

    return jsonify({'message': msg.to_dict()}), 201


# ═══════════════════════════════════════════════════════════════════════
# DELETE MESSAGE
# ═══════════════════════════════════════════════════════════════════════

@chat_bp.route('/conversations/<int:convo_id>/messages/<int:msg_id>', methods=['DELETE'])
@chat_auth_required
def delete_message(convo_id, msg_id):
    """
    DELETE /api/v1/chat/conversations/<id>/messages/<msg_id>
    Only the sender can delete their own messages.
    """
    user = _current_user()
    convo = Conversation.query.get_or_404(convo_id)
    msg = ChatMessage.query.get_or_404(msg_id)

    if msg.conversation_id != convo_id:
        return jsonify({'error': 'Message not in this conversation'}), 400

    if not _can_access_conversation(user, convo):
        return jsonify({'error': 'Access denied'}), 403

    if msg.sender_id != user.id:
        return jsonify({'error': 'Can only delete your own messages'}), 403

    # Delete image from Cloudinary if it exists
    if msg.message_type == 'image' and msg.image_public_id:
        try:
            cloudinary.uploader.destroy(msg.image_public_id)
        except Exception as e:
            print(f'Warning: Failed to delete image from Cloudinary: {e}')

    # Soft delete: keep the row but clear content
    msg.is_deleted = True
    msg.text = None
    msg.image_url = None
    msg.image_public_id = None
    msg.message_type = 'deleted'
    db.session.flush()
    _refresh_conversation_preview(convo)
    db.session.commit()

    return jsonify({'message': msg.to_dict()}), 200


# ═══════════════════════════════════════════════════════════════════════
# READ RECEIPTS & UNREAD COUNTS
# ═══════════════════════════════════════════════════════════════════════

@chat_bp.route('/conversations/<int:convo_id>/read', methods=['POST'])
@chat_auth_required
def mark_as_read(convo_id):
    """
    POST /api/v1/chat/conversations/<id>/read
    Marks all messages in this conversation as read for the current user
    and resets the unread counter.
    """
    user = _current_user()
    convo = Conversation.query.get_or_404(convo_id)

    if not _can_access_conversation(user, convo):
        return jsonify({'error': 'Access denied'}), 403

    now = pht_now()

    # Mark unread messages from the OTHER person as read
    ChatMessage.query.filter(
        ChatMessage.conversation_id == convo_id,
        ChatMessage.sender_id != user.id,
        ChatMessage.is_read == False
    ).update({
        ChatMessage.is_read: True,
        ChatMessage.read_at: now,
    }, synchronize_session='fetch')

    # Reset unread counter
    if user.id == convo.customer_id:
        convo.customer_unread = 0
    else:
        convo.seller_unread = 0

    db.session.commit()

    return jsonify({'message': 'Messages marked as read'}), 200


@chat_bp.route('/unread-count', methods=['GET'])
@chat_auth_required
def total_unread_count():
    """
    GET /api/v1/chat/unread-count
    Returns the total unread message count across all conversations.
    Used for the floating chat badge.

    Must match list_conversations filters + Conversation.unread_for() so
    seller/admin badges stay consistent with the inbox.
    """
    user = _current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    if user.role == 'admin':
        admin_ids = _admin_user_ids() or [user.id]
        convo_filter = or_(
            db.and_(
                Conversation.customer_id == user.id,
                Conversation.customer_deleted_at.is_(None),
            ),
            db.and_(
                Conversation.seller_id.in_(admin_ids),
                Conversation.seller_deleted_at.is_(None),
            ),
        )
    else:
        convo_filter = or_(
            db.and_(
                Conversation.customer_id == user.id,
                Conversation.customer_deleted_at.is_(None),
            ),
            db.and_(
                Conversation.seller_id == user.id,
                Conversation.seller_deleted_at.is_(None),
            ),
        )

    unread_expr = func.coalesce(
        case(
            (Conversation.customer_id == user.id, Conversation.customer_unread),
            else_=Conversation.seller_unread,
        ),
        0,
    )
    total = (
        db.session.query(func.coalesce(func.sum(unread_expr), 0))
        .filter(convo_filter)
        .scalar()
    )

    return jsonify({'unread_count': int(total or 0)}), 200


# ═══════════════════════════════════════════════════════════════════════
# ONLINE STATUS
# ═══════════════════════════════════════════════════════════════════════

@chat_bp.route('/users/<int:user_id>/online', methods=['GET'])
@chat_auth_required
def check_online_status(user_id):
    """
    GET /api/v1/chat/users/<id>/online
    Returns whether a user was active within the last 5 minutes.
    Uses the user's updated_at field as a proxy for activity.
    """
    target = User.query.get_or_404(user_id)
    from datetime import timedelta
    threshold = pht_now() - timedelta(minutes=5)
    last_active = _to_pht(target.updated_at)
    is_online = last_active is not None and last_active >= threshold

    return jsonify({
        'user_id': target.id,
        'is_online': bool(is_online),
        'last_active': last_active.isoformat() if last_active else None,
    }), 200


# ═══════════════════════════════════════════════════════════════════════
# TYPING INDICATOR (Polling fallback)
# ═══════════════════════════════════════════════════════════════════════

# In-memory typing state (per-conversation, per-user)
# {convo_id: {user_id: {'at': datetime, 'name': str}}}
_typing_state = {}
_TYPING_TTL_SECONDS = 6


@chat_bp.route('/conversations/<int:convo_id>/typing', methods=['POST'])
@chat_auth_required
def set_typing(convo_id):
    """
    POST /api/v1/chat/conversations/<id>/typing
    Signals that the current user is typing. Expires after a few seconds.
    """
    user = _current_user()
    convo = Conversation.query.get_or_404(convo_id)

    if not _can_access_conversation(user, convo):
        return jsonify({'error': 'Access denied'}), 403

    if convo_id not in _typing_state:
        _typing_state[convo_id] = {}
    _typing_state[convo_id][user.id] = {
        'at': pht_now(),
        'name': user.full_name or 'Someone',
    }

    return jsonify({'status': 'ok'}), 200


@chat_bp.route('/conversations/<int:convo_id>/typing', methods=['GET'])
@chat_auth_required
def get_typing(convo_id):
    """
    GET /api/v1/chat/conversations/<id>/typing
    Returns who is currently typing in this conversation (if anyone).
    """
    user = _current_user()
    convo = Conversation.query.get_or_404(convo_id)

    if not _can_access_conversation(user, convo):
        return jsonify({'error': 'Access denied'}), 403

    threshold = pht_now() - timedelta(seconds=_TYPING_TTL_SECONDS)
    typing_users = []

    state = _typing_state.get(convo_id) or {}
    for uid, meta in list(state.items()):
        # Back-compat if an older process still stored bare datetimes.
        if isinstance(meta, datetime):
            ts = meta
            name = None
        else:
            ts = meta.get('at')
            name = meta.get('name')

        ts_pht = _to_pht(ts) or ts
        if ts_pht is None or ts_pht < threshold:
            state.pop(uid, None)
            continue
        if uid == user.id:
            continue

        if not name:
            u = User.query.get(uid)
            name = u.full_name if u else 'Someone'
        typing_users.append({'id': uid, 'full_name': name})

    if convo_id in _typing_state and not _typing_state[convo_id]:
        _typing_state.pop(convo_id, None)

    return jsonify({'typing': typing_users}), 200
