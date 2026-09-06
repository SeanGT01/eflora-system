"""
Socket.IO event handlers for real-time chat.
Provides: message delivery, typing indicators, read receipts, online presence.
"""

from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_jwt_extended import decode_token
from datetime import datetime

from app.extensions import db
from app.models import User, Conversation, ChatMessage

socketio = SocketIO()

# Track connected users: {user_id: set(sid, ...)}
_online_users = {}


def _room_name(convo_id):
    return f'convo_{convo_id}'


def _user_from_token(token_str):
    """Decode a JWT token string and return the User, or None."""
    try:
        payload = decode_token(token_str)
        uid = payload.get('sub') or payload.get('user_id')
        if uid:
            return User.query.get(int(uid))
    except Exception:
        pass
    return None


def _user_id_from_sid(sid):
    for uid, sids in _online_users.items():
        if sid in sids:
            return uid
    return None


def _can_access_conversation(user, convo):
    if not user or not convo:
        return False
    if user.id in (convo.customer_id, convo.seller_id):
        return True
    if user.role == 'admin':
        seller = User.query.get(convo.seller_id)
        return bool(seller and seller.role == 'admin')
    return False


def _conversations_for_user(user):
    """Join rooms by customer_id OR seller_id (covers riders/admins on seller slot)."""
    if user.role == 'admin':
        admin_ids = [row[0] for row in db.session.query(User.id).filter_by(role='admin').all()] or [user.id]
        return Conversation.query.filter(
            db.or_(
                Conversation.customer_id == user.id,
                Conversation.seller_id.in_(admin_ids),
            )
        ).all()
    return Conversation.query.filter(
        db.or_(
            Conversation.customer_id == user.id,
            Conversation.seller_id == user.id,
        )
    ).all()


def is_user_online(user_id):
    """Check if a user has any active socket connections."""
    return user_id in _online_users and len(_online_users[user_id]) > 0


# ═══════════════════════════════════════════════════════════════════════
# CONNECTION
# ═══════════════════════════════════════════════════════════════════════

@socketio.on('connect')
def handle_connect(auth=None):
    """Client sends auth={token: "jwt..."} on connect."""
    from flask import request as flask_request
    token = None
    if auth and isinstance(auth, dict):
        token = auth.get('token')
    if not token:
        token = flask_request.args.get('token')
    if not token:
        return False  # reject connection

    user = _user_from_token(token)
    if not user:
        return False

    sid = flask_request.sid
    _online_users.setdefault(user.id, set()).add(sid)

    convos = _conversations_for_user(user)
    for c in convos:
        join_room(_room_name(c.id))

    for c in convos:
        emit('user_online', {'user_id': user.id}, room=_room_name(c.id), include_self=False)

    emit('connected', {'user_id': user.id, 'status': 'ok'})


@socketio.on('disconnect')
def handle_disconnect():
    """Clean up on disconnect."""
    from flask import request as flask_request
    sid = flask_request.sid

    disconnected_uid = None
    for uid, sids in list(_online_users.items()):
        if sid in sids:
            sids.discard(sid)
            if not sids:
                del _online_users[uid]
                disconnected_uid = uid
            break

    if disconnected_uid:
        user = User.query.get(disconnected_uid)
        if user:
            for c in _conversations_for_user(user):
                emit('user_offline', {'user_id': disconnected_uid}, room=_room_name(c.id))


# ═══════════════════════════════════════════════════════════════════════
# JOIN / LEAVE CONVERSATION
# ═══════════════════════════════════════════════════════════════════════

@socketio.on('join_conversation')
def handle_join(data):
    from flask import request as flask_request
    uid = _user_id_from_sid(flask_request.sid)
    if not uid:
        return
    user = User.query.get(uid)
    convo_id = (data or {}).get('conversation_id')
    if not convo_id:
        return
    convo = Conversation.query.get(convo_id)
    if not _can_access_conversation(user, convo):
        emit('error', {'message': 'Access denied'})
        return
    join_room(_room_name(convo_id))
    emit('joined', {'conversation_id': convo_id})


