"""
Chat / Messaging API Routes
Real-time-ready REST endpoints for the e-Flora chat feature.
Supports both Flask session auth (website) and JWT auth (mobile app).
"""

from decimal import Decimal
from flask import Blueprint, request, jsonify, session, g
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
from datetime import datetime, timedelta
from functools import wraps
import json
import re
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

# In-memory active-session presence: {user_id: last_seen_pht}
# Kept fresh by /presence/heartbeat (app/web foreground) and any chat API call.
# Online ≠ "has a valid JWT/session cookie" (those last days); Online = recently active.
_presence = {}
_PRESENCE_TTL_SECONDS = 120


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


def _touch_presence(user_id):
    """Mark a user as currently active in their logged-in session."""
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return
    _presence[uid] = pht_now()


def _is_present(user_id):
    """True when the user had recent active-session activity within the TTL."""
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False
    seen = _presence.get(uid)
    if seen is None:
        return False
    return (pht_now() - seen).total_seconds() <= _PRESENCE_TTL_SECONDS


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
            _touch_presence(g.chat_user_id)
            return fn(*args, **kwargs)

        # 2) Try JWT token (mobile app / chat widget with session-bridge token)
        try:
            verify_jwt_in_request()
            identity = get_jwt_identity()
            g.chat_user_id = int(identity) if isinstance(identity, str) else identity
            _touch_presence(g.chat_user_id)
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


