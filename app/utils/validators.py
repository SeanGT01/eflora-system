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

