"""
Dispatch OTP delivery to Gmail or iProg SMS based on otp_channel.
"""

from __future__ import annotations

from app.utils.phone_utils import mask_email, mask_phone
from app.utils.sms_helper import (
    SMS_SENDER_NAME_REQUIRED_CODE,
    SMS_SENDER_NAME_REQUIRED_MESSAGE,
    SMS_SERVICE_UNAVAILABLE_CODE,
    SMS_SERVICE_UNAVAILABLE_MESSAGE,
    send_otp_sms,
)


VALID_OTP_CHANNELS = frozenset({'email', 'sms'})


def normalize_otp_channel(value, default='email'):
    channel = (value or default or 'email').strip().lower()
    if channel in ('mail', 'gmail'):
        channel = 'email'
    if channel in ('text', 'phone', 'mobile'):
        channel = 'sms'
    return channel if channel in VALID_OTP_CHANNELS else None


def sync_hashed_otp_record(record, meta, plain_code):
    """
    If iProg generated a different OTP than plain_code, re-hash and persist.
    No-op for email deliveries (no delivered_otp in meta).
    """
    delivered = (meta or {}).get('delivered_otp')
    if not delivered or not record or delivered == plain_code:
        return plain_code

    from app.extensions import db
    from app.utils.otp_service import hash_otp

    record.otp_hash = hash_otp(delivered)
    db.session.commit()
    return delivered


def sync_plain_otp_record(record, meta, plain_code, attr='verification_token'):
    """If iProg generated a different OTP, update a plaintext token column."""
    delivered = (meta or {}).get('delivered_otp')
    if not delivered or not record or delivered == plain_code:
        return plain_code

    from app.extensions import db

    setattr(record, attr, delivered)
    db.session.commit()
    return delivered


def deliver_otp(
    channel,
    *,
    otp_code,
    email=None,
    phone=None,
    email_sender_fn=None,
    email_sender_kwargs=None,
    expiry_minutes=5,
    sms_purpose='verification',
):
    """
    Send OTP via email or SMS.

    Returns:
        (ok: bool, error_payload: dict|None, meta: dict)
        meta includes destination_masked, otp_channel, and optionally
        delivered_otp (when SMS provider generates the code).
    """
    channel = normalize_otp_channel(channel)
    if not channel:
        return False, {
            'success': False,
            'error': 'otp_channel must be "email" or "sms".',
        }, {}

    if channel == 'email':
        if not email or not callable(email_sender_fn):
            return False, {
                'success': False,
                'error': 'Email delivery is not available for this request.',
            }, {}
        kwargs = dict(email_sender_kwargs or {})
        sent = email_sender_fn(
            recipient_email=email,
            otp_code=otp_code,
            **kwargs,
        )
        if not sent:
            from app.utils.email_helper import (
                EMAIL_SERVICE_UNAVAILABLE_CODE,
                EMAIL_SERVICE_UNAVAILABLE_MESSAGE,
            )
            return False, {
                'success': False,
                'error': EMAIL_SERVICE_UNAVAILABLE_MESSAGE,
                'error_code': EMAIL_SERVICE_UNAVAILABLE_CODE,
            }, {'otp_channel': 'email', 'destination_masked': mask_email(email)}
        return True, None, {
            'otp_channel': 'email',
            'destination_masked': mask_email(email),
        }

    # SMS — use iProg OTP API (IPROGOTP) so Smart/TNT works
    if not phone:
        return False, {
            'success': False,
            'error': 'A valid Philippine mobile number is required for SMS verification.',
        }, {}
    sent, delivered_otp, err_code = send_otp_sms(
        phone=phone,
        otp_code=otp_code,
        expiry_minutes=expiry_minutes,
        purpose=sms_purpose,
    )
    dest = mask_phone(phone)
    if not sent:
        if err_code == SMS_SENDER_NAME_REQUIRED_CODE:
            return False, {
                'success': False,
                'error': SMS_SENDER_NAME_REQUIRED_MESSAGE,
                'error_code': SMS_SENDER_NAME_REQUIRED_CODE,
            }, {'otp_channel': 'sms', 'destination_masked': dest}
        return False, {
            'success': False,
            'error': SMS_SERVICE_UNAVAILABLE_MESSAGE,
            'error_code': SMS_SERVICE_UNAVAILABLE_CODE,
        }, {'otp_channel': 'sms', 'destination_masked': dest}

    meta = {
        'otp_channel': 'sms',
        'destination_masked': dest,
    }
    if delivered_otp:
        meta['delivered_otp'] = str(delivered_otp).strip()
    return True, None, meta
