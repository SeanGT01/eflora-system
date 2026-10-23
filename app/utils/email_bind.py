"""
Helpers for verifying and binding a Gmail address to a phone-registered seller account.
Allows phone-only sellers to receive stock alerts, order notifications, and login via email.
"""

from __future__ import annotations

import re
from datetime import datetime
from flask import jsonify
from sqlalchemy import func

from app.extensions import db
from app.models import CustomerOTP, SellerApplication, User
from app.utils.email_helper import send_email_bind_otp_email
from app.utils.otp_service import (
    DEFAULT_EXPIRY_MINUTES,
    MAX_VERIFY_ATTEMPTS,
    RESEND_COOLDOWN_SECONDS,
    attempts_remaining,
    can_resend,
    new_otp_pair,
    verify_otp,
)
from app.utils.phone_utils import is_synthetic_account_email

EMAIL_REGEX = re.compile(
    r'^[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$'
)


def email_bind_otp_key(user_id: int) -> str:
    """Internal key stored in CustomerOTP table for email binding requests."""
    return f'emailbind.{int(user_id)}@otp.eflora.internal'


def _validate_target_email(target_email_raw: str, current_user_id: int):
    """Validate email format and check for duplicates across existing users."""
    if not target_email_raw or not str(target_email_raw).strip():
        return None, (jsonify({'success': False, 'error': 'Please enter a valid email address.'}), 400)

    clean_email = str(target_email_raw).strip().lower()

    if len(clean_email) > 254 or '..' in clean_email or clean_email.endswith('.'):
        return None, (jsonify({'success': False, 'error': 'Please enter a valid email address format (e.g. name@gmail.com).'}), 400)

    if not EMAIL_REGEX.match(clean_email):
        return None, (jsonify({'success': False, 'error': 'Please enter a valid email address format (e.g. name@gmail.com).'}), 400)

    parts = clean_email.split('@')
    if len(parts) != 2:
        return None, (jsonify({'success': False, 'error': 'Please enter a valid email address format (e.g. name@gmail.com).'}), 400)

    local_part, domain_part = parts
    if len(local_part) > 64:
        return None, (jsonify({'success': False, 'error': 'Email username is too long.'}), 400)

    domain_parts = domain_part.split('.')
    tld = domain_parts[-1]
    if len(tld) < 2 or not tld.isalpha():
        return None, (jsonify({'success': False, 'error': 'Please enter a valid email domain (e.g. name@gmail.com).'}), 400)

    if is_synthetic_account_email(clean_email) or clean_email.endswith('@eflora.internal') or 'otp.eflora.internal' in clean_email:
        return None, (jsonify({'success': False, 'error': 'Invalid email address. Please use a real email like Gmail.'}), 400)

    # Check if this email is already registered to another account
    existing = User.query.filter(
        func.lower(User.email) == clean_email,
        User.id != current_user_id,
    ).first()

    if existing:
        return None, (jsonify({'success': False, 'error': 'This email address is already connected to another E-Flora account.'}), 409)

    return clean_email, None


