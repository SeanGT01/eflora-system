"""Helpers for creating in-app seller notifications from customer actions."""

from __future__ import annotations

import logging

from app.extensions import db
from app.models import Notification, Store, StoreAdmin

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
        store = Store.query.get(store_id) if store_id else None
        if store is None and seller_id:
            store = (
                Store.query.filter_by(seller_id=seller_id)
                .order_by(Store.id.desc())
                .first()
            )

        recipient_ids = []
        owner_id = seller_id or (store.seller_id if store else None)
        if owner_id:
            recipient_ids.append(owner_id)
        if store:
            staff_ids = [
                row.user_id
                for row in StoreAdmin.query.filter_by(
                    store_id=store.id,
                    is_active=True,
                    is_archived=False,
                ).all()
            ]
            recipient_ids.extend(staff_ids)

        seen = set()
        unique_ids = []
        for uid in recipient_ids:
            if uid and uid not in seen:
                seen.add(uid)
                unique_ids.append(uid)

        if not unique_ids:
            logger.warning(
                'notify_store_seller skipped: no seller for store_id=%s type=%s',
                store_id, type,
            )
            return None

        first = None
        for uid in unique_ids:
            notif = Notification(
                user_id=uid,
                title=(title or 'Notification')[:200],
                message=message or '',
                type=type,
                reference_id=reference_id,
            )
            db.session.add(notif)
            if first is None:
                first = notif
        return first
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
