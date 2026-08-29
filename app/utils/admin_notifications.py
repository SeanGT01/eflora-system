"""Helpers for creating in-app admin notifications."""

from __future__ import annotations

import logging

from app.extensions import db
from app.models import Notification, User

logger = logging.getLogger(__name__)


def notify_admins(
    *,
    title: str,
    message: str,
    type: str,
    reference_id=None,
):
    """
    Queue a Notification for every active admin account.

    Does not commit — caller owns the transaction. Failures are logged and
    swallowed so the primary action is never blocked.
    """
    try:
        admins = User.query.filter(User.role == 'admin').all()
        if not admins:
            logger.warning('notify_admins skipped: no admin users type=%s', type)
            return []

        created = []
        for admin in admins:
            notif = Notification(
                user_id=admin.id,
                title=(title or 'Notification')[:200],
                message=message or '',
                type=type,
                reference_id=reference_id,
            )
            db.session.add(notif)
            created.append(notif)
        return created
    except Exception as exc:
        logger.exception('notify_admins failed: %s', exc)
        return []