def _json_safe(obj):
    """Ensure chat payloads are JSON-serializable (Decimal, nested add-ons, etc.)."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def _addon_chat_dict(addon):
    try:
        qty = int(getattr(addon, 'quantity', None) or 1)
        price = float(getattr(addon, 'price', None) or 0)
        image = (getattr(addon, 'image_url', None) or '').strip() or None
        return {
            'id': getattr(addon, 'id', None),
            'name': getattr(addon, 'name', None) or 'Add-on',
            'price': price,
            'quantity': qty,
            'image_url': image,
            'total': price * qty,
        }
    except (TypeError, ValueError, AttributeError):
        return None


def _load_order_for_card(order_id):
    if not order_id:
        return None
    return Order.query.options(
        joinedload(Order.items).joinedload(OrderItem.product).joinedload(Product.images),
        joinedload(Order.items).joinedload(OrderItem.variant),
        joinedload(Order.items).joinedload(OrderItem.addons),
        joinedload(Order.store),
    ).get(int(order_id))


def _build_order_chat_context(order):
    """Compact order summary for rider↔customer chat headers."""
    if not order:
        return None

    items = []
    for item in (order.items or []):
        try:
            addons_list = []
            try:
                for addon in (item.addons or []):
                    row = _addon_chat_dict(addon)
                    if row:
                        addons_list.append(row)
            except Exception:
                addons_list = []
            addons_sum = sum(float(a.get('total') or 0) for a in addons_list)
            unit = float(item.price or 0)
            qty = int(item.quantity or 1)
            product = getattr(item, 'product', None)
            variant = getattr(item, 'variant', None)
            try:
                image_url = item.product_image
            except Exception:
                image_url = None
            items.append({
                'id': item.id,
                'name': product.name if product else 'Product',
                'variant_name': variant.name if variant else None,
                'quantity': qty,
                'price': unit,
                'total': (qty * unit) + addons_sum,
                'image_url': image_url,
                'addons': addons_list,
                'addons_total': addons_sum,
            })
        except Exception:
            continue

    store = getattr(order, 'store', None)
    return _json_safe({
        'order_id': order.id,
        'order_number': 'ORD-%05d' % int(order.id),
        'status': order.status,
        'store_name': store.name if store else None,
        'total_amount': float(order.total_amount or 0),
        'subtotal_amount': float(order.subtotal_amount or 0),
        'delivery_fee': float(order.delivery_fee or 0),
        'item_count': len(items),
        'items': items,
    })


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
            joinedload(Order.items).joinedload(OrderItem.addons),
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
    try:
        order = _resolve_order_for_rider_conversation(convo, preferred_order_id)
        if order:
            data['is_rider_thread'] = True
            data['order_context'] = _build_order_chat_context(order)
        else:
            data['is_rider_thread'] = False
            data['order_context'] = None
    except Exception:
        data['is_rider_thread'] = True if preferred_order_id else data.get('is_rider_thread', False)
        if preferred_order_id and not data.get('order_context'):
            data['order_context'] = _json_safe({
                'order_id': int(preferred_order_id),
                'order_number': 'ORD-%05d' % int(preferred_order_id),
                'status': '',
                'store_name': None,
                'total_amount': 0,
                'subtotal_amount': 0,
                'delivery_fee': 0,
                'item_count': 0,
                'items': [],
            })
    return data


def _order_card_preview(ctx):
    if not ctx:
        return 'Order details'
    num = ctx.get('order_number') or ('ORD-%05d' % int(ctx.get('order_id') or 0))
    return 'Order %s' % num


def _id_from_order_number(value):
    if not value:
        return None
    match = re.search(r'ORD-(\d+)', str(value), re.I)
    if not match:
        return None
    try:
        return int(match.group(1)) or None
    except (TypeError, ValueError):
        return None


def _parse_order_card_id(msg):
    if not msg or msg.is_deleted:
        return None
    if (msg.message_type or '') not in ('order_card', 'text'):
        return None
    raw = (msg.text or '').strip()
    payload = None
    if raw.startswith('{'):
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = None
    if isinstance(payload, dict):
        try:
            oid = int(payload.get('order_id') or payload.get('orderId') or 0) or None
        except (TypeError, ValueError):
            oid = None
        if oid:
            return oid
        return _id_from_order_number(
            payload.get('order_number') or payload.get('orderNumber')
        )
    if (msg.message_type or '') == 'order_card':
        return _id_from_order_number(raw)
    return None


def _orders_for_rider_thread(convo):
    if not convo:
        return []
    rider = Rider.query.filter_by(user_id=convo.seller_id, is_archived=False).first()
    if not rider:
        rider = Rider.query.filter_by(user_id=convo.seller_id).first()
    if not rider:
        return []
    return (
        Order.query.options(
            joinedload(Order.items).joinedload(OrderItem.product).joinedload(Product.images),
            joinedload(Order.items).joinedload(OrderItem.variant),
            joinedload(Order.items).joinedload(OrderItem.addons),
            joinedload(Order.store),
        )
        .filter_by(
            customer_id=convo.customer_id,
            store_id=convo.store_id,
            rider_id=rider.id,
        )
        .order_by(Order.created_at.asc(), Order.id.asc())
        .all()
    )


def _assign_card_order_ids(card_msgs, orders):
    """Give each order-card message its own order when snapshots were overwritten."""
    assigned = {}
    if not card_msgs:
        return assigned
    ordered_cards = sorted(card_msgs, key=lambda m: (str(m.created_at or ''), m.id or 0))
    parsed = [_parse_order_card_id(m) for m in ordered_cards]
    unique_ok = (
        all(parsed) and len(set(parsed)) == len(parsed)
    )
    if unique_ok:
        for msg, oid in zip(ordered_cards, parsed):
            assigned[msg.id] = oid
        return assigned

    unused = [o.id for o in orders]
    for msg, oid in zip(ordered_cards, parsed):
        if oid and oid in unused:
            assigned[msg.id] = oid
            unused.remove(oid)
        elif unused:
            assigned[msg.id] = unused.pop(0)
        elif oid:
            assigned[msg.id] = oid
    return assigned


def _complete_order_card_payload(msg, persist=False, forced_order_id=None):
    """Return this message's own order snapshot. Never use another order in the thread."""
    if not msg or msg.is_deleted:
        return None
    raw = (msg.text or '').strip()
    payload = None
    if raw.startswith('{'):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                payload = parsed
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = None

    items = []
    if payload:
        items = payload.get('items') if isinstance(payload.get('items'), list) else []
    oid = forced_order_id or _parse_order_card_id(msg)
    is_card = (msg.message_type or '') == 'order_card'
    snapshot_oid = None
    if isinstance(payload, dict):
        try:
            snapshot_oid = int(payload.get('order_id') or payload.get('orderId') or 0) or None
        except (TypeError, ValueError):
            snapshot_oid = None

    # Keep a complete snapshot if it already belongs to this card's order.
    if payload and items and snapshot_oid and (not oid or snapshot_oid == oid):
        live_oid = oid or snapshot_oid
        live = _build_order_chat_context(_load_order_for_card(live_oid)) if live_oid else None
        live_items = (live or {}).get('items') or []
        live_has_addons = any((i.get('addons') or []) for i in live_items)
        stored_has_addons = any((i.get('addons') or []) for i in items)
        if live and live_has_addons and not stored_has_addons:
            if persist and is_card:
                snap = json.dumps(live)
                if msg.text != snap:
                    msg.text = snap
                    msg.message_type = 'order_card'
            return live
        return _json_safe(payload)

    if oid:
        order = _load_order_for_card(oid)
        ctx = _build_order_chat_context(order) if order else None
        if ctx and ctx.get('items'):
            if persist and is_card:
                snap = json.dumps(ctx)
                if msg.text != snap:
                    msg.text = snap
                    msg.message_type = 'order_card'
            return ctx

    if payload and items:
        return _json_safe(payload)
    if not is_card:
        return None
    if oid:
        return _json_safe({
            'order_id': oid,
            'order_number': 'ORD-%05d' % int(oid),
            'status': (payload or {}).get('status') or '',
            'store_name': (payload or {}).get('store_name'),
            'total_amount': float((payload or {}).get('total_amount') or 0),
            'subtotal_amount': float((payload or {}).get('subtotal_amount') or 0),
            'delivery_fee': float((payload or {}).get('delivery_fee') or 0),
            'item_count': len(items),
            'items': items,
        })
    return _json_safe(payload) if payload else None


