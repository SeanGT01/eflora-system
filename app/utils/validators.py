"""Shared profile/input validation helpers."""
from datetime import date, datetime


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
