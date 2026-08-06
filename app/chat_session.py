"""
Chat Session Bridge - Connects Flask sessions to JWT-based chat API
"""

from flask import Blueprint, session, jsonify, current_app
from datetime import datetime, timedelta
import jwt

chat_session_bp = Blueprint('chat_session', __name__)


@chat_session_bp.route('/session-check', methods=['GET'])
def session_check():
    """
    Check if user is logged in via Flask session.
    Returns a temporary JWT token for chat API access.
    
    GET /api/chat/session-check
    Returns: { logged_in: true, user_id, token, role } or { logged_in: false }
    """
    user_id = session.get('user_id')
    user_role = session.get('role')
    
    if not user_id:
        # Public status check — not an auth failure; avoid noisy 401s for guests
        return jsonify({'logged_in': False}), 200
    
    # Create a temporary JWT token for this request
    payload = {
        'sub': user_id,
        'user_id': user_id,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(hours=1),
    }
    
    token = jwt.encode(
        payload,
        current_app.config.get('JWT_SECRET_KEY', 'dev-secret-key'),
        algorithm='HS256'
    )
    
    return jsonify({
        'logged_in': True,
        'user_id': user_id,
        'token': token,
        'role': user_role
    }), 200
