"""
Database migration & update script to diversify product, variant, addon, and restock prices/costs
with realistic, market-accurate gross profit margins instead of a flat 40% margin.

Run with: python scripts/update_diversified_prices.py
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
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
    print("[INFO] Starting diversified realistic pricing update...")

    # 1. Update Products
    products = Product.query.all()
    prod_count = 0
    margin_buckets = {}

    for p in products:
        price_val = float(p.price or 0.0)
        cat_display = p.category_display or 'Uncategorized'
        target_m = get_realistic_margin_rate(p.name, cat_display, p.id)
        new_cost = calculate_realistic_cost(price_val, target_m)
        p.cost_price = Decimal(str(new_cost))
        prod_count += 1

        actual_margin = round(((price_val - new_cost) / price_val * 100), 1) if price_val > 0 else 0.0
        bucket = f"{int(actual_margin // 5 * 5)}-{int(actual_margin // 5 * 5 + 5)}%"
        margin_buckets[bucket] = margin_buckets.get(bucket, 0) + 1

    db.session.flush()
    print(f"[OK] Updated cost prices for {prod_count} products.")
    print("     Diversified product margin distribution:")
    for b, count in sorted(margin_buckets.items()):
        print(f"       {b:10s}: {count} products")

    # 2. Update Product Variants
    variants = ProductVariant.query.all()
    var_count = 0
    for v in variants:
        p_name = v.product.name if v.product else ''
        cat_display = v.product.category_display if v.product else 'Uncategorized'
        var_full_name = f"{p_name} - {v.name}" if p_name else v.name
        price_val = float(v.price if v.price is not None else (v.product.price if v.product else 0.0))
        target_m = get_realistic_margin_rate(var_full_name, cat_display, v.id)
        new_cost = calculate_realistic_cost(price_val, target_m)
        v.cost_price = Decimal(str(new_cost))
        var_count += 1
    db.session.flush()
    print(f"[OK] Updated cost prices for {var_count} variants.")

    # 3. Update Product Add-on Options
    addons = ProductAddonOption.query.all()
    addon_count = 0
    for a in addons:
        price_val = float(a.price or 0.0)
        a_name = (a.name or '').lower()
        if any(k in a_name for k in ['chocolate', 'ferrero', 'toblerone', 'cadbury', 'sweet', 'candy']):
            m_rate = 0.32
        elif any(k in a_name for k in ['card', 'topper', 'message', 'ribbon', 'wrapper', 'tag', 'envelope']):
            m_rate = 0.68
        elif any(k in a_name for k in ['bear', 'teddy', 'plush', 'toy', 'balloon']):
            m_rate = 0.48
        else:
            m_rate = 0.45
        new_cost = calculate_realistic_cost(price_val, m_rate)
        a.cost_price = Decimal(str(new_cost))
        addon_count += 1
    db.session.flush()
    print(f"[OK] Updated cost prices for {addon_count} add-on options.")

    # 4. Update Past Online Orders (OrderItem)
    order_items = OrderItem.query.all()
    oi_count = 0
    for oi in order_items:
        if oi.variant and oi.variant.cost_price and oi.variant.cost_price > 0:
            oi.cost_price = oi.variant.cost_price
        elif oi.product and oi.product.cost_price and oi.product.cost_price > 0:
            oi.cost_price = oi.product.cost_price
        else:
            price_val = float(oi.price or 0.0)
            oi.cost_price = Decimal(str(calculate_realistic_cost(price_val, margin_rate=0.55)))
        oi_count += 1
    db.session.flush()
    print(f"[OK] Updated cost prices for {oi_count} online order items.")

    # 5. Update Past In-Store Orders (POSOrderItem)
    pos_items = POSOrderItem.query.all()
    pos_count = 0
    for pi in pos_items:
        if pi.variant and pi.variant.cost_price and pi.variant.cost_price > 0:
            pi.cost_price = pi.variant.cost_price
        elif pi.product and pi.product.cost_price and pi.product.cost_price > 0:
            pi.cost_price = pi.product.cost_price
        elif pi.addon_option and pi.addon_option.cost_price and pi.addon_option.cost_price > 0:
            pi.cost_price = pi.addon_option.cost_price
        else:
            price_val = float(pi.price or 0.0)
            pi.cost_price = Decimal(str(calculate_realistic_cost(price_val, margin_rate=0.50)))
        pos_count += 1
    db.session.flush()
    print(f"[OK] Updated cost prices for {pos_count} POS order items.")

    # 6. Update OrderItemAddon
    order_addons = OrderItemAddon.query.all()
    oia_count = 0
    for oia in order_addons:
        if oia.addon_option and oia.addon_option.cost_price and oia.addon_option.cost_price > 0:
            oia.cost_price = oia.addon_option.cost_price
        else:
            price_val = float(oia.price or 0.0)
            oia.cost_price = Decimal(str(calculate_realistic_cost(price_val, margin_rate=0.45)))
        oia_count += 1
    db.session.flush()
    print(f"[OK] Updated cost prices for {oia_count} order item addons.")

    # 7. Update StockReduction (Restock Batch Logs & Historical Costs)
    restocks = StockReduction.query.all()
    sr_count = 0
    for sr in restocks:
        unit_c = None
        if sr.variant and sr.variant.cost_price and sr.variant.cost_price > 0:
            unit_c = sr.variant.cost_price
        elif sr.addon_option and sr.addon_option.cost_price and sr.addon_option.cost_price > 0:
            unit_c = sr.addon_option.cost_price
        elif sr.product and sr.product.cost_price and sr.product.cost_price > 0:
            unit_c = sr.product.cost_price

        if unit_c is not None:
            sr.unit_cost = unit_c
            sr.total_cost = round(Decimal(str(sr.reduction_amount or 0)) * unit_c, 2)
            sr_count += 1

    db.session.flush()
    print(f"[OK] Synchronized unit_cost & total_cost for {sr_count} stock reduction / restock records.")

    db.session.commit()
    print("\n[SUCCESS] All product and inventory prices & costs diversified and committed successfully!")
