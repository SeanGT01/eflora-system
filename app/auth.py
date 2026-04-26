# app/auth.py
from flask import Blueprint, request, jsonify, current_app 
from flask_jwt_extended import create_access_token, decode_token, jwt_required, get_jwt_identity, get_jwt
from app.models import User, CustomerOTP
from app.extensions import db
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import jwt as pyjwt
import re
    

auth_bp = Blueprint('auth', __name__)


# ═══════════════════════════════════════════════════════════════════════════════
# CUSTOMER REGISTRATION — OTP-VERIFIED FLOW
# ═══════════════════════════════════════════════════════════════════════════════
# Mirrors the rider OTP design (RiderOTP / send_rider_otp_email) but is initiated
# by the prospective customer themselves. Three endpoints:
#
#   POST /api/v1/auth/customer/send-otp     → start registration, email a 6-digit code
#   POST /api/v1/auth/customer/verify-otp   → confirm the code, mark row verified
#   POST /api/v1/auth/customer/register     → finalise account creation, return JWT
#
# Plus an optional helper:
#   POST /api/v1/auth/customer/resend-otp   → re-issue an OTP within cooldown limits
#
# Storage: app.models.CustomerOTP (one row per email). The OTP code itself is
# hashed with werkzeug.security; only the hash is persisted.
# ═══════════════════════════════════════════════════════════════════════════════

EMAIL_REGEX = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
PASSWORD_SPECIAL_REGEX = re.compile(r'[^A-Za-z0-9]')


def _validate_password_strength(password):
    pw = password or ''
    if len(pw) < 8:
        return 'Password must be at least 8 characters'
    if not re.search(r'[a-z]', pw):
        return 'Password must include at least one lowercase letter'
    if not re.search(r'[A-Z]', pw):
        return 'Password must include at least one uppercase letter'
    if not PASSWORD_SPECIAL_REGEX.search(pw):
        return 'Password must include at least one special character'
    return None


def _normalize_email(value):
    return (value or '').strip().lower()


def _validate_registration_payload(data, require_password=True):
    """Shared validation for send-otp + register payloads."""
    full_name = (data.get('full_name') or '').strip()
    email = _normalize_email(data.get('email'))
    password = data.get('password') or ''
    phone = (data.get('phone') or '').strip() or None

    if not full_name:
        return None, ('full_name is required', 400)
    if not email or not EMAIL_REGEX.match(email):
        return None, ('A valid email is required', 400)
    if require_password:
        if not password:
            return None, ('password is required', 400)
        pw_error = _validate_password_strength(password)
        if pw_error:
            return None, (pw_error, 400)

    return {
        'full_name': full_name,
        'email': email,
        'password': password,
        'phone': phone,
    }, None


