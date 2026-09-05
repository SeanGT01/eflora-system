"""
SMS delivery for OTP codes and credential texts.

OTP generation and verification stay in this app. Providers only send the
code we already created.

Order: sms8.io (Android SIM gateway) first, then iProg as backup.
Do not use SMS8's /ajax/otp-send.php — that would store OTPs on their side.
"""

from __future__ import annotations

from flask import current_app

from app.utils.phone_utils import normalize_ph_mobile

SMS_SERVICE_UNAVAILABLE_CODE = 'sms_service_unavailable'
SMS_SERVICE_UNAVAILABLE_MESSAGE = (
    "We couldn't send your verification SMS right now. "
    "This is a temporary system issue on our side — not a problem with your details. "
    "Please try again shortly, switch to email verification if available, "
    "or contact support. Support: efloralaguna@gmail.com"
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


def _sms8_config():
    key = (current_app.config.get('SMS8_API_KEY') or '').strip()
    base = (current_app.config.get('SMS8_BASE_URL') or 'https://app.sms8.io/services').rstrip('/')
    return key, base


def _iprog_phone_number(phone_raw):
    """Return (09XXXXXXXXX, 63XXXXXXXXXX) for iProg."""
    normalized = normalize_ph_mobile(phone_raw)
    if not normalized:
        return None, None
    if normalized.startswith('0') and len(normalized) == 11:
        return normalized, '63' + normalized[1:]
    return normalized, normalized


def _e164_ph(phone_raw):
    _local, msisdn_63 = _iprog_phone_number(phone_raw)
    if not msisdn_63:
        return None
    if str(msisdn_63).startswith('+'):
        return str(msisdn_63)
    return f'+{msisdn_63}'


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


def _otp_sms_body(otp_code, expiry_minutes, purpose='verification'):
    minutes = int(expiry_minutes) if expiry_minutes else 5
    code = str(otp_code).strip()
    if purpose == 'password_reset':
        return (
            f'E-FLORA: Your password reset code is {code}. '
            f'It expires in {minutes} minutes. Do not share this code.'
        )
    return (
        f'E-FLORA: Your verification code is {code}. '
        f'It expires in {minutes} minutes. Do not share this code.'
    )


def _sms8_send(phone_raw, message):
    """Send free-form SMS via sms8.io. Returns (ok, error_code)."""
    try:
        import requests
    except ImportError:
        current_app.logger.error('SMS: requests package not available')
        return False, SMS_SERVICE_UNAVAILABLE_CODE

    key, base = _sms8_config()
    if not key:
        return False, None

    e164 = _e164_ph(phone_raw)
    if not e164:
        current_app.logger.error('SMS: invalid phone number')
        return False, SMS_SERVICE_UNAVAILABLE_CODE

    text = (message or '').strip()
    if not text:
        return False, SMS_SERVICE_UNAVAILABLE_CODE

    url = f'{base}/send.php'
    try:
        response = requests.post(
            url,
            data={'key': key, 'number': e164, 'message': text},
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=15,
        )
        data = {}
        try:
            data = response.json() if response.content else {}
        except Exception:
            data = {}

        ok = response.status_code in (200, 201) and (
            data.get('success') is True
            or (
                isinstance(data, dict)
                and data.get('success') is not False
                and bool(data.get('data'))
            )
        )
        if ok:
            current_app.logger.info('SMS: queued via sms8 for %s***', e164[:6])
            return True, None

        current_app.logger.warning(
            'SMS: sms8 send failed status=%s body=%s',
            response.status_code,
            str(data)[:300] if data else (response.text or '')[:300],
        )
        return False, SMS_SERVICE_UNAVAILABLE_CODE
    except Exception as exc:
        current_app.logger.warning('SMS: sms8 request error %s: %s', type(exc).__name__, exc)
        return False, SMS_SERVICE_UNAVAILABLE_CODE


def _iprog_send_otp(phone_raw, otp_code=None, expiry_minutes=5):
    """Send OTP via iProg /otp/send_otp. May return a provider-generated code."""
    try:
        import requests
    except ImportError:
        current_app.logger.error('SMS: requests package not available')
        return False, None, SMS_SERVICE_UNAVAILABLE_CODE

    token, base = _iprog_config()
    if not token:
        current_app.logger.error('SMS: IPROG_API_TOKEN is not configured')
        return False, None, SMS_SERVICE_UNAVAILABLE_CODE

    local_09, msisdn_63 = _iprog_phone_number(phone_raw)
    if not local_09:
        current_app.logger.error('SMS: invalid phone number')
        return False, None, SMS_SERVICE_UNAVAILABLE_CODE

    # Omit custom `message`. Custom copy can leave the IPROGOTP sender and
    # Smart/TNT never delivers, while the dashboard still shows the OTP.
    url = f'{base}/otp/send_otp'
    payload = {
        'api_token': token,
        'phone_number': msisdn_63,
        'expires_in_minutes': int(expiry_minutes) if expiry_minutes else 5,
        'sms_provider': 2,
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
            nested = data.get('data') if isinstance(data.get('data'), dict) else {}
            delivered = (
                (nested.get('otp_code') if nested else None)
                or data.get('otp_code')
                or otp_code
            )
            if delivered is not None:
                delivered = str(delivered).strip()
            current_app.logger.info(
                'SMS: OTP queued via iProg /otp/send_otp for %s***',
                local_09[:4],
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


def send_otp_sms(phone, otp_code=None, expiry_minutes=5, purpose='verification'):
    """
    Send the app-generated OTP. sms8.io first, iProg backup.

    Returns (ok: bool, delivered_otp: str|None, error_code: str|None).
    delivered_otp is the code the user must enter (ours, unless iProg
    generated a different one). Never logs the plaintext OTP or API keys.
    """
    local_09, _msisdn = _iprog_phone_number(phone)
    if not local_09:
        current_app.logger.error('SMS: invalid phone number')
        return False, None, SMS_SERVICE_UNAVAILABLE_CODE

    code = str(otp_code).strip() if otp_code else ''
    use_sms8 = True
    use_iprog = True
    try:
        from app.utils.feature_controls import iprog_enabled, sms8_enabled
        use_sms8 = sms8_enabled()
        use_iprog = iprog_enabled()
    except Exception:
        pass

    if not use_sms8 and not use_iprog:
        current_app.logger.error('SMS: both sms8 and iProg are disabled in Admin Controls')
        return False, None, SMS_SERVICE_UNAVAILABLE_CODE

    sms8_key, _base = _sms8_config()
    if use_sms8 and sms8_key and code:
        ok, err = _sms8_send(phone, _otp_sms_body(code, expiry_minutes, purpose))
        if ok:
            return True, code, None
        if use_iprog:
            current_app.logger.warning('SMS: sms8 failed, trying iProg backup')
        else:
            return False, None, err or SMS_SERVICE_UNAVAILABLE_CODE
    elif use_sms8 and not sms8_key:
        current_app.logger.info('SMS: SMS8_API_KEY not set')
        if not use_iprog:
            return False, None, SMS_SERVICE_UNAVAILABLE_CODE
    elif not use_sms8:
        current_app.logger.info('SMS: sms8 disabled in Admin Controls')
    elif not code:
        current_app.logger.warning('SMS: no app OTP code, skipping sms8')

    if use_iprog:
        return _iprog_send_otp(phone, otp_code=otp_code, expiry_minutes=expiry_minutes)

    return False, None, SMS_SERVICE_UNAVAILABLE_CODE


def send_sms_message(phone, message):
    """
    Send a free-form SMS. sms8.io first when enabled, then iProg if enabled.
    Returns (ok: bool, error_code: str|None).
    """
    use_sms8 = True
    use_iprog = True
    try:
        from app.utils.feature_controls import iprog_enabled, sms8_enabled
        use_sms8 = sms8_enabled()
        use_iprog = iprog_enabled()
    except Exception:
        pass

    if not use_sms8 and not use_iprog:
        current_app.logger.error('SMS: both sms8 and iProg are disabled in Admin Controls')
        return False, SMS_SERVICE_UNAVAILABLE_CODE

    sms8_key, _base = _sms8_config()
    if use_sms8 and sms8_key:
        ok, err = _sms8_send(phone, message)
        if ok:
            return True, None
        if use_iprog:
            current_app.logger.warning('SMS: sms8 failed, trying iProg backup')
        else:
            return False, err or SMS_SERVICE_UNAVAILABLE_CODE
    elif use_sms8 and not sms8_key:
        current_app.logger.info('SMS: SMS8_API_KEY not set')
        if not use_iprog:
            return False, SMS_SERVICE_UNAVAILABLE_CODE

    if not use_iprog:
        return False, SMS_SERVICE_UNAVAILABLE_CODE

    try:
        import requests
    except ImportError:
        current_app.logger.error('SMS: requests package not available')
        return False, SMS_SERVICE_UNAVAILABLE_CODE

    token, base = _iprog_config()
    if not token:
        current_app.logger.error('SMS: IPROG_API_TOKEN is not configured')
        return False, SMS_SERVICE_UNAVAILABLE_CODE

    local_09, msisdn_63 = _iprog_phone_number(phone)
    if not local_09:
        current_app.logger.error('SMS: invalid phone number')
        return False, SMS_SERVICE_UNAVAILABLE_CODE

    text = (message or '').strip()
    if not text:
        return False, SMS_SERVICE_UNAVAILABLE_CODE

    url = f'{base}/sms_messages'
    payload = {
        'api_token': token,
        'phone_number': msisdn_63,
        'message': text,
        'sms_provider': 2,
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


def send_store_admin_credentials_sms(phone, full_name, default_password, store_name, login_id=None):
    login = (login_id or normalize_ph_mobile(phone) or phone or '').strip()
    message = (
        f'E-Flora: Hi {full_name}, your store admin account for {store_name} is ready. '
        f'Login: {login} Password: {default_password}. Change password after login.'
    )
    ok, _err = send_sms_message(phone, message)
    return ok
