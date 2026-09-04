"""Reusable analytics + report builders for the E-FLORA seller dashboard.

This module is the single source of truth for the data shown on
``/analytics`` and ``/reports``. It exposes:

* ``period_range(period, custom_from, custom_to)`` - resolve a label like
  ``"week"`` / ``"month"`` into a ``(start_dt, end_dt, label)`` tuple.
* ``compute_analytics(store, period=...)`` - one big context dict used by
  ``analytics.html``. Includes KPIs, chart data, top products, recent orders,
  reviews and delivery performance.
* ``build_report_payload(store, types, period=...)`` - returns a list of
  *report sections* (orders / customers / products / revenue / etc.) used by
  the PDF + CSV exporters.
* ``render_pdf(sections, store)`` - returns the PDF as bytes.
* ``render_csv_bundle(sections)`` - returns ``(filename, bytes, mime)``;
  one CSV when one section, otherwise a ZIP of CSVs.

All queries are scoped to the seller's store so there is zero risk of
leaking other shops' data.
"""

from __future__ import annotations

import csv
import io
import zipfile
import os
from collections import OrderedDict, defaultdict
from datetime import datetime, timedelta, date, time as dt_time
from decimal import Decimal
from typing import Iterable, List, Optional, Sequence, Tuple
import pytz
from urllib.request import urlopen

from sqlalchemy import func, text
from sqlalchemy.orm import joinedload

from app.utils.phone_utils import display_login_id
from app.extensions import db
from app.models import (
    Category,
    Order,
    OrderItem,
    OrderItemAddon,
    POSOrder,
    POSOrderItem,
    Product,
    ProductAddonGroup,
    ProductAddonOption,
    ProductRating,
    ProductVariant,
    Rider,
    Store,
    Testimonial,
    User,
)

PHT = pytz.timezone('Asia/Manila')


def _to_pht(dt: Optional[datetime]) -> Optional[datetime]:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(PHT)


def _pht_date(dt: Optional[datetime]) -> Optional[date]:
    """Calendar date in Asia/Manila for a UTC-naive or aware timestamp."""
    local = _to_pht(dt)
    return local.date() if local else None


def _pht_midnight_utc_naive(d: date) -> datetime:
    """Philippine calendar day start as naive UTC (matches stored timestamps)."""
    local_start = PHT.localize(datetime.combine(d, dt_time.min))
    return local_start.astimezone(pytz.utc).replace(tzinfo=None)


def _format_pht(dt: Optional[datetime], fmt: str = '%b %d, %Y %I:%M %p') -> str:
    """Format a stored UTC-naive (or aware) timestamp in Philippine time."""
    local = _to_pht(dt)
    return local.strftime(fmt) if local else ''


def _format_pht_date(dt: Optional[datetime]) -> str:
    return _format_pht(dt, '%b %d, %Y')


def _iter_pht_months(start: datetime, end: datetime):
    """Yield ``(label, bucket_start, bucket_end)`` for each PHT calendar month in range."""
    start_d = _pht_date(start)
    end_d = _pht_date(end)
    if not start_d or not end_d:
        return
    cursor_d = date(start_d.year, start_d.month, 1)
    while cursor_d < end_d:
        next_d = (cursor_d + timedelta(days=32)).replace(day=1)
        b_start = _pht_midnight_utc_naive(cursor_d)
        b_end = _pht_midnight_utc_naive(next_d)
        if b_start < start:
            b_start = start
        if b_end > end:
            b_end = end
        yield cursor_d.strftime('%b %Y'), b_start, b_end
        cursor_d = next_d


def pht_sql_hour(column):
    """Hour 0–23 in Asia/Manila from a naive UTC timestamp."""
    return func.cast(func.extract('hour', column + text("INTERVAL '8 hours'")), db.Integer)


def pht_sql_date(column):
    """PostgreSQL: naive UTC timestamp → Philippine calendar date (UTC+8)."""
    return func.date(column + text("INTERVAL '8 hours'"))


def _format_hour_12(hour: int) -> str:
    hour = int(hour) % 24
    if hour == 0:
        return '12AM'
    if hour == 12:
        return '12PM'
    if hour < 12:
        return f'{hour}AM'
    return f'{hour - 12}PM'


def _peak_hours_from_counts(by_hour: dict) -> list:
    """Equal 2-hour windows so a late-night dump cannot dwarf daytime peaks."""
    out = []
    for start in range(0, 24, 2):
        end = start + 2
        count = int(by_hour.get(start, 0)) + int(by_hour.get(start + 1, 0))
        out.append({
            'label': f'{_format_hour_12(start)}–{_format_hour_12(end % 24)}',
            'count': count,
        })
    return out


def _hour_counts_for_orders(start, end, store_id=None):
    hour = pht_sql_hour(Order.created_at)
    q = db.session.query(hour, func.count(Order.id)).filter(
        Order.created_at >= start,
        Order.created_at < end,
    )
    if store_id is not None:
        q = q.filter(Order.store_id == store_id)
    return q.group_by(hour).all()


def _hour_counts_for_pos(start, end, store_id=None):
    hour = pht_sql_hour(POSOrder.created_at)
    q = db.session.query(hour, func.count(POSOrder.id)).filter(
        POSOrder.created_at >= start,
        POSOrder.created_at < end,
    )
    if store_id is not None:
        q = q.filter(POSOrder.store_id == store_id)
    return q.group_by(hour).all()


def _merge_hour_rows(*row_sets) -> dict:
    by_hour = defaultdict(int)
    for rows in row_sets:
        for hour, cnt in rows:
            if hour is None:
                continue
            by_hour[int(hour) % 24] += int(cnt or 0)
    return by_hour


def _iter_pht_days(start: datetime, end: datetime):
    """Yield each Philippine calendar day in the half-open UTC range [start, end)."""
    start_d = _pht_date(start)
    # end is exclusive — last included local day is the day before end's PHT date
    end_exclusive_d = _pht_date(end)
    if not start_d or not end_exclusive_d:
        return
    cur = start_d
    while cur < end_exclusive_d:
        yield cur
        cur += timedelta(days=1)


# ─────────────────────────────────────────────────────────────────────────────
# Period helpers
# ─────────────────────────────────────────────────────────────────────────────

PERIOD_LABELS = {
    'today':   'Today',
    'week':    'This Week',
    'month':   'This Month',
    'quarter': 'This Quarter',
    'year':    'This Year',
    'custom':  'Custom Range',
    'all':     'All Time',
    'yesterday': 'Yesterday',
}


def _parse_iso_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def period_range(
    period: str = 'month',
    custom_from: Optional[str] = None,
    custom_to: Optional[str] = None,
) -> Tuple[datetime, datetime, str]:
    """Resolve a period name into ``(start, end, human_label)``.

    ``end`` is exclusive (i.e. start of the next day) so that range filters
    can use ``column >= start AND column < end`` without timezone surprises.
    """
    now_pht = datetime.now(PHT)
    today = now_pht.date()
    period = (period or 'month').lower().strip()

    def _pht_midnight_to_utc_naive(d: date) -> datetime:
        """Convert a Philippine calendar day start to naive UTC datetime."""
        return _pht_midnight_utc_naive(d)

    if period == 'today':
        start = _pht_midnight_to_utc_naive(today)
        end = _pht_midnight_to_utc_naive(today + timedelta(days=1))
        label = f"Today ({today.strftime('%b %d, %Y')})"
    elif period == 'yesterday':
        y = today - timedelta(days=1)
        start = _pht_midnight_to_utc_naive(y)
        end = _pht_midnight_to_utc_naive(y + timedelta(days=1))
        label = f"Yesterday ({y.strftime('%b %d, %Y')})"
    elif period == 'week':
        start_date = today - timedelta(days=today.weekday())  # Monday
        start = _pht_midnight_to_utc_naive(start_date)
        end = _pht_midnight_to_utc_naive(start_date + timedelta(days=7))
        label = f"This Week ({start_date.strftime('%b %d')} – {(start_date+timedelta(days=6)).strftime('%b %d, %Y')})"
    elif period == 'month':
        month_start = date(today.year, today.month, 1)
        next_month_start = (month_start + timedelta(days=32)).replace(day=1)
        start = _pht_midnight_to_utc_naive(month_start)
        end = _pht_midnight_to_utc_naive(next_month_start)
        label = f"This Month ({month_start.strftime('%B %Y')})"
    elif period == 'quarter':
        q = (today.month - 1) // 3
        quarter_start = date(today.year, q * 3 + 1, 1)
        end_month = q * 3 + 4
        end_year = today.year
        if end_month > 12:
            end_month -= 12
            end_year += 1
        quarter_end = date(end_year, end_month, 1)
        start = _pht_midnight_to_utc_naive(quarter_start)
        end = _pht_midnight_to_utc_naive(quarter_end)
        label = f"Q{q+1} {today.year}"
    elif period == 'year':
        year_start = date(today.year, 1, 1)
        next_year_start = date(today.year + 1, 1, 1)
        start = _pht_midnight_to_utc_naive(year_start)
        end = _pht_midnight_to_utc_naive(next_year_start)
        label = f"This Year ({today.year})"
    elif period == 'all':
        start = datetime(2000, 1, 1)
        end = datetime.utcnow() + timedelta(days=1)
        label = "All Time"
    elif period == 'custom':
        f = _parse_iso_date(custom_from) or today.replace(day=1)
        t = _parse_iso_date(custom_to) or today
        if t < f:
            f, t = t, f
        start = _pht_midnight_to_utc_naive(f)
        end = _pht_midnight_to_utc_naive(t + timedelta(days=1))
        label = f"{f.strftime('%b %d, %Y')} – {t.strftime('%b %d, %Y')}"
    else:
        return period_range('month')

    return start, end, label


# ─────────────────────────────────────────────────────────────────────────────
# Money / formatting helpers (used by templates + exporters)
# ─────────────────────────────────────────────────────────────────────────────

PESO = '\u20b1'  # ₱


def _report_email(email: Optional[str], phone: Optional[str] = None) -> str:
    """Show phone for SMS placeholder accounts instead of …@sms.eflora.internal."""
    return display_login_id(email=email, phone=phone) or ''


def peso(amount) -> str:
    """Format a number as ``₱1,234.56``."""
    try:
        v = float(amount or 0)
    except (TypeError, ValueError):
        v = 0.0
    return f"{PESO}{v:,.2f}"


