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


def _normalize_email(value):
    return (value or '').strip().lower()


def _find_user_by_phone(normalized_09):
    """Find User whose phone matches any common PH format of normalized_09."""
    from app.utils.phone_utils import phone_lookup_variants

    if not normalized_09:
        return None
    variants = phone_lookup_variants(normalized_09)
    return User.query.filter(User.phone.in_(variants)).first()


def _find_user_by_login_identifier(raw):
    """Resolve login / session lookup by email or PH mobile."""
    from app.utils.phone_utils import (
        is_synthetic_account_email,
        is_valid_ph_mobile,
        normalize_ph_mobile,
        phone_to_account_email,
    )

    raw = (raw or '').strip()
    if not raw:
        return None

    if '@' in raw:
        email = _normalize_email(raw)
        if is_synthetic_account_email(email):
            local, _, _ = email.partition('@')
            phone = normalize_ph_mobile(local)
            if phone:
                return _find_user_by_phone(phone) or User.query.filter_by(email=email).first()
        return User.query.filter_by(email=email).first()

    if is_valid_ph_mobile(raw):
        phone = normalize_ph_mobile(raw)
        # Prefer the phone-only account (synthetic email) over another user
        # who happens to have the same number on their profile.
        synth_user = User.query.filter_by(email=phone_to_account_email(phone)).first()
        if synth_user:
            return synth_user
        return _find_user_by_phone(phone)

    return None


def _phone_taken(normalized_09, exclude_email=None):
    if not normalized_09:
        return False
    user = _find_user_by_phone(normalized_09)
    if not user:
        from app.utils.phone_utils import phone_to_account_email
        # Phone-only accounts may only have the synthetic email set
        synth = phone_to_account_email(normalized_09)
        user = User.query.filter_by(email=synth).first()
        if not user:
            return False
    if exclude_email and user.email == exclude_email:
        return False
    return True


def _parse_forgot_identifier(data):
    """
    Resolve forgot-password identifier to (user, channel, phone_or_none) or error.

    Accepts identifier (preferred) or legacy email field.
    Email → Gmail OTP; PH phone → SMS OTP.
    """
    from app.utils.phone_utils import (
        is_synthetic_account_email,
        is_valid_ph_mobile,
        normalize_ph_mobile,
        phone_to_account_email,
    )

    raw = (data.get('identifier') if data.get('identifier') is not None else data.get('email'))
    raw = (raw or '').strip()
    if not raw:
        return None, ({
            'success': False,
            'error': 'Enter your email address or Philippine mobile number.',
        }, 400)

    if '@' in raw:
        email = _normalize_email(raw)
        if is_synthetic_account_email(email):
            return None, ({
                'success': False,
                'error': 'Enter a valid email or Philippine mobile number (e.g. 09171234567).',
            }, 400)
        if not EMAIL_REGEX.match(email):
            return None, ({
                'success': False,
                'error': 'A valid email is required',
            }, 400)
        user = User.query.filter_by(email=email).first()
        if not user:
            return None, ({
                'success': False,
                'error': 'No account found with this email. Please check and try again.',
            }, 404)
        return {'user': user, 'channel': 'email', 'phone': None}, None

    if not is_valid_ph_mobile(raw):
        return None, ({
            'success': False,
            'error': 'Enter a valid email or Philippine mobile number (e.g. 09171234567).',
        }, 400)

    phone = normalize_ph_mobile(raw)
    # Prefer phone-only (SMS) accounts — same as login — so a customer profile
    # that happens to store this number does not steal the reset flow.
    user = (
        User.query.filter_by(email=phone_to_account_email(phone)).first()
        or _find_user_by_phone(phone)
        or _find_user_by_login_identifier(phone)
    )
    if not user:
        return None, ({
            'success': False,
            'error': 'No account found with this phone number. Please check and try again.',
        }, 404)
    return {'user': user, 'channel': 'sms', 'phone': phone}, None


