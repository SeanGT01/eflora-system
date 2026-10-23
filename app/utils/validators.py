"""Shared profile/input validation helpers."""
from datetime import date, datetime
import re


def parse_and_validate_birthday(birthday_str, min_age=13, max_age=120):
    """
    Parse YYYY-MM-DD birthday and enforce not-future + min/max age.
    Returns (date|None, error|None). Empty/None -> (None, None).
    """
    raw = (birthday_str or '').strip()
    if not raw:
        return None, None
    try:
        bday = datetime.strptime(raw, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None, 'Invalid birthday format. Use YYYY-MM-DD.'

    today = date.today()
    if bday > today:
        return None, 'Birthday cannot be in the future.'

    age = today.year - bday.year - (
        1 if (today.month, today.day) < (bday.month, bday.day) else 0
    )
    if age < min_age:
        return None, f'You must be at least {min_age} years old.'
    if age > max_age:
        return None, 'Please enter a valid birthday.'
    return bday, None


# Typical Filipino names: a few given names + a compound surname.
# Whole name stays well under the VARCHAR(100) column.
FIRST_NAME_MAX = 50
LAST_NAME_MAX = 30
FULL_NAME_MAX = FIRST_NAME_MAX + 1 + LAST_NAME_MAX  # 81: first + space + last
_NAME_TOKEN = r"[A-Za-zÀ-ÖØ-öø-ÿÑñ]+"
_PERSON_NAME_RE = re.compile(
    rf'^{_NAME_TOKEN}(?:[ \'\-]{_NAME_TOKEN})*$'
)


def _clean_name_whitespace(raw):
    return re.sub(r'\s+', ' ', (raw or '').strip())


def normalize_person_name(raw, *, field='Name', max_len=FIRST_NAME_MAX, required=True):
    """Validate a first or last name. Returns (cleaned|None, error|None)."""
    text = _clean_name_whitespace(raw)
    if not text:
        return (None, f'{field} is required.') if required else ('', None)
    if len(text) < 2:
        return None, f'{field} must be at least 2 letters.'
    if len(text) > max_len:
        return None, f'{field} must be at most {max_len} characters.'
    if not _PERSON_NAME_RE.match(text):
        return None, f'{field} can only contain letters, spaces, hyphens, and apostrophes.'
    return text, None


def compose_full_name(first_name, last_name):
    """Build User.full_name from first + last."""
    first, err = normalize_person_name(first_name, field='First name', max_len=FIRST_NAME_MAX)
    if err:
        return None, err
    last, err = normalize_person_name(last_name, field='Last name', max_len=LAST_NAME_MAX)
    if err:
        return None, err
    full = f'{first} {last}'
    if len(full) > FULL_NAME_MAX:
        return None, f'Full name must be at most {FULL_NAME_MAX} characters.'
    return full, None


def normalize_full_name(raw):
    """Validate a single full-name field (registration) as first + last."""
    text = _clean_name_whitespace(raw)
    if not text:
        return None, 'Full name is required.'
    if ' ' not in text:
        return None, 'Enter your first and last name.'
    first, last = text.rsplit(' ', 1)
    return compose_full_name(first, last)


# LTO private plates: ABC 1234 / ABC 123 (3 letters + 3–4 digits)
# Motorcycle plates: AB 12345 / AB 1234 (2 letters + 4–5 digits)
_PH_PLATE = re.compile(
    r'^(?:([A-Z]{3})[\s-]?(\d{3,4})|([A-Z]{2})[\s-]?(\d{4,5}))$',
    re.IGNORECASE,
)

PH_PLATE_ERROR = (
    'Enter a Philippine plate number (e.g. ABC 1234, ABC 123, or AB 12345).'
)


def normalize_ph_license_plate(raw):
    """
    Validate and normalize a PH plate. Empty is allowed.
    Returns (normalized|None, error|None). Normalized uses a space: ABC 1234.
    """
    text = (raw or '').strip().upper()
    if not text:
        return '', None
    match = _PH_PLATE.match(text)
    if not match:
        return None, PH_PLATE_ERROR
    if match.group(1):
        return f'{match.group(1)} {match.group(2)}', None
    return f'{match.group(3)} {match.group(4)}', None


EMAIL_REGEX = re.compile(
    r'^[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$'
)

VALID_EMAIL_TLDS = {
    'com', 'org', 'net', 'edu', 'gov', 'mil', 'int',
    'info', 'biz', 'name', 'pro', 'coop', 'aero', 'museum',
    'app', 'dev', 'io', 'ai', 'me', 'co', 'store', 'online', 'shop',
    'site', 'tech', 'cloud', 'xyz', 'top', 'club', 'live', 'email',
    'space', 'website', 'media', 'agency', 'design', 'digital',
    'world', 'global', 'solutions', 'services', 'systems', 'network',
    'ph', 'us', 'uk', 'ca', 'au', 'nz', 'de', 'fr', 'jp', 'sg', 'my',
    'id', 'th', 'vn', 'in', 'cn', 'hk', 'tw', 'kr', 'es', 'it', 'nl',
    'se', 'no', 'fi', 'dk', 'ch', 'at', 'be', 'ie', 'ru', 'br', 'mx',
    'za', 'ae', 'sa', 'il', 'tr', 'gr', 'pt', 'pl', 'cz', 'eu', 'asia'
}

COMMON_DOMAIN_TYPOS = {
    'gmai.com': 'gmail.com',
    'gamil.com': 'gmail.com',
    'gmial.com': 'gmail.com',
    'gmaill.com': 'gmail.com',
    'gmail.co': 'gmail.com',
    'yaho.com': 'yahoo.com',
    'yahooo.com': 'yahoo.com',
    'outlok.com': 'outlook.com',
    'hotmial.com': 'hotmail.com',
}


def validate_email_format(email_raw: str) -> tuple[str | None, str | None]:
    """
    Validate email address format strictly.
    Returns (cleaned_email, None) on success or (None, error_message) on failure.
    Enforces valid RFC structure, real IANA TLDs, no all-numeric usernames,
    typo prevention, and strict Gmail constraints (6-30 chars, no illegal symbols,
    official domains, plus-tag validation).
    """
    if not email_raw or not str(email_raw).strip():
        return None, 'Please enter a valid email address.'

    clean_email = str(email_raw).strip().lower()

    if len(clean_email) > 254 or '..' in clean_email or clean_email.endswith('.') or ' ' in clean_email:
        return None, 'Please enter a valid email address format (e.g. name@gmail.com).'

    if not EMAIL_REGEX.match(clean_email):
        return None, 'Please enter a valid email address format (e.g. name@gmail.com).'

    parts = clean_email.split('@')
    if len(parts) != 2:
        return None, 'Please enter a valid email address format (e.g. name@gmail.com).'

    local_part, domain_part = parts
    if len(local_part) > 64:
        return None, 'Email username is too long.'

    # Username cannot be all digits (e.g. 112222)
    if not re.search(r'[a-z]', local_part):
        return None, 'Email username cannot be all numbers. Please enter a valid email address.'

    # Check common domain typos
    if domain_part in COMMON_DOMAIN_TYPOS:
        return None, f"Did you mean @{COMMON_DOMAIN_TYPOS[domain_part]}?"

    domain_parts = domain_part.split('.')
    tld = domain_parts[-1]
    if len(tld) < 2 or not tld.isalpha() or tld not in VALID_EMAIL_TLDS:
        return None, f"'.{tld}' is not a valid domain extension. Please check your email address."

    # Specific strict validation for Gmail
    if 'gmail' in domain_part or 'googlemail' in domain_part:
        if domain_part not in ('gmail.com', 'googlemail.com'):
            return None, 'Invalid Gmail domain. Did you mean @gmail.com?'

        if '+' in local_part and local_part.count('+') > 1:
            return None, 'Gmail address can only contain one plus (+) extension tag.'

        base_user = local_part.split('+')[0]
        tag_part = local_part.split('+')[1] if '+' in local_part else None

        clean_user = base_user.replace('.', '')
        if len(clean_user) < 6:
            return None, 'Gmail usernames must be at least 6 characters long.'
        if len(clean_user) > 30:
            return None, 'Gmail usernames cannot exceed 30 characters.'
        if not re.match(r'^[a-z0-9.]+$', base_user):
            return None, 'Gmail usernames can only contain letters (a-z), numbers (0-9), and periods (.).'
        if base_user.startswith('.') or base_user.endswith('.') or '..' in base_user:
            return None, 'Gmail usernames cannot start, end, or contain consecutive periods.'
        if tag_part is not None:
            if not tag_part or not re.match(r'^[a-z0-9._-]+$', tag_part):
                return None, 'Invalid Gmail plus extension tag format.'

    from app.utils.phone_utils import is_synthetic_account_email
    if is_synthetic_account_email(clean_email) or clean_email.endswith('@eflora.internal') or 'otp.eflora.internal' in clean_email:
        return None, 'Invalid email address. Please use a real email like Gmail.'

    return clean_email, None


