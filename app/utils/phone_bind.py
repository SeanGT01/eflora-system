"""Bind or change a customer's delivery phone via SMS OTP."""
from __future__ import annotations

from datetime import datetime

from flask import jsonify

from app.extensions import db
from app.models import CustomerOTP, User
from app.utils.phone_utils import (
    is_synthetic_account_email,
    is_valid_ph_mobile,
    mask_phone,
    normalize_ph_mobile,
    phone_to_account_email,
    tel_href,
)

# Flip to True to require SMS OTP again for profile phone bind.
# Keep send_phone_bind_otp / verify_phone_bind_otp — this only skips the OTP gate.
PHONE_BIND_OTP_REQUIRED = False


def phone_bind_otp_email_key(user_id: int) -> str:
    return f'phonebind.{int(user_id)}@otp.eflora.internal'


def needs_delivery_phone(user) -> bool:
    return not is_valid_ph_mobile(getattr(user, 'phone', None))


def _validate_phone_bind_request(user, phone_raw):
    """Return ``(phone, error_response)``. ``error_response`` is a Flask tuple or None."""
    from app.auth import _phone_taken

    if not user:
        return None, (jsonify({'success': False, 'error': 'User not found'}), 404)

    if is_synthetic_account_email(user.email or ''):
        return None, (jsonify({
            'success': False,
            'error': 'Your login number cannot be changed here. It is tied to your account sign-in.',
        }), 403)

    if not is_valid_ph_mobile(phone_raw):
        return None, (jsonify({
            'success': False,
            'error': 'Enter a valid Philippine mobile number (e.g. 09171234567 or +639171234567).',
        }), 400)

    phone = normalize_ph_mobile(phone_raw)
    current = normalize_ph_mobile(user.phone)
    if current and current == phone:
        return None, (jsonify({
            'success': False,
            'error': 'That is already your saved phone number.',
        }), 400)

    if _phone_taken(
        phone,
        exclude_email=user.email,
        exclude_user_id=user.id,
        roles=('customer',),
    ):
        return None, (jsonify({
            'success': False,
            'error': 'This phone number is already used by another customer account.',
        }), 409)

    return phone, None


def _commit_bound_phone(user, phone):
    """Persist the delivery phone after validation (OTP or skip)."""
    from app.auth import _phone_taken

    if _phone_taken(
        phone,
        exclude_email=user.email,
        exclude_user_id=user.id,
        roles=('customer',),
    ):
        return None, (jsonify({
            'success': False,
            'error': 'This phone number is already used by another customer account.',
        }), 409)

    if is_synthetic_account_email(user.email):
        new_email = phone_to_account_email(phone)
        clash = User.query.filter(User.email == new_email, User.id != user.id).first()
        if clash:
            return None, (jsonify({
                'success': False,
                'error': 'This phone number is already registered to another account.',
            }), 409)
        user.email = new_email

    user.phone = phone
    user.updated_at = datetime.utcnow()
    db.session.commit()

    payload = user.to_dict()
    payload['needs_phone'] = needs_delivery_phone(user)
    return payload, None