def _message_to_dict(msg, persist_card=False, forced_order_id=None):
    data = msg.to_dict()
    if msg.is_deleted:
        return data
    is_card = (msg.message_type == 'order_card') or (data.get('message_type') == 'order_card')
    if not is_card:
        return data
    card = _complete_order_card_payload(
        msg, persist=persist_card, forced_order_id=forced_order_id
    )
    if card:
        data['message_type'] = 'order_card'
        data['order_card'] = card
        data['text'] = json.dumps(card)
    return data


def _hydrate_message_list(convo, msgs, persist=False):
    cards = [
        m for m in msgs
        if not m.is_deleted and (m.message_type or '') == 'order_card'
    ]
    assigned = {}
    if cards:
        assigned = _assign_card_order_ids(cards, _orders_for_rider_thread(convo))
    out = []
    for m in msgs:
        out.append(_message_to_dict(
            m,
            persist_card=persist,
            forced_order_id=assigned.get(m.id),
        ))
    return out


def _existing_order_card(convo_id, order_id):
    """True only if this exact order was already shared in the thread."""
    msgs = ChatMessage.query.filter(
        ChatMessage.conversation_id == convo_id,
        ChatMessage.is_deleted.isnot(True),
    ).all()
    want = int(order_id)
    for msg in msgs:
        if _parse_order_card_id(msg) == want:
            return msg
    return None


def _order_for_rider_card(user, convo, order_id):
    """Validate that this thread can share a one-time card for the given order."""
    order = _load_order_for_card(order_id)
    if not order:
        return None, 'Order not found'
    if not order.rider_id:
        return None, 'No rider assigned to this order yet'
    rider = Rider.query.get(order.rider_id)
    if not rider or not rider.user_id:
        return None, 'Rider profile not found'
    if convo.customer_id != order.customer_id or convo.store_id != order.store_id:
        return None, 'This chat is not for that order'
    if convo.seller_id != rider.user_id:
        return None, 'This chat is not for that order'
    if user.id not in (convo.customer_id, convo.seller_id):
        return None, 'Access denied'
    if user.role == 'customer' and order.customer_id != user.id:
        return None, 'Access denied'
    if user.role == 'rider':
        mine = Rider.query.filter_by(user_id=user.id, is_archived=False).first()
        if not mine or order.rider_id != mine.id:
            return None, 'Access denied'
    return order, None


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
            # Rider / support / admin threads — skip seller notify
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