@auth_bp.route('/customer/send-otp', methods=['POST'])
def customer_send_otp():
    """
    Begin customer registration. Stores pending account data + emails a 6-digit OTP.

    Request JSON:
        { "full_name": str, "email": str, "password": str (>=6), "phone": str? }

    Responses:
        200  { "success": true, "message": str, "expires_in_seconds": int }
        400  validation error
        409  email already belongs to an active account
        429  resend cooldown not yet elapsed
        500  email delivery failed
    """
    from app.utils.otp_service import (
        DEFAULT_EXPIRY_MINUTES,
        RESEND_COOLDOWN_SECONDS,
        can_resend,
        new_otp_pair,
    )
    from app.utils.email_helper import send_customer_otp_email

    data = request.get_json(silent=True) or {}
    fields, err = _validate_registration_payload(data, require_password=True)
    if err:
        return jsonify({'success': False, 'error': err[0]}), err[1]

    email = fields['email']

    if User.query.filter_by(email=email).first():
        return jsonify({
            'success': False,
            'error': 'This email is already registered. Please log in instead.',
        }), 409

    plain_code, otp_hash, expires_at = new_otp_pair(DEFAULT_EXPIRY_MINUTES)

    pending = {
        'full_name': fields['full_name'],
        'password_hash': generate_password_hash(fields['password']),
        'phone': fields['phone'],
    }

    record = CustomerOTP.query.filter_by(email=email).first()
    if record:
        if not record.is_verified:
            allowed, retry_after = can_resend(record.last_sent_at, RESEND_COOLDOWN_SECONDS)
            if not allowed:
                return jsonify({
                    'success': False,
                    'error': 'Please wait before requesting another code.',
                    'retry_after_seconds': retry_after,
                }), 429
        record.otp_hash = otp_hash
        record.customer_data = pending
        record.expires_at = expires_at
        record.last_sent_at = datetime.utcnow()
        record.attempts = 0
        record.is_verified = False
        record.verified_at = None
    else:
        record = CustomerOTP(
            email=email,
            otp_hash=otp_hash,
            customer_data=pending,
            expires_at=expires_at,
            last_sent_at=datetime.utcnow(),
        )
        db.session.add(record)

    db.session.commit()

    sent = send_customer_otp_email(
        recipient_email=email,
        otp_code=plain_code,
        full_name=fields['full_name'],
        expiry_minutes=DEFAULT_EXPIRY_MINUTES,
    )
    if not sent:
        return jsonify({
            'success': False,
            'error': 'Failed to send verification email. Please try again shortly.',
        }), 500

    return jsonify({
        'success': True,
        'message': f'A 6-digit verification code has been sent to {email}.',
        'expires_in_seconds': DEFAULT_EXPIRY_MINUTES * 60,
        'resend_cooldown_seconds': RESEND_COOLDOWN_SECONDS,
    }), 200


@auth_bp.route('/customer/resend-otp', methods=['POST'])
def customer_resend_otp():
    """
    Re-issue an OTP for an existing pending registration without requiring the
    full payload again. Cooldown applies.

    Request JSON: { "email": str }
    """
    from app.utils.otp_service import (
        DEFAULT_EXPIRY_MINUTES,
        RESEND_COOLDOWN_SECONDS,
        can_resend,
        new_otp_pair,
    )
    from app.utils.email_helper import send_customer_otp_email

    data = request.get_json(silent=True) or {}
    email = _normalize_email(data.get('email'))
    if not email or not EMAIL_REGEX.match(email):
        return jsonify({'success': False, 'error': 'A valid email is required'}), 400

    record = CustomerOTP.query.filter_by(email=email, is_verified=False).first()
    if not record:
        return jsonify({
            'success': False,
            'error': 'No pending verification found for this email. Please start registration again.',
        }), 404

    allowed, retry_after = can_resend(record.last_sent_at, RESEND_COOLDOWN_SECONDS)
    if not allowed:
        return jsonify({
            'success': False,
            'error': 'Please wait before requesting another code.',
            'retry_after_seconds': retry_after,
        }), 429

    plain_code, otp_hash, expires_at = new_otp_pair(DEFAULT_EXPIRY_MINUTES)
    record.otp_hash = otp_hash
    record.expires_at = expires_at
    record.last_sent_at = datetime.utcnow()
    record.attempts = 0
    db.session.commit()

    pending = record.customer_data or {}
    sent = send_customer_otp_email(
        recipient_email=email,
        otp_code=plain_code,
        full_name=pending.get('full_name'),
        expiry_minutes=DEFAULT_EXPIRY_MINUTES,
    )
    if not sent:
        return jsonify({
            'success': False,
            'error': 'Failed to send verification email. Please try again shortly.',
        }), 500

    return jsonify({
        'success': True,
        'message': f'A new verification code has been sent to {email}.',
        'expires_in_seconds': DEFAULT_EXPIRY_MINUTES * 60,
    }), 200


