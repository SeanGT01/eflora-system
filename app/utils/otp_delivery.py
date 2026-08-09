"""
Dispatch OTP delivery to Gmail or iProg SMS based on otp_channel.
"""

from __future__ import annotations

from app.utils.phone_utils import mask_email, mask_phone
from app.utils.sms_helper import (
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
        meta includes destination_masked and otp_channel.
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

    # SMS
    if not phone:
        return False, {
            'success': False,
            'error': 'A valid Philippine mobile number is required for SMS verification.',
        }, {}
    sent = send_otp_sms(
        phone=phone,
        otp_code=otp_code,
        expiry_minutes=expiry_minutes,
        purpose=sms_purpose,
    )
    if not sent:
        return False, {
            'success': False,
            'error': SMS_SERVICE_UNAVAILABLE_MESSAGE,
            'error_code': SMS_SERVICE_UNAVAILABLE_CODE,
        }, {'otp_channel': 'sms', 'destination_masked': mask_phone(phone)}
    return True, None, {
        'otp_channel': 'sms',
        'destination_masked': mask_phone(phone),
    }