def _maybe_notify_admin_new_chat(convo, user, preview_text):
    """Notify admins when a customer messages a support/admin thread."""
    try:
        if not convo or not user:
            return
        if user.id != convo.customer_id:
            return
        if not convo.seller_id:
            return

        seller = User.query.get(convo.seller_id)
        if not seller or seller.role != 'admin':
            return

        snippet = (preview_text or '').strip()
        if len(snippet) > 120:
            snippet = snippet[:117] + '...'
        customer_name = (user.full_name or 'Customer').strip() or 'Customer'
        from app.utils.admin_notifications import notify_admins
        notify_admins(
            title='New support message',
            message=f'{customer_name}: {snippet}' if snippet else f'{customer_name} sent a support message.',
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
    elif latest.message_type == 'order_card':
        try:
            preview = _order_card_preview(json.loads(latest.text or '{}'))
        except (TypeError, ValueError, json.JSONDecodeError):
            preview = 'Order details'
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

    Opens (or creates) the private rider↔customer thread for an order.
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

    rider_user_id = None
    if user.role == 'rider':
        my_rider = Rider.query.filter_by(user_id=user.id, is_archived=False).first()
        if not my_rider:
            return jsonify({'error': 'Rider profile not found'}), 404
        if my_rider.store_id != order.store_id:
            return jsonify({'error': 'Order is not from your store'}), 403
        if not order.rider_id or order.rider_id != my_rider.id:
            return jsonify({'error': 'Order is not assigned to this rider'}), 403
        rider_user_id = my_rider.user_id
    elif user.role == 'customer':
        if order.customer_id != user.id:
            return jsonify({'error': 'Access denied'}), 403
        if not order.rider_id:
            return jsonify({'error': 'No rider assigned to this order yet'}), 400
        assigned_rider = Rider.query.get(order.rider_id)
        if not assigned_rider or not assigned_rider.user_id:
            return jsonify({'error': 'Rider profile not found'}), 404
        rider_user_id = assigned_rider.user_id
    else:
        return jsonify({'error': 'Only the customer or rider can open this chat'}), 403

    store = Store.query.get(order.store_id)
    if not store:
        return jsonify({'error': 'Store not found'}), 404

    convo = Conversation.query.filter_by(
        customer_id=order.customer_id,
        store_id=order.store_id,
        seller_id=rider_user_id,
    ).first()
    created = False
    if not convo:
        convo = Conversation(
            customer_id=order.customer_id,
            seller_id=rider_user_id,  # private rider-customer thread
            store_id=order.store_id,
        )
        db.session.add(convo)
        db.session.commit()
        created = True
    try:
        payload = _conversation_payload(convo, user, preferred_order_id=order.id)
    except Exception:
        payload = convo.to_dict(current_user_id=user.id)
        payload['is_rider_thread'] = True
        payload['order_context'] = _json_safe({
            'order_id': order.id,
            'order_number': 'ORD-%05d' % int(order.id),
            'status': order.status,
            'store_name': order.store.name if order.store else None,
            'total_amount': float(order.total_amount or 0),
            'subtotal_amount': float(order.subtotal_amount or 0),
            'delivery_fee': float(order.delivery_fee or 0),
            'item_count': 0,
            'items': [],
        })
    return jsonify({'conversation': payload, 'order_context': payload.get('order_context')}), (201 if created else 200)


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

    chrono = list(reversed(pagination.items))
    messages = _hydrate_message_list(convo, chrono, persist=True)
    if db.session.dirty:
        db.session.commit()

    return jsonify({
        'messages': messages,  # chronological
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
         or { "message_type": "order_card", "order_id": <int> }
    Sends a text message, or a one-time order-details card.
    """
    user = _current_user()
    convo = Conversation.query.get_or_404(convo_id)

    if not _can_access_conversation(user, convo):
        return jsonify({'error': 'Access denied'}), 403

    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    msg_type = data.get('message_type', 'text')
    preview_text = text

    if msg_type == 'order_card':
        order_id = data.get('order_id')
        try:
            order_id = int(order_id)
        except (TypeError, ValueError):
            return jsonify({'error': 'order_id is required'}), 400
        order, err = _order_for_rider_card(user, convo, order_id)
        if err:
            return jsonify({'error': err}), 400
        existing = _existing_order_card(convo.id, order_id)
        if existing:
            return jsonify({'message': _message_to_dict(existing), 'already_sent': True}), 200
        ctx = _build_order_chat_context(order)
        text = json.dumps(ctx)
        preview_text = _order_card_preview(ctx)
    elif msg_type != 'text':
        return jsonify({'error': 'Unsupported message type'}), 400

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
    convo.last_message_text = (preview_text or text or '[Image]')[:200]
    convo.last_message_at = now
    convo.last_sender_id = user.id
    convo.updated_at = now

    # Increment unread for the OTHER participant (atomic)
    _bump_other_unread(convo, user.id)

    _maybe_notify_seller_new_chat(convo, user, preview_text or '[Image]')
    _maybe_notify_admin_new_chat(convo, user, preview_text or '[Image]')
    try:
        from app.utils.push import queue_chat_push
        queue_chat_push(convo, user, preview_text or '[Image]')
    except Exception:
        pass

    db.session.commit()

    return jsonify({'message': _message_to_dict(msg)}), 201


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
    _maybe_notify_admin_new_chat(convo, user, caption if caption else '[Image]')
    try:
        from app.utils.push import queue_chat_push
        queue_chat_push(convo, user, caption if caption else '[Image]')
    except Exception:
        pass

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
    Online = active socket OR recent active-session heartbeat/chat activity.
    """
    target = User.query.get_or_404(user_id)

    is_online = False
    try:
        from app.chat_socket import is_user_online as socket_online
        is_online = bool(socket_online(user_id))
    except Exception:
        is_online = False

    if not is_online:
        is_online = _is_present(user_id)

    last_active = _presence.get(int(user_id))
    if last_active is None:
        last_active = _to_pht(target.updated_at)

    return jsonify({
        'user_id': target.id,
        'is_online': bool(is_online),
        'last_active': last_active.isoformat() if last_active else None,
    }), 200


@chat_bp.route('/presence/heartbeat', methods=['POST'])
@chat_auth_required
def presence_heartbeat():
    """
    POST /api/v1/chat/presence/heartbeat
    Called by Flutter/web while the logged-in client is in the foreground.
    chat_auth_required already touches presence; this endpoint exists so
    clients can stay Online without opening chat.
    """
    return jsonify({
        'success': True,
        'ttl_seconds': _PRESENCE_TTL_SECONDS,
    }), 200


@chat_bp.route('/presence/status', methods=['POST'])
@chat_auth_required
def presence_status_batch():
    """
    POST /api/v1/chat/presence/status
    Body: { "user_ids": [1, 2, 3] }
    Returns: { "online": { "1": true, "2": false } }
    Used by the chat inbox to show Messenger-style green dots.
    """
    data = request.get_json(silent=True) or {}
    raw_ids = data.get('user_ids') or []
    online_map = {}

    try:
        from app.chat_socket import is_user_online as socket_online
    except Exception:
        socket_online = None

    seen = set()
    for raw in raw_ids:
        try:
            uid = int(raw)
        except (TypeError, ValueError):
            continue
        if uid <= 0 or uid in seen:
            continue
        seen.add(uid)
        is_online = False
        if socket_online is not None:
            try:
                is_online = bool(socket_online(uid))
            except Exception:
                is_online = False
        if not is_online:
            is_online = _is_present(uid)
        online_map[str(uid)] = bool(is_online)

    return jsonify({'online': online_map}), 200


# ═══════════════════════════════════════════════════════════════════════
# TYPING INDICATOR (Polling fallback)
# ═══════════════════════════════════════════════════════════════════════

# In-memory typing state (per-conversation, per-user)
# {convo_id: {user_id: {'at': datetime, 'name': str}}}
_typing_state = {}
# Must stay above client typing-poll interval (≈2s) with network slack.
_TYPING_TTL_SECONDS = 10


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
