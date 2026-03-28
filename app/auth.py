# app/auth.py
from flask import Blueprint, request, jsonify, current_app 
from flask_jwt_extended import create_access_token, decode_token, jwt_required, get_jwt_identity, get_jwt
from app.models import User
from app.extensions import db
from datetime import datetime, timedelta
import jwt as pyjwt
    

auth_bp = Blueprint('auth', __name__)

# In app/auth.py - Update login function
# app/auth.py - Replace your login function with this
# app/auth.py - Update login function

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400

    user = User.query.filter_by(email=data.get('email', '').lower()).first()

    if not user or not user.check_password(data.get('password', '')):
        return jsonify({'error': 'Invalid email or password'}), 401

    if user.status != 'active':
        return jsonify({'error': 'Account is not active'}), 403

    # Use PyJWT directly but make 'sub' a STRING

    # Create payload manually - make 'sub' a STRING
    payload = {
        'sub': str(user.id),  # <-- IMPORTANT: Convert to string
        'user_id': user.id,    # Keep as int for backward compatibility
        'email': user.email,
        'role': user.role,
        'name': user.full_name,
        'exp': datetime.utcnow() + timedelta(days=30),
        'iat': datetime.utcnow()
    }
    
    # Encode the token
    token = pyjwt.encode(
        payload,
        current_app.config['JWT_SECRET_KEY'],
        algorithm='HS256'
    )
    
    # Debug: Print what we put in the token
    print("=" * 60)
    print("✅ TOKEN CREATED WITH PAYLOAD:")
    for key, value in payload.items():
        print(f"  {key}: {value} (type: {type(value)})")
    print("=" * 60)

    return jsonify({
        'success': True,
        'token': token,
        'user': {
            'id': user.id,
            'full_name': user.full_name,
            'email': user.email,
            'role': user.role,
            'avatar_filename': user.avatar_filename,
            'phone': user.phone
        }
    })

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400

    required = ['full_name', 'email', 'password']
    if not all(data.get(f) for f in required):
        return jsonify({'error': 'full_name, email and password are required'}), 400

    if len(data['password']) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    if User.query.filter_by(email=data['email'].lower()).first():
        return jsonify({'error': 'Email already registered'}), 409

    user = User(
        full_name=data['full_name'].strip(),
        email=data['email'].lower().strip(),
        role='customer',
        status='active',
    )
    user.set_password(data['password'])
    db.session.add(user)
    db.session.commit()

    # FIXED: Explicitly add 'sub' claim to the token
    token = create_access_token(
        identity=str(user.id),
        expires_delta=timedelta(days=30),
        additional_claims={
            'sub': str(user.id),  # Explicitly add sub claim
            'user_id': user.id,   # Keep for backward compatibility
            'role': user.role,
            'email': user.email,
        }
    )
    
    print(f"✅ Registration successful for user {user.id}")
    print(f"🔑 Token claims: sub={user.id}, role={user.role}, email={user.email}")

    return jsonify({
        'token': token,
        'user_id': user.id,
        'full_name': user.full_name,
        'email': user.email,
        'role': user.role,
    }), 201


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def me():
    """Get current user profile — Flutter calls this to verify token."""
    # Get the JWT claims to debug
    claims = get_jwt()
    print(f"🔍 /me called - JWT claims: {claims}")
    
    user_id = int(get_jwt_identity())
    print(f"👤 User ID from token: {user_id}")
    
    user = User.query.get(user_id)
    if not user:
        print(f"❌ User not found for ID: {user_id}")
        return jsonify({'error': 'User not found'}), 404
    
    print(f"✅ User found: {user.email}")
    return jsonify(user.to_dict())


# Debug endpoint to check token claims
@auth_bp.route('/debug/token', methods=['GET'])
@jwt_required()
def debug_token():
    """Debug endpoint to examine JWT token claims"""
    claims = get_jwt()
    user_id = get_jwt_identity()
    
    return jsonify({
        'authenticated': True,
        'user_id': user_id,
        'claims': claims,
        'has_sub': 'sub' in claims,
    })


# Enhanced debug endpoint to check token with more details
@auth_bp.route('/debug/check-token', methods=['GET'])
@jwt_required()
def debug_check_token():
    """Enhanced debug endpoint to check what the server sees in the token"""
    claims = get_jwt()
    user_id = get_jwt_identity()
    
    # Get the raw token from header
    auth_header = request.headers.get('Authorization', '')
    
    return jsonify({
        'authenticated': True,
        'user_id': user_id,
        'claims': claims,
        'has_sub': 'sub' in claims,
        'auth_header_preview': auth_header[:50] if auth_header else None,
        'token_valid': True,
    })

