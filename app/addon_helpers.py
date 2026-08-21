"""Helpers for structured product add-ons (dropdown groups/options)."""
from decimal import Decimal

from flask import jsonify

from app.extensions import db
from app.models import ProductAddonOption, CartItemAddon, OrderItemAddon


def normalize_addon_selections(raw):
    """
    Accept list of ints or dicts with addon_option_id / id and optional quantity.
    Returns [{id, units}] with units summed when the same id appears more than once.
    """
    if not raw:
        return []
    if not isinstance(raw, list):
        raise ValueError('addon_option_ids must be a list')

    merged = {}
    order = []
    for item in raw:
        if item is None or item == '' or item is False:
            continue
        units = 1
        if isinstance(item, dict):
            val = item.get('addon_option_id') or item.get('id')
            try:
                units = int(item.get('quantity') or item.get('units') or 1)
            except (TypeError, ValueError):
                units = 1
        else:
            val = item
        try:
            oid = int(val)
        except (TypeError, ValueError):
            raise ValueError('Invalid addon_option_id')
        if oid <= 0:
            continue
        units = max(1, units)
        if oid not in merged:
            order.append(oid)
            merged[oid] = 0
        merged[oid] += units

    return [{'id': oid, 'units': merged[oid]} for oid in order]


def normalize_addon_option_ids(raw):
    """Backward-compatible: unique option ids only."""
    return [row['id'] for row in normalize_addon_selections(raw)]


def resolve_structured_addon_selections(product, option_ids, quantity_per_option=1):
    """
    Validate option selections for this product.
    Allows:
      - options that belong to this product (dropdown add-ons)
      - YMAL-flagged options from any product in the same store
    Each selection may include a unit count (stack from dropdown + YMAL).
    line['quantity'] = units * quantity_per_option (stock / order charge units).
    line['units'] = stacked selection count stored on cart rows.
    """
    try:
        selections = normalize_addon_selections(option_ids)
    except ValueError as e:
        return None, (jsonify({'error': str(e)}), 400)

    if not selections:
        return [], None

    main_qty = max(1, int(quantity_per_option or 1))
    lines = []
    store_id = getattr(product, 'store_id', None)

    for sel in selections:
        oid = sel['id']
        units = int(sel['units'])
        opt = ProductAddonOption.query.get(oid)
        if not opt or not opt.group or not opt.group.product:
            return None, (jsonify({
                'error': f'Add-on option #{oid} is not valid for this product'
            }), 400)

        source_product = opt.group.product
        same_product = source_product.id == product.id
        same_store_ymal = (
            store_id is not None
            and source_product.store_id == store_id
            and bool(opt.show_in_you_may_also_like)
        )
        if not same_product and not same_store_ymal:
            return None, (jsonify({
                'error': f'Add-on option #{oid} is not valid for this product'
            }), 400)

        if not opt.group.is_active:
            return None, (jsonify({
                'error': f'Add-on "{opt.group.name}" is no longer available'
            }), 400)
        if not opt.is_available:
            return None, (jsonify({
                'error': f'"{opt.name}" is no longer available'
            }), 400)

        need = units * main_qty
        if int(opt.stock_quantity or 0) < need:
            return None, (jsonify({
                'error': (
                    f'Insufficient stock for "{opt.name}". '
                    f'Available: {opt.stock_quantity}'
                )
            }), 400)

        lines.append({
            'option': opt,
            'units': units,
            'quantity': need,
            'price': Decimal(str(opt.price or 0)),
            'name': opt.name,
            'image_url': opt.image_url or '',
            'group_id': opt.group_id,
            'group_name': opt.group.name if opt.group else None,
        })

    return lines, None


def structured_addons_subtotal(lines):
    total = Decimal('0')
    for line in lines or []:
        total += Decimal(str(line['price'])) * int(line['quantity'])
    return total


def sync_cart_item_addons(cart_item, product, option_ids):
    """Replace cart_item.addons with validated selections. Returns error tuple or None."""
    lines, err = resolve_structured_addon_selections(product, option_ids, quantity_per_option=1)
    if err:
        return err

    for row in list(cart_item.addons or []):
        db.session.delete(row)
    db.session.flush()

    for line in lines:
        db.session.add(CartItemAddon(
            cart_item_id=cart_item.id,
            addon_option_id=line['option'].id,
            quantity=int(line.get('units') or 1),
        ))
    return None


def attach_order_item_addons(order_item, lines):
    """Persist OrderItemAddon snapshots from resolved lines."""
    for line in lines or []:
        opt = line['option']
        db.session.add(OrderItemAddon(
            order_item_id=order_item.id,
            addon_option_id=opt.id,
            name=line['name'],
            price=line['price'],
            quantity=int(line['quantity']),
            image_url=line.get('image_url') or None,
        ))


def decrement_addon_option_stock(lines, user_id=None, reason='other', reason_notes=None):
    """
    Reduce structured add-on option stock and optionally write StockReduction
    audit rows so seller inventory history shows the change.
    """
    from app.models import StockReduction

    for line in lines or []:
        opt = line['option']
        qty = int(line['quantity'])
        if qty <= 0:
            continue
        if int(opt.stock_quantity or 0) < qty:
            raise ValueError(f'Insufficient stock for "{opt.name}"')
        opt.stock_quantity = int(opt.stock_quantity or 0) - qty
        if hasattr(opt, 'updated_at'):
            from datetime import datetime
            opt.updated_at = datetime.utcnow()

        if not user_id or not opt.group:
            continue
        db.session.add(StockReduction(
            product_id=opt.group.product_id,
            variant_id=None,
            addon_option_id=opt.id,
            reduction_amount=qty,
            reason=reason,
            reason_notes=reason_notes,
            reduced_by=user_id,
        ))


def ymal_addon_option_dicts(product):
    """
    YMAL add-on options for the product page carousel.
    Includes every active YMAL-flagged option from products in the same store
    (not only options defined on this product).
    """
    from sqlalchemy.orm import joinedload

    from app.models import Product, ProductAddonGroup

    if not product or not getattr(product, 'store_id', None):
        return []

    rows = (
        ProductAddonOption.query
        .join(ProductAddonGroup, ProductAddonOption.group_id == ProductAddonGroup.id)
        .join(Product, ProductAddonGroup.product_id == Product.id)
        .options(joinedload(ProductAddonOption.group).joinedload(ProductAddonGroup.product))
        .filter(
            Product.store_id == product.store_id,
            ProductAddonOption.show_in_you_may_also_like.is_(True),
            ProductAddonOption.is_available.is_(True),
            ProductAddonGroup.is_active.is_(True),
            Product.is_available.is_(True),
        )
        .order_by(
            ProductAddonGroup.sort_order.asc(),
            ProductAddonOption.sort_order.asc(),
            ProductAddonOption.id.asc(),
        )
        .all()
    )

    out = []
    seen = set()
    for opt in rows:
        if opt.id in seen:
            continue
        seen.add(opt.id)
        d = opt.to_dict()
        d['group_id'] = opt.group_id
        d['group_name'] = opt.group.name if opt.group else None
        d['source_product_id'] = opt.group.product_id if opt.group else None
        d['ymal_type'] = 'addon_option'
        out.append(d)
    return out