def send_phone_bind_otp(user, phone_raw):
    from app.utils.otp_delivery import deliver_otp, sync_hashed_otp_record
    from app.utils.otp_service import (
        DEFAULT_EXPIRY_MINUTES,
        RESEND_COOLDOWN_SECONDS,
        can_resend,
        new_otp_pair,
    )

    phone, err = _validate_phone_bind_request(user, phone_raw)
    if err:
        return err

    if not PHONE_BIND_OTP_REQUIRED:
        payload, err = _commit_bound_phone(user, phone)
        if err:
            return err
        return jsonify({
            'success': True,
            'message': 'Phone number saved.',
            'otp_required': False,
            'user': payload,
            'phone': phone,
            'phone_masked': mask_phone(phone),
        }), 200

    key = phone_bind_otp_email_key(user.id)
    record = CustomerOTP.query.filter_by(email=key).first()
    if record and not record.is_verified:
        allowed, retry_after = can_resend(record.last_sent_at, RESEND_COOLDOWN_SECONDS)
        if not allowed:
            return jsonify({
                'success': False,
                'error': 'Please wait before requesting another code.',
                'retry_after_seconds': retry_after,
            }), 429

    plain_code, otp_hash, expires_at = new_otp_pair(DEFAULT_EXPIRY_MINUTES)
    pending = {
        'purpose': 'phone_bind',
        'user_id': user.id,
        'phone': phone,
        'otp_channel': 'sms',
    }

    if record:
        record.otp_hash = otp_hash
        record.customer_data = pending
        record.expires_at = expires_at
        record.last_sent_at = datetime.utcnow()
        record.attempts = 0
        record.is_verified = False
        record.verified_at = None
    else:
        record = CustomerOTP(
            email=key,
            otp_hash=otp_hash,
            customer_data=pending,
            expires_at=expires_at,
            last_sent_at=datetime.utcnow(),
        )
        db.session.add(record)
    db.session.commit()

    ok, err, meta = deliver_otp(
        'sms',
        otp_code=plain_code,
        phone=phone,
        expiry_minutes=DEFAULT_EXPIRY_MINUTES,
        sms_purpose='verification',
    )
    if not ok:
        return jsonify(err or {'success': False, 'error': 'Could not send SMS OTP.'}), 502

    sync_hashed_otp_record(record, meta, plain_code)
    return jsonify({
        'success': True,
        'message': f'A 6-digit code was sent to {mask_phone(phone)}.',
        'otp_required': True,
        'phone': phone,
        'phone_masked': mask_phone(phone),
        'otp_channel': 'sms',
        'retry_after_seconds': RESEND_COOLDOWN_SECONDS,
    }), 200


def verify_phone_bind_otp(user, otp_code_raw):
    from app.utils.otp_service import MAX_VERIFY_ATTEMPTS, attempts_remaining, verify_otp

    if not PHONE_BIND_OTP_REQUIRED:
        return jsonify({
            'success': False,
            'otp_required': False,
            'error': 'SMS OTP is temporarily disabled. Save the phone number without a code.',
        }), 400

    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    otp_code = (otp_code_raw or '').strip()
    if not otp_code or not otp_code.isdigit() or len(otp_code) != 6:
        return jsonify({'success': False, 'error': 'Enter the 6-digit code sent to your phone.'}), 400

    key = phone_bind_otp_email_key(user.id)
    record = CustomerOTP.query.filter_by(email=key).first()
    if not record:
        return jsonify({
            'success': False,
            'error': 'No verification request found. Please send a new code.',
        }), 404

    pending = record.customer_data or {}
    if pending.get('purpose') != 'phone_bind' or int(pending.get('user_id') or 0) != int(user.id):
        return jsonify({'success': False, 'error': 'Invalid verification request. Please send a new code.'}), 400

    phone = pending.get('phone')
    if not is_valid_ph_mobile(phone):
        return jsonify({'success': False, 'error': 'Invalid pending phone. Please send a new code.'}), 400
    phone = normalize_ph_mobile(phone)

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

    payload, err = _commit_bound_phone(user, phone)
    if err:
        db.session.delete(record)
        db.session.commit()
        return err

    db.session.delete(record)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Phone number verified and saved.',
        'otp_required': True,
        'user': payload,
        'phone': phone,
        'phone_masked': mask_phone(phone),
    }), 200


def attach_order_customer_contact(order_dict, customer):
    from app.utils.phone_utils import customer_account_contact

    contact = customer_account_contact(customer)
    order_dict['customer_phone'] = contact.get('phone')
    order_dict['customer_email'] = contact.get('email')
    order_dict['customer_contact'] = contact.get('value')
    order_dict['customer_contact_label'] = contact.get('label')
    order_dict['customer_tel'] = contact.get('tel')
    return order_dict
