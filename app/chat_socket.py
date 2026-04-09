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

    # Auto-join all the user's conversation rooms
    if user.role == 'seller':
        convos = Conversation.query.filter_by(seller_id=user.id).all()
    else:
        convos = Conversation.query.filter_by(customer_id=user.id).all()

    for c in convos:
        join_room(_room_name(c.id))

    # Broadcast online status to relevant conversations
    for c in convos:
        emit('user_online', {'user_id': user.id}, room=_room_name(c.id), include_self=False)

    emit('connected', {'user_id': user.id, 'status': 'ok'})


@socketio.on('disconnect')
def handle_disconnect():
    """Clean up on disconnect."""
    from flask import request as flask_request
    sid = flask_request.sid

    # Find and remove from online tracking
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
            if user.role == 'seller':
                convos = Conversation.query.filter_by(seller_id=user.id).all()
            else:
                convos = Conversation.query.filter_by(customer_id=user.id).all()
            for c in convos:
                emit('user_offline', {'user_id': disconnected_uid}, room=_room_name(c.id))


# ═══════════════════════════════════════════════════════════════════════
# JOIN / LEAVE CONVERSATION
# ═══════════════════════════════════════════════════════════════════════

@socketio.on('join_conversation')
def handle_join(data):
    convo_id = data.get('conversation_id')
    if convo_id:
        join_room(_room_name(convo_id))
        emit('joined', {'conversation_id': convo_id})


@socketio.on('leave_conversation')
def handle_leave(data):
    convo_id = data.get('conversation_id')
    if convo_id:
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
    if not convo or user.id not in (convo.customer_id, convo.seller_id):
        emit('error', {'message': 'Invalid conversation'})
        return

    text = (data.get('text') or '').strip()
    msg_type = data.get('message_type', 'text')

    if msg_type == 'text' and not text:
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
    else:
        convo.customer_unread = (convo.customer_unread or 0) + 1

    db.session.commit()

    # Broadcast to room
    emit('new_message', msg.to_dict(), room=_room_name(convo_id), include_self=True)

    # Also emit conversation update for inbox refresh
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
    if not convo or user.id not in (convo.customer_id, convo.seller_id):
        return

    now = datetime.utcnow()
    ChatMessage.query.filter(
        ChatMessage.conversation_id == convo_id,
        ChatMessage.sender_id != user.id,
        ChatMessage.is_read == False
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


def is_user_online(user_id):
    """Check if a user has any active socket connections."""
    return user_id in _online_users and len(_online_users[user_id]) > 0
