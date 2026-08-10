"""
iProg SMS delivery for OTP codes.

Sends locally generated OTPs via:
  POST https://sms.iprogtech.com/api/v1/sms_messages
Verification stays in-app (hashed OTP rows) — iProg is transport only.
"""

from __future__ import annotations

from flask import current_app

from app.utils.phone_utils import normalize_ph_mobile

SMS_SERVICE_UNAVAILABLE_CODE = 'sms_service_unavailable'
SMS_SERVICE_UNAVAILABLE_MESSAGE = (
    "We couldn't send your verification SMS right now. "
    "This is a temporary system issue on our side — not a problem with your details. "
    "Please try again shortly, switch to email verification if available, "
    "or contact support. Support: support@eflora.ph"
)


def _iprog_config():
    token = (current_app.config.get('IPROG_API_TOKEN') or '').strip()
    base = (current_app.config.get('IPROG_SMS_BASE_URL') or 'https://sms.iprogtech.com/api/v1').rstrip('/')
    return token, base


def send_otp_sms(phone, otp_code, expiry_minutes=5, purpose='verification'):
    """
    Send a 6-digit OTP SMS via iProg.

    Returns True on accepted queue response, False on failure / misconfig.
    Never logs the plaintext OTP or API token.
    """
    try:
        import requests
    except ImportError:
        current_app.logger.error('SMS: requests package not available')
        return False

    token, base = _iprog_config()
    if not token:
        current_app.logger.error('SMS: IPROG_API_TOKEN is not configured')
        return False

    normalized = normalize_ph_mobile(phone)
    if not normalized:
        current_app.logger.error('SMS: invalid phone number')
        return False

    message = (
        f'Your E-Flora {purpose} code is {otp_code}. '
        f'Valid for {expiry_minutes} minutes. Do not share.'
    )

    url = f'{base}/sms_messages'
    payload = {
        'api_token': token,
        'phone_number': normalized,
        'message': message,
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        data = {}
        try:
            data = response.json() if response.content else {}
        except Exception:
            data = {}

        status = data.get('status')
        ok = response.status_code in (200, 201) and (
            status in (200, '200', 'success', True) or
            (isinstance(status, int) and 200 <= status < 300) or
            ('successfully' in str(data.get('message') or '').lower()) or
            bool(data.get('message_id'))
        )

        if ok:
            current_app.logger.info(
                'SMS: OTP queued for %s*** (message_id=%s)',
                normalized[:4],
                data.get('message_id') or 'n/a',
            )
            return True

        current_app.logger.error(
            'SMS: iProg send failed status=%s body=%s',
            response.status_code,
            str(data)[:300] if data else (response.text or '')[:300],
        )
        return False
    except Exception as exc:
        current_app.logger.error('SMS: request error %s: %s', type(exc).__name__, exc)
        return False


def send_sms_message(phone, message):
    """Send a free-form SMS via iProg. Returns True on success."""
    try:
        import requests
    except ImportError:
        current_app.logger.error('SMS: requests package not available')
        return False

    token, base = _iprog_config()
    if not token:
        current_app.logger.error('SMS: IPROG_API_TOKEN is not configured')
        return False

    normalized = normalize_ph_mobile(phone)
    if not normalized:
        current_app.logger.error('SMS: invalid phone number')
        return False

    text = (message or '').strip()
    if not text:
        return False

    url = f'{base}/sms_messages'
    payload = {
        'api_token': token,
        'phone_number': normalized,
        'message': text,
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        data = {}
        try:
            data = response.json() if response.content else {}
        except Exception:
            data = {}

        status = data.get('status')
        ok = response.status_code in (200, 201) and (
            status in (200, '200', 'success', True) or
            (isinstance(status, int) and 200 <= status < 300) or
            ('successfully' in str(data.get('message') or '').lower()) or
            bool(data.get('message_id'))
        )
        if not ok:
            current_app.logger.error(
                'SMS: message send failed status=%s body=%s',
                response.status_code,
                str(data)[:300] if data else (response.text or '')[:300],
            )
        return bool(ok)
    except Exception as exc:
        current_app.logger.error('SMS: request error %s: %s', type(exc).__name__, exc)
        return False


def send_rider_credentials_sms(phone, full_name, default_password, store_name, login_id=None):
    """SMS login credentials after rider OTP verification (phone-only accounts)."""
    login = (login_id or normalize_ph_mobile(phone) or phone or '').strip()
    message = (
        f'E-Flora: Hi {full_name}, your rider account for {store_name} is ready. '
        f'Login: {login} Password: {default_password}. Change password after login.'
    )
    return send_sms_message(phone, message)