@socketio.on('leave_conversation')
def handle_leave(data):
    from flask import request as flask_request
    uid = _user_id_from_sid(flask_request.sid)
    if not uid:
        return
    convo_id = (data or {}).get('conversation_id')
    if not convo_id:
        return
    user = User.query.get(uid)
    convo = Conversation.query.get(convo_id)
    if not _can_access_conversation(user, convo):
        return
    leave_room(_room_name(convo_id))


# ═══════════════════════════════════════════════════════════════════════
# SEND MESSAGE (via Socket)
# ═══════════════════════════════════════════════════════════════════════

@socketio.on('send_message')
def handle_send_message(data):
    """
    data: {token, conversation_id, text, message_type?}
    Broadcasts the new message to the conversation room.
    """
    token = data.get('token')
    user = _user_from_token(token) if token else None
    if not user:
        emit('error', {'message': 'Unauthorized'})
        return

    convo_id = data.get('conversation_id')
    convo = Conversation.query.get(convo_id)
    if not _can_access_conversation(user, convo):
        emit('error', {'message': 'Invalid conversation'})
        return

    text = (data.get('text') or '').strip()
    msg_type = data.get('message_type', 'text')

    if msg_type != 'text':
        emit('error', {'message': 'Unsupported message type'})
        return
        emit('error', {'message': 'Empty message'})
        return

    msg = ChatMessage(
        conversation_id=convo.id,
        sender_id=user.id,
        message_type=msg_type,
        text=text if text else None,
    )
    db.session.add(msg)

    now = datetime.utcnow()
    convo.last_message_text = text[:200] if text else '[Image]'
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

    try:
        from app.chat import _maybe_notify_seller_new_chat, _maybe_notify_admin_new_chat
        _maybe_notify_seller_new_chat(convo, user, text or '[Image]')
        _maybe_notify_admin_new_chat(convo, user, text or '[Image]')
    except Exception:
        pass

    db.session.commit()

    emit('new_message', msg.to_dict(), room=_room_name(convo_id), include_self=True)

    for uid in (convo.customer_id, convo.seller_id):
        emit('conversation_updated', convo.to_dict(current_user_id=uid), room=_room_name(convo_id))


# ═══════════════════════════════════════════════════════════════════════
# TYPING INDICATOR
# ═══════════════════════════════════════════════════════════════════════

@socketio.on('typing_start')
def handle_typing_start(data):
    token = data.get('token')
    user = _user_from_token(token) if token else None
    if not user:
        return

    convo_id = data.get('conversation_id')
    convo = Conversation.query.get(convo_id)
    if not _can_access_conversation(user, convo):
        return

    emit('typing', {
        'conversation_id': convo_id,
        'user_id': user.id,
        'full_name': user.full_name,
        'is_typing': True,
    }, room=_room_name(convo_id), include_self=False)


@socketio.on('typing_stop')
def handle_typing_stop(data):
    token = data.get('token')
    user = _user_from_token(token) if token else None
    if not user:
        return

    convo_id = data.get('conversation_id')
    convo = Conversation.query.get(convo_id)
    if not _can_access_conversation(user, convo):
        return

    emit('typing', {
        'conversation_id': convo_id,
        'user_id': user.id,
        'full_name': user.full_name,
        'is_typing': False,
    }, room=_room_name(convo_id), include_self=False)


# ═══════════════════════════════════════════════════════════════════════
# READ RECEIPT (via Socket)
# ═══════════════════════════════════════════════════════════════════════

@socketio.on('mark_read')
def handle_mark_read(data):
    token = data.get('token')
    user = _user_from_token(token) if token else None
    if not user:
        return

    convo_id = data.get('conversation_id')
    convo = Conversation.query.get(convo_id)
    if not _can_access_conversation(user, convo):
        return

    now = datetime.utcnow()
    ChatMessage.query.filter(
        ChatMessage.conversation_id == convo_id,
        ChatMessage.sender_id != user.id,
        ChatMessage.is_read == False  # noqa: E712
    ).update({
        ChatMessage.is_read: True,
        ChatMessage.read_at: now,
    }, synchronize_session='fetch')

    if user.id == convo.customer_id:
        convo.customer_unread = 0
    else:
        convo.seller_unread = 0

    db.session.commit()

    emit('messages_read', {
        'conversation_id': convo_id,
        'read_by': user.id,
        'read_at': now.isoformat(),
    }, room=_room_name(convo_id), include_self=False)