def _resolve_password_reset_email(raw):
    """
    Map login id / account email / phone to the users.email key used by PasswordResetOTP.
    Accepts synthetic account emails (internal) for mid-flow verify/resend/reset.
    """
    from app.utils.phone_utils import is_synthetic_account_email

    raw = (raw or '').strip()
    if not raw:
        return None

    if '@' in raw:
        email = _normalize_email(raw)
        if is_synthetic_account_email(email):
            return email
        if EMAIL_REGEX.match(email):
            return email
        return None

    user = _find_user_by_login_identifier(raw)
    return user.email if user else None


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


def _validate_registration_payload(data, require_password=True):
    """Shared validation for send-otp payloads.

    One login identity: email OR PH mobile (not both).
    Channel: email → Gmail OTP; phone → SMS OTP (account email is synthetic).
    """
    from app.utils.phone_utils import (
        is_synthetic_account_email,
        is_valid_ph_mobile,
        normalize_ph_mobile,
        phone_to_account_email,
    )

    full_name = (data.get('full_name') or '').strip()
    password = data.get('password') or ''

    # Prefer single identifier; fall back to legacy email/phone pair.
    raw_id = (data.get('identifier') if data.get('identifier') is not None else None)
    if raw_id is None or str(raw_id).strip() == '':
        legacy_email = _normalize_email(data.get('email'))
        legacy_phone = (data.get('phone') or '').strip() or None
        if legacy_email and legacy_phone:
            return None, (
                'Use either an email or a phone number to create your account — not both.',
                400,
            )
        if legacy_phone and not legacy_email:
            raw_id = legacy_phone
        else:
            raw_id = legacy_email or ''
    raw_id = (raw_id or '').strip()

    if not full_name:
        return None, ('full_name is required', 400)
    if not raw_id:
        return None, ('Enter your email address or Philippine mobile number.', 400)
    if require_password:
        if not password:
            return None, ('password is required', 400)
        pw_error = _validate_password_strength(password)
        if pw_error:
            return None, (pw_error, 400)

    if '@' in raw_id:
        email = _normalize_email(raw_id)
        if is_synthetic_account_email(email) or not EMAIL_REGEX.match(email):
            return None, ('A valid email is required', 400)
        return {
            'full_name': full_name,
            'email': email,
            'password': password,
            'phone': None,
            'otp_channel': 'email',
        }, None

    if not is_valid_ph_mobile(raw_id):
        return None, (
            'Enter a valid email or Philippine mobile number (e.g. 09171234567).',
            400,
        )

    phone = normalize_ph_mobile(raw_id)
    email = phone_to_account_email(phone)
    return {
        'full_name': full_name,
        'email': email,
        'password': password,
        'phone': phone,
        'otp_channel': 'sms',
    }, None


