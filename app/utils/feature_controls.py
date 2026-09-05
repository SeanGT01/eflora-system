"""Admin-managed feature flags for OTP and SMS providers."""
from __future__ import annotations

from datetime import datetime

from app.extensions import db

KEY_PHONE_BIND_OTP = 'phone_bind_otp'
KEY_SMS_SMS8 = 'sms_provider_sms8'
KEY_SMS_IPROG = 'sms_provider_iprog'

DEFAULTS = {
    KEY_PHONE_BIND_OTP: False,
    KEY_SMS_SMS8: True,
    KEY_SMS_IPROG: True,
}


def ensure_system_controls_table():
    from sqlalchemy import inspect
    from app.models import SystemControl

    try:
        existing = inspect(db.engine).get_table_names()
        if 'system_controls' not in existing:
            SystemControl.__table__.create(db.engine, checkfirst=True)
        for key, default in DEFAULTS.items():
            row = SystemControl.query.get(key)
            if row is None:
                db.session.add(SystemControl(
                    key=key,
                    enabled=default,
                    updated_at=datetime.utcnow(),
                ))
        db.session.commit()
    except Exception:
        db.session.rollback()


def get_feature_controls():
    from app.models import SystemControl

    ensure_system_controls_table()
    out = dict(DEFAULTS)
    try:
        for row in SystemControl.query.all():
            if row.key in out:
                out[row.key] = bool(row.enabled)
    except Exception:
        db.session.rollback()
    return out


def public_flags():
    flags = get_feature_controls()
    return {
        KEY_PHONE_BIND_OTP: flags[KEY_PHONE_BIND_OTP],
        KEY_SMS_SMS8: flags[KEY_SMS_SMS8],
        KEY_SMS_IPROG: flags[KEY_SMS_IPROG],
        'sms_priority': 'sms8 then iprog' if flags[KEY_SMS_SMS8] and flags[KEY_SMS_IPROG] else (
            'sms8' if flags[KEY_SMS_SMS8] else ('iprog' if flags[KEY_SMS_IPROG] else 'none')
        ),
    }


def phone_bind_otp_required() -> bool:
    return bool(get_feature_controls().get(KEY_PHONE_BIND_OTP))


def sms8_enabled() -> bool:
    return bool(get_feature_controls().get(KEY_SMS_SMS8))


def iprog_enabled() -> bool:
    return bool(get_feature_controls().get(KEY_SMS_IPROG))


def set_feature_controls(payload):
    from app.models import SystemControl

    ensure_system_controls_table()
    data = payload if isinstance(payload, dict) else {}
    mapping = {
        KEY_PHONE_BIND_OTP: data.get(KEY_PHONE_BIND_OTP),
        KEY_SMS_SMS8: data.get(KEY_SMS_SMS8),
        KEY_SMS_IPROG: data.get(KEY_SMS_IPROG),
    }
    for key, value in mapping.items():
        if value is None:
            continue
        enabled = value in (True, 1, '1', 'true', 'on', 'yes')
        row = SystemControl.query.get(key)
        if row is None:
            row = SystemControl(key=key, enabled=enabled, updated_at=datetime.utcnow())
            db.session.add(row)
        else:
            row.enabled = enabled
            row.updated_at = datetime.utcnow()
    db.session.commit()
    return get_feature_controls()
