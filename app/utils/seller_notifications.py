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
    store_id=None,
    product,
    stock_before: int,
    stock_after: int,
    threshold: int = LOW_STOCK_THRESHOLD,
    variant=None,
):
    """
    Notify store seller when stock crosses thresholds:
    - Out of stock alert: stock drops to 0 or below (stock_before > 0 and stock_after <= 0).
    - Low stock alert: stock crosses from above threshold into low stock range (stock_before > threshold and 0 < stock_after <= threshold).
    """
    try:
        if product is None or stock_before is None or stock_after is None:
            return None

        try:
            stock_before = int(stock_before)
            stock_after = int(stock_after)
            threshold = int(threshold)
        except (ValueError, TypeError):
            return None

        sid = store_id or getattr(product, 'store_id', None)
        if not sid:
            return None

        base_name = getattr(product, 'name', None) or 'Product'
        variant_name = getattr(variant, 'name', None) if variant else None
        item_name = f"{base_name} ({variant_name})" if variant_name else base_name
        pid = getattr(product, 'id', None)

        # 1. Out of stock alert (takes precedence if dropped directly to 0)
        if stock_before > 0 and stock_after <= 0:
            return notify_store_seller(
                store_id=sid,
                title='Out of stock alert',
                message=f'"{item_name}" is now out of stock (0 left).',
                type='out_of_stock',
                reference_id=pid,
            )

        # 2. Low stock alert
        if stock_before > threshold and 0 < stock_after <= threshold:
            return notify_store_seller(
                store_id=sid,
                title='Low stock alert',
                message=f'"{item_name}" is low on stock ({stock_after} left).',
                type='low_stock',
                reference_id=pid,
            )

        # 3. Restocked above threshold -> automatically remove out_of_stock and low_stock alerts
        if stock_after > threshold:
            clear_resolved_stock_notifications(product_id=pid, current_stock=stock_after, store_id=sid)

        # 4. Restocked from 0 to low stock (1..5) -> remove out_of_stock alert
        elif stock_before <= 0 and 0 < stock_after <= threshold:
            clear_resolved_stock_notifications(product_id=pid, current_stock=stock_after, store_id=sid)
    except Exception as exc:
        logger.exception('notify_low_stock_if_crossed failed: %s', exc)
    return None


notify_stock_alerts_if_crossed = notify_low_stock_if_crossed


def clear_resolved_stock_notifications(
    *,
    product_id: int,
    current_stock: int = None,
    store_id: int = None,
    threshold: int = LOW_STOCK_THRESHOLD,
):
    """
    Remove or resolve stock alerts once a product is restocked:
    - If current_stock > threshold: completely remove 'out_of_stock' and 'low_stock' alerts.
    - If 0 < current_stock <= threshold: remove 'out_of_stock' alert (since it now has stock).
    """
    try:
        from app.models import Product
        if not product_id:
            return 0

        product = Product.query.get(product_id)
        if not product:
            return 0

        sid = store_id or getattr(product, 'store_id', None)
        if not sid:
            return 0

        store = Store.query.get(sid)
        if not store or not store.seller_id:
            return 0

        seller_id = store.seller_id
        recipients = [seller_id]
        staff = StoreAdmin.query.filter_by(store_id=store.id, is_active=True, is_archived=False).all()
        recipients.extend([s.user_id for s in staff if s.user_id])
        recipients = list(set([r for r in recipients if r]))

        qty = current_stock if current_stock is not None else int(getattr(product, 'stock_quantity', 0) or 0)

        deleted = 0
        if qty > threshold:
            deleted = Notification.query.filter(
                Notification.user_id.in_(recipients),
                Notification.type.in_(['out_of_stock', 'low_stock']),
                Notification.reference_id == product.id,
            ).delete(synchronize_session=False)
            if deleted:
                db.session.commit()
        elif qty > 0:
            deleted = Notification.query.filter(
                Notification.user_id.in_(recipients),
                Notification.type == 'out_of_stock',
                Notification.reference_id == product.id,
            ).delete(synchronize_session=False)
            if deleted:
                db.session.commit()
        return deleted
    except Exception as exc:
        logger.exception('clear_resolved_stock_notifications failed: %s', exc)
        return 0


def clear_store_restocked_notifications(store_id: int, cleared_at=None, dismissed_products=None):
    """
    Remove obsolete stock alerts for products that are restocked (> LOW_STOCK_THRESHOLD)
    or out-of-stock alerts for products that now have stock (> 0).
    Never creates new notifications (notifications are created when stock changes occur).
    """
    try:
        from app.models import Product
        store = Store.query.get(store_id)
        if not store or not store.seller_id:
            return 0

        seller_id = store.seller_id
        recipients = [seller_id]
        staff = StoreAdmin.query.filter_by(store_id=store.id, is_active=True, is_archived=False).all()
        recipients.extend([s.user_id for s in staff if s.user_id])
        recipients = list(set([r for r in recipients if r]))

        # A. Products restocked above threshold (> 5) or archived: remove both alerts
        safe_products = Product.query.filter(
            Product.store_id == store.id,
            (Product.stock_quantity > LOW_STOCK_THRESHOLD) | (Product.is_archived == True)
        ).with_entities(Product.id).all()
        safe_ids = [p[0] for p in safe_products]
        if safe_ids:
            Notification.query.filter(
                Notification.user_id.in_(recipients),
                Notification.type.in_(['low_stock', 'out_of_stock']),
                Notification.reference_id.in_(safe_ids),
            ).delete(synchronize_session=False)

        # B. Products with stock > 0: remove any obsolete out_of_stock alert
        in_stock_products = Product.query.filter(
            Product.store_id == store.id,
            Product.stock_quantity > 0,
        ).with_entities(Product.id).all()
        in_stock_ids = [p[0] for p in in_stock_products]
        if in_stock_ids:
            Notification.query.filter(
                Notification.user_id.in_(recipients),
                Notification.type == 'out_of_stock',
                Notification.reference_id.in_(in_stock_ids),
            ).delete(synchronize_session=False)

        db.session.commit()
        return 0
    except Exception as exc:
        logger.exception('clear_store_restocked_notifications failed: %s', exc)
        return 0


# Keep aliases for backward compatibility
sync_store_stock_notifications = clear_store_restocked_notifications
record_store_notifs_cleared = lambda *args, **kwargs: None
get_store_notifs_cleared = lambda *args, **kwargs: None
record_product_notif_dismissed = lambda *args, **kwargs: None
get_product_notif_dismissed = lambda *args, **kwargs: None


