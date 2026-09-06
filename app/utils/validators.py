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
    """Validate a single full-name field (registration)."""
    text = _clean_name_whitespace(raw)
    if not text:
        return None, 'Full name is required.'
    if len(text) < 3:
        return None, 'Enter your first and last name.'
    if len(text) > FULL_NAME_MAX:
        return None, f'Full name must be at most {FULL_NAME_MAX} characters.'
    if not _PERSON_NAME_RE.match(text):
        return None, 'Full name can only contain letters, spaces, hyphens, and apostrophes.'
    if ' ' not in text:
        return None, 'Enter your first and last name.'
    return text, None


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

