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


_RECENT_STOCK_ALERT_EMAILS = {}
STOCK_ALERT_EMAIL_COOLDOWN_SECONDS = 7200  # 2 hours cooldown between identical alerts to the same recipient


def _send_stock_alert_emails(
    *,
    store_id: int,
    product,
    variant=None,
    addon_option=None,
    current_stock: int,
    alert_type: str,
    threshold: int,
):
    """
    Queue background stock alert email to store seller and active store admins via Gmail OAuth.
    Includes edge-crossing, recipient deduplication, and a 2-hour cooldown debounce guard.
    """
    try:
        import time
        from app.models import Store, StoreAdmin
        from app.utils.email_helper import send_stock_alert_email

        store = Store.query.get(store_id) if store_id else None
        if not store:
            return

        recipients = []
        if store.seller and store.seller.email:
            recipients.append({
                'email': store.seller.email.strip(),
                'name': store.seller.full_name or store.name,
            })

        admins = StoreAdmin.query.filter_by(
            store_id=store.id,
            is_active=True,
            is_archived=False,
        ).all()
        for sa in admins:
            if sa.user and sa.user.email:
                em = sa.user.email.strip()
                if not any(r['email'].lower() == em.lower() for r in recipients):
                    recipients.append({
                        'email': em,
                        'name': sa.user.full_name or sa.user.email,
                    })

        if not recipients:
            return

        # Determine product image
        image_url = None
        if variant and getattr(variant, 'image_url', None):
            image_url = variant.image_url
        elif product and hasattr(product, 'images') and product.images:
            sorted_imgs = sorted(product.images, key=lambda x: getattr(x, 'sort_order', 0))
            primary = next((img for img in sorted_imgs if getattr(img, 'is_primary', False)), sorted_imgs[0])
            image_url = getattr(primary, 'url', None)

        prod_name = getattr(product, 'name', None) or 'Product'
        var_name = getattr(variant, 'name', None) if variant else None
        opt_name = getattr(addon_option, 'name', None) if addon_option else None
        pid = getattr(product, 'id', None)

        now = time.time()
        # Clean up stale cache entries older than 24h
        if len(_RECENT_STOCK_ALERT_EMAILS) > 500:
            cutoff = now - 86400
            stale_keys = [k for k, ts in _RECENT_STOCK_ALERT_EMAILS.items() if ts < cutoff]
            for k in stale_keys:
                _RECENT_STOCK_ALERT_EMAILS.pop(k, None)

        for rec in recipients:
            cache_key = (
                rec['email'].lower(),
                alert_type,
                pid,
                getattr(variant, 'id', None),
                getattr(addon_option, 'id', None),
            )
            last_sent = _RECENT_STOCK_ALERT_EMAILS.get(cache_key, 0)
            if now - last_sent < STOCK_ALERT_EMAIL_COOLDOWN_SECONDS:
                logger.info('Suppressing duplicate stock alert email for %s (cooldown active)', cache_key)
                continue

            _RECENT_STOCK_ALERT_EMAILS[cache_key] = now

            send_stock_alert_email(
                recipient_email=rec['email'],
                seller_name=rec['name'],
                store_name=store.name,
                product_name=prod_name,
                current_stock=current_stock,
                alert_type=alert_type,
                threshold=threshold,
                variant_name=var_name,
                addon_name=opt_name,
                product_id=pid,
                image_url=image_url,
            )
    except Exception as exc:
        logger.exception('_send_stock_alert_emails failed: %s', exc)


def notify_low_stock_if_crossed(
    *,
    store_id=None,
    product,
    stock_before: int,
    stock_after: int,
    threshold: int = LOW_STOCK_THRESHOLD,
    variant=None,
    addon_option=None,
):
    """
    Notify store seller when stock crosses thresholds:
    - Out of stock alert: stock drops to 0 or below (stock_before > 0 and stock_after <= 0).
    - Low stock alert: stock crosses from above threshold into low stock range (stock_before > threshold and 0 < stock_after <= threshold).
    Sends both in-app seller notification and Gmail alert to store manager(s).
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
        addon_name = getattr(addon_option, 'name', None) if addon_option else None

        if variant_name:
            item_name = f"{base_name} ({variant_name})"
        elif addon_name:
            item_name = f"{base_name} - {addon_name}"
        else:
            item_name = base_name

        pid = getattr(product, 'id', None)

        # 1. Out of stock alert (takes precedence if dropped directly to 0)
        if stock_before > 0 and stock_after <= 0:
            notif = notify_store_seller(
                store_id=sid,
                title='Out of stock alert',
                message=f'"{item_name}" is now out of stock (0 left).',
                type='out_of_stock',
                reference_id=pid,
            )
            _send_stock_alert_emails(
                store_id=sid,
                product=product,
                variant=variant,
                addon_option=addon_option,
                current_stock=stock_after,
                alert_type='out_of_stock',
                threshold=threshold,
            )
            return notif

        # 2. Low stock alert
        if stock_before > threshold and 0 < stock_after <= threshold:
            notif = notify_store_seller(
                store_id=sid,
                title='Low stock alert',
                message=f'"{item_name}" is low on stock ({stock_after} left).',
                type='low_stock',
                reference_id=pid,
            )
            _send_stock_alert_emails(
                store_id=sid,
                product=product,
                variant=variant,
                addon_option=addon_option,
                current_stock=stock_after,
                alert_type='low_stock',
                threshold=threshold,
            )
            return notif

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