def _to_float(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Core query helpers (always scoped to ``store``)
# ─────────────────────────────────────────────────────────────────────────────

# These statuses count as "completed/paid" revenue for online orders.
COMPLETED_ORDER_STATUSES = ('delivered', 'completed')


def _order_status_key(status) -> str:
    return (status or '').strip().lower()


def _is_paid_order_status(status) -> bool:
    return _order_status_key(status) in COMPLETED_ORDER_STATUSES


def _paid_order_status_filter():
    return Order.status.in_(COMPLETED_ORDER_STATUSES)


def _order_item_qty_subquery():
    return (
        db.session.query(
            OrderItem.order_id.label('order_id'),
            func.coalesce(func.sum(OrderItem.quantity), 0).label('item_qty'),
        )
        .group_by(OrderItem.order_id)
        .subquery()
    )


def _stock_status_label(stock: int):
    stock = int(stock or 0)
    if stock <= 0:
        return stock, 'Out of Stock'
    if stock <= 10:
        return stock, 'Low Stock'
    return stock, 'Available'


def _order_line_details_map(order_ids: Sequence[int]) -> dict:
    """Compact variant + add-on text per order, for the orders report column."""
    if not order_ids:
        return {}
    items = (
        db.session.query(OrderItem)
        .options(
            joinedload(OrderItem.product),
            joinedload(OrderItem.variant),
            joinedload(OrderItem.addons),
        )
        .filter(OrderItem.order_id.in_(list(order_ids)))
        .all()
    )
    grouped = defaultdict(list)
    for it in items:
        name = it.product.name if it.product else 'Item'
        if it.variant and it.variant.name:
            name = f"{name} — {it.variant.name}"
        chunk = f"{name} x{int(it.quantity or 0)}"
        addon_bits = [
            f"{a.name} x{int(a.quantity or 1)}"
            for a in (it.addons or [])
            if a and a.name
        ]
        if addon_bits:
            chunk = f"{chunk} (+ {', '.join(addon_bits)})"
        grouped[it.order_id].append(chunk)
    return {oid: '; '.join(parts) for oid, parts in grouped.items()}


def _period_catalog_sales(start, end, store_id=None):
    """Units and revenue for product/variant lines and add-on options (online + POS)."""
    oi_q = (
        db.session.query(
            OrderItem.product_id.label('product_id'),
            OrderItem.variant_id.label('variant_id'),
            func.coalesce(func.sum(OrderItem.quantity), 0).label('qty'),
            func.coalesce(func.sum(OrderItem.quantity * OrderItem.price), 0).label('revenue'),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            _paid_order_status_filter(),
            Order.created_at >= start,
            Order.created_at < end,
        )
    )
    if store_id is not None:
        oi_q = oi_q.filter(Order.store_id == store_id)
    oi_q = oi_q.group_by(OrderItem.product_id, OrderItem.variant_id)

    pos_q = (
        db.session.query(
            POSOrderItem.product_id.label('product_id'),
            POSOrderItem.variant_id.label('variant_id'),
            func.coalesce(func.sum(POSOrderItem.quantity), 0).label('qty'),
            func.coalesce(func.sum(POSOrderItem.quantity * POSOrderItem.price), 0).label('revenue'),
        )
        .join(POSOrder, POSOrder.id == POSOrderItem.pos_order_id)
        .filter(
            POSOrder.created_at >= start,
            POSOrder.created_at < end,
            POSOrderItem.addon_option_id.is_(None),
        )
    )
    if store_id is not None:
        pos_q = pos_q.filter(POSOrder.store_id == store_id)
    pos_q = pos_q.group_by(POSOrderItem.product_id, POSOrderItem.variant_id)

    pv = {}
    for r in list(oi_q.all()) + list(pos_q.all()):
        key = (int(r.product_id), int(r.variant_id) if r.variant_id else None)
        entry = pv.setdefault(key, {'qty': 0, 'revenue': 0.0})
        entry['qty'] += int(r.qty or 0)
        entry['revenue'] += _to_float(r.revenue)

    ao_q = (
        db.session.query(
            OrderItemAddon.addon_option_id.label('addon_option_id'),
            func.coalesce(func.sum(OrderItemAddon.quantity), 0).label('qty'),
            func.coalesce(func.sum(OrderItemAddon.quantity * OrderItemAddon.price), 0).label('revenue'),
        )
        .join(OrderItem, OrderItem.id == OrderItemAddon.order_item_id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            _paid_order_status_filter(),
            Order.created_at >= start,
            Order.created_at < end,
            OrderItemAddon.addon_option_id.isnot(None),
        )
    )
    if store_id is not None:
        ao_q = ao_q.filter(Order.store_id == store_id)
    ao_q = ao_q.group_by(OrderItemAddon.addon_option_id)

    pos_ao_q = (
        db.session.query(
            POSOrderItem.addon_option_id.label('addon_option_id'),
            func.coalesce(func.sum(POSOrderItem.quantity), 0).label('qty'),
            func.coalesce(func.sum(POSOrderItem.quantity * POSOrderItem.price), 0).label('revenue'),
        )
        .join(POSOrder, POSOrder.id == POSOrderItem.pos_order_id)
        .filter(
            POSOrder.created_at >= start,
            POSOrder.created_at < end,
            POSOrderItem.addon_option_id.isnot(None),
        )
    )
    if store_id is not None:
        pos_ao_q = pos_ao_q.filter(POSOrder.store_id == store_id)
    pos_ao_q = pos_ao_q.group_by(POSOrderItem.addon_option_id)

    addons = {}
    for r in list(ao_q.all()) + list(pos_ao_q.all()):
        if not r.addon_option_id:
            continue
        key = int(r.addon_option_id)
        entry = addons.setdefault(key, {'qty': 0, 'revenue': 0.0})
        entry['qty'] += int(r.qty or 0)
        entry['revenue'] += _to_float(r.revenue)

    return pv, addons


def _online_revenue(store_id: int, start: datetime, end: datetime) -> float:
    """Sum of ``total_amount`` for delivered and completed orders in [start, end)."""
    total = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(
        Order.store_id == store_id,
        _paid_order_status_filter(),
        Order.created_at >= start,
        Order.created_at < end,
    ).scalar()
    return _to_float(total)


def _pos_revenue(store_id: int, start: datetime, end: datetime) -> float:
    total = db.session.query(
        func.coalesce(func.sum(POSOrder.total_amount), 0)
    ).filter(
        POSOrder.store_id == store_id,
        POSOrder.created_at >= start,
        POSOrder.created_at < end,
    ).scalar()
    return _to_float(total)


def _online_order_count(store_id: int, start: datetime, end: datetime) -> int:
    return db.session.query(func.count(Order.id)).filter(
        Order.store_id == store_id,
        Order.created_at >= start,
        Order.created_at < end,
    ).scalar() or 0


def _completed_online_order_count(store_id, start, end) -> int:
    return db.session.query(func.count(Order.id)).filter(
        Order.store_id == store_id,
        _paid_order_status_filter(),
        Order.created_at >= start,
        Order.created_at < end,
    ).scalar() or 0


def _pos_order_count(store_id, start, end) -> int:
    return db.session.query(func.count(POSOrder.id)).filter(
        POSOrder.store_id == store_id,
        POSOrder.created_at >= start,
        POSOrder.created_at < end,
    ).scalar() or 0


def _new_customer_count(store_id, start, end) -> int:
    """Customers whose *first* order at this store falls in the period."""
    first_orders = db.session.query(
        Order.customer_id,
        func.min(Order.created_at).label('first_order'),
    ).filter(Order.store_id == store_id).group_by(Order.customer_id).subquery()

    return db.session.query(func.count(first_orders.c.customer_id)).filter(
        first_orders.c.first_order >= start,
        first_orders.c.first_order < end,
    ).scalar() or 0


def _top_products(store_id, start, end, limit=5):
    """Return list of dicts with ``name``, ``category``, ``quantity``, ``revenue``.
    Groups by product + variant; merges completed online + POS sales."""
    from app.models import ProductVariant
    online_rows = db.session.query(
        Product.id,
        Product.name,
        ProductVariant.id.label('variant_id'),
        ProductVariant.name.label('variant_name'),
        Category.name.label('category_name'),
        func.coalesce(func.sum(OrderItem.quantity), 0).label('qty'),
        func.coalesce(func.sum(OrderItem.quantity * OrderItem.price), 0).label('revenue'),
    ).join(OrderItem, OrderItem.product_id == Product.id) \
     .join(Order, Order.id == OrderItem.order_id) \
     .outerjoin(ProductVariant, ProductVariant.id == OrderItem.variant_id) \
     .outerjoin(Category, Category.id == Product.main_category_id) \
     .filter(
        Order.store_id == store_id,
        _paid_order_status_filter(),
        Order.created_at >= start,
        Order.created_at < end,
     ).group_by(Product.id, Product.name, ProductVariant.id, ProductVariant.name, Category.name).all()

    pos_rows = db.session.query(
        Product.id,
        Product.name,
        ProductVariant.id.label('variant_id'),
        ProductVariant.name.label('variant_name'),
        Category.name.label('category_name'),
        func.coalesce(func.sum(POSOrderItem.quantity), 0).label('qty'),
        func.coalesce(func.sum(POSOrderItem.quantity * POSOrderItem.price), 0).label('revenue'),
    ).join(POSOrderItem, POSOrderItem.product_id == Product.id) \
     .join(POSOrder, POSOrder.id == POSOrderItem.pos_order_id) \
     .outerjoin(ProductVariant, ProductVariant.id == POSOrderItem.variant_id) \
     .outerjoin(Category, Category.id == Product.main_category_id) \
     .filter(
        POSOrder.store_id == store_id,
        POSOrder.created_at >= start,
        POSOrder.created_at < end,
     ).group_by(Product.id, Product.name, ProductVariant.id, ProductVariant.name, Category.name).all()

    merged = {}
    for r in list(online_rows) + list(pos_rows):
        key = (int(r.id), int(r.variant_id) if r.variant_id else None)
        entry = merged.setdefault(key, {
            'id': r.id,
            'name': f"{r.name} — {r.variant_name}" if r.variant_name else r.name,
            'category': r.category_name or 'Uncategorized',
            'quantity': 0,
            'revenue': 0.0,
        })
        entry['quantity'] += int(r.qty or 0)
        entry['revenue'] += _to_float(r.revenue)

    return sorted(merged.values(), key=lambda x: x['revenue'], reverse=True)[:limit]


def _order_status_breakdown(store_id, start, end):
    rows = db.session.query(
        Order.status,
        func.count(Order.id),
    ).filter(
        Order.store_id == store_id,
        Order.created_at >= start,
        Order.created_at < end,
    ).group_by(Order.status).all()

    out = OrderedDict([
        ('delivered', 0),
        ('on_delivery', 0),
        ('preparing', 0),
        ('pending', 0),
        ('cancelled', 0),
    ])
    fold = {
        'completed': 'delivered',
        'accepted': 'preparing',
        'done_preparing': 'preparing',
    }
    for status, count in rows:
        key = (status or 'pending').lower()
        key = fold.get(key, key)
        if key not in out:
            key = 'pending'
        out[key] = (out.get(key) or 0) + int(count or 0)
    return out


def _sales_by_category(store_id, start, end):
    online_rows = db.session.query(
        Category.name,
        func.coalesce(func.sum(OrderItem.quantity), 0).label('qty'),
        func.coalesce(func.sum(OrderItem.quantity * OrderItem.price), 0).label('revenue'),
    ).join(Product, Product.main_category_id == Category.id) \
     .join(OrderItem, OrderItem.product_id == Product.id) \
     .join(Order, Order.id == OrderItem.order_id) \
     .filter(
        Order.store_id == store_id,
        _paid_order_status_filter(),
        Order.created_at >= start,
        Order.created_at < end,
     ).group_by(Category.name) \
      .all()

    pos_rows = db.session.query(
        Category.name,
        func.coalesce(func.sum(POSOrderItem.quantity), 0).label('qty'),
        func.coalesce(func.sum(POSOrderItem.quantity * POSOrderItem.price), 0).label('revenue'),
    ).join(Product, POSOrderItem.product_id == Product.id) \
     .outerjoin(Category, Category.id == Product.main_category_id) \
     .join(POSOrder, POSOrder.id == POSOrderItem.pos_order_id) \
     .filter(
        POSOrder.store_id == store_id,
        POSOrder.created_at >= start,
        POSOrder.created_at < end,
     ).group_by(Category.name) \
      .all()

    merged = {}
    for row in online_rows:
        key = row[0] or 'Uncategorized'
        merged.setdefault(key, {
            'name': key,
            'online_qty': 0,
            'online_revenue': 0.0,
            'pos_qty': 0,
            'pos_revenue': 0.0,
            'revenue': 0.0,
        })
        merged[key]['online_qty'] += int(row[1] or 0)
        merged[key]['online_revenue'] += _to_float(row[2])

    for row in pos_rows:
        key = row[0] or 'Uncategorized'
        merged.setdefault(key, {
            'name': key,
            'online_qty': 0,
            'online_revenue': 0.0,
            'pos_qty': 0,
            'pos_revenue': 0.0,
            'revenue': 0.0,
        })
        merged[key]['pos_qty'] += int(row[1] or 0)
        merged[key]['pos_revenue'] += _to_float(row[2])

    out = []
    for entry in merged.values():
        entry['revenue'] = entry['online_revenue'] + entry['pos_revenue']
        out.append(entry)
    out.sort(key=lambda x: x['revenue'], reverse=True)
    return out


def _peak_hours(store_id, start, end):
    """Order volume by Philippine local time, in equal 2-hour windows (online + POS)."""
    by_hour = _merge_hour_rows(
        _hour_counts_for_orders(start, end, store_id=store_id),
        _hour_counts_for_pos(start, end, store_id=store_id),
    )
    return _peak_hours_from_counts(by_hour)


def _revenue_series(store_id, start, end):
    """Daily completed online + POS revenue, bucketed by Philippine calendar day."""
    days = (end - start).days or 1
    if days > 31:
        return _bucketed_revenue(store_id, start, end, buckets=12)

    online_rows = db.session.query(Order.created_at, Order.total_amount).filter(
        Order.store_id == store_id,
        _paid_order_status_filter(),
        Order.created_at >= start,
        Order.created_at < end,
    ).all()
    pos_rows = db.session.query(POSOrder.created_at, POSOrder.total_amount).filter(
        POSOrder.store_id == store_id,
        POSOrder.created_at >= start,
        POSOrder.created_at < end,
    ).all()

    online_by_day = defaultdict(lambda: [0.0, 0])
    for ts, amt in online_rows:
        d = _pht_date(ts)
        if d:
            online_by_day[d][0] += _to_float(amt)
            online_by_day[d][1] += 1

    pos_by_day = defaultdict(lambda: [0.0, 0])
    for ts, amt in pos_rows:
        d = _pht_date(ts)
        if d:
            pos_by_day[d][0] += _to_float(amt)
            pos_by_day[d][1] += 1

    labels, revenues, order_counts = [], [], []
    online_revenues, pos_revenues = [], []
    online_orders, pos_orders = [], []
    for cur in _iter_pht_days(start, end):
        o_rev, o_cnt = online_by_day.get(cur, [0.0, 0])
        p_rev, p_cnt = pos_by_day.get(cur, [0.0, 0])
        labels.append(cur.strftime('%b %d'))
        revenues.append(o_rev + p_rev)
        order_counts.append(o_cnt + p_cnt)
        online_revenues.append(o_rev)
        pos_revenues.append(p_rev)
        online_orders.append(o_cnt)
        pos_orders.append(p_cnt)
    return {
        'labels': labels,
        'revenue': revenues,
        'orders': order_counts,
        'online_revenue': online_revenues,
        'pos_revenue': pos_revenues,
        'online_orders': online_orders,
        'pos_orders': pos_orders,
    }


def _bucketed_revenue(store_id, start, end, buckets=12):
    span = (end - start).total_seconds()
    if span <= 0:
        return {
            'labels': [],
            'revenue': [],
            'orders': [],
            'online_revenue': [],
            'pos_revenue': [],
            'online_orders': [],
            'pos_orders': [],
        }
    step = span / buckets
    edges = [start + timedelta(seconds=step * i) for i in range(buckets + 1)]

    online_rows = db.session.query(
        Order.created_at,
        Order.total_amount,
    ).filter(
        Order.store_id == store_id,
        _paid_order_status_filter(),
        Order.created_at >= start,
        Order.created_at < end,
    ).all()

    pos_rows = db.session.query(
        POSOrder.created_at,
        POSOrder.total_amount,
    ).filter(
        POSOrder.store_id == store_id,
        POSOrder.created_at >= start,
        POSOrder.created_at < end,
    ).all()

    online_rev = [0.0] * buckets
    online_cnt = [0] * buckets
    pos_rev = [0.0] * buckets
    pos_cnt = [0] * buckets

    for ts, amt in online_rows:
        for i in range(buckets):
            if edges[i] <= ts < edges[i + 1]:
                online_rev[i] += _to_float(amt)
                online_cnt[i] += 1
                break

    for ts, amt in pos_rows:
        for i in range(buckets):
            if edges[i] <= ts < edges[i + 1]:
                pos_rev[i] += _to_float(amt)
                pos_cnt[i] += 1
                break

    rev = [online_rev[i] + pos_rev[i] for i in range(buckets)]
    cnt = [online_cnt[i] + pos_cnt[i] for i in range(buckets)]
    labels = [edges[i].strftime('%b %d') for i in range(buckets)]
    return {
        'labels': labels,
        'revenue': rev,
        'orders': cnt,
        'online_revenue': online_rev,
        'pos_revenue': pos_rev,
        'online_orders': online_cnt,
        'pos_orders': pos_cnt,
    }


def _delivery_performance(store_id, start, end):
    """On-time rate, avg delivery time (minutes), cancellation %."""
    fulfilled = db.session.query(Order).filter(
        Order.store_id == store_id,
        _paid_order_status_filter(),
        Order.created_at >= start,
        Order.created_at < end,
    ).all()

    cancelled = db.session.query(func.count(Order.id)).filter(
        Order.store_id == store_id,
        Order.status == 'cancelled',
        Order.created_at >= start,
        Order.created_at < end,
    ).scalar() or 0

    total = db.session.query(func.count(Order.id)).filter(
        Order.store_id == store_id,
        Order.created_at >= start,
        Order.created_at < end,
    ).scalar() or 0

    delivery_minutes = []
    on_time = 0
    for o in fulfilled:
        mins, thresh = _measure_order_delivery(o)
        if mins is None:
            continue
        delivery_minutes.append(mins)
        if mins <= thresh:
            on_time += 1

    avg_minutes = round(sum(delivery_minutes) / len(delivery_minutes), 1) if delivery_minutes else 0.0
    on_time_rate = round((on_time / len(delivery_minutes)) * 100, 1) if delivery_minutes else 0.0
    cancel_rate = round((cancelled / total) * 100, 1) if total else 0.0

    series_days = []
    series_rates = []
    end_d = _pht_date(end) or end.date()
    for i in range(7):
        d = end_d - timedelta(days=7 - i)
        days_orders = []
        ok = 0
        for o in fulfilled:
            if not o.delivered_at or _pht_date(o.delivered_at) != d:
                continue
            mins, thresh = _measure_order_delivery(o)
            if mins is None:
                continue
            days_orders.append(mins)
            if mins <= thresh:
                ok += 1
        series_rates.append(round((ok / len(days_orders)) * 100, 1) if days_orders else 0)
        series_days.append(d.strftime('%a'))

    return {
        'on_time_rate': on_time_rate,
        'avg_minutes': avg_minutes,
        'cancellation_rate': cancel_rate,
        'series': {'labels': series_days, 'rates': series_rates},
    }


def _recent_orders(store_id, limit=5):
    orders = (Order.query
              .filter(Order.store_id == store_id)
              .order_by(Order.created_at.desc())
              .limit(limit)
              .all())
    out = []
    for o in orders:
        out.append({
            'id': o.id,
            'order_no': f"#{o.id:05d}",
            'customer_name': o.customer.full_name if o.customer else 'Walk-in',
            'amount': _to_float(o.total_amount),
            'status': o.status or 'pending',
            'created_at': o.created_at,
            'created_at_display': (_to_pht(o.created_at).strftime('%b %d, %Y %I:%M %p') if _to_pht(o.created_at) else ''),
        })
    return out


def _store_rating(store_id):
    """Returns average product rating, total count, and 1-5 distribution."""
    rows = db.session.query(
        ProductRating.rating,
        func.count(ProductRating.id),
    ).join(Product, Product.id == ProductRating.product_id) \
     .filter(Product.store_id == store_id) \
     .group_by(ProductRating.rating).all()
    counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r, c in rows:
        if r in counts:
            counts[r] = int(c or 0)
    total = sum(counts.values())
    avg = round(sum(k * v for k, v in counts.items()) / total, 1) if total else 0.0
    return {'average': avg, 'total': total, 'distribution': counts}


def _recent_reviews(store_id, limit=3):
    reviews = (db.session.query(ProductRating)
               .join(Product, Product.id == ProductRating.product_id)
               .filter(Product.store_id == store_id)
               .order_by(ProductRating.created_at.desc())
               .limit(limit).all())
    return [{
        'customer_name': r.customer.full_name if r.customer else 'Anonymous',
        'rating': r.rating or 0,
        'comment': r.comment or '',
        'created_at': r.created_at,
    } for r in reviews]


# ─────────────────────────────────────────────────────────────────────────────
# Public: analytics context
# ─────────────────────────────────────────────────────────────────────────────

def compute_analytics(
    store: Store,
    period: str = 'week',
    custom_from: Optional[str] = None,
    custom_to: Optional[str] = None,
) -> dict:
    """Build the giant context dict consumed by ``analytics.html``."""
    start, end, period_label = period_range(period, custom_from, custom_to)

    # Previous comparable period (same length, immediately before)
    prev_start = start - (end - start)
    prev_end = start

    online_rev = _online_revenue(store.id, start, end)
    pos_rev = _pos_revenue(store.id, start, end)
    total_rev = online_rev + pos_rev

    online_orders = _online_order_count(store.id, start, end)
    completed_online = _completed_online_order_count(store.id, start, end)
    pos_orders = _pos_order_count(store.id, start, end)
    total_orders = online_orders + pos_orders

    # AOV = completed ticket average (revenue is completed online + all POS)
    sold_orders = completed_online + pos_orders
    avg_order = (total_rev / sold_orders) if sold_orders else 0.0
    new_customers = _new_customer_count(store.id, start, end)

    # Previous-period comparisons for the % badges
    prev_rev = _online_revenue(store.id, prev_start, prev_end) + _pos_revenue(store.id, prev_start, prev_end)
    prev_completed = _completed_online_order_count(store.id, prev_start, prev_end) + _pos_order_count(store.id, prev_start, prev_end)
    prev_orders = _online_order_count(store.id, prev_start, prev_end) + _pos_order_count(store.id, prev_start, prev_end)
    prev_avg = (prev_rev / prev_completed) if prev_completed else 0.0
    prev_new_customers = _new_customer_count(store.id, prev_start, prev_end)

    def pct_change(now, before):
        if not before:
            return None
        return round(((now - before) / before) * 100, 1)

    # Totals (NOT period-scoped — for the bottom-of-page summary numbers)
    total_customers = db.session.query(func.count(func.distinct(Order.customer_id))).filter(
        Order.store_id == store.id
    ).scalar() or 0
    total_products = db.session.query(func.count(Product.id)).filter(
        Product.store_id == store.id, Product.is_archived.is_(False)
    ).scalar() or 0

    return {
        'store': store,
        'period': period,
        'period_label': period_label,
        'period_start': start,
        'period_end': end,

        # KPIs
        'totals': {
            'revenue': total_rev,
            'revenue_display': peso(total_rev),
            'orders': total_orders,
            'avg_order': avg_order,
            'avg_order_display': peso(avg_order),
            'new_customers': new_customers,

            'all_customers': total_customers,
            'all_products': total_products,
            'completed_orders': completed_online + pos_orders,
        },
        'deltas': {
            'revenue_pct': pct_change(total_rev, prev_rev),
            'orders_pct': pct_change(total_orders, prev_orders),
            'avg_pct': pct_change(avg_order, prev_avg),
            'new_pct': pct_change(new_customers, prev_new_customers),
        },

        # Charts + lists
        'top_products': _top_products(store.id, start, end, limit=5),
        'order_status': _order_status_breakdown(store.id, start, end),
        'sales_by_category': _sales_by_category(store.id, start, end),
        'peak_hours': _peak_hours(store.id, start, end),
        'revenue_series': _revenue_series(store.id, start, end),
        'delivery': _delivery_performance(store.id, start, end),
        'recent_orders': _recent_orders(store.id, limit=5),
        'rating': _store_rating(store.id),
        'reviews': _recent_reviews(store.id, limit=3),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Report sections (used for PDF + CSV)
# ─────────────────────────────────────────────────────────────────────────────

# Canonical set of report types (also drives the multi-select UI).
REPORT_TYPES = ['orders', 'customers', 'products', 'revenue', 'riders', 'year_end']

REPORT_TYPE_LABELS = {
    'orders':    'Orders Report',
    'customers': 'Customers Report',
    'products':  'Products Report',
    'revenue':   'Revenue Report',
    'riders':    'Riders Report',
    'year_end':  'Year-End Summary Report',
}


def _normalise_types(raw: Iterable[str]) -> List[str]:
    """Normalise + dedupe a list of report-type identifiers.

    Accepts ``"all"`` (expands to everything) and silently drops unknown values.
    """
    out: List[str] = []
    for t in raw or []:
        if not t:
            continue
        t = str(t).strip().lower()
        if t == 'all':
            return list(REPORT_TYPES)
        if t in REPORT_TYPES and t not in out:
            out.append(t)
    return out or list(REPORT_TYPES)


# ── Section builders ────────────────────────────────────────────────────────

def _orders_section(store_id, start, end):
    qty = _order_item_qty_subquery()
    results = (
        db.session.query(Order, func.coalesce(qty.c.item_qty, 0))
        .outerjoin(qty, qty.c.order_id == Order.id)
        .options(joinedload(Order.customer))
        .filter(
            Order.store_id == store_id,
            Order.created_at >= start,
            Order.created_at < end,
        )
        .order_by(Order.created_at.desc())
        .all()
    )
    rows = []
    orders = []
    for o, item_qty in results:
        orders.append(o)
    details_map = _order_line_details_map([o.id for o in orders])
    for o, item_qty in results:
        rows.append([
            f"#{o.id:05d}",
            o.customer.full_name if o.customer else 'Walk-in',
            _format_pht(o.created_at),
            int(item_qty or 0),
            details_map.get(o.id) or '—',
            float(o.total_amount or 0),
            (o.status or 'pending').replace('_', ' ').title(),
            (o.payment_method or 'gcash').upper(),
            (o.payment_status or 'pending').replace('_', ' ').title(),
        ])
    delivered = sum(1 for o in orders if _order_status_key(o.status) == 'delivered')
    completed = sum(1 for o in orders if _order_status_key(o.status) == 'completed')
    cancelled = sum(1 for o in orders if _order_status_key(o.status) == 'cancelled')
    revenue = sum(float(o.total_amount or 0) for o in orders if _is_paid_order_status(o.status))
    summary = [
        ('Total Orders', f"{len(orders):,}"),
        ('Delivered', f"{delivered:,}"),
        ('Completed', f"{completed:,}"),
        ('Cancelled', f"{cancelled:,}"),
        ('Revenue (Delivered + Completed)', peso(revenue)),
    ]
    return {
        'key': 'orders',
        'title': REPORT_TYPE_LABELS['orders'],
        'columns': [
            'Order ID', 'Customer', 'Date (PHT)', 'Items', 'Variants / Add-ons',
            'Amount (₱)', 'Status', 'Payment', 'Payment Status',
        ],
        'rows': rows,
        'summary': summary,
    }


def _customers_section(store_id, start, end):
    rows = db.session.query(
        User.id,
        User.full_name,
        User.email,
        func.count(Order.id).label('order_count'),
        func.coalesce(func.sum(Order.total_amount), 0).label('total_spent'),
        func.max(Order.created_at).label('last_order'),
    ).join(Order, Order.customer_id == User.id) \
     .filter(Order.store_id == store_id,
             Order.created_at >= start,
             Order.created_at < end) \
     .group_by(User.id, User.full_name, User.email) \
     .order_by(func.sum(Order.total_amount).desc()).all()

    out_rows = []
    for r in rows:
        out_rows.append([
            r.full_name,
            _report_email(r.email),
            int(r.order_count or 0),
            float(r.total_spent or 0),
            _format_pht_date(r.last_order),
        ])
    new_count = _new_customer_count(store_id, start, end)
    summary = [
        ('Customers in Period', f"{len(out_rows):,}"),
        ('New Customers', f"{new_count:,}"),
        ('Total Spent', peso(sum(r[3] for r in out_rows))),
    ]
    return {
        'key': 'customers',
        'title': REPORT_TYPE_LABELS['customers'],
        'columns': ['Customer', 'Email', 'Orders', 'Total Spent (₱)', 'Last Order (PHT)'],
        'rows': out_rows,
        'summary': summary,
    }


def _products_section(store_id, start, end):
    return _build_products_section(start, end, store_id=store_id, include_store=False)


def _build_products_section(start, end, store_id=None, include_store=False):
    """Catalogue rows for base products, each variant, and each add-on option."""
    pv_sales, addon_sales = _period_catalog_sales(start, end, store_id=store_id)
    q = (
        Product.query
        .options(
            joinedload(Product.variants),
            joinedload(Product.addon_groups).joinedload(ProductAddonGroup.options),
            joinedload(Product.main_category),
            joinedload(Product.store),
        )
        .filter(Product.is_archived.is_(False))
    )
    if store_id is not None:
        q = q.filter(Product.store_id == store_id)
    products = q.order_by(Product.name.asc()).all()

    out_rows = []
    low_stock = 0
    out_of_stock = 0
    variant_count = 0
    addon_count = 0
    units_sold = 0

    def _append_row(product, kind, option_name, stock, price, sold, revenue):
        nonlocal low_stock, out_of_stock, units_sold
        stock, stock_label = _stock_status_label(stock)
        if stock_label == 'Out of Stock':
            out_of_stock += 1
        elif stock_label == 'Low Stock':
            low_stock += 1
        units_sold += int(sold or 0)
        row = [product.name]
        if include_store:
            row.append(product.store.name if product.store else '—')
        row.extend([
            kind,
            option_name or '—',
            product.main_category.name if product.main_category else 'Uncategorized',
            int(sold or 0),
            float(revenue or 0),
            stock,
            float(price or 0),
            stock_label,
        ])
        out_rows.append(row)

    for product in products:
        variants = list(product.variants or [])
        if variants:
            for variant in sorted(variants, key=lambda v: (v.sort_order or 0, v.name or '')):
                variant_count += 1
                sales = pv_sales.get((product.id, variant.id), {'qty': 0, 'revenue': 0.0})
                price = variant.special_price if (
                    variant.special_price and variant.special_price < variant.price
                ) else variant.price
                _append_row(
                    product,
                    'Variant',
                    variant.name,
                    variant.stock_quantity,
                    price,
                    sales['qty'],
                    sales['revenue'],
                )
            base_sales = pv_sales.get((product.id, None), {'qty': 0, 'revenue': 0.0})
            if base_sales['qty'] or base_sales['revenue']:
                _append_row(
                    product,
                    'Product',
                    'No variant',
                    product.stock_quantity,
                    product.price,
                    base_sales['qty'],
                    base_sales['revenue'],
                )
        else:
            sales = pv_sales.get((product.id, None), {'qty': 0, 'revenue': 0.0})
            _append_row(
                product,
                'Product',
                '—',
                product.stock_quantity,
                product.price,
                sales['qty'],
                sales['revenue'],
            )

        for group in sorted(product.addon_groups or [], key=lambda g: g.sort_order or 0):
            for opt in sorted(group.options or [], key=lambda o: o.sort_order or 0):
                addon_count += 1
                sales = addon_sales.get(opt.id, {'qty': 0, 'revenue': 0.0})
                label = f"{group.name} — {opt.name}" if group.name else opt.name
                _append_row(
                    product,
                    'Add-on',
                    label,
                    opt.stock_quantity,
                    opt.price,
                    sales['qty'],
                    sales['revenue'],
                )

    summary = [
        ('Catalogue Rows', f"{len(out_rows):,}"),
        ('Variants', f"{variant_count:,}"),
        ('Add-ons', f"{addon_count:,}"),
        ('Low Stock', f"{low_stock:,}"),
        ('Out of Stock', f"{out_of_stock:,}"),
        ('Units Sold', f"{units_sold:,}"),
    ]
    columns = ['Product']
    if include_store:
        columns.append('Store')
    columns.extend([
        'Type', 'Variant / Add-on', 'Category', 'Units Sold',
        'Revenue (₱)', 'Stock', 'Price (₱)', 'Status',
    ])
    return {
        'key': 'products',
        'title': (
            'Products Report (All Stores)' if include_store else REPORT_TYPE_LABELS['products']
        ),
        'columns': columns,
        'rows': out_rows,
        'summary': summary,
    }


def _revenue_section(store_id, start, end):
    day = pht_sql_date(Order.created_at)
    daily = db.session.query(
        day.label('d'),
        func.count(Order.id).label('orders'),
        func.coalesce(func.sum(Order.total_amount), 0).label('rev'),
    ).filter(
        Order.store_id == store_id,
        _paid_order_status_filter(),
        Order.created_at >= start,
        Order.created_at < end,
    ).group_by(day).order_by(day).all()

    rows = []
    total_rev = 0.0
    total_orders = 0
    for r in daily:
        rev = float(r.rev or 0)
        oc = int(r.orders or 0)
        rows.append([
            r.d.strftime('%Y-%m-%d') if hasattr(r.d, 'strftime') else str(r.d),
            oc,
            rev,
            (rev / oc) if oc else 0.0,
        ])
        total_rev += rev
        total_orders += oc

    pos_rev = _pos_revenue(store_id, start, end)
    summary = [
        ('Online Revenue', peso(total_rev)),
        ('POS Revenue', peso(pos_rev)),
        ('Total Revenue', peso(total_rev + pos_rev)),
        ('Online Orders', f"{total_orders:,}"),
    ]
    return {
        'key': 'revenue',
        'title': REPORT_TYPE_LABELS['revenue'],
        'columns': ['Date', 'Orders', 'Revenue (₱)', 'Avg Order (₱)'],
        'rows': rows,
        'summary': summary,
    }


def _riders_section(store_id, start, end):
    riders = (Rider.query
              .options(joinedload(Rider.user))
              .filter(Rider.store_id == store_id)
              .order_by(Rider.created_at.asc())
              .all())
    rider_ids = [r.id for r in riders]
    period_orders = []
    if rider_ids:
        period_orders = (Order.query
                         .filter(Order.rider_id.in_(rider_ids),
                                 Order.created_at >= start,
                                 Order.created_at < end)
                         .all())
    orders_by_rider = defaultdict(list)
    for o in period_orders:
        orders_by_rider[o.rider_id].append(o)

    rows = []
    total_assigned = 0
    total_delivered = 0
    total_cancelled = 0
    on_time_values = []

    for rider in riders:
        rider_orders = orders_by_rider.get(rider.id, [])
        assigned = len(rider_orders)
        delivered_orders = [o for o in rider_orders if _is_paid_order_status(o.status)]
        cancelled = sum(1 for o in rider_orders if _order_status_key(o.status) == 'cancelled')

        delivery_minutes = []
        on_time = 0
        for o in delivered_orders:
            if o.delivered_at and o.confirmed_at:
                mins = (o.delivered_at - o.confirmed_at).total_seconds() / 60.0
                if mins >= 0:
                    delivery_minutes.append(mins)
                    if mins <= 60:
                        on_time += 1
            elif o.delivered_at and o.created_at:
                mins = (o.delivered_at - o.created_at).total_seconds() / 60.0
                if mins >= 0 and mins < 60 * 24 * 3:
                    delivery_minutes.append(mins)
                    if mins <= 90:
                        on_time += 1

        avg_minutes = round(sum(delivery_minutes) / len(delivery_minutes), 1) if delivery_minutes else 0.0
        on_time_rate = round((on_time / len(delivered_orders)) * 100, 1) if delivered_orders else 0.0
        status_label = 'Active' if rider.is_active else 'Inactive'

        rows.append([
            rider.user.full_name if rider.user else f"Rider #{rider.id}",
            _report_email(rider.user.email if rider.user else '', getattr(rider.user, 'phone', None) if rider.user else None),
            rider.vehicle_type or '-',
            assigned,
            len(delivered_orders),
            cancelled,
            on_time_rate,
            avg_minutes,
            status_label,
        ])

        total_assigned += assigned
        total_delivered += len(delivered_orders)
        total_cancelled += cancelled
        if delivered_orders:
            on_time_values.append(on_time_rate)

    summary = [
        ('Total Riders', f"{len(riders):,}"),
        ('Active Riders', f"{sum(1 for r in riders if r.is_active):,}"),
        ('Assigned Orders', f"{total_assigned:,}"),
        ('Delivered Orders', f"{total_delivered:,}"),
        ('Cancelled Orders', f"{total_cancelled:,}"),
        ('Avg On-time Rate', f"{(round(sum(on_time_values) / len(on_time_values), 1) if on_time_values else 0.0):.1f}%"),
    ]

    return {
        'key': 'riders',
        'title': REPORT_TYPE_LABELS['riders'],
        'columns': [
            'Rider', 'Email', 'Vehicle', 'Assigned Orders', 'Delivered',
            'Cancelled', 'On-time Rate (%)', 'Avg Delivery (min)', 'Status',
        ],
        'rows': rows,
        'summary': summary,
    }


def _year_end_section(store_id, start, end):
    """Executive yearly summary with KPIs and month-by-month performance."""
    online_rev = _online_revenue(store_id, start, end)
    pos_rev = _pos_revenue(store_id, start, end)
    total_rev = online_rev + pos_rev

    online_orders = _online_order_count(store_id, start, end)
    pos_orders = _pos_order_count(store_id, start, end)
    total_orders = online_orders + pos_orders
    avg_order = (total_rev / total_orders) if total_orders else 0.0

    new_customers = _new_customer_count(store_id, start, end)
    active_products = db.session.query(func.count(Product.id)).filter(
        Product.store_id == store_id,
        Product.is_archived.is_(False),
    ).scalar() or 0

    total_riders = db.session.query(func.count(Rider.id)).filter(
        Rider.store_id == store_id
    ).scalar() or 0
    active_riders = db.session.query(func.count(Rider.id)).filter(
        Rider.store_id == store_id,
        Rider.is_active.is_(True),
    ).scalar() or 0

    # Top customer by delivered-order spend
    top_customer_row = db.session.query(
        User.full_name,
        User.email,
        func.coalesce(func.sum(Order.total_amount), 0).label('spent'),
        func.count(Order.id).label('orders'),
    ).join(Order, Order.customer_id == User.id).filter(
        Order.store_id == store_id,
        _paid_order_status_filter(),
        Order.created_at >= start,
        Order.created_at < end,
    ).group_by(User.full_name, User.email) \
     .order_by(func.sum(Order.total_amount).desc()) \
     .first()

    top_customer_name = top_customer_row.full_name if top_customer_row else 'N/A'
    top_customer_spent = _to_float(top_customer_row.spent) if top_customer_row else 0.0

    # Top rider by delivered volume
    top_rider_row = db.session.query(
        User.full_name,
        func.count(Order.id).label('delivered_count'),
    ).join(Rider, Rider.user_id == User.id) \
     .join(Order, Order.rider_id == Rider.id) \
     .filter(
        Rider.store_id == store_id,
        _paid_order_status_filter(),
        Order.created_at >= start,
        Order.created_at < end,
     ).group_by(User.full_name) \
      .order_by(func.count(Order.id).desc()) \
      .first()
    top_rider_name = top_rider_row.full_name if top_rider_row else 'N/A'
    top_rider_delivered = int(top_rider_row.delivered_count or 0) if top_rider_row else 0

    # Top products snapshot
    top_products = _top_products(store_id, start, end, limit=3)
    top_products_label = ', '.join(p['name'] for p in top_products) if top_products else 'N/A'

    rows = [
        ['KPI', 'Total Revenue', total_rev, f"Online {peso(online_rev)} + POS {peso(pos_rev)}"],
        ['KPI', 'Total Orders', total_orders, f"Online {online_orders:,} + POS {pos_orders:,}"],
        ['KPI', 'Average Order Value', avg_order, 'Total revenue / total orders'],
        ['KPI', 'New Customers', new_customers, 'Customers placing their first order in period'],
        ['KPI', 'Active Products', active_products, 'Non-archived products in catalogue'],
        ['KPI', 'Active Riders', active_riders, f"{active_riders:,} active of {total_riders:,} total"],
        ['Highlight', 'Top Customer', top_customer_name, f"{peso(top_customer_spent)} in completed sales"],
        ['Highlight', 'Top Rider', top_rider_name, f"{top_rider_delivered:,} delivered/completed orders"],
        ['Highlight', 'Top Products', top_products_label, 'Top 3 by completed revenue'],
    ]

    # Month-by-month breakdown within selected range
    for month_label, b_start, b_end in _iter_pht_months(start, end):
        m_online_rev = _online_revenue(store_id, b_start, b_end)
        m_pos_rev = _pos_revenue(store_id, b_start, b_end)
        m_total_rev = m_online_rev + m_pos_rev
        m_orders = _online_order_count(store_id, b_start, b_end) + _pos_order_count(store_id, b_start, b_end)
        m_avg = (m_total_rev / m_orders) if m_orders else 0.0

        rows.append([
            'Month',
            month_label,
            m_total_rev,
            f"Orders {m_orders:,} · Avg {peso(m_avg)}",
        ])

    summary = [
        ('Total Revenue', peso(total_rev)),
        ('Total Orders', f"{total_orders:,}"),
        ('Avg Order', peso(avg_order)),
        ('New Customers', f"{new_customers:,}"),
        ('Active Riders', f"{active_riders:,}"),
    ]

    return {
        'key': 'year_end',
        'title': REPORT_TYPE_LABELS['year_end'],
        'columns': ['Section', 'Metric', 'Value', 'Details'],
        'rows': rows,
        'summary': summary,
    }


def build_report_payload(
    store: Store,
    types: Sequence[str],
    period: str = 'month',
    custom_from: Optional[str] = None,
    custom_to: Optional[str] = None,
) -> dict:
    """Resolve ``types`` into concrete sections, with date range metadata."""
    start, end, label = period_range(period, custom_from, custom_to)
    types = _normalise_types(types)

    builders = {
        'orders':    _orders_section,
        'customers': _customers_section,
        'products':  _products_section,
        'revenue':   _revenue_section,
        'riders':    _riders_section,
        'year_end':  _year_end_section,
    }

    sections = [builders[t](store.id, start, end) for t in types if t in builders]

    return {
        'store': store,
        'is_admin': False,
        'period': period,
        'period_label': label,
        'period_start': start,
        'period_end': end,
        'types': types,
        'generated_at': datetime.now(PHT).strftime('%b %d, %Y %I:%M %p PHT'),
        'sections': sections,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PDF rendering (reportlab)
# ─────────────────────────────────────────────────────────────────────────────

def render_pdf(payload: dict) -> bytes:
    """Render a payload from :func:`build_report_payload` into a PDF (bytes)."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, HRFlowable, Image as RLImage,
    )
    from reportlab.graphics.shapes import Drawing, Circle, String
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from xml.sax.saxutils import escape as _xml_escape

    MAROON = colors.HexColor('#8F1738')
    TEXT = colors.HexColor('#222222')
    MUTED = colors.HexColor('#666666')
    BORDER = colors.HexColor('#E5E5E5')
    WHITE = colors.HexColor('#FFFFFF')
    ZEBRA = colors.HexColor('#FAFAFA')

    STATUS_PILLS = {
        'cancelled': ('#FDECEC', '#B42318'),
        'preparing': ('#FEF4E6', '#B54708'),
        'pending': ('#F5F5F5', '#666666'),
        'accepted': ('#FEF4E6', '#B54708'),
        'done preparing': ('#E8F1FB', '#175CD3'),
        'on delivery': ('#F3EEF9', '#6941C6'),
        'delivered': ('#EAF6EE', '#067647'),
        'completed': ('#EAF6EE', '#067647'),
        'available': ('#EAF6EE', '#067647'),
        'low stock': ('#FEF9C3', '#854D0E'),
        'out of stock': ('#FDECEC', '#B42318'),
    }
    PAYMENT_PILLS = {
        'cod pending': ('#FEF4E6', '#B54708'),
        'cod approved': ('#EAF6EE', '#067647'),
        'verified': ('#E8F1FB', '#175CD3'),
        'pending': ('#FEF4E6', '#B54708'),
        'paid': ('#EAF6EE', '#067647'),
        'unpaid': ('#FDECEC', '#B42318'),
        'failed': ('#FDECEC', '#B42318'),
    }

    store: Store = payload['store']
    sections = payload['sections']
    period_label = payload['period_label']
    requested_by = (payload.get('requested_by') or '').strip() or 'Unknown user'

    buf = io.BytesIO()
    max_cols = max((len(s.get('columns') or []) for s in sections), default=0)
    page_size = landscape(A4) if max_cols >= 7 else A4
    page_w, page_h = page_size
    doc = SimpleDocTemplate(
        buf,
        pagesize=page_size,
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=20 * mm,
        title='E-FLORA Business Report',
        author='E-FLORA',
    )
    content_w = doc.width

    base = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'EFloraTitle', parent=base['Normal'],
        fontName='Helvetica-Bold', fontSize=18,
        textColor=TEXT, spaceAfter=0, leading=22, alignment=TA_LEFT,
        wordWrap='LTR', splitLongWords=0,
    )
    meta_label_style = ParagraphStyle(
        'EFloraMetaLabel', parent=base['Normal'],
        fontName='Helvetica-Bold', fontSize=8, textColor=TEXT, leading=11, spaceAfter=0,
        wordWrap='LTR', splitLongWords=0,
    )
    meta_value_style = ParagraphStyle(
        'EFloraMetaValue', parent=base['Normal'],
        fontName='Helvetica', fontSize=9, textColor=MUTED, leading=12, spaceAfter=6,
        wordWrap='LTR', splitLongWords=1,
    )
    section_style = ParagraphStyle(
        'EFloraSection', parent=base['Heading2'],
        fontName='Helvetica-Bold', fontSize=14,
        textColor=MAROON, spaceBefore=0, spaceAfter=8, leading=18,
    )
    kpi_label_style = ParagraphStyle(
        'EFloraKpiLabel', parent=base['Normal'],
        fontName='Helvetica', fontSize=6.8, textColor=MUTED,
        alignment=TA_CENTER, leading=9, spaceAfter=3,
        wordWrap='LTR', splitLongWords=0,
    )
    kpi_value_style = ParagraphStyle(
        'EFloraKpiValue', parent=base['Normal'],
        fontName='Helvetica-Bold', fontSize=11, textColor=TEXT,
        alignment=TA_CENTER, leading=14, splitLongWords=0, wordWrap='LTR',
    )
    kpi_value_emphasis = ParagraphStyle(
        'EFloraKpiValueEm', parent=kpi_value_style,
        textColor=MAROON, fontSize=12,
    )
    empty_style = ParagraphStyle(
        'EFloraEmpty', parent=base['Italic'],
        fontName='Helvetica-Oblique', fontSize=9, textColor=MUTED, spaceAfter=10,
    )
    header_cell_style = ParagraphStyle(
        'EFloraHeaderCell', parent=base['Normal'],
        fontName='Helvetica-Bold', fontSize=7.2,
        textColor=WHITE, leading=9.2, wordWrap='LTR', splitLongWords=0,
    )
    body_cell_left = ParagraphStyle(
        'EFloraBodyLeft', parent=base['Normal'],
        fontName='Helvetica', fontSize=7.5, textColor=TEXT, leading=9.6,
        wordWrap='LTR', splitLongWords=1, alignment=TA_LEFT,
    )
    body_cell_center = ParagraphStyle(
        'EFloraBodyCenter', parent=body_cell_left, alignment=TA_CENTER,
    )
    body_cell_right = ParagraphStyle(
        'EFloraBodyRight', parent=body_cell_left, alignment=TA_RIGHT,
        fontName='Helvetica',
    )
    pill_style = ParagraphStyle(
        'EFloraPill', parent=base['Normal'],
        fontName='Helvetica-Bold', fontSize=6.4, leading=8.2, alignment=TA_CENTER,
        wordWrap='LTR', splitLongWords=0,
    )

    story = []

    def _load_pdf_image(source: Optional[str], max_w: float, max_h: float):
        if not source:
            return None
        try:
            if str(source).startswith(('http://', 'https://')):
                data = urlopen(source, timeout=8).read()
                img = RLImage(io.BytesIO(data))
            else:
                if not os.path.exists(source):
                    return None
                img = RLImage(source)
            iw, ih = img.wrap(0, 0)
            if not iw or not ih:
                return None
            scale = min(max_w / iw, max_h / ih)
            img.drawWidth = iw * scale
            img.drawHeight = ih * scale
            return img
        except Exception:
            return None

    def _pdf_plain(value) -> str:
        """Helvetica has no peso glyph; a missing-glyph box looked like a maroon square."""
        return str(value if value is not None else '').replace('\u20b1', 'PHP ').replace('₱', 'PHP ')

    def _pill(text: str, kind: str):
        key = (text or '').replace('_', ' ').strip().lower()
        mapping = PAYMENT_PILLS if kind == 'payment' else STATUS_PILLS
        bg, fg = mapping.get(key, ('#F5F5F5', '#666666'))
        label = (text or '').replace('_', ' ').strip() or '—'
        para = Paragraph(
            f'<font color="{fg}">{_xml_escape(label)}</font>',
            pill_style,
        )
        t = Table([[para]])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(bg)),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 1.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        return t

    def _col_kind(header_name: str) -> str:
        h = (header_name or '').lower()
        if 'payment status' in h:
            return 'payment_status'
        if h.strip() in ('status',) or (h.endswith(' status') and 'payment' not in h):
            return 'status'
        if 'date' in h:
            return 'datetime'
        if 'joined' in h or 'last order' in h:
            return 'date'
        if h.strip() in ('type',):
            return 'center'
        if any(k in h for k in ('amount', 'revenue', 'price', 'total', 'spent', 'avg', 'aov')):
            return 'amount'
        if h.strip() in ('items',) or any(k in h for k in ('qty', 'count', 'units sold', 'stock')):
            return 'center'
        if 'payment' in h and 'status' not in h:
            return 'center'
        return 'left'

    def _format_cell_text(cell, kind: str = 'left') -> str:
        is_number = isinstance(cell, (int, float, Decimal)) and not isinstance(cell, bool)
        if kind == 'amount' and is_number:
            return f"{float(cell):,.2f}"
        if isinstance(cell, float):
            return f"{cell:,.2f}"
        if isinstance(cell, Decimal):
            return f"{float(cell):,.2f}"
        if isinstance(cell, int) and not isinstance(cell, bool):
            return f"{cell:,}"
        text = _pdf_plain(cell)
        if '@sms.eflora.internal' in text.lower():
            return _report_email(text)
        return text

    default_system_logo = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', 'static', 'images', 'eflora-flower-logo.png')
    )
    system_logo_src = payload.get('system_logo_path')
    if not system_logo_src and os.path.exists(default_system_logo):
        system_logo_src = default_system_logo
    logo = _load_pdf_image(system_logo_src, 28, 28)
    if logo is None:
        logo = Drawing(24, 24)
        logo.add(Circle(12, 12, 11, fillColor=colors.HexColor('#F8E8EC'),
                        strokeColor=MAROON, strokeWidth=0.8))
        logo.add(String(12, 8.5, 'EF', fontName='Helvetica-Bold', fontSize=8,
                        fillColor=MAROON, textAnchor='middle'))

    store_logo_src = payload.get('store_logo_url') or getattr(store, 'logo_url', None)
    store_logo = _load_pdf_image(store_logo_src, 28, 28)

    title_text = 'E-FLORA — Business Report'
    title_w = stringWidth(title_text, 'Helvetica-Bold', 18) + 20
    eflora_col = 36
    store_col = 36 if store_logo else 0
    header_cols = [logo, Paragraph('E-FLORA&nbsp;—&nbsp;Business&nbsp;Report', title_style)]
    header_widths = [eflora_col, title_w]
    if store_logo:
        header_cols.append(store_logo)
        header_widths.append(store_col)
    header_tbl = Table([header_cols], colWidths=header_widths, hAlign='LEFT')
    header_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (0, 0), 8),
        ('RIGHTPADDING', (1, 0), (1, 0), 8 if store_logo else 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(header_tbl)
    story.append(HRFlowable(width='100%', thickness=0.6, color=BORDER, spaceAfter=12, spaceBefore=0))

    if payload.get('is_admin'):
        label_map = dict(REPORT_TYPE_LABELS)
        label_map.update(ADMIN_REPORT_TYPE_LABELS)
    else:
        label_map = dict(REPORT_TYPE_LABELS)
    type_labels = [
        label_map.get(t, str(t).replace('_', ' ').title()) for t in payload['types']
    ] or ['All']
    type_chunks = [', '.join(type_labels[i:i + 2]) for i in range(0, len(type_labels), 2)]
    type_names_html = '<br/>'.join(_xml_escape(chunk) for chunk in type_chunks)
    generated_pht = payload.get('generated_at') or datetime.now(PHT).strftime('%b %d, %Y %I:%M %p PHT')
    store_name = getattr(store, 'name', None) or 'All Stores'

    def _meta_col(pairs, width):
        rows = []
        for label, value, is_html in pairs:
            rows.append([Paragraph(_xml_escape(label), meta_label_style)])
            rows.append([
                Paragraph(value if is_html else _xml_escape(_pdf_plain(value)), meta_value_style)
            ])
        t = Table(rows, colWidths=[width])
        t.setStyle(TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        return t

    meta_left = _meta_col(
        [
            ('Store', store_name, False),
            ('Period', period_label, False),
            ('Section', type_names_html, True),
        ],
        content_w * 0.58,
    )
    meta_right = _meta_col(
        [
            ('Generated by', requested_by, False),
            ('Generated', generated_pht, False),
        ],
        content_w * 0.42,
    )
    meta_tbl = Table(
        [[meta_left, meta_right]],
        colWidths=[content_w * 0.58, content_w * 0.42],
        hAlign='LEFT',
    )
    meta_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (0, 0), 16),
        ('RIGHTPADDING', (1, 0), (1, 0), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 10))

    for idx, sec in enumerate(sections):
        if idx > 0:
            story.append(PageBreak())

        story.append(Paragraph(_xml_escape(_pdf_plain(sec['title'])), section_style))
        story.append(Spacer(1, 6))

        summary = sec.get('summary') or []
        if summary:
            def _kpi_label_html(raw_label):
                text = _pdf_plain(raw_label)
                if '(' in text and len(text) > 16:
                    head, rest = text.split('(', 1)
                    return f'{_xml_escape(head.strip())}<br/>({_xml_escape(rest)}'
                return _xml_escape(text)

            def _kpi_chunks(items):
                per_row = 6 if content_w > 620 else 4
                n = len(items)
                if n <= per_row:
                    return [items]
                mid = (n + 1) // 2
                return [items[:mid], items[mid:]]

            def _kpi_style(n_cols):
                cmds = [
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('BOX', (0, 0), (-1, -1), 0.6, BORDER),
                    ('TOPPADDING', (0, 0), (-1, -1), 7),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
                    ('LEFTPADDING', (0, 0), (-1, -1), 3),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 3),
                    ('BACKGROUND', (0, 0), (-1, -1), WHITE),
                ]
                for i in range(n_cols - 1):
                    cmds.append(('LINEAFTER', (i, 0), (i, 0), 0.5, BORDER))
                return TableStyle(cmds)

            for chunk in _kpi_chunks(summary):
                kpi_cols = []
                for k, v in chunk:
                    value_style = kpi_value_emphasis if 'revenue' in str(k).lower() else kpi_value_style
                    kpi_cols.append([
                        Paragraph(_kpi_label_html(k), kpi_label_style),
                        Paragraph(_xml_escape(_pdf_plain(v)), value_style),
                    ])
                n = len(kpi_cols)
                kpi_tbl = Table([kpi_cols], colWidths=[content_w / n] * n, hAlign='LEFT')
                kpi_tbl.setStyle(_kpi_style(n))
                story.append(kpi_tbl)
            story.append(Spacer(1, 12))

        rows = sec['rows']
        if not rows:
            story.append(Paragraph('No data found for this period.', empty_style))
            continue

        header = sec['columns']
        kinds = [_col_kind(h) for h in header]
        formatted_rows = [
            [_format_cell_text(c, kinds[i] if i < len(kinds) else 'left') for i, c in enumerate(r)]
            for r in rows
        ]

        def _datetime_html(text):
            raw = (text or '').strip()
            parts = raw.rsplit(' ', 2)
            if len(parts) == 3 and ':' in parts[1] and parts[2].upper() in ('AM', 'PM'):
                return f'{_xml_escape(parts[0])}<br/>{_xml_escape(parts[1] + " " + parts[2])}'
            return _xml_escape(raw)

        def _body_cell(text, kind):
            if kind == 'status':
                return _pill(text, 'status')
            if kind == 'payment_status':
                return _pill(text, 'payment')
            if kind == 'datetime':
                return Paragraph(_datetime_html(text), body_cell_left)
            if kind == 'amount':
                return Paragraph(_xml_escape(text), body_cell_right)
            if kind == 'center':
                return Paragraph(_xml_escape(text), body_cell_center)
            return Paragraph(_xml_escape(text), body_cell_left)

        wrapped_header = []
        for h, kind in zip(header, kinds):
            st = ParagraphStyle(
                'hdr_' + kind, parent=header_cell_style,
                alignment=TA_RIGHT if kind == 'amount' else (TA_CENTER if kind in ('center', 'status', 'payment_status') else TA_LEFT),
            )
            raw_h = _pdf_plain(h)
            if ' / ' in raw_h:
                header_html = '<br/>'.join(_xml_escape(p) for p in raw_h.split(' / '))
            elif '(' in raw_h and raw_h.endswith(')'):
                head, rest = raw_h.rsplit('(', 1)
                header_html = f'{_xml_escape(head.strip())}<br/>({_xml_escape(rest)}'
            elif ' ' in raw_h and len(raw_h) > 12:
                header_html = _xml_escape(raw_h)
            else:
                header_html = _xml_escape(raw_h).replace(' ', '&nbsp;')
            wrapped_header.append(Paragraph(header_html, st))

        wrapped_rows = [
            [_body_cell(c, kinds[i] if i < len(kinds) else 'left') for i, c in enumerate(row)]
            for row in formatted_rows
        ]
        table_data = [wrapped_header] + wrapped_rows

        def _measure(text, font='Helvetica', size=7.5):
            return stringWidth(str(text or '')[:60], font, size)

        col_count = max(1, len(header))
        sample_rows = formatted_rows[:80]
        pad = 10
        mins, ideals = [], []
        for i in range(col_count):
            h = str(header[i]) if i < len(header) else ''
            hlow = h.lower()
            kind = kinds[i] if i < len(kinds) else 'left'
            min_w = 38
            if kind in ('status', 'payment_status'):
                min_w = 58
            elif kind == 'amount':
                min_w = 50
            elif kind == 'datetime':
                min_w = 70
            elif 'date' in hlow or 'joined' in hlow or 'last order' in hlow:
                min_w = 68
            elif 'order id' in hlow:
                min_w = 42
            elif 'add-on' in hlow or 'variant' in hlow:
                min_w = 110
            elif 'customer' in hlow or 'email' in hlow:
                min_w = 68
            elif 'product' in hlow:
                min_w = 72
            elif 'payment' in hlow:
                min_w = 44
            elif hlow.strip() in ('items', 'stock', 'type'):
                min_w = 32

            header_w = _measure(_pdf_plain(h).replace(' / ', '/'), 'Helvetica-Bold', 7.2) + pad
            body_w = 0
            cap = 28 if ('add-on' in hlow or 'variant' in hlow or 'customer' in hlow or 'product' in hlow) else 18
            for r in sample_rows:
                if i < len(r):
                    body_w = max(body_w, _measure(r[i][:cap]))
            ideal = min(max(min_w, header_w, body_w + pad), 150)
            mins.append(min_w)
            ideals.append(ideal)

        total_ideal = sum(ideals) or float(col_count)
        if total_ideal <= content_w:
            extra = content_w - total_ideal
            grow = [
                i for i, (kind, h) in enumerate(zip(kinds, header))
                if kind == 'left' or 'add-on' in str(h).lower() or 'variant' in str(h).lower()
                or 'customer' in str(h).lower() or 'product' in str(h).lower()
            ]
            if not grow:
                grow = list(range(col_count))
            add = extra / len(grow)
            col_sizes = list(ideals)
            for i in grow:
                col_sizes[i] += add
        else:
            scale = content_w / total_ideal
            col_sizes = [max(mins[i] * 0.85, ideals[i] * scale) for i in range(col_count)]
            col_sizes[-1] += content_w - sum(col_sizes)

        tight = col_count >= 8
        table = Table(table_data, colWidths=col_sizes, repeatRows=1, hAlign='LEFT')
        table_cmds = [
            ('BACKGROUND', (0, 0), (-1, 0), MAROON),
            ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 7.0 if tight else 7.4),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('TOPPADDING', (0, 0), (-1, 0), 6),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, ZEBRA]),
            ('LINEBELOW', (0, 0), (-1, -2), 0.4, BORDER),
            ('LINEBELOW', (0, -1), (-1, -1), 0.4, BORDER),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 3 if tight else 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3 if tight else 4),
            ('TOPPADDING', (0, 1), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ]
        for i, kind in enumerate(kinds):
            if kind == 'amount':
                table_cmds.append(('ALIGN', (i, 0), (i, -1), 'RIGHT'))
            elif kind in ('center', 'status', 'payment_status'):
                table_cmds.append(('ALIGN', (i, 0), (i, -1), 'CENTER'))
        table.setStyle(TableStyle(table_cmds))
        story.append(table)

    if not sections:
        story.append(Paragraph('No report types selected.', empty_style))

    footer_logo = _load_pdf_image(system_logo_src, 12, 12)

    def _footer(canvas, doc_):
        canvas.saveState()
        y = 12 * mm
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(doc.leftMargin, y + 8 * mm, page_w - doc.rightMargin, y + 8 * mm)
        if footer_logo:
            footer_logo.wrapOn(canvas, 12, 12)
            footer_logo.drawOn(canvas, doc.leftMargin, y + 0.5 * mm)
            text_x = doc.leftMargin + 16
        else:
            text_x = doc.leftMargin
        canvas.setFillColor(TEXT)
        canvas.setFont('Helvetica-Bold', 7)
        canvas.drawString(text_x, y + 3.2 * mm, 'E-FLORA')
        canvas.setFillColor(MUTED)
        canvas.setFont('Helvetica', 6.5)
        canvas.drawString(text_x, y + 0.2 * mm, 'Business Report')
        canvas.setFont('Helvetica', 6.2)
        canvas.drawRightString(
            page_w - doc.rightMargin, y + 3.2 * mm,
            'This report was generated automatically.',
        )
        canvas.drawRightString(
            page_w - doc.rightMargin, y + 0.2 * mm,
            f'For questions, contact your system administrator at efloralaguna@gmail.com.   Page {doc_.page}',
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# CSV rendering
# ─────────────────────────────────────────────────────────────────────────────

def _section_to_csv_bytes(section: dict) -> bytes:
    """Serialize a single section into UTF-8 CSV bytes (with BOM for Excel)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([f"# {section['title']}"])
    for k, v in section.get('summary', []):
        writer.writerow([f"# {k}", v])
    writer.writerow([])
    writer.writerow(section['columns'])
    for row in section['rows']:
        writer.writerow([
            f"{cell:.2f}" if isinstance(cell, (float, Decimal)) else cell
            for cell in row
        ])
    # \ufeff = BOM so Excel auto-detects UTF-8 + the peso symbol
    return ('\ufeff' + buf.getvalue()).encode('utf-8')


def render_csv_bundle(payload: dict) -> Tuple[str, bytes, str]:
    """Return ``(filename, bytes, mime_type)``.

    * 1 section ⇒ ``foo.csv`` (text/csv)
    * 2+ sections ⇒ ``eflora_reports.zip`` (application/zip)
    """
    sections = payload.get('sections', [])
    timestamp = datetime.now(PHT).strftime('%Y%m%d_%H%M')

    if len(sections) == 1:
        sec = sections[0]
        filename = f"eflora_{sec['key']}_{timestamp}.csv"
        return filename, _section_to_csv_bytes(sec), 'text/csv'

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for sec in sections:
            zf.writestr(f"eflora_{sec['key']}_{timestamp}.csv", _section_to_csv_bytes(sec))
    return f"eflora_reports_{timestamp}.zip", buf.getvalue(), 'application/zip'


# ═════════════════════════════════════════════════════════════════════════════
# ADMIN / PLATFORM-WIDE BUILDERS
# ─────────────────────────────────────────────────────────────────────────────
# These mirror the seller helpers above but aggregate across *all* stores so
# the same templates (`analytics.html`, `reports.html`) can be reused for the
# admin role. Output shape is intentionally identical to the seller versions
# so no template changes are needed beyond minor labelling tweaks.
# ═════════════════════════════════════════════════════════════════════════════

class AdminScope:
    """Lightweight stand-in for a ``Store`` row used by admin views.

    Templates and the PDF renderer only need ``.id`` and ``.name``; this stub
    keeps the rest of the pipeline untouched while making the page header read
    "All Stores" instead of a single shop name.
    """

    __slots__ = ('id', 'name', 'description', 'logo_url')

    def __init__(self, name: str = 'All Stores'):
        self.id = None
        self.name = name
        self.description = 'Platform-wide aggregate'
        self.logo_url = None


# ── Platform-wide query helpers (no store_id filter) ────────────────────────

def _platform_online_revenue(start, end) -> float:
    total = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(
        _paid_order_status_filter(),
        Order.created_at >= start,
        Order.created_at < end,
    ).scalar()
    return _to_float(total)


def _platform_pos_revenue(start, end) -> float:
    total = db.session.query(
        func.coalesce(func.sum(POSOrder.total_amount), 0)
    ).filter(
        POSOrder.created_at >= start,
        POSOrder.created_at < end,
    ).scalar()
    return _to_float(total)


def _platform_online_order_count(start, end) -> int:
    return db.session.query(func.count(Order.id)).filter(
        Order.created_at >= start,
        Order.created_at < end,
    ).scalar() or 0


def _platform_completed_online_order_count(start, end) -> int:
    return db.session.query(func.count(Order.id)).filter(
        _paid_order_status_filter(),
        Order.created_at >= start,
        Order.created_at < end,
    ).scalar() or 0


def _platform_pos_order_count(start, end) -> int:
    return db.session.query(func.count(POSOrder.id)).filter(
        POSOrder.created_at >= start,
        POSOrder.created_at < end,
    ).scalar() or 0


def _platform_new_customer_count(start, end) -> int:
    """Customers whose *very first* online order falls in the period."""
    first_orders = db.session.query(
        Order.customer_id,
        func.min(Order.created_at).label('first_order'),
    ).group_by(Order.customer_id).subquery()

    return db.session.query(func.count(first_orders.c.customer_id)).filter(
        first_orders.c.first_order >= start,
        first_orders.c.first_order < end,
    ).scalar() or 0


def _platform_top_products(start, end, limit=5):
    """Top products by completed online + POS revenue in [start, end)."""
    from app.models import ProductVariant
    online_rows = db.session.query(
        Product.id,
        Product.name,
        ProductVariant.id.label('variant_id'),
        ProductVariant.name.label('variant_name'),
        Category.name.label('category_name'),
        func.coalesce(func.sum(OrderItem.quantity), 0).label('qty'),
        func.coalesce(func.sum(OrderItem.quantity * OrderItem.price), 0).label('revenue'),
    ).join(OrderItem, OrderItem.product_id == Product.id) \
     .join(Order, Order.id == OrderItem.order_id) \
     .outerjoin(ProductVariant, ProductVariant.id == OrderItem.variant_id) \
     .outerjoin(Category, Category.id == Product.main_category_id) \
     .filter(
        _paid_order_status_filter(),
        Order.created_at >= start,
        Order.created_at < end,
     ).group_by(Product.id, Product.name, ProductVariant.id, ProductVariant.name, Category.name).all()

    pos_rows = db.session.query(
        Product.id,
        Product.name,
        ProductVariant.id.label('variant_id'),
        ProductVariant.name.label('variant_name'),
        Category.name.label('category_name'),
        func.coalesce(func.sum(POSOrderItem.quantity), 0).label('qty'),
        func.coalesce(func.sum(POSOrderItem.quantity * POSOrderItem.price), 0).label('revenue'),
    ).join(POSOrderItem, POSOrderItem.product_id == Product.id) \
     .join(POSOrder, POSOrder.id == POSOrderItem.pos_order_id) \
     .outerjoin(ProductVariant, ProductVariant.id == POSOrderItem.variant_id) \
     .outerjoin(Category, Category.id == Product.main_category_id) \
     .filter(
        POSOrder.created_at >= start,
        POSOrder.created_at < end,
     ).group_by(Product.id, Product.name, ProductVariant.id, ProductVariant.name, Category.name).all()

    merged = {}
    for r in list(online_rows) + list(pos_rows):
        key = (int(r.id), int(r.variant_id) if r.variant_id else None)
        entry = merged.setdefault(key, {
            'id': r.id,
            'name': f"{r.name} — {r.variant_name}" if r.variant_name else r.name,
            'category': r.category_name or 'Uncategorized',
            'quantity': 0,
            'revenue': 0.0,
        })
        entry['quantity'] += int(r.qty or 0)
        entry['revenue'] += _to_float(r.revenue)

    out = sorted(merged.values(), key=lambda x: x['revenue'], reverse=True)
    return out[:limit]


def _platform_top_stores(start, end, limit=5):
    """Top stores by completed online + POS revenue in [start, end)."""
    online_rows = db.session.query(
        Store.id,
        Store.name,
        func.coalesce(func.sum(Order.total_amount), 0).label('revenue'),
        func.count(Order.id).label('orders'),
    ).join(Order, Order.store_id == Store.id) \
     .filter(
        _paid_order_status_filter(),
        Order.created_at >= start,
        Order.created_at < end,
     ).group_by(Store.id, Store.name).all()

    pos_rows = db.session.query(
        Store.id,
        Store.name,
        func.coalesce(func.sum(POSOrder.total_amount), 0).label('revenue'),
        func.count(POSOrder.id).label('orders'),
    ).join(POSOrder, POSOrder.store_id == Store.id) \
     .filter(
        POSOrder.created_at >= start,
        POSOrder.created_at < end,
     ).group_by(Store.id, Store.name).all()

    merged = {}
    for r in online_rows:
        merged[int(r.id)] = {
            'id': r.id,
            'name': r.name,
            'revenue': _to_float(r.revenue),
            'orders': int(r.orders or 0),
        }
    for r in pos_rows:
        entry = merged.setdefault(int(r.id), {
            'id': r.id,
            'name': r.name,
            'revenue': 0.0,
            'orders': 0,
        })
        entry['revenue'] += _to_float(r.revenue)
        entry['orders'] += int(r.orders or 0)

    rows = sorted(merged.values(), key=lambda x: x['revenue'], reverse=True)[:limit]

    # Store.logo_url is a Python @property (not a SQL column), so resolve it
    # after the aggregate query using ORM instances.
    store_ids = [int(r['id']) for r in rows]
    store_map = {}
    if store_ids:
        for s in Store.query.filter(Store.id.in_(store_ids)).all():
            store_map[s.id] = s

    return [{
        'id': r['id'],
        'name': r['name'],
        'logo_url': (store_map.get(r['id']).logo_url if store_map.get(r['id']) else None),
        'revenue': r['revenue'],
        'orders': r['orders'],
    } for r in rows]


def _platform_order_status_breakdown(start, end):
    rows = db.session.query(
        Order.status,
        func.count(Order.id),
    ).filter(
        Order.created_at >= start,
        Order.created_at < end,
    ).group_by(Order.status).all()

    out = OrderedDict([
        ('delivered', 0),
        ('on_delivery', 0),
        ('preparing', 0),
        ('pending', 0),
        ('cancelled', 0),
    ])
    # Fold less-common statuses into the five chart buckets analytics.html expects.
    fold = {
        'completed': 'delivered',
        'accepted': 'preparing',
        'done_preparing': 'preparing',
    }
    for status, count in rows:
        key = (status or 'pending').lower()
        key = fold.get(key, key)
        if key not in out:
            key = 'pending'
        out[key] = (out.get(key) or 0) + int(count or 0)
    return out


def _platform_sales_by_category(start, end):
    online_rows = db.session.query(
        Category.name,
        func.coalesce(func.sum(OrderItem.quantity), 0).label('qty'),
        func.coalesce(func.sum(OrderItem.quantity * OrderItem.price), 0).label('revenue'),
    ).join(Product, Product.main_category_id == Category.id) \
     .join(OrderItem, OrderItem.product_id == Product.id) \
     .join(Order, Order.id == OrderItem.order_id) \
     .filter(
        _paid_order_status_filter(),
        Order.created_at >= start,
        Order.created_at < end,
     ).group_by(Category.name) \
      .all()

    pos_rows = db.session.query(
        Category.name,
        func.coalesce(func.sum(POSOrderItem.quantity), 0).label('qty'),
        func.coalesce(func.sum(POSOrderItem.quantity * POSOrderItem.price), 0).label('revenue'),
    ).join(Product, POSOrderItem.product_id == Product.id) \
     .outerjoin(Category, Category.id == Product.main_category_id) \
     .join(POSOrder, POSOrder.id == POSOrderItem.pos_order_id) \
     .filter(
        POSOrder.created_at >= start,
        POSOrder.created_at < end,
     ).group_by(Category.name) \
      .all()

    merged = {}
    for row in online_rows:
        key = row[0] or 'Uncategorized'
        merged.setdefault(key, {
            'name': key,
            'online_qty': 0,
            'online_revenue': 0.0,
            'pos_qty': 0,
            'pos_revenue': 0.0,
            'revenue': 0.0,
        })
        merged[key]['online_qty'] += int(row[1] or 0)
        merged[key]['online_revenue'] += _to_float(row[2])

    for row in pos_rows:
        key = row[0] or 'Uncategorized'
        merged.setdefault(key, {
            'name': key,
            'online_qty': 0,
            'online_revenue': 0.0,
            'pos_qty': 0,
            'pos_revenue': 0.0,
            'revenue': 0.0,
        })
        merged[key]['pos_qty'] += int(row[1] or 0)
        merged[key]['pos_revenue'] += _to_float(row[2])

    out = []
    for entry in merged.values():
        entry['revenue'] = entry['online_revenue'] + entry['pos_revenue']
        out.append(entry)
    out.sort(key=lambda x: x['revenue'], reverse=True)
    return out


def _platform_peak_hours(start, end):
    """Order volume by Philippine local time, in equal 2-hour windows (online + POS)."""
    by_hour = _merge_hour_rows(
        _hour_counts_for_orders(start, end),
        _hour_counts_for_pos(start, end),
    )
    return _peak_hours_from_counts(by_hour)


def _platform_revenue_series(start, end):
    """Daily completed online + POS revenue, bucketed by Philippine calendar day."""
    days = (end - start).days or 1
    if days > 31:
        return _platform_bucketed_revenue(start, end, buckets=12)

    online_rows = db.session.query(Order.created_at, Order.total_amount).filter(
        _paid_order_status_filter(),
        Order.created_at >= start,
        Order.created_at < end,
    ).all()
    pos_rows = db.session.query(POSOrder.created_at, POSOrder.total_amount).filter(
        POSOrder.created_at >= start,
        POSOrder.created_at < end,
    ).all()

    online_by_day = defaultdict(lambda: [0.0, 0])
    for ts, amt in online_rows:
        d = _pht_date(ts)
        if d:
            online_by_day[d][0] += _to_float(amt)
            online_by_day[d][1] += 1

    pos_by_day = defaultdict(lambda: [0.0, 0])
    for ts, amt in pos_rows:
        d = _pht_date(ts)
        if d:
            pos_by_day[d][0] += _to_float(amt)
            pos_by_day[d][1] += 1

    labels, revenues, order_counts = [], [], []
    online_revenues, pos_revenues = [], []
    online_orders, pos_orders = [], []
    for cur in _iter_pht_days(start, end):
        o_rev, o_cnt = online_by_day.get(cur, [0.0, 0])
        p_rev, p_cnt = pos_by_day.get(cur, [0.0, 0])
        labels.append(cur.strftime('%b %d'))
        revenues.append(o_rev + p_rev)
        order_counts.append(o_cnt + p_cnt)
        online_revenues.append(o_rev)
        pos_revenues.append(p_rev)
        online_orders.append(o_cnt)
        pos_orders.append(p_cnt)
    return {
        'labels': labels,
        'revenue': revenues,
        'orders': order_counts,
        'online_revenue': online_revenues,
        'pos_revenue': pos_revenues,
        'online_orders': online_orders,
        'pos_orders': pos_orders,
    }


def _platform_bucketed_revenue(start, end, buckets=12):
    span = (end - start).total_seconds()
    if span <= 0:
        return {
            'labels': [],
            'revenue': [],
            'orders': [],
            'online_revenue': [],
            'pos_revenue': [],
            'online_orders': [],
            'pos_orders': [],
        }
    step = span / buckets
    edges = [start + timedelta(seconds=step * i) for i in range(buckets + 1)]

    online_rows = db.session.query(
        Order.created_at,
        Order.total_amount,
    ).filter(
        _paid_order_status_filter(),
        Order.created_at >= start,
        Order.created_at < end,
    ).all()

    pos_rows = db.session.query(
        POSOrder.created_at,
        POSOrder.total_amount,
    ).filter(
        POSOrder.created_at >= start,
        POSOrder.created_at < end,
    ).all()

    online_rev = [0.0] * buckets
    online_cnt = [0] * buckets
    pos_rev = [0.0] * buckets
    pos_cnt = [0] * buckets

    for ts, amt in online_rows:
        for i in range(buckets):
            if edges[i] <= ts < edges[i + 1]:
                online_rev[i] += _to_float(amt)
                online_cnt[i] += 1
                break

    for ts, amt in pos_rows:
        for i in range(buckets):
            if edges[i] <= ts < edges[i + 1]:
                pos_rev[i] += _to_float(amt)
                pos_cnt[i] += 1
                break

    rev = [online_rev[i] + pos_rev[i] for i in range(buckets)]
    cnt = [online_cnt[i] + pos_cnt[i] for i in range(buckets)]
    labels = [edges[i].strftime('%b %d') for i in range(buckets)]
    return {
        'labels': labels,
        'revenue': rev,
        'orders': cnt,
        'online_revenue': online_rev,
        'pos_revenue': pos_rev,
        'online_orders': online_cnt,
        'pos_orders': pos_cnt,
    }


def _measure_order_delivery(o):
    """Return (minutes, on_time_threshold_minutes) or (None, None) if unmeasurable."""
    if not getattr(o, 'delivered_at', None):
        return None, None
    if o.confirmed_at:
        mins = (o.delivered_at - o.confirmed_at).total_seconds() / 60.0
        if mins >= 0:
            return mins, 60.0
    elif o.created_at:
        mins = (o.delivered_at - o.created_at).total_seconds() / 60.0
        if mins >= 0 and mins < 60 * 24 * 3:
            return mins, 90.0
    return None, None


def _platform_delivery_performance(start, end):
    fulfilled = db.session.query(Order).filter(
        _paid_order_status_filter(),
        Order.created_at >= start,
        Order.created_at < end,
    ).all()

    cancelled = db.session.query(func.count(Order.id)).filter(
        Order.status == 'cancelled',
        Order.created_at >= start,
        Order.created_at < end,
    ).scalar() or 0

    total = db.session.query(func.count(Order.id)).filter(
        Order.created_at >= start,
        Order.created_at < end,
    ).scalar() or 0

    delivery_minutes = []
    on_time = 0
    for o in fulfilled:
        mins, thresh = _measure_order_delivery(o)
        if mins is None:
            continue
        delivery_minutes.append(mins)
        if mins <= thresh:
            on_time += 1

    avg_minutes = round(sum(delivery_minutes) / len(delivery_minutes), 1) if delivery_minutes else 0.0
    # Denominator = orders with a measurable delivery window (not all fulfilled).
    on_time_rate = round((on_time / len(delivery_minutes)) * 100, 1) if delivery_minutes else 0.0
    cancel_rate = round((cancelled / total) * 100, 1) if total else 0.0

    series_days = []
    series_rates = []
    end_d = _pht_date(end) or end.date()
    for i in range(7):
        d = end_d - timedelta(days=7 - i)
        days_orders = []
        ok = 0
        for o in fulfilled:
            if not o.delivered_at:
                continue
            if _pht_date(o.delivered_at) != d:
                continue
            mins, thresh = _measure_order_delivery(o)
            if mins is None:
                continue
            days_orders.append(mins)
            if mins <= thresh:
                ok += 1
        series_rates.append(round((ok / len(days_orders)) * 100, 1) if days_orders else 0)
        series_days.append(d.strftime('%a'))

    return {
        'on_time_rate': on_time_rate,
        'avg_minutes': avg_minutes,
        'cancellation_rate': cancel_rate,
        'series': {'labels': series_days, 'rates': series_rates},
    }


def _platform_recent_orders(limit=5):
    orders = (Order.query
              .order_by(Order.created_at.desc())
              .limit(limit)
              .all())
    out = []
    for o in orders:
        out.append({
            'id': o.id,
            'order_no': f"#{o.id:05d}",
            'customer_name': o.customer.full_name if o.customer else 'Walk-in',
            'store_name': o.store.name if getattr(o, 'store', None) else '—',
            'amount': _to_float(o.total_amount),
            'status': o.status or 'pending',
            'created_at': o.created_at,
            'created_at_display': (_to_pht(o.created_at).strftime('%b %d, %Y %I:%M %p') if _to_pht(o.created_at) else ''),
        })
    return out


def _platform_rating():
    """Average product rating across all stores."""
    rows = db.session.query(
        ProductRating.rating,
        func.count(ProductRating.id),
    ).group_by(ProductRating.rating).all()
    counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r, c in rows:
        if r in counts:
            counts[r] = int(c or 0)
    total = sum(counts.values())
    avg = round(sum(k * v for k, v in counts.items()) / total, 1) if total else 0.0
    return {'average': avg, 'total': total, 'distribution': counts}


def _platform_recent_reviews(limit=3):
    reviews = (ProductRating.query
               .order_by(ProductRating.created_at.desc())
               .limit(limit).all())
    return [{
        'customer_name': r.customer.full_name if r.customer else 'Anonymous',
        'rating': r.rating or 0,
        'comment': r.comment or '',
        'created_at': r.created_at,
    } for r in reviews]


# ── Public: admin analytics context ─────────────────────────────────────────

def compute_admin_analytics(
    period: str = 'week',
    custom_from: Optional[str] = None,
    custom_to: Optional[str] = None,
) -> dict:
    """Build the platform-wide analytics context.

    Returns a dict with the same shape as :func:`compute_analytics` so that
    ``analytics.html`` can render either without conditional logic. The
    ``store`` key is an :class:`AdminScope` stub so the page header reads
    "All Stores" instead of a specific shop name.
    """
    start, end, period_label = period_range(period, custom_from, custom_to)

    prev_start = start - (end - start)
    prev_end = start

    online_rev = _platform_online_revenue(start, end)
    pos_rev = _platform_pos_revenue(start, end)
    total_rev = online_rev + pos_rev

    online_orders = _platform_online_order_count(start, end)
    completed_online = _platform_completed_online_order_count(start, end)
    pos_orders = _platform_pos_order_count(start, end)
    total_orders = online_orders + pos_orders

    # AOV = completed ticket average (revenue is completed online + all POS)
    sold_orders = completed_online + pos_orders
    avg_order = (total_rev / sold_orders) if sold_orders else 0.0
    new_customers = _platform_new_customer_count(start, end)

    prev_rev = _platform_online_revenue(prev_start, prev_end) + _platform_pos_revenue(prev_start, prev_end)
    prev_completed = _platform_completed_online_order_count(prev_start, prev_end) + _platform_pos_order_count(prev_start, prev_end)
    prev_orders = _platform_online_order_count(prev_start, prev_end) + _platform_pos_order_count(prev_start, prev_end)
    prev_avg = (prev_rev / prev_completed) if prev_completed else 0.0
    prev_new_customers = _platform_new_customer_count(prev_start, prev_end)

    def pct_change(now, before):
        if not before:
            return None
        return round(((now - before) / before) * 100, 1)

    total_customers = db.session.query(func.count(User.id)).filter(
        User.role == 'customer'
    ).scalar() or 0
    total_products = db.session.query(func.count(Product.id)).filter(
        Product.is_archived.is_(False)
    ).scalar() or 0
    total_active_stores = db.session.query(func.count(Store.id)).filter(
        Store.status == 'active'
    ).scalar() or 0

    return {
        'store': AdminScope('All Stores'),
        'is_admin': True,
        'period': period,
        'period_label': period_label,
        'period_start': start,
        'period_end': end,

        'totals': {
            'revenue': total_rev,
            'revenue_display': peso(total_rev),
            'orders': total_orders,
            'avg_order': avg_order,
            'avg_order_display': peso(avg_order),
            'new_customers': new_customers,
            'all_customers': total_customers,
            'all_products': total_products,
            'completed_orders': completed_online + pos_orders,
            'active_stores': total_active_stores,
        },
        'deltas': {
            'revenue_pct': pct_change(total_rev, prev_rev),
            'orders_pct': pct_change(total_orders, prev_orders),
            'avg_pct': pct_change(avg_order, prev_avg),
            'new_pct': pct_change(new_customers, prev_new_customers),
        },

        'top_products': _platform_top_products(start, end, limit=5),
        'top_stores': _platform_top_stores(start, end, limit=5),
        'order_status': _platform_order_status_breakdown(start, end),
        'sales_by_category': _platform_sales_by_category(start, end),
        'peak_hours': _platform_peak_hours(start, end),
        'revenue_series': _platform_revenue_series(start, end),
        'delivery': _platform_delivery_performance(start, end),
        'recent_orders': _platform_recent_orders(limit=5),
        'rating': _platform_rating(),
        'reviews': _platform_recent_reviews(limit=3),
    }


# ── Admin section builders (platform-wide) ──────────────────────────────────

def _admin_orders_section(start, end):
    qty = _order_item_qty_subquery()
    results = (
        db.session.query(Order, func.coalesce(qty.c.item_qty, 0))
        .outerjoin(qty, qty.c.order_id == Order.id)
        .options(joinedload(Order.customer), joinedload(Order.store))
        .filter(
            Order.created_at >= start,
            Order.created_at < end,
        )
        .order_by(Order.created_at.desc())
        .all()
    )
    rows = []
    orders = []
    for o, item_qty in results:
        orders.append(o)
    details_map = _order_line_details_map([o.id for o in orders])
    for o, item_qty in results:
        rows.append([
            f"#{o.id:05d}",
            o.store.name if getattr(o, 'store', None) else '—',
            o.customer.full_name if o.customer else 'Walk-in',
            _format_pht(o.created_at),
            int(item_qty or 0),
            details_map.get(o.id) or '—',
            float(o.total_amount or 0),
            (o.status or 'pending').replace('_', ' ').title(),
            (o.payment_method or 'gcash').upper(),
        ])
    delivered = sum(1 for o in orders if _order_status_key(o.status) == 'delivered')
    completed = sum(1 for o in orders if _order_status_key(o.status) == 'completed')
    cancelled = sum(1 for o in orders if _order_status_key(o.status) == 'cancelled')
    revenue = sum(float(o.total_amount or 0) for o in orders if _is_paid_order_status(o.status))
    summary = [
        ('Total Orders', f"{len(orders):,}"),
        ('Delivered', f"{delivered:,}"),
        ('Completed', f"{completed:,}"),
        ('Cancelled', f"{cancelled:,}"),
        ('Revenue (Delivered + Completed)', peso(revenue)),
    ]
    return {
        'key': 'orders',
        'title': 'Orders Report (All Stores)',
        'columns': ['Order ID', 'Store', 'Customer', 'Date (PHT)', 'Items', 'Variants / Add-ons',
                    'Amount (₱)', 'Status', 'Payment'],
        'rows': rows,
        'summary': summary,
    }


def _admin_customers_section(start, end):
    rows = db.session.query(
        User.id,
        User.full_name,
        User.email,
        func.count(Order.id).label('order_count'),
        func.coalesce(func.sum(Order.total_amount), 0).label('total_spent'),
        func.max(Order.created_at).label('last_order'),
    ).join(Order, Order.customer_id == User.id) \
     .filter(Order.created_at >= start,
             Order.created_at < end) \
     .group_by(User.id, User.full_name, User.email) \
     .order_by(func.sum(Order.total_amount).desc()).all()

    out_rows = []
    for r in rows:
        out_rows.append([
            r.full_name,
            _report_email(r.email),
            int(r.order_count or 0),
            float(r.total_spent or 0),
            _format_pht_date(r.last_order),
        ])
    new_count = _platform_new_customer_count(start, end)
    summary = [
        ('Customers in Period', f"{len(out_rows):,}"),
        ('New Customers', f"{new_count:,}"),
        ('Total Spent', peso(sum(r[3] for r in out_rows))),
    ]
    return {
        'key': 'customers',
        'title': 'Customers Report (All Stores)',
        'columns': ['Customer', 'Email', 'Orders', 'Total Spent (₱)', 'Last Order (PHT)'],
        'rows': out_rows,
        'summary': summary,
    }


def _admin_stores_section(start, end):
    rows = db.session.query(
        Store.id,
        Store.name,
        Store.status,
        User.full_name.label('owner_name'),
        User.email.label('owner_email'),
        func.coalesce(func.count(Order.id.distinct()), 0).label('orders'),
        func.coalesce(func.sum(Order.total_amount), 0).label('revenue'),
    ).outerjoin(User, User.id == Store.seller_id) \
     .outerjoin(Order, (Order.store_id == Store.id)
                       & (_paid_order_status_filter())
                       & (Order.created_at >= start)
                       & (Order.created_at < end)) \
     .group_by(Store.id, Store.name, Store.status, User.full_name, User.email) \
     .order_by(func.sum(Order.total_amount).desc().nullslast()) \
     .all()

    out_rows = []
    combined_revenue = 0.0
    for r in rows:
        revenue = float(r.revenue or 0)
        combined_revenue += revenue
        out_rows.append([
            r.name,
            (r.status or 'pending').replace('_', ' ').title(),
            r.owner_name or 'Unassigned',
            _report_email(r.owner_email),
            int(r.orders or 0),
            peso(revenue),
        ])
    active = sum(1 for r in rows if (r.status or '').lower() == 'active')
    pending = sum(1 for r in rows if (r.status or '').lower() == 'pending')
    suspended = sum(1 for r in rows if (r.status or '').lower() == 'suspended')
    summary = [
        ('Total Stores', f"{len(out_rows):,}"),
        ('Active', f"{active:,}"),
        ('Pending', f"{pending:,}"),
        ('Suspended', f"{suspended:,}"),
        ('Combined Revenue', peso(combined_revenue)),
    ]
    return {
        'key': 'stores',
        'title': 'Stores Performance Report',
        'columns': ['Store', 'Status', 'Owner', 'Email',
                    'Delivered Orders', 'Revenue (₱)'],
        'rows': out_rows,
        'summary': summary,
    }


def _admin_products_section(start, end):
    return _build_products_section(start, end, store_id=None, include_store=True)


def _admin_revenue_section(start, end):
    day = pht_sql_date(Order.created_at)
    daily = db.session.query(
        day.label('d'),
        func.count(Order.id).label('orders'),
        func.coalesce(func.sum(Order.total_amount), 0).label('rev'),
    ).filter(
        _paid_order_status_filter(),
        Order.created_at >= start,
        Order.created_at < end,
    ).group_by(day).order_by(day).all()

    rows = []
    total_rev = 0.0
    total_orders = 0
    for r in daily:
        rev = float(r.rev or 0)
        oc = int(r.orders or 0)
        rows.append([
            r.d.strftime('%Y-%m-%d') if hasattr(r.d, 'strftime') else str(r.d),
            oc,
            rev,
            (rev / oc) if oc else 0.0,
        ])
        total_rev += rev
        total_orders += oc

    pos_rev = _platform_pos_revenue(start, end)
    summary = [
        ('Online Revenue', peso(total_rev)),
        ('POS Revenue', peso(pos_rev)),
        ('Total Revenue', peso(total_rev + pos_rev)),
        ('Online Orders', f"{total_orders:,}"),
    ]
    return {
        'key': 'revenue',
        'title': 'Platform Revenue Report',
        'columns': ['Date', 'Orders', 'Revenue (₱)', 'Avg Order (₱)'],
        'rows': rows,
        'summary': summary,
    }


def _admin_users_section(start, end):
    """All registered users joined in [start, end), grouped by role."""
    rows = db.session.query(
        User.id,
        User.full_name,
        User.email,
        User.role,
        User.created_at,
        func.coalesce(func.count(Order.id), 0).label('order_count'),
    ).outerjoin(Order, Order.customer_id == User.id) \
     .filter(User.created_at >= start, User.created_at < end) \
     .group_by(User.id, User.full_name, User.email, User.role, User.created_at) \
     .order_by(User.created_at.desc()).all()

    out_rows = []
    role_counts = defaultdict(int)
    for r in rows:
        out_rows.append([
            r.full_name or '—',
            _report_email(r.email),
            (r.role or 'customer').title(),
            _format_pht_date(r.created_at),
            int(r.order_count or 0),
        ])
        role_counts[(r.role or 'customer').lower()] += 1

    summary = [
        ('New Users', f"{len(out_rows):,}"),
        ('Customers', f"{role_counts.get('customer', 0):,}"),
        ('Sellers', f"{role_counts.get('seller', 0):,}"),
        ('Riders', f"{role_counts.get('rider', 0):,}"),
    ]
    return {
        'key': 'users',
        'title': 'New Users Report',
        'columns': ['Name', 'Email', 'Role', 'Joined (PHT)', 'Orders'],
        'rows': out_rows,
        'summary': summary,
    }


def _admin_year_end_section(start, end):
    online_rev = _platform_online_revenue(start, end)
    pos_rev = _platform_pos_revenue(start, end)
    total_rev = online_rev + pos_rev

    online_orders = _platform_online_order_count(start, end)
    pos_orders = _platform_pos_order_count(start, end)
    total_orders = online_orders + pos_orders
    avg_order = (total_rev / total_orders) if total_orders else 0.0

    new_customers = _platform_new_customer_count(start, end)
    active_stores = db.session.query(func.count(Store.id)).filter(Store.status == 'active').scalar() or 0
    pending_stores = db.session.query(func.count(Store.id)).filter(Store.status == 'pending').scalar() or 0
    total_riders = db.session.query(func.count(Rider.id)).scalar() or 0
    active_riders = db.session.query(func.count(Rider.id)).filter(Rider.is_active.is_(True)).scalar() or 0

    top_store_row = db.session.query(
        Store.name,
        func.coalesce(func.sum(Order.total_amount), 0).label('rev'),
    ).join(Order, Order.store_id == Store.id) \
     .filter(
        _paid_order_status_filter(),
        Order.created_at >= start,
        Order.created_at < end,
     ).group_by(Store.name) \
      .order_by(func.sum(Order.total_amount).desc()) \
      .first()
    top_store_name = top_store_row.name if top_store_row else 'N/A'
    top_store_rev = _to_float(top_store_row.rev) if top_store_row else 0.0

    top_products = _platform_top_products(start, end, limit=3)
    top_products_label = ', '.join(p['name'] for p in top_products) if top_products else 'N/A'

    rows = [
        ['KPI', 'Total Revenue', total_rev, f"Online {peso(online_rev)} + POS {peso(pos_rev)}"],
        ['KPI', 'Total Orders', total_orders, f"Online {online_orders:,} + POS {pos_orders:,}"],
        ['KPI', 'Average Order Value', avg_order, 'Total revenue / total orders'],
        ['KPI', 'New Customers', new_customers, 'Customers placing first order in period'],
        ['KPI', 'Active Stores', active_stores, f"{pending_stores:,} pending review"],
        ['KPI', 'Active Riders', active_riders, f"{active_riders:,} active of {total_riders:,} total"],
        ['Highlight', 'Top Store', top_store_name, f"{peso(top_store_rev)} in completed sales"],
        ['Highlight', 'Top Products', top_products_label, 'Top 3 by completed revenue'],
    ]

    for month_label, b_start, b_end in _iter_pht_months(start, end):
        m_online_rev = _platform_online_revenue(b_start, b_end)
        m_pos_rev = _platform_pos_revenue(b_start, b_end)
        m_total_rev = m_online_rev + m_pos_rev
        m_orders = _platform_online_order_count(b_start, b_end) + _platform_pos_order_count(b_start, b_end)
        m_avg = (m_total_rev / m_orders) if m_orders else 0.0

        rows.append([
            'Month',
            month_label,
            m_total_rev,
            f"Orders {m_orders:,} · Avg {peso(m_avg)}",
        ])

    summary = [
        ('Total Revenue', peso(total_rev)),
        ('Total Orders', f"{total_orders:,}"),
        ('Avg Order', peso(avg_order)),
        ('New Customers', f"{new_customers:,}"),
        ('Active Stores', f"{active_stores:,}"),
    ]

    return {
        'key': 'year_end',
        'title': 'Year-End Summary (Platform)',
        'columns': ['Section', 'Metric', 'Value', 'Details'],
        'rows': rows,
        'summary': summary,
    }


ADMIN_REPORT_TYPES = ['orders', 'customers', 'stores', 'products', 'revenue', 'users', 'year_end']

ADMIN_REPORT_TYPE_LABELS = {
    'orders':    'Orders Report (All Stores)',
    'customers': 'Customers Report (All Stores)',
    'stores':    'Stores Performance Report',
    'products':  'Products Report (All Stores)',
    'revenue':   'Platform Revenue Report',
    'users':     'New Users Report',
    'year_end':  'Year-End Summary (Platform)',
}


def _normalise_admin_types(raw: Iterable[str]) -> List[str]:
    out: List[str] = []
    for t in raw or []:
        if not t:
            continue
        t = str(t).strip().lower()
        if t == 'all':
            return list(ADMIN_REPORT_TYPES)
        if t in ADMIN_REPORT_TYPES and t not in out:
            out.append(t)
    return out or list(ADMIN_REPORT_TYPES)


def build_admin_report_payload(
    types: Sequence[str],
    period: str = 'month',
    custom_from: Optional[str] = None,
    custom_to: Optional[str] = None,
) -> dict:
    """Resolve admin report types into platform-wide sections."""
    start, end, label = period_range(period, custom_from, custom_to)
    types = _normalise_admin_types(types)

    builders = {
        'orders':    _admin_orders_section,
        'customers': _admin_customers_section,
        'stores':    _admin_stores_section,
        'products':  _admin_products_section,
        'revenue':   _admin_revenue_section,
        'users':     _admin_users_section,
        'year_end':  _admin_year_end_section,
    }

    sections = [builders[t](start, end) for t in types if t in builders]

    return {
        'store': AdminScope('All Stores'),
        'is_admin': True,
        'period': period,
        'period_label': label,
        'period_start': start,
        'period_end': end,
        'types': types,
        'generated_at': datetime.now(PHT).strftime('%b %d, %Y %I:%M %p PHT'),
        'sections': sections,
    }
