"""
One-time script to backfill realistic dummy cost prices for existing inventory and past sales.
Run with: python backfill_dummy_cost_prices.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from decimal import Decimal
from app import create_app
from app.extensions import db
from app.cost_helpers import calculate_realistic_cost, get_realistic_margin_rate
from app.models import (
    Product,
    ProductVariant,
    ProductAddonOption,
    StockReduction,
    OrderItem,
    POSOrderItem,
    OrderItemAddon,
)

app = create_app()

with app.app_context():
    print("[INFO] Starting dummy cost price backfill...")

    # 1. Backfill Products
    products = Product.query.all()
    prod_count = 0
    for p in products:
        if p.cost_price is None or p.cost_price <= 0:
            price_val = float(p.price or 0)
            cat_display = p.category_display or 'Uncategorized'
            target_m = get_realistic_margin_rate(p.name, cat_display, p.id)
            p.cost_price = Decimal(str(calculate_realistic_cost(price_val, target_m)))
            prod_count += 1
    db.session.flush()
    print(f"[OK] Backfilled cost prices for {prod_count} products (out of {len(products)})")

    # 2. Backfill Product Variants
    variants = ProductVariant.query.all()
    var_count = 0
    for v in variants:
        if v.cost_price is None or v.cost_price <= 0:
            p_name = v.product.name if v.product else ''
            cat_display = v.product.category_display if v.product else 'Uncategorized'
            var_full_name = f"{p_name} - {v.name}" if p_name else v.name
            price_val = float(v.price if v.price is not None else (v.product.price if v.product else 0))
            target_m = get_realistic_margin_rate(var_full_name, cat_display, v.id)
            v.cost_price = Decimal(str(calculate_realistic_cost(price_val, target_m)))
            var_count += 1
    db.session.flush()
    print(f"[OK] Backfilled cost prices for {var_count} variants (out of {len(variants)})")

    # 3. Backfill Product Addon Options
    addons = ProductAddonOption.query.all()
    addon_count = 0
    for a in addons:
        if a.cost_price is None or a.cost_price <= 0:
            price_val = float(a.price or 0)
            a_name = (a.name or '').lower()
            if any(k in a_name for k in ['chocolate', 'ferrero', 'sweet', 'candy']):
                m_rate = 0.32
            elif any(k in a_name for k in ['card', 'topper', 'message', 'ribbon', 'tag']):
                m_rate = 0.68
            else:
                m_rate = 0.45
            a.cost_price = Decimal(str(calculate_realistic_cost(price_val, m_rate)))
            addon_count += 1
    db.session.flush()
    print(f"[OK] Backfilled cost prices for {addon_count} add-on options (out of {len(addons)})")

    # 4. Backfill OrderItems (Past Online Orders)
    order_items = OrderItem.query.all()
    oi_count = 0
    for oi in order_items:
        if oi.cost_price is None or oi.cost_price <= 0:
            if oi.variant and oi.variant.cost_price and oi.variant.cost_price > 0:
                oi.cost_price = oi.variant.cost_price
            elif oi.product and oi.product.cost_price and oi.product.cost_price > 0:
                oi.cost_price = oi.product.cost_price
            else:
                price_val = Decimal(str(oi.price or 0))
                oi.cost_price = round(price_val * Decimal('0.60'), 2)
            oi_count += 1
    db.session.flush()
    print(f"[OK] Backfilled cost prices for {oi_count} past online order items (out of {len(order_items)})")

    # 5. Backfill POSOrderItems (Past In-Store Walk-in Orders)
    pos_items = POSOrderItem.query.all()
    pos_count = 0
    for pi in pos_items:
        if pi.cost_price is None or pi.cost_price <= 0:
            if pi.variant and pi.variant.cost_price and pi.variant.cost_price > 0:
                pi.cost_price = pi.variant.cost_price
            elif pi.product and pi.product.cost_price and pi.product.cost_price > 0:
                pi.cost_price = pi.product.cost_price
            elif pi.addon_option and pi.addon_option.cost_price and pi.addon_option.cost_price > 0:
                pi.cost_price = pi.addon_option.cost_price
            else:
                price_val = Decimal(str(pi.price or 0))
                pi.cost_price = round(price_val * Decimal('0.60'), 2)
            pos_count += 1
    db.session.flush()
    print(f"[OK] Backfilled cost prices for {pos_count} past POS order items (out of {len(pos_items)})")

    # 6. Backfill OrderItemAddon
    order_addons = OrderItemAddon.query.all()
    oia_count = 0
    for oia in order_addons:
        if oia.cost_price is None or oia.cost_price <= 0:
            if oia.addon_option and oia.addon_option.cost_price and oia.addon_option.cost_price > 0:
                oia.cost_price = oia.addon_option.cost_price
            else:
                price_val = Decimal(str(oia.price or 0))
                oia.cost_price = round(price_val * Decimal('0.50'), 2)
            oia_count += 1
    db.session.flush()
    print(f"[OK] Backfilled cost prices for {oia_count} order item addons (out of {len(order_addons)})")

    # 7. Backfill StockReduction Restock Records
    restocks = StockReduction.query.filter(
        StockReduction.reason.in_(['restock', 'found_stock', 'receiving_error'])
    ).all()
    sr_count = 0
    for sr in restocks:
        if sr.unit_cost is None:
            unit_c = Decimal('0.00')
            if sr.variant and sr.variant.cost_price and sr.variant.cost_price > 0:
                unit_c = sr.variant.cost_price
            elif sr.addon_option and sr.addon_option.cost_price and sr.addon_option.cost_price > 0:
                unit_c = sr.addon_option.cost_price
            elif sr.product and sr.product.cost_price and sr.product.cost_price > 0:
                unit_c = sr.product.cost_price
            sr.unit_cost = unit_c
            sr.total_cost = round(Decimal(str(sr.reduction_amount or 0)) * unit_c, 2)
            sr_count += 1
    db.session.flush()
    print(f"[OK] Backfilled unit_cost & total_cost for {sr_count} restock audit logs (out of {len(restocks)})")

    db.session.commit()
    print("\n[DONE] All dummy cost prices committed successfully!")
