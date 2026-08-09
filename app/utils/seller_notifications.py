"""Helpers for creating in-app seller notifications from customer actions."""

from __future__ import annotations

import logging

from app.extensions import db
from app.models import Notification, Store

logger = logging.getLogger(__name__)

# Matches seller dashboard "low stock" threshold.
LOW_STOCK_THRESHOLD = 5


def notify_store_seller(
    *,
    store_id=None,
    seller_id=None,
    title: str,
    message: str,
    type: str,
    reference_id=None,
):
    """
    Queue a Notification for a store's seller.

    Does not commit — caller owns the transaction (same pattern as checkout
    new_order notifications). Failures are logged and swallowed so the main
    customer action is never blocked.
    """
    try:
        resolved_seller_id = seller_id
        if not resolved_seller_id and store_id:
            store = Store.query.get(store_id)
            if store:
                resolved_seller_id = store.seller_id

        if not resolved_seller_id:
            logger.warning(
                'notify_store_seller skipped: no seller for store_id=%s type=%s',
                store_id, type,
            )
            return None

        notif = Notification(
            user_id=resolved_seller_id,
            title=(title or 'Notification')[:200],
            message=message or '',
            type=type,
            reference_id=reference_id,
        )
        db.session.add(notif)
        return notif
    except Exception as exc:
        logger.exception('notify_store_seller failed: %s', exc)
        return None


def notify_low_stock_if_crossed(
    *,
    store_id,
    product,
    stock_before: int,
    stock_after: int,
    threshold: int = LOW_STOCK_THRESHOLD,
):
    """Notify once when stock crosses from above threshold into <= threshold."""
    try:
        if stock_before is None or stock_after is None:
            return None
        if stock_before > threshold and stock_after <= threshold:
            name = getattr(product, 'name', None) or 'Product'
            pid = getattr(product, 'id', None)
            return notify_store_seller(
                store_id=store_id,
                title='Low stock alert',
                message=f'"{name}" is low on stock ({stock_after} left after a customer order).',
                type='low_stock',
                reference_id=pid,
            )
    except Exception as exc:
        logger.exception('notify_low_stock_if_crossed failed: %s', exc)
    return None
