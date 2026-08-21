"""Shared wishlist helpers for web session + customer JWT APIs."""
from __future__ import annotations

from flask import current_app
from sqlalchemy import inspect
from sqlalchemy.orm import joinedload, selectinload

from app.extensions import db
from app.models import Product, ProductVariant, WishlistItem


def ensure_wishlist_items_table() -> bool:
    """Create wishlist_items from ORM if migration was not applied yet."""
    try:
        if inspect(db.engine).has_table('wishlist_items'):
            return True
        WishlistItem.__table__.create(db.engine, checkfirst=True)
        try:
            current_app.logger.info('Created missing table wishlist_items from model')
        except RuntimeError:
            pass
        return True
    except Exception as exc:
        try:
            current_app.logger.warning('Could not ensure wishlist_items table: %s', exc)
        except RuntimeError:
            pass
        return False


def _normalize_variant_id(variant_id):
    if variant_id in (None, '', 'null', 'None'):
        return None
    try:
        return int(variant_id)
    except (TypeError, ValueError):
        return None


def find_wishlist_item(user_id: int, product_id: int, variant_id=None):
    variant_id = _normalize_variant_id(variant_id)
    q = WishlistItem.query.filter_by(user_id=user_id, product_id=product_id)
    if variant_id is None:
        q = q.filter(WishlistItem.variant_id.is_(None))
    else:
        q = q.filter_by(variant_id=variant_id)
    return q.first()


def wishlist_variant_keys_for_product(user_id: int, product_id: int):
    """Return list of keys: null for main product, else variant id ints."""
    if not ensure_wishlist_items_table():
        return []
    rows = WishlistItem.query.filter_by(user_id=user_id, product_id=product_id).all()
    return [None if r.variant_id is None else int(r.variant_id) for r in rows]


def toggle_wishlist(user_id: int, product_id: int, variant_id=None):
    """
    Add or remove a wishlist entry.
    Returns (item_dict_or_None, wished: bool, error_response_or_None)
    """
    if not ensure_wishlist_items_table():
        return None, False, ({'error': 'Wishlist unavailable'}, 503)

    try:
        product_id = int(product_id)
    except (TypeError, ValueError):
        return None, False, ({'error': 'product_id is required'}, 400)

    variant_id = _normalize_variant_id(variant_id)

    product = Product.query.get(product_id)
    if not product:
        return None, False, ({'error': 'Product not found'}, 404)

    if variant_id is not None:
        variant = ProductVariant.query.get(variant_id)
        if not variant or variant.product_id != product_id:
            return None, False, ({'error': 'Variant not found'}, 404)

    existing = find_wishlist_item(user_id, product_id, variant_id)
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return None, False, None

    item = WishlistItem(
        user_id=user_id,
        product_id=product_id,
        variant_id=variant_id,
    )
    db.session.add(item)
    db.session.commit()
    item = (
        WishlistItem.query
        .options(
            joinedload(WishlistItem.product).joinedload(Product.store),
            joinedload(WishlistItem.product).selectinload(Product.images),
            joinedload(WishlistItem.variant),
        )
        .get(item.id)
    )
    return (item.to_dict() if item else None), True, None


def list_wishlist_items(user_id: int):
    if not ensure_wishlist_items_table():
        return []
    rows = (
        WishlistItem.query
        .filter_by(user_id=user_id)
        .options(
            joinedload(WishlistItem.product).joinedload(Product.store),
            joinedload(WishlistItem.product).selectinload(Product.images),
            joinedload(WishlistItem.variant),
        )
        .order_by(WishlistItem.created_at.desc())
        .all()
    )
    return [r.to_dict() for r in rows]


def remove_wishlist_item(user_id: int, item_id: int):
    if not ensure_wishlist_items_table():
        return False, ({'error': 'Wishlist unavailable'}, 503)
    item = WishlistItem.query.filter_by(id=item_id, user_id=user_id).first()
    if not item:
        return False, ({'error': 'Wishlist item not found'}, 404)
    db.session.delete(item)
    db.session.commit()
    return True, None
