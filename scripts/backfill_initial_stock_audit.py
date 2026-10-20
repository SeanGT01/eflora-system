"""
Backfill Initial Inventory Stock Audit Records for Old Items
============================================================
Creates an initial audit record in `StockReduction` for all products, variants,
and add-on options that were created prior to the recent real-time creation audit feature.

Key details:
- Date & time: Set to the exact timestamp the item was created (product.created_at, variant.created_at, etc.)
- Reason: 'restock' (categorized as 'addition' with green '+' in Item History)
- Reason notes:
    - Products: 'Initial inventory on product creation'
    - Variants: 'Initial inventory for variant: <variant_name>'
    - Addons:   'Initial inventory for add-on: <option_name>'
- Quantity: Initial stock quantity (current stock + prior reductions - prior restocks)
- Unit cost & Total cost: Wholesale cost per unit and total batch capital tied
- Actor: Store's seller user ID
"""

import os
import sys
from datetime import datetime

# Add project root to sys.path
sys.path.insert(0, os.path.abspath('.'))

from app import create_app, db
from app.models import Product, ProductVariant, ProductAddonOption, StockReduction

def run_backfill(commit=True):
    app = create_app()
    with app.app_context():
        print("="*80)
        print("BACKFILLING INITIAL INVENTORY AUDIT RECORDS FOR OLD ITEMS")
        print("="*80)

        # 1. Existing initial inventory IDs
        existing_initial_prod_ids = {
            r.product_id for r in StockReduction.query.filter(
                StockReduction.variant_id.is_(None),
                StockReduction.addon_option_id.is_(None),
                StockReduction.reason_notes.like('%Initial inventory%')
            ).all()
        }
        existing_initial_var_ids = {
            r.variant_id for r in StockReduction.query.filter(
                StockReduction.variant_id.isnot(None),
                StockReduction.reason_notes.like('%Initial inventory%')
            ).all()
        }
        existing_initial_opt_ids = {
            r.addon_option_id for r in StockReduction.query.filter(
                StockReduction.addon_option_id.isnot(None),
                StockReduction.reason_notes.like('%Initial inventory%')
            ).all()
        }

        print(f"Skipping items that already have initial inventory records:")
        print(f"  Existing Products: {len(existing_initial_prod_ids)}")
        print(f"  Existing Variants: {len(existing_initial_var_ids)}")
        print(f"  Existing Addons:   {len(existing_initial_opt_ids)}")

        new_records = []

        # 2. Backfill Main Products
        products = Product.query.order_by(Product.id.asc()).all()
        for p in products:
            if p.id in existing_initial_prod_ids:
                continue

            reds = StockReduction.query.filter_by(product_id=p.id, variant_id=None, addon_option_id=None).all()
            total_reduced = sum(r.reduction_amount for r in reds if r.reason != 'restock')
            total_restocked = sum(r.reduction_amount for r in reds if r.reason == 'restock')

            inferred_stock = (p.stock_quantity or 0) + total_reduced - total_restocked
            init_stock = max(p.stock_quantity or 0, inferred_stock)

            if init_stock > 0:
                cost = float(p.cost_price or 0.0)
                seller_id = p.store.seller_id if (p.store and p.store.seller_id) else 1
                created_dt = p.created_at or datetime.utcnow()

                sr = StockReduction(
                    product_id=p.id,
                    variant_id=None,
                    addon_option_id=None,
                    reduction_amount=init_stock,
                    reason='restock',
                    reason_notes='Initial inventory on product creation',
                    reduced_by=seller_id,
                    unit_cost=cost,
                    total_cost=round(cost * init_stock, 2),
                    created_at=created_dt,
                    updated_at=created_dt
                )
                new_records.append(sr)

        # 3. Backfill Variants
        variants = ProductVariant.query.order_by(ProductVariant.id.asc()).all()
        for v in variants:
            if v.id in existing_initial_var_ids:
                continue

            reds = StockReduction.query.filter_by(variant_id=v.id).all()
            total_reduced = sum(r.reduction_amount for r in reds if r.reason != 'restock')
            total_restocked = sum(r.reduction_amount for r in reds if r.reason == 'restock')

            inferred_stock = (v.stock_quantity or 0) + total_reduced - total_restocked
            init_stock = max(v.stock_quantity or 0, inferred_stock)

            if init_stock > 0:
                cost = float(v.cost_price or (v.product.cost_price if v.product else 0.0) or 0.0)
                seller_id = v.product.store.seller_id if (v.product and v.product.store and v.product.store.seller_id) else 1
                v_created = v.created_at or (v.product.created_at if v.product else datetime.utcnow())

                sr = StockReduction(
                    product_id=v.product_id,
                    variant_id=v.id,
                    addon_option_id=None,
                    reduction_amount=init_stock,
                    reason='restock',
                    reason_notes=f"Initial inventory for variant: {v.name}",
                    reduced_by=seller_id,
                    unit_cost=cost,
                    total_cost=round(cost * init_stock, 2),
                    created_at=v_created,
                    updated_at=v_created
                )
                new_records.append(sr)

        # 4. Backfill Addon Options
        options = ProductAddonOption.query.order_by(ProductAddonOption.id.asc()).all()
        for o in options:
            if o.id in existing_initial_opt_ids:
                continue

            reds = StockReduction.query.filter_by(addon_option_id=o.id).all()
            total_reduced = sum(r.reduction_amount for r in reds if r.reason != 'restock')
            total_restocked = sum(r.reduction_amount for r in reds if r.reason == 'restock')

            inferred_stock = (o.stock_quantity or 0) + total_reduced - total_restocked
            init_stock = max(o.stock_quantity or 0, inferred_stock)

            if init_stock > 0:
                cost = float(o.cost_price or 0.0)
                p = o.group.product if o.group else None
                seller_id = p.store.seller_id if (p and p.store and p.store.seller_id) else 1
                o_created = o.created_at or (p.created_at if p else datetime.utcnow())

                sr = StockReduction(
                    product_id=p.id if p else 0,
                    variant_id=None,
                    addon_option_id=o.id,
                    reduction_amount=init_stock,
                    reason='restock',
                    reason_notes=f"Initial inventory for add-on: {o.name}",
                    reduced_by=seller_id,
                    unit_cost=cost,
                    total_cost=round(cost * init_stock, 2),
                    created_at=o_created,
                    updated_at=o_created
                )
                new_records.append(sr)

        print(f"\nPrepared {len(new_records)} initial inventory records to insert.")

        if commit:
            db.session.add_all(new_records)
            db.session.commit()
            print(f"SUCCESS: Committed {len(new_records)} initial inventory audit records into stock_reductions table.")
        else:
            print("DRY-RUN: No changes committed.")

if __name__ == '__main__':
    run_backfill(commit=True)