# app/auth.py - Add this debug endpoint

@auth_bp.route('/debug/token-creation', methods=['POST'])
def debug_token_creation():
    """Debug endpoint to test token creation"""
    data = request.get_json() or {}
    user_id = data.get('user_id', 4)
    
    # Create token exactly as in login
    token = create_access_token(
        identity=user_id,  # This should become 'sub'
        expires_delta=timedelta(days=30),
        additional_claims={
            'user_id': user_id,
            'role': data.get('role', 'customer'),
            'email': data.get('email', 'test@example.com'),
        }
    )
    
    # Decode it to see what's actually in it
    try:
        from flask_jwt_extended import decode_token
        decoded = decode_token(token)
        return jsonify({
            'token': token,
            'decoded': {
                'sub': decoded.get('sub'),
                'user_id': decoded.get('user_id'),
                'all_claims': {k: str(v)[:50] for k, v in decoded.items() 
                              if k not in ['exp', 'iat', 'jti']}
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    

# app/auth.py - Add this at the bottom

@auth_bp.route('/debug/token-check', methods=['GET'])
def debug_token_check():
    """Debug endpoint to check token creation and validation"""
    from flask_jwt_extended import create_access_token, decode_token
    from flask import current_app
    
    # Create a test token
    test_token = create_access_token(
        identity=999,
        additional_claims={'test': 'value', 'user_id': 999}
    )
    
    # Decode it
    try:
        decoded = decode_token(test_token)
        token_info = {
            'test_token': test_token[:50] + '...',
            'decoded_claims': decoded,
            'has_sub': 'sub' in decoded,
            'sub_value': decoded.get('sub'),
            'sub_type': str(type(decoded.get('sub'))),
            'has_user_id': 'user_id' in decoded,
        }
    except Exception as e:
        token_info = {'error': str(e)}
    
    # Check config
    config_info = {
        'JWT_SECRET_KEY': current_app.config.get('JWT_SECRET_KEY', 'NOT SET')[:10] + '...',
        'JWT_IDENTITY_CLAIM': current_app.config.get('JWT_IDENTITY_CLAIM', 'NOT SET'),
        'JWT_DECODE_OPTIONS': current_app.config.get('JWT_DECODE_OPTIONS', {}),
    }
    
    return jsonify({
        'config': config_info,
        'token_test': token_info
    })


# ═══════════════════════════════════════════════════════════════════════════════
# PROFILE & PASSWORD MANAGEMENT (JWT-protected, for mobile app)
# ═══════════════════════════════════════════════════════════════════════════════

@auth_bp.route('/profile/update', methods=['POST'])
@jwt_required()
def update_profile():
    """Update name and phone for the logged-in user (JWT auth)."""
    try:
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        data = request.get_json(silent=True) or {}
        first_name = data.get('first_name', '').strip()
        last_name  = data.get('last_name', '').strip()
        phone      = data.get('phone', '').strip()

        if first_name or last_name:
            user.full_name = f"{first_name} {last_name}".strip()
        if phone:
            user.phone = phone
        elif 'phone' in data:
            user.phone = None  # allow clearing phone

        user.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({'success': True, 'user': user.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        print(f'❌ UpdateProfile exception: {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/password/change', methods=['POST'])
@jwt_required()
def change_password():
    """Change password for the logged-in user (JWT auth)."""
    try:
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        data = request.get_json(silent=True) or {}
        current_password = data.get('current_password', '')
        new_password     = data.get('new_password', '')
        confirm_password = data.get('confirm_password', '')

        if not all([current_password, new_password, confirm_password]):
            return jsonify({'error': 'All fields are required'}), 400
        if new_password != confirm_password:
            return jsonify({'error': 'New passwords do not match'}), 400
        if len(new_password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        if not user.check_password(current_password):
            return jsonify({'error': 'Current password is incorrect'}), 400

        user.set_password(new_password)
        user.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({'success': True, 'message': 'Password changed successfully'}), 200
    except Exception as e:
        db.session.rollback()
        print(f'❌ ChangePassword exception: {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC RIDER EMAIL VERIFICATION (rider clicks link from email)
# ═══════════════════════════════════════════════════════════════════════════════
# The verification is handled via GET /verify-rider/<token> in templates_routes.py
# since it renders an HTML page for the rider.