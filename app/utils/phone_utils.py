"""Philippine mobile helpers shared by OTP / SMS flows."""

from __future__ import annotations

import re

PH_MOBILE_REGEX = re.compile(r'^(?:\+63|0)9\d{9}$')
EMAIL_REGEX = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')

# Phone-only accounts still need a unique users.email (NOT NULL).
# Store a non-deliverable placeholder; login/OTP use the real phone.
SYNTHETIC_EMAIL_DOMAIN = 'sms.eflora.internal'


def normalize_ph_mobile(phone_raw):
    """Normalize PH mobile to 09XXXXXXXXX. Returns None for blank input."""
    phone = (phone_raw or '').strip()
    if not phone:
        return None

    compact = re.sub(r'[\s\-()]', '', phone)
    if compact.startswith('+63'):
        compact = '0' + compact[3:]
    elif compact.startswith('63') and len(compact) == 12:
        compact = '0' + compact[2:]

    return compact


def is_valid_ph_mobile(phone_raw) -> bool:
    normalized = normalize_ph_mobile(phone_raw)
    if not normalized:
        return False
    return bool(re.fullmatch(r'09\d{9}', normalized))


def phone_to_account_email(phone_09: str) -> str:
    """Map a normalized 09… mobile to the internal account email key."""
    phone = normalize_ph_mobile(phone_09) or (phone_09 or '').strip()
    return f'{phone}@{SYNTHETIC_EMAIL_DOMAIN}'


def is_synthetic_account_email(email: str) -> bool:
    email = (email or '').strip().lower()
    return email.endswith('@' + SYNTHETIC_EMAIL_DOMAIN)


def display_login_id(email: str = None, phone: str = None) -> str:
    """Value shown/prefilled for login (phone for phone-only accounts)."""
    email = (email or '').strip()
    phone_norm = normalize_ph_mobile(phone) or ((phone or '').strip() or None)
    if is_synthetic_account_email(email):
        if phone_norm:
            return phone_norm
        local = email.split('@', 1)[0]
        if is_valid_ph_mobile(local):
            return normalize_ph_mobile(local) or local
    return email or phone_norm or ''


def tel_href(phone_raw):
    """Return a tel: URI for a PH mobile, or None."""
    n = normalize_ph_mobile(phone_raw)
    if not n or not n.startswith('0') or len(n) != 11:
        return None
    return 'tel:+63' + n[1:]


def customer_account_contact(customer) -> dict:
    """
    Preferred delivery contact: verified User.phone when present,
    otherwise the signup email (never the synthetic SMS email).
    """
    empty = {
        'value': None,
        'label': 'Contact',
        'is_phone': False,
        'phone': None,
        'email': None,
        'tel': None,
    }
    if not customer:
        return empty

    email = getattr(customer, 'email', None)
    phone = normalize_ph_mobile(getattr(customer, 'phone', None))
    show_email = None if is_synthetic_account_email(email or '') else (email or None)
    if phone:
        return {
            'value': phone,
            'label': 'Phone',
            'is_phone': True,
            'phone': phone,
            'email': show_email,
            'tel': tel_href(phone),
        }
    return {
        'value': show_email,
        'label': 'Email',
        'is_phone': False,
        'phone': None,
        'email': show_email,
        'tel': None,
    }


def phone_lookup_variants(normalized_09: str):
    """Common stored formats for a normalized 09XXXXXXXXX number."""
    if not normalized_09 or not normalized_09.startswith('0'):
        return [normalized_09] if normalized_09 else []
    rest = normalized_09[1:]
    return list({
        normalized_09,
        '+63' + rest,
        '63' + rest,
        '0' + rest,
    })


def mask_phone(phone: str) -> str:
    """Mask for UI: 0917***4567."""
    n = normalize_ph_mobile(phone) or (phone or '').strip()
    if len(n) < 7:
        return '***'
    return f'{n[:4]}***{n[-4:]}'


def mask_email(email: str) -> str:
    email = (email or '').strip()
    if is_synthetic_account_email(email):
        local, _, _ = email.partition('@')
        return mask_phone(local)
    if '@' not in email:
        return email
    local, _, domain = email.partition('@')
    if len(local) <= 2:
        masked_local = local[:1] + '***'
    else:
        masked_local = local[:2] + '***'
    return f'{masked_local}@{domain}'


def parse_email_or_phone_identifier(raw):
    """
    Resolve one contact field to account email + optional phone + OTP channel.

    Returns (result, error_message). On success, result has:
      email, phone (or None), otp_channel ('email'|'sms'), login_id
    """
    raw_id = (raw or '').strip()
    if not raw_id:
        return None, 'Enter an email address or Philippine mobile number.'

    if '@' in raw_id:
        email = raw_id.lower()
        if is_synthetic_account_email(email) or not EMAIL_REGEX.match(email):
            return None, 'Enter a valid email address.'
        return {
            'email': email,
            'phone': None,
            'otp_channel': 'email',
            'login_id': email,
        }, None

    if not is_valid_ph_mobile(raw_id):
        return None, (
            'Enter a valid email or Philippine mobile number '
            '(e.g. 09171234567 or +639171234567).'
        )

    phone = normalize_ph_mobile(raw_id)
    return {
        'email': phone_to_account_email(phone),
        'phone': phone,
        'otp_channel': 'sms',
        'login_id': phone,
    }, None