def send_email_bind_otp(user, target_email_raw: str, store=None):
    """
    Generate and send a 6-digit OTP code to the requested email via Gmail OAuth.
    Includes rate limiting / cooldown protection.
    """
    if isinstance(user, int):
        user = User.query.get(user)
    if not user:
        return jsonify({'success': False, 'error': 'User not found. Please log in again.'}), 401

    clean_email, err = _validate_target_email(target_email_raw, user.id)
    if err:
        return err

    # Check if user already has this exact email bound
    if (user.email or '').strip().lower() == clean_email:
        return jsonify({
            'success': False,
            'error': 'This email address is already connected to your account.',
        }), 400

    key = email_bind_otp_key(user.id)
    record = CustomerOTP.query.filter_by(email=key).first()

    if record and not record.is_verified:
        allowed, retry_after = can_resend(record.last_sent_at, RESEND_COOLDOWN_SECONDS)
        if not allowed:
            return jsonify({
                'success': False,
                'error': f'Please wait {retry_after} seconds before requesting another verification code.',
                'retry_after_seconds': retry_after,
            }), 429

    plain_code, otp_hash, expires_at = new_otp_pair(DEFAULT_EXPIRY_MINUTES)
    pending_payload = {
        'purpose': 'email_bind',
        'user_id': user.id,
        'target_email': clean_email,
    }

    if record:
        record.otp_hash = otp_hash
        record.customer_data = pending_payload
        record.expires_at = expires_at
        record.last_sent_at = datetime.utcnow()
        record.attempts = 0
        record.is_verified = False
        record.verified_at = None
    else:
        record = CustomerOTP(
            email=key,
            otp_hash=otp_hash,
            customer_data=pending_payload,
            expires_at=expires_at,
            last_sent_at=datetime.utcnow(),
        )
        db.session.add(record)
    db.session.commit()

    # Send OTP code via Gmail OAuth service
    store_name = store.name if store else getattr(user, 'store_name', None)
    ok = send_email_bind_otp_email(
        recipient_email=clean_email,
        otp_code=plain_code,
        full_name=user.full_name,
        store_name=store_name,
        expiry_minutes=DEFAULT_EXPIRY_MINUTES,
    )

    if not ok:
        return jsonify({
            'success': False,
            'error': 'Unable to send verification email. Please check that the email is spelled correctly and try again.',
        }), 502

    return jsonify({
        'success': True,
        'message': f'Verification code sent to {clean_email}. Please check your inbox.',
        'target_email': clean_email,
        'retry_after_seconds': RESEND_COOLDOWN_SECONDS,
    }), 200


def verify_email_bind_otp(user, target_email_raw: str, otp_code_raw: str):
    """
    Verify the 6-digit OTP code and permanently bind the email address to the user account.
    """
    if isinstance(user, int):
        user = User.query.get(user)
    if not user:
        return jsonify({'success': False, 'error': 'User not found. Please log in again.'}), 401

    clean_email, err = _validate_target_email(target_email_raw, user.id)
    if err:
        return err

    otp_code = (otp_code_raw or '').strip()
    if not otp_code or not otp_code.isdigit() or len(otp_code) != 6:
        return jsonify({'success': False, 'error': 'Please enter the 6-digit verification code.'}), 400

    key = email_bind_otp_key(user.id)
    record = CustomerOTP.query.filter_by(email=key).first()

    if not record:
        return jsonify({
            'success': False,
            'error': 'No verification code request found. Please request a new code.',
        }), 404

    pending = record.customer_data or {}
    if pending.get('purpose') != 'email_bind' or int(pending.get('user_id') or 0) != int(user.id):
        return jsonify({
            'success': False,
            'error': 'Invalid verification request. Please request a new code.',
        }), 400

    expected_email = (pending.get('target_email') or '').strip().lower()
    if clean_email != expected_email:
        return jsonify({
            'success': False,
            'error': 'The email being verified does not match the requested address. Please request a new code.',
        }), 400

    if record.is_expired():
        return jsonify({
            'success': False,
            'error': 'Verification code has expired. Please request a new code.',
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
        remaining = attempts_remaining(record.attempts, MAX_VERIFY_ATTEMPTS)
        if remaining > 0:
            return jsonify({
                'success': False,
                'error': f'Incorrect code. {remaining} attempt{"s" if remaining != 1 else ""} remaining.',
                'attempts_remaining': remaining,
            }), 400
        return jsonify({
            'success': False,
            'error': 'Too many incorrect attempts. Please request a new code.',
            'locked': True,
        }), 429

    # Double check email uniqueness right before binding (prevent race conditions)
    clash = User.query.filter(
        func.lower(User.email) == clean_email,
        User.id != user.id,
    ).first()
    if clash:
        return jsonify({
            'success': False,
            'error': 'This email address was recently registered to another account.',
        }), 409

    # Mark OTP verified
    record.is_verified = True
    record.verified_at = datetime.utcnow()

    # Update User email
    old_email = user.email
    user.email = clean_email
    user.updated_at = datetime.utcnow()

    # Also update any seller applications for this user
    for app_row in SellerApplication.query.filter_by(user_id=user.id).all():
        app_row.applicant_email = clean_email

    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Success! Your Gmail address ({clean_email}) is now connected. Stock alerts will be sent here.',
        'email': clean_email,
        'previous_email': old_email,
    }), 200