@auth_bp.route('/customer/send-otp', methods=['POST'])
def customer_send_otp():
    """
    Begin customer registration. Stores pending account data + sends a 6-digit OTP.

    One login identity — email OR PH mobile:
        { "full_name": str, "identifier": str, "password": str }

    Legacy email (+ optional phone) is still accepted but phone-only or email-only
    is required (not both).
    """
    from app.utils.otp_service import (
        DEFAULT_EXPIRY_MINUTES,
        RESEND_COOLDOWN_SECONDS,
        can_resend,
        new_otp_pair,
    )
    from app.utils.email_helper import send_customer_otp_email
    from app.utils.otp_delivery import deliver_otp, sync_hashed_otp_record
    from app.utils.phone_utils import display_login_id

    data = request.get_json(silent=True) or {}
    fields, err = _validate_registration_payload(data, require_password=True)
    if err:
        return jsonify({'success': False, 'error': err[0]}), err[1]

    email = fields['email']
    channel = fields['otp_channel']
    phone = fields['phone']

    if User.query.filter_by(email=email).first():
        kind = 'phone number' if channel == 'sms' else 'email'
        return jsonify({
            'success': False,
            'error': f'This {kind} is already registered. Please log in instead.',
        }), 409

    if phone and _phone_taken(phone, exclude_email=email):
        return jsonify({
            'success': False,
            'error': 'This phone number is already registered to another account.',
        }), 409

    plain_code, otp_hash, expires_at = new_otp_pair(DEFAULT_EXPIRY_MINUTES)

    pending = {
        'full_name': fields['full_name'],
        'password_hash': generate_password_hash(fields['password']),
        'phone': phone,
        'otp_channel': channel,
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

    ok, fail, meta = deliver_otp(
        channel,
        otp_code=plain_code,
        email=email,
        phone=phone,
        email_sender_fn=send_customer_otp_email,
        email_sender_kwargs={'full_name': fields['full_name'], 'expiry_minutes': DEFAULT_EXPIRY_MINUTES},
        expiry_minutes=DEFAULT_EXPIRY_MINUTES,
        sms_purpose='verification',
    )
    if not ok:
        return jsonify(fail), 503
    sync_hashed_otp_record(record, meta, plain_code)

    dest = meta.get('destination_masked') or (phone if channel == 'sms' else email)
    return jsonify({
        'success': True,
        'message': f'A 6-digit verification code has been sent to {dest}.',
        'otp_channel': channel,
        'destination_masked': dest,
        'email': email,
        'login_id': display_login_id(email=email, phone=phone),
        'expires_in_seconds': DEFAULT_EXPIRY_MINUTES * 60,
        'resend_cooldown_seconds': RESEND_COOLDOWN_SECONDS,
    }), 200


@auth_bp.route('/customer/resend-otp', methods=['POST'])
def customer_resend_otp():
    """
    Re-issue an OTP for an existing pending registration without requiring the
    full payload again. Uses the otp_channel stored on the pending row.

    Request JSON: { "email": str }
    """
    from app.utils.otp_service import (
        DEFAULT_EXPIRY_MINUTES,
        RESEND_COOLDOWN_SECONDS,
        can_resend,
        new_otp_pair,
    )
    from app.utils.email_helper import send_customer_otp_email
    from app.utils.otp_delivery import deliver_otp, normalize_otp_channel, sync_hashed_otp_record

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

    pending = record.customer_data or {}
    channel = normalize_otp_channel(pending.get('otp_channel'), default='email') or 'email'
    phone = pending.get('phone')

    plain_code, otp_hash, expires_at = new_otp_pair(DEFAULT_EXPIRY_MINUTES)
    record.otp_hash = otp_hash
    record.expires_at = expires_at
    record.last_sent_at = datetime.utcnow()
    record.attempts = 0
    db.session.commit()

    ok, fail, meta = deliver_otp(
        channel,
        otp_code=plain_code,
        email=email,
        phone=phone,
        email_sender_fn=send_customer_otp_email,
        email_sender_kwargs={'full_name': pending.get('full_name'), 'expiry_minutes': DEFAULT_EXPIRY_MINUTES},
        expiry_minutes=DEFAULT_EXPIRY_MINUTES,
        sms_purpose='verification',
    )
    if not ok:
        return jsonify(fail), 503
    sync_hashed_otp_record(record, meta, plain_code)

    dest = meta.get('destination_masked') or (phone if channel == 'sms' else email)
    return jsonify({
        'success': True,
        'message': f'A new verification code has been sent to {dest}.',
        'otp_channel': channel,
        'destination_masked': dest,
        'email': email,
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

# ═══════════════════════════════════════════════════════════════════════════════
# FORGOT PASSWORD — OTP-VERIFIED RESET (same Gmail OTP pipeline as registration)
# ═══════════════════════════════════════════════════════════════════════════════
#   POST /api/v1/auth/forgot-password/send-otp
#   POST /api/v1/auth/forgot-password/resend-otp
#   POST /api/v1/auth/forgot-password/verify-otp
#   POST /api/v1/auth/forgot-password/reset
# ═══════════════════════════════════════════════════════════════════════════════

def _ensure_password_reset_otps_table():
    """Create password_reset_otps from ORM if migration wasn't applied yet."""
    from sqlalchemy import inspect as sa_inspect, text
    from app.models import PasswordResetOTP

    try:
        if not sa_inspect(db.engine).has_table('password_reset_otps'):
            PasswordResetOTP.__table__.create(db.engine, checkfirst=True)
            try:
                current_app.logger.info('Created missing table password_reset_otps from model')
            except RuntimeError:
                pass
        # Ensure otp_channel exists on older DBs
        cols = {c['name'] for c in sa_inspect(db.engine).get_columns('password_reset_otps')}
        if 'otp_channel' not in cols:
            with db.engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE password_reset_otps "
                    "ADD COLUMN IF NOT EXISTS otp_channel VARCHAR(10) DEFAULT 'email' NOT NULL"
                ))
        return True
    except Exception as exc:
        try:
            current_app.logger.warning('Could not ensure password_reset_otps table: %s', exc)
        except RuntimeError:
            pass
        return False


def _upsert_password_reset_otp(email, otp_channel='email'):
    """Create/refresh a PasswordResetOTP row and return (plain_code, record) or error tuple."""
    from app.models import PasswordResetOTP
    from app.utils.otp_service import (
        DEFAULT_EXPIRY_MINUTES,
        RESEND_COOLDOWN_SECONDS,
        can_resend,
        new_otp_pair,
    )
    from app.utils.otp_delivery import normalize_otp_channel

    channel = normalize_otp_channel(otp_channel, default='email') or 'email'
    _ensure_password_reset_otps_table()
    plain_code, otp_hash, expires_at = new_otp_pair(DEFAULT_EXPIRY_MINUTES)
    record = PasswordResetOTP.query.filter_by(email=email).first()
    if record:
        allowed, retry_after = can_resend(record.last_sent_at, RESEND_COOLDOWN_SECONDS)
        if not allowed and not record.is_verified:
            return None, ({
                'success': False,
                'error': 'Please wait before requesting another code.',
                'retry_after_seconds': retry_after,
            }, 429)
        record.otp_hash = otp_hash
        record.otp_channel = channel
        record.expires_at = expires_at
        record.last_sent_at = datetime.utcnow()
        record.attempts = 0
        record.is_verified = False
        record.verified_at = None
    else:
        record = PasswordResetOTP(
            email=email,
            otp_hash=otp_hash,
            otp_channel=channel,
            expires_at=expires_at,
            last_sent_at=datetime.utcnow(),
        )
        db.session.add(record)
    db.session.commit()
    return (plain_code, record), None


@auth_bp.route('/forgot-password/send-otp', methods=['POST'])
def forgot_password_send_otp():
    """
    Start forgot-password. Identifier is email (Gmail OTP) or PH phone (SMS OTP).

    Request JSON: { "identifier": str }  (or legacy "email")
    """
    from app.utils.otp_service import DEFAULT_EXPIRY_MINUTES, RESEND_COOLDOWN_SECONDS
    from app.utils.email_helper import send_password_reset_otp_email
    from app.utils.otp_delivery import deliver_otp, sync_hashed_otp_record
    from app.utils.phone_utils import normalize_ph_mobile, display_login_id

    data = request.get_json(silent=True) or {}
    parsed, err = _parse_forgot_identifier(data)
    if err:
        return jsonify(err[0]), err[1]

    user = parsed['user']
    channel = parsed['channel']
    phone = parsed['phone'] or normalize_ph_mobile(user.phone)

    # Phone-only accounts: recover mobile from synthetic email if phone column empty
    if channel == 'sms' and not phone:
        from app.utils.phone_utils import is_synthetic_account_email
        if is_synthetic_account_email(user.email):
            local, _, _ = user.email.partition('@')
            phone = normalize_ph_mobile(local)

    if user.status != 'active':
        return jsonify({
            'success': False,
            'error': 'This account is not active. Please contact support.',
        }), 403

    if channel == 'sms' and not phone:
        return jsonify({
            'success': False,
            'error': 'This account has no mobile number on file for SMS reset.',
        }), 400

    email = user.email
    result, upsert_err = _upsert_password_reset_otp(email, otp_channel=channel)
    if upsert_err:
        return jsonify(upsert_err[0]), upsert_err[1]

    plain_code, record = result
    ok, fail, meta = deliver_otp(
        channel,
        otp_code=plain_code,
        email=email,
        phone=phone,
        email_sender_fn=send_password_reset_otp_email,
        email_sender_kwargs={'full_name': user.full_name, 'expiry_minutes': DEFAULT_EXPIRY_MINUTES},
        expiry_minutes=DEFAULT_EXPIRY_MINUTES,
        sms_purpose='password reset',
    )
    if not ok:
        return jsonify(fail), 503
    sync_hashed_otp_record(record, meta, plain_code)

    dest = meta.get('destination_masked')
    return jsonify({
        'success': True,
        'message': f'A 6-digit verification code has been sent to {dest}.',
        'email': email,
        'login_id': display_login_id(email=email, phone=phone or user.phone),
        'otp_channel': channel,
        'destination_masked': dest,
        'expires_in_seconds': DEFAULT_EXPIRY_MINUTES * 60,
        'resend_cooldown_seconds': RESEND_COOLDOWN_SECONDS,
    }), 200


@auth_bp.route('/forgot-password/resend-otp', methods=['POST'])
def forgot_password_resend_otp():
    """Re-issue a password-reset OTP. Request JSON: { "email"|"identifier": str }."""
    from app.models import PasswordResetOTP
    from app.utils.otp_service import (
        DEFAULT_EXPIRY_MINUTES,
        RESEND_COOLDOWN_SECONDS,
        can_resend,
        new_otp_pair,
    )
    from app.utils.email_helper import send_password_reset_otp_email
    from app.utils.otp_delivery import deliver_otp, normalize_otp_channel, sync_hashed_otp_record
    from app.utils.phone_utils import normalize_ph_mobile

    data = request.get_json(silent=True) or {}
    raw = data.get('identifier') if data.get('identifier') is not None else data.get('email')
    email = _resolve_password_reset_email(raw)
    if not email:
        return jsonify({
            'success': False,
            'error': 'Enter your email address or Philippine mobile number.',
        }), 400

    _ensure_password_reset_otps_table()
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({
            'success': False,
            'error': 'No account found with this email.',
        }), 404

    record = PasswordResetOTP.query.filter_by(email=email).first()
    if not record:
        return jsonify({
            'success': False,
            'error': 'No password reset request found. Please start again.',
        }), 404

    allowed, retry_after = can_resend(record.last_sent_at, RESEND_COOLDOWN_SECONDS)
    if not allowed:
        return jsonify({
            'success': False,
            'error': 'Please wait before requesting another code.',
            'retry_after_seconds': retry_after,
        }), 429

    channel = normalize_otp_channel(getattr(record, 'otp_channel', None), default='email') or 'email'
    phone = normalize_ph_mobile(user.phone)
    if channel == 'sms' and not phone:
        from app.utils.phone_utils import is_synthetic_account_email
        if is_synthetic_account_email(user.email):
            local, _, _ = user.email.partition('@')
            phone = normalize_ph_mobile(local)
    if channel == 'sms' and not phone:
        return jsonify({
            'success': False,
            'error': 'This account has no mobile number on file for SMS reset.',
        }), 400

    plain_code, otp_hash, expires_at = new_otp_pair(DEFAULT_EXPIRY_MINUTES)
    record.otp_hash = otp_hash
    record.otp_channel = channel
    record.expires_at = expires_at
    record.last_sent_at = datetime.utcnow()
    record.attempts = 0
    record.is_verified = False
    record.verified_at = None
    db.session.commit()

    ok, fail, meta = deliver_otp(
        channel,
        otp_code=plain_code,
        email=email,
        phone=phone,
        email_sender_fn=send_password_reset_otp_email,
        email_sender_kwargs={'full_name': user.full_name, 'expiry_minutes': DEFAULT_EXPIRY_MINUTES},
        expiry_minutes=DEFAULT_EXPIRY_MINUTES,
        sms_purpose='password reset',
    )
    if not ok:
        return jsonify(fail), 503
    sync_hashed_otp_record(record, meta, plain_code)

    dest = meta.get('destination_masked')
    return jsonify({
        'success': True,
        'message': f'A new verification code has been sent to {dest}.',
        'email': email,
        'otp_channel': channel,
        'destination_masked': dest,
        'expires_in_seconds': DEFAULT_EXPIRY_MINUTES * 60,
        'resend_cooldown_seconds': RESEND_COOLDOWN_SECONDS,
    }), 200


@auth_bp.route('/forgot-password/verify-otp', methods=['POST'])
def forgot_password_verify_otp():
    """Verify the password-reset OTP. Request JSON: { "email"|"identifier": str, "otp_code": str }"""
    from app.models import PasswordResetOTP
    from app.utils.otp_service import (
        MAX_VERIFY_ATTEMPTS,
        attempts_remaining,
        verify_otp,
    )

    data = request.get_json(silent=True) or {}
    raw = data.get('identifier') if data.get('identifier') is not None else data.get('email')
    email = _resolve_password_reset_email(raw)
    otp_code = (data.get('otp_code') or '').strip()

    if not email or not otp_code:
        return jsonify({'success': False, 'error': 'Email/phone and OTP code are required'}), 400

    _ensure_password_reset_otps_table()
    record = PasswordResetOTP.query.filter_by(email=email).first()
    if not record:
        return jsonify({
            'success': False,
            'error': 'No password reset request found for this account.',
        }), 404

    if record.is_verified:
        return jsonify({
            'success': True,
            'message': 'Code already verified. You can set a new password.',
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
        'message': 'Code verified. You can now set a new password.',
        'verified': True,
    }), 200


@auth_bp.route('/forgot-password/reset', methods=['POST'])
def forgot_password_reset():
    """
    Set a new password after OTP verification.

    Request JSON:
        { "email"|"identifier": str, "new_password": str, "confirm_password": str }
    """
    from app.models import PasswordResetOTP

    data = request.get_json(silent=True) or {}
    raw = data.get('identifier') if data.get('identifier') is not None else data.get('email')
    email = _resolve_password_reset_email(raw)
    new_password = data.get('new_password') or ''
    confirm_password = data.get('confirm_password') or ''

    if not email:
        return jsonify({'success': False, 'error': 'Email or phone is required'}), 400
    if not new_password or not confirm_password:
        return jsonify({'success': False, 'error': 'New password and confirmation are required'}), 400
    if new_password != confirm_password:
        return jsonify({'success': False, 'error': 'Passwords do not match'}), 400
    pw_error = _validate_password_strength(new_password)
    if pw_error:
        return jsonify({'success': False, 'error': pw_error}), 400

    _ensure_password_reset_otps_table()
    record = PasswordResetOTP.query.filter_by(email=email).first()
    if not record or not record.is_verified:
        return jsonify({
            'success': False,
            'error': 'Please verify the code before resetting your password.',
        }), 403
    if record.is_expired():
        return jsonify({
            'success': False,
            'error': 'Your verification has expired. Please request a new code.',
            'expired': True,
        }), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'success': False, 'error': 'Account not found.'}), 404
    if user.status != 'active':
        return jsonify({'success': False, 'error': 'This account is not active.'}), 403

    user.set_password(new_password)
    user.updated_at = datetime.utcnow()
    db.session.delete(record)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Password updated successfully. You can sign in with your new password.',
    }), 200


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400

    raw = data.get('identifier') if data.get('identifier') is not None else data.get('email')
    user = _find_user_by_login_identifier(raw)
    password = data.get('password', '')
    if isinstance(password, str):
        password = password.strip()

    if not user or not user.check_password(password):
        return jsonify({'error': 'Invalid email/phone or password'}), 401

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
        'user': user.to_dict(),
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
    """Update profile fields for the logged-in user (JWT auth). Login identity is not editable."""
    try:
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        data = request.get_json(silent=True) or {}
        first_name = (data.get('first_name') or '').strip()
        last_name  = (data.get('last_name') or '').strip()
        birthday   = (data.get('birthday') or '').strip()
        gender     = (data.get('gender') or '').strip()

        if first_name or last_name:
            user.full_name = f"{first_name} {last_name}".strip()
        if birthday:
            try:
                user.birthday = datetime.strptime(birthday, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'error': 'Invalid birthday format. Use YYYY-MM-DD.'}), 400
        if gender:
            user.gender = gender

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