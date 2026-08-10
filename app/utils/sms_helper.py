"""
iProg SMS delivery for OTP codes.

OTP codes use:
  POST {base}/otp/send_otp
so iProg routes via IPROGOTP (works on Smart/TNT + Globe/DITO).

Generic SMS (credentials, etc.) still uses:
  POST {base}/sms_messages
which needs an approved custom sender name for Smart/TNT.
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

SMS_SENDER_NAME_REQUIRED_CODE = 'sms_sender_name_required'
SMS_SENDER_NAME_REQUIRED_MESSAGE = (
    "SMS to this number requires an approved iProg sender name "
    "(Smart/TNT does not accept shared senders). "
    "Apply at https://www.iprogsms.com/sender-names/new, "
    "or invite/verify using email instead."
)


def _iprog_config():
    token = (current_app.config.get('IPROG_API_TOKEN') or '').strip()
    base = (current_app.config.get('IPROG_SMS_BASE_URL') or 'https://sms.iprogtech.com/api/v1').rstrip('/')
    return token, base


def _is_sender_name_error(data) -> bool:
    raw = data.get('message') if isinstance(data, dict) else data
    if isinstance(raw, list):
        text = ' '.join(str(x) for x in raw)
    else:
        text = str(raw or '')
    lower = text.lower()
    return 'sender name' in lower or 'smart/tnt' in lower


def _extract_error_text(data) -> str:
    raw = data.get('message') if isinstance(data, dict) else data
    if isinstance(raw, list):
        return ' '.join(str(x) for x in raw)
    return str(raw or '')


def send_otp_sms(phone, otp_code=None, expiry_minutes=5, purpose='verification'):
    """
    Send a 6-digit OTP via iProg's OTP endpoint (IPROGOTP sender).

    Returns (ok: bool, delivered_otp: str|None, error_code: str|None).
    delivered_otp is the code iProg actually sent (may differ from otp_code).
    Never logs the plaintext OTP or API token.
    """
    try:
        import requests
    except ImportError:
        current_app.logger.error('SMS: requests package not available')
        return False, None, SMS_SERVICE_UNAVAILABLE_CODE

    token, base = _iprog_config()
    if not token:
        current_app.logger.error('SMS: IPROG_API_TOKEN is not configured')
        return False, None, SMS_SERVICE_UNAVAILABLE_CODE

    normalized = normalize_ph_mobile(phone)
    if not normalized:
        current_app.logger.error('SMS: invalid phone number')
        return False, None, SMS_SERVICE_UNAVAILABLE_CODE

    # :otp is replaced by iProg; this uses the IPROGOTP sender (all networks).
    message = (
        f'Your E-Flora {purpose} code is :otp. '
        f'Valid for {expiry_minutes} minutes. Do not share.'
    )

    url = f'{base}/otp/send_otp'
    payload = {
        'api_token': token,
        'phone_number': normalized,
        'message': message,
        'expires_in_minutes': int(expiry_minutes) if expiry_minutes else 5,
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
            ('success' in str(data.get('message') or '').lower())
        )

        if ok:
            delivered = None
            nested = data.get('data') if isinstance(data.get('data'), dict) else {}
            delivered = (
                (nested.get('otp_code') if nested else None)
                or data.get('otp_code')
                or otp_code
            )
            if delivered is not None:
                delivered = str(delivered).strip()
            current_app.logger.info(
                'SMS: OTP queued via /otp/send_otp for %s***',
                normalized[:4],
            )
            return True, delivered, None

        if _is_sender_name_error(data):
            current_app.logger.error(
                'SMS: sender name blocked status=%s body=%s',
                response.status_code,
                str(data)[:300],
            )
            return False, None, SMS_SENDER_NAME_REQUIRED_CODE

        current_app.logger.error(
            'SMS: iProg OTP send failed status=%s body=%s',
            response.status_code,
            str(data)[:300] if data else (response.text or '')[:300],
        )
        return False, None, SMS_SERVICE_UNAVAILABLE_CODE
    except Exception as exc:
        current_app.logger.error('SMS: request error %s: %s', type(exc).__name__, exc)
        return False, None, SMS_SERVICE_UNAVAILABLE_CODE


def send_sms_message(phone, message):
    """
    Send a free-form SMS via iProg sms_messages.
    Returns (ok: bool, error_code: str|None).
    """
    try:
        import requests
    except ImportError:
        current_app.logger.error('SMS: requests package not available')
        return False, SMS_SERVICE_UNAVAILABLE_CODE

    token, base = _iprog_config()
    if not token:
        current_app.logger.error('SMS: IPROG_API_TOKEN is not configured')
        return False, SMS_SERVICE_UNAVAILABLE_CODE

    normalized = normalize_ph_mobile(phone)
    if not normalized:
        current_app.logger.error('SMS: invalid phone number')
        return False, SMS_SERVICE_UNAVAILABLE_CODE

    text = (message or '').strip()
    if not text:
        return False, SMS_SERVICE_UNAVAILABLE_CODE

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
        if ok:
            return True, None

        if _is_sender_name_error(data):
            current_app.logger.error(
                'SMS: sender name blocked status=%s body=%s',
                response.status_code,
                _extract_error_text(data)[:300],
            )
            return False, SMS_SENDER_NAME_REQUIRED_CODE

        current_app.logger.error(
            'SMS: message send failed status=%s body=%s',
            response.status_code,
            str(data)[:300] if data else (response.text or '')[:300],
        )
        return False, SMS_SERVICE_UNAVAILABLE_CODE
    except Exception as exc:
        current_app.logger.error('SMS: request error %s: %s', type(exc).__name__, exc)
        return False, SMS_SERVICE_UNAVAILABLE_CODE


def send_rider_credentials_sms(phone, full_name, default_password, store_name, login_id=None):
    """SMS login credentials after rider OTP verification (phone-only accounts)."""
    login = (login_id or normalize_ph_mobile(phone) or phone or '').strip()
    message = (
        f'E-Flora: Hi {full_name}, your rider account for {store_name} is ready. '
        f'Login: {login} Password: {default_password}. Change password after login.'
    )
    ok, _err = send_sms_message(phone, message)
    return ok
