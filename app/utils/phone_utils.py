"""Philippine mobile helpers shared by OTP / SMS flows."""

from __future__ import annotations

import re

PH_MOBILE_REGEX = re.compile(r'^(?:\+63|0)9\d{9}$')

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
    if is_synthetic_account_email(email or '') and phone:
        return normalize_ph_mobile(phone) or phone
    return (email or phone or '').strip()


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
