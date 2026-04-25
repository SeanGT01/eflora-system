"""
Reusable OTP service for email-based verification flows.

Used by:
- Customer self-registration (see app/auth.py)
- Rider account creation initiated by sellers (see app/seller.py)

Design notes
------------
- OTPs are 6-digit numeric codes generated via secrets.choice (cryptographically secure).
- The plaintext code is sent via email; only a salted hash is stored in the database
  (using werkzeug.security.generate_password_hash, the same primitive used for User.password_hash).
- Verification is constant-time via werkzeug.security.check_password_hash.
- Helpers for resend cooldown and brute-force lockout are exposed so callers can
  implement consistent rate limiting per-row without duplicating logic.
"""

import secrets
import string
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash, check_password_hash


# Tunable defaults — keep aligned with the rider OTP flow unless explicitly stated.
OTP_LENGTH = 6
DEFAULT_EXPIRY_MINUTES = 5         # customer registration: 5 minutes (per spec)
RESEND_COOLDOWN_SECONDS = 60       # minimum gap between two OTP emails
MAX_VERIFY_ATTEMPTS = 5            # lock the row after this many bad attempts


def generate_otp_code(length: int = OTP_LENGTH) -> str:
    """Cryptographically secure N-digit numeric OTP."""
    return ''.join(secrets.choice(string.digits) for _ in range(length))


def hash_otp(plain_code: str) -> str:
    """One-way hash for safe storage."""
    return generate_password_hash(plain_code)


def verify_otp(plain_code: str, hashed_code: str) -> bool:
    """Constant-time comparison between submitted code and stored hash."""
    if not plain_code or not hashed_code:
        return False
    try:
        return check_password_hash(hashed_code, plain_code.strip())
    except Exception:
        return False


def new_otp_pair(expiry_minutes: int = DEFAULT_EXPIRY_MINUTES):
    """
    Convenience: generate (plain_code, hashed_code, expires_at) in one call.

    The caller emails `plain_code` to the user and persists `hashed_code`
    + `expires_at` on their OTP row.
    """
    plain = generate_otp_code()
    return plain, hash_otp(plain), datetime.utcnow() + timedelta(minutes=expiry_minutes)


def is_expired(expires_at) -> bool:
    """True when `expires_at` is missing or has elapsed."""
    if expires_at is None:
        return True
    return datetime.utcnow() > expires_at


def can_resend(last_sent_at, cooldown_seconds: int = RESEND_COOLDOWN_SECONDS):
    """
    Check if a new OTP email may be sent.

    Returns:
        (allowed: bool, retry_after_seconds: int)
        retry_after_seconds is 0 when allowed=True.
    """
    if last_sent_at is None:
        return True, 0
    elapsed = (datetime.utcnow() - last_sent_at).total_seconds()
    if elapsed >= cooldown_seconds:
        return True, 0
    return False, int(cooldown_seconds - elapsed)


def attempts_remaining(attempts: int, max_attempts: int = MAX_VERIFY_ATTEMPTS) -> int:
    """Helper for response payloads — never returns negative."""
    return max(max_attempts - (attempts or 0), 0)
