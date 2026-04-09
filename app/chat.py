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

from app.extensions import db
from app.models import User, Store, Conversation, ChatMessage

import cloudinary
import cloudinary.uploader

chat_bp = Blueprint('chat', __name__)

# Philippines timezone
PHT = pytz.timezone('Asia/Manila')

def pht_now():
    """Get current time in Philippines timezone (UTC+8)"""
    return datetime.now(PHT)


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


# ═══════════════════════════════════════════════════════════════════════
# CONVERSATIONS
# ═══════════════════════════════════════════════════════════════════════

@chat_bp.route('/conversations', methods=['GET'])
@chat_auth_required
def list_conversations():
    """
    GET /api/v1/chat/conversations
    Returns all conversations for the current user (customer or seller).
    """
    user = _current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    if user.role == 'seller':
        convos = Conversation.query.filter(
            Conversation.seller_id == user.id,
            Conversation.seller_deleted_at.is_(None)
        ).order_by(Conversation.last_message_at.desc().nullslast()).all()
    else:
        convos = Conversation.query.filter(
            Conversation.customer_id == user.id,
            Conversation.customer_deleted_at.is_(None)
        ).order_by(Conversation.last_message_at.desc().nullslast()).all()

    return jsonify({
        'conversations': [c.to_dict(current_user_id=user.id) for c in convos]
    }), 200


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
    convo = Conversation.query.filter_by(customer_id=user.id, store_id=store.id).first()
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
    db.session.commit()

    return jsonify({'conversation': convo.to_dict(current_user_id=user.id)}), 201


@chat_bp.route('/conversations/<int:convo_id>', methods=['GET'])
@chat_auth_required
def get_conversation(convo_id):
    """
    GET /api/v1/chat/conversations/<id>
    Returns conversation details (header info).
    """
    user = _current_user()
    convo = Conversation.query.get_or_404(convo_id)

    if user.id not in (convo.customer_id, convo.seller_id):
        return jsonify({'error': 'Access denied'}), 403

    return jsonify({'conversation': convo.to_dict(current_user_id=user.id)}), 200


@chat_bp.route('/conversations/<int:convo_id>', methods=['DELETE'])
@chat_auth_required
def delete_conversation(convo_id):
    """
    DELETE /api/v1/chat/conversations/<id>
    Soft-deletes the conversation for the current user only.
    """
    user = _current_user()
    convo = Conversation.query.get_or_404(convo_id)

    if user.id not in (convo.customer_id, convo.seller_id):
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

    if user.id not in (convo.customer_id, convo.seller_id):
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

    if user.id not in (convo.customer_id, convo.seller_id):
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

    # Increment unread for the OTHER participant
    if user.id == convo.customer_id:
        convo.seller_unread = (convo.seller_unread or 0) + 1
        # Un-delete for seller if they had deleted the conversation
        if convo.seller_deleted_at:
            convo.seller_deleted_at = None
    else:
        convo.customer_unread = (convo.customer_unread or 0) + 1
        if convo.customer_deleted_at:
            convo.customer_deleted_at = None

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

    if user.id not in (convo.customer_id, convo.seller_id):
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

    if user.id == convo.customer_id:
        convo.seller_unread = (convo.seller_unread or 0) + 1
        if convo.seller_deleted_at:
            convo.seller_deleted_at = None
    else:
        convo.customer_unread = (convo.customer_unread or 0) + 1
        if convo.customer_deleted_at:
            convo.customer_deleted_at = None

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

    if user.id not in (convo.customer_id, convo.seller_id):
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

    if user.id not in (convo.customer_id, convo.seller_id):
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
    """
    user = _current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    if user.role == 'seller':
        total = db.session.query(db.func.coalesce(db.func.sum(Conversation.seller_unread), 0)) \
            .filter(Conversation.seller_id == user.id, Conversation.seller_deleted_at.is_(None)) \
            .scalar()
    else:
        total = db.session.query(db.func.coalesce(db.func.sum(Conversation.customer_unread), 0)) \
            .filter(Conversation.customer_id == user.id, Conversation.customer_deleted_at.is_(None)) \
            .scalar()

    return jsonify({'unread_count': int(total)}), 200


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
    is_online = target.updated_at and target.updated_at >= threshold

    return jsonify({
        'user_id': target.id,
        'is_online': bool(is_online),
        'last_active': target.updated_at.isoformat() if target.updated_at else None,
    }), 200


# ═══════════════════════════════════════════════════════════════════════
# TYPING INDICATOR (Polling fallback)
# ═══════════════════════════════════════════════════════════════════════

# In-memory typing state (per-conversation, per-user)
_typing_state = {}  # {convo_id: {user_id: datetime}}


@chat_bp.route('/conversations/<int:convo_id>/typing', methods=['POST'])
@chat_auth_required
def set_typing(convo_id):
    """
    POST /api/v1/chat/conversations/<id>/typing
    Signals that the current user is typing. Expires after 5 seconds.
    """
    user = _current_user()
    convo = Conversation.query.get_or_404(convo_id)

    if user.id not in (convo.customer_id, convo.seller_id):
        return jsonify({'error': 'Access denied'}), 403

    if convo_id not in _typing_state:
        _typing_state[convo_id] = {}
    _typing_state[convo_id][user.id] = pht_now()

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

    if user.id not in (convo.customer_id, convo.seller_id):
        return jsonify({'error': 'Access denied'}), 403

    from datetime import timedelta
    threshold = pht_now() - timedelta(seconds=5)
    typing_users = []

    if convo_id in _typing_state:
        for uid, ts in list(_typing_state[convo_id].items()):
            if ts >= threshold and uid != user.id:
                u = User.query.get(uid)
                if u:
                    typing_users.append({'id': u.id, 'full_name': u.full_name})
            elif ts < threshold:
                del _typing_state[convo_id][uid]

    return jsonify({'typing': typing_users}), 200