@auth_bp.route('/customer/verify-otp', methods=['POST'])
def customer_verify_otp():
    """
    Verify a 6-digit OTP. On success the row is marked is_verified=True so the
    follow-up /customer/register call may proceed. Codes cannot be reused —
    once consumed they are deleted by /customer/register.

    Request JSON: { "email": str, "otp_code": str }
    """
    from app.utils.otp_service import (
        MAX_VERIFY_ATTEMPTS,
        attempts_remaining,
        verify_otp,
    )

    data = request.get_json(silent=True) or {}
    email = _normalize_email(data.get('email'))
    otp_code = (data.get('otp_code') or '').strip()

    if not email or not otp_code:
        return jsonify({'success': False, 'error': 'Email and OTP code are required'}), 400

    record = CustomerOTP.query.filter_by(email=email).first()
    if not record:
        return jsonify({
            'success': False,
            'error': 'No verification request found for this email.',
        }), 404

    if record.is_verified:
        return jsonify({
            'success': True,
            'message': 'Email already verified. You can finish registration.',
            'verified': True,
        }), 200

    if record.is_expired():
        return jsonify({
            'success': False,
            'error': 'OTP has expired. Please request a new code.',
            'expired': True,
        }), 400

    if (record.attempts or 0) >= MAX_VERIFY_ATTEMPTS:
        return jsonify({
            'success': False,
            'error': 'Too many incorrect attempts. Please request a new code.',
            'locked': True,
        }), 429

    if not verify_otp(otp_code, record.otp_hash):
        record.attempts = (record.attempts or 0) + 1
        db.session.commit()
        return jsonify({
            'success': False,
            'error': 'Invalid OTP code. Please try again.',
            'attempts_remaining': attempts_remaining(record.attempts, MAX_VERIFY_ATTEMPTS),
        }), 400

    record.is_verified = True
    record.verified_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Email verified. You can now finalise your registration.',
        'verified': True,
    }), 200


@auth_bp.route('/customer/register', methods=['POST'])
def customer_register():
    """
    Finalise customer registration. Requires the email to have been verified by
    /customer/verify-otp. The pending data captured at /send-otp time is used to
    create the User row, then the OTP record is consumed (deleted).

    Request JSON: { "email": str }
    Response   : same shape as the legacy /auth/register so existing Flutter code
                 paths continue to work after a one-line URL swap.
    """
    data = request.get_json(silent=True) or {}
    email = _normalize_email(data.get('email'))
    if not email:
        return jsonify({'success': False, 'error': 'Email is required'}), 400

    record = CustomerOTP.query.filter_by(email=email).first()
    if not record:
        return jsonify({
            'success': False,
            'error': 'No verification record found. Please start registration again.',
        }), 404

    if not record.is_verified:
        return jsonify({
            'success': False,
            'error': 'Email is not verified yet. Please verify the OTP first.',
        }), 403

    if User.query.filter_by(email=email).first():
        # Race-condition safety: clean up the orphan OTP row.
        db.session.delete(record)
        db.session.commit()
        return jsonify({
            'success': False,
            'error': 'This email is already registered. Please log in instead.',
        }), 409

    pending = record.customer_data or {}
    full_name = pending.get('full_name')
    password_hash = pending.get('password_hash')
    phone = pending.get('phone')

    if not full_name or not password_hash:
        return jsonify({
            'success': False,
            'error': 'Stored registration data is incomplete. Please start over.',
        }), 400

    user = User(
        full_name=full_name,
        email=email,
        role='customer',
        status='active',
        phone=phone,
    )
    user.password_hash = password_hash  # already hashed during /send-otp
    db.session.add(user)
    db.session.flush()

    # Single-use OTP: drop the row so the same code can never be reused.
    db.session.delete(record)
    db.session.commit()

    token = create_access_token(
        identity=str(user.id),
        expires_delta=timedelta(days=30),
        additional_claims={
            'sub': str(user.id),
            'user_id': user.id,
            'role': user.role,
            'email': user.email,
        },
    )

    return jsonify({
        'success': True,
        'message': 'Account created successfully.',
        'token': token,
        'user_id': user.id,
        'full_name': user.full_name,
        'email': user.email,
        'role': user.role,
        'user': user.to_dict(),
    }), 201

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

    pw_error = _validate_password_strength(data['password'])
    if pw_error:
        return jsonify({'error': pw_error}), 400

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
        pw_error = _validate_password_strength(new_password)
        if pw_error:
            return jsonify({'error': pw_error}), 400
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