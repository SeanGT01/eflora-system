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

from sqlalchemy import func

from app.extensions import db
from app.models import (
    Category,
    Order,
    OrderItem,
    POSOrder,
    POSOrderItem,
    Product,
    ProductRating,
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
    now = datetime.utcnow()
    today = now.date()
    period = (period or 'month').lower().strip()

    if period == 'today':
        start = datetime.combine(today, dt_time.min)
        end = start + timedelta(days=1)
        label = f"Today ({today.strftime('%b %d, %Y')})"
    elif period == 'yesterday':
        y = today - timedelta(days=1)
        start = datetime.combine(y, dt_time.min)
        end = start + timedelta(days=1)
        label = f"Yesterday ({y.strftime('%b %d, %Y')})"
    elif period == 'week':
        start_date = today - timedelta(days=today.weekday())  # Monday
        start = datetime.combine(start_date, dt_time.min)
        end = start + timedelta(days=7)
        label = f"This Week ({start_date.strftime('%b %d')} – {(start_date+timedelta(days=6)).strftime('%b %d, %Y')})"
    elif period == 'month':
        start = datetime(today.year, today.month, 1)
        next_month = (start + timedelta(days=32)).replace(day=1)
        end = next_month
        label = f"This Month ({start.strftime('%B %Y')})"
    elif period == 'quarter':
        q = (today.month - 1) // 3
        start = datetime(today.year, q * 3 + 1, 1)
        end_month = q * 3 + 4
        end_year = today.year
        if end_month > 12:
            end_month -= 12
            end_year += 1
        end = datetime(end_year, end_month, 1)
        label = f"Q{q+1} {today.year}"
    elif period == 'year':
        start = datetime(today.year, 1, 1)
        end = datetime(today.year + 1, 1, 1)
        label = f"This Year ({today.year})"
    elif period == 'all':
        start = datetime(2000, 1, 1)
        end = now + timedelta(days=1)
        label = "All Time"
    elif period == 'custom':
        f = _parse_iso_date(custom_from) or today.replace(day=1)
        t = _parse_iso_date(custom_to) or today
        if t < f:
            f, t = t, f
        start = datetime.combine(f, dt_time.min)
        end = datetime.combine(t, dt_time.min) + timedelta(days=1)
        label = f"{f.strftime('%b %d, %Y')} – {t.strftime('%b %d, %Y')}"
    else:
        return period_range('month')

    return start, end, label


# ─────────────────────────────────────────────────────────────────────────────
# Money / formatting helpers (used by templates + exporters)
# ─────────────────────────────────────────────────────────────────────────────

PESO = '\u20b1'  # ₱


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
COMPLETED_ORDER_STATUSES = ('delivered',)


def _online_revenue(store_id: int, start: datetime, end: datetime) -> float:
    """Sum of ``total_amount`` for delivered orders in [start, end)."""
    total = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(
        Order.store_id == store_id,
        Order.status.in_(COMPLETED_ORDER_STATUSES),
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
        Order.status.in_(COMPLETED_ORDER_STATUSES),
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
    """Return list of dicts with ``name``, ``category``, ``quantity``, ``revenue``."""
    rows = db.session.query(
        Product.id,
        Product.name,
        Category.name.label('category_name'),
        func.coalesce(func.sum(OrderItem.quantity), 0).label('qty'),
        func.coalesce(func.sum(OrderItem.quantity * OrderItem.price), 0).label('revenue'),
    ).join(OrderItem, OrderItem.product_id == Product.id) \
     .join(Order, Order.id == OrderItem.order_id) \
     .outerjoin(Category, Category.id == Product.main_category_id) \
     .filter(
        Order.store_id == store_id,
        Order.status.in_(COMPLETED_ORDER_STATUSES),
        Order.created_at >= start,
        Order.created_at < end,
     ).group_by(Product.id, Product.name, Category.name) \
      .order_by(func.sum(OrderItem.quantity * OrderItem.price).desc()) \
      .limit(limit).all()

    return [{
        'id': r.id,
        'name': r.name,
        'category': r.category_name or 'Uncategorized',
        'quantity': int(r.qty or 0),
        'revenue': _to_float(r.revenue),
    } for r in rows]


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
    for status, count in rows:
        key = (status or 'pending').lower()
        out[key] = (out.get(key) or 0) + int(count or 0)
    return out


def _sales_by_category(store_id, start, end):
    rows = db.session.query(
        Category.name,
        func.coalesce(func.sum(OrderItem.quantity * OrderItem.price), 0).label('revenue'),
    ).join(Product, Product.main_category_id == Category.id) \
     .join(OrderItem, OrderItem.product_id == Product.id) \
     .join(Order, Order.id == OrderItem.order_id) \
     .filter(
        Order.store_id == store_id,
        Order.status.in_(COMPLETED_ORDER_STATUSES),
        Order.created_at >= start,
        Order.created_at < end,
     ).group_by(Category.name) \
      .order_by(func.sum(OrderItem.quantity * OrderItem.price).desc()) \
      .all()
    return [{'name': r[0] or 'Uncategorized', 'revenue': _to_float(r[1])} for r in rows]


def _peak_hours(store_id, start, end):
    """Return 7 buckets across the day showing order counts."""
    rows = db.session.query(
        func.extract('hour', Order.created_at).label('h'),
        func.count(Order.id),
    ).filter(
        Order.store_id == store_id,
        Order.created_at >= start,
        Order.created_at < end,
    ).group_by('h').all()

    by_hour = defaultdict(int)
    for hour, count in rows:
        by_hour[int(hour or 0)] += int(count or 0)

    buckets = [
        ('8AM',  range(7, 10)),
        ('10AM', range(10, 12)),
        ('12PM', range(12, 14)),
        ('2PM',  range(14, 16)),
        ('4PM',  range(16, 18)),
        ('6PM',  range(18, 20)),
        ('8PM',  range(20, 23)),
    ]
    return [{'label': lbl, 'count': sum(by_hour[h] for h in span)} for lbl, span in buckets]


def _revenue_series(store_id, start, end):
    """Daily revenue + order count series across ``[start, end)``."""
    rows = db.session.query(
        func.date(Order.created_at).label('d'),
        func.coalesce(func.sum(Order.total_amount), 0).label('rev'),
        func.count(Order.id).label('orders'),
    ).filter(
        Order.store_id == store_id,
        Order.status.in_(COMPLETED_ORDER_STATUSES),
        Order.created_at >= start,
        Order.created_at < end,
    ).group_by('d').order_by('d').all()

    by_day = {r.d: (_to_float(r.rev), int(r.orders or 0)) for r in rows}

    days = (end - start).days or 1
    # For long ranges, downsample to ~12 buckets
    if days > 31:
        return _bucketed_revenue(store_id, start, end, buckets=12)

    labels, revenues, order_counts = [], [], []
    cur = start.date()
    end_d = end.date()
    while cur < end_d:
        rev, oc = by_day.get(cur, (0.0, 0))
        labels.append(cur.strftime('%b %d'))
        revenues.append(rev)
        order_counts.append(oc)
        cur += timedelta(days=1)
    return {'labels': labels, 'revenue': revenues, 'orders': order_counts}


def _bucketed_revenue(store_id, start, end, buckets=12):
    span = (end - start).total_seconds()
    if span <= 0:
        return {'labels': [], 'revenue': [], 'orders': []}
    step = span / buckets
    edges = [start + timedelta(seconds=step * i) for i in range(buckets + 1)]

    rows = db.session.query(
        Order.created_at,
        Order.total_amount,
    ).filter(
        Order.store_id == store_id,
        Order.status.in_(COMPLETED_ORDER_STATUSES),
        Order.created_at >= start,
        Order.created_at < end,
    ).all()

    rev = [0.0] * buckets
    cnt = [0] * buckets
    for ts, amt in rows:
        for i in range(buckets):
            if edges[i] <= ts < edges[i + 1]:
                rev[i] += _to_float(amt)
                cnt[i] += 1
                break
    labels = [edges[i].strftime('%b %d') for i in range(buckets)]
    return {'labels': labels, 'revenue': rev, 'orders': cnt}


def _delivery_performance(store_id, start, end):
    """On-time rate, avg delivery time (minutes), cancellation %."""
    delivered = db.session.query(Order).filter(
        Order.store_id == store_id,
        Order.status == 'delivered',
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
    for o in delivered:
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
    on_time_rate = round((on_time / len(delivered)) * 100, 1) if delivered else 0.0
    cancel_rate = round((cancelled / total) * 100, 1) if total else 0.0

    # Per-day on-time rate (last 7 days within the range)
    series_days = []
    series_rates = []
    end_d = end.date()
    for i in range(7):
        d = end_d - timedelta(days=7 - i)
        days_orders = [o for o in delivered if o.delivered_at and o.delivered_at.date() == d]
        if days_orders:
            ok = sum(
                1 for o in days_orders
                if (o.confirmed_at and (o.delivered_at - o.confirmed_at).total_seconds() / 60 <= 60)
                or (not o.confirmed_at and (o.delivered_at - o.created_at).total_seconds() / 60 <= 90)
            )
            series_rates.append(round((ok / len(days_orders)) * 100, 1))
        else:
            series_rates.append(0)
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

    avg_order = (total_rev / total_orders) if total_orders else 0.0
    new_customers = _new_customer_count(store.id, start, end)

    # Previous-period comparisons for the % badges
    prev_rev = _online_revenue(store.id, prev_start, prev_end) + _pos_revenue(store.id, prev_start, prev_end)
    prev_orders = _online_order_count(store.id, prev_start, prev_end) + _pos_order_count(store.id, prev_start, prev_end)
    prev_avg = (prev_rev / prev_orders) if prev_orders else 0.0
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
            'completed_orders': completed_online,
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
    orders = (Order.query
              .filter(Order.store_id == store_id,
                      Order.created_at >= start,
                      Order.created_at < end)
              .order_by(Order.created_at.desc()).all())
    rows = []
    for o in orders:
        rows.append([
            f"#{o.id:05d}",
            o.customer.full_name if o.customer else 'Walk-in',
            o.created_at.strftime('%Y-%m-%d %H:%M') if o.created_at else '',
            sum(i.quantity or 0 for i in o.items),
            float(o.total_amount or 0),
            (o.status or 'pending').replace('_', ' ').title(),
            (o.payment_method or 'gcash').upper(),
            (o.payment_status or 'pending').replace('_', ' ').title(),
        ])
    delivered = sum(1 for o in orders if o.status == 'delivered')
    cancelled = sum(1 for o in orders if o.status == 'cancelled')
    revenue = sum(float(o.total_amount or 0) for o in orders if o.status == 'delivered')
    summary = [
        ('Total Orders', f"{len(orders):,}"),
        ('Delivered', f"{delivered:,}"),
        ('Cancelled', f"{cancelled:,}"),
        ('Revenue (Delivered)', peso(revenue)),
    ]
    return {
        'key': 'orders',
        'title': REPORT_TYPE_LABELS['orders'],
        'columns': ['Order ID', 'Customer', 'Date', 'Items', 'Amount (₱)', 'Status', 'Payment', 'Payment Status'],
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
            r.email,
            int(r.order_count or 0),
            float(r.total_spent or 0),
            r.last_order.strftime('%Y-%m-%d') if r.last_order else '',
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
        'columns': ['Customer', 'Email', 'Orders', 'Total Spent (₱)', 'Last Order'],
        'rows': out_rows,
        'summary': summary,
    }


def _products_section(store_id, start, end):
    rows = db.session.query(
        Product.id,
        Product.name,
        Category.name.label('category'),
        Product.stock_quantity,
        Product.price,
        func.coalesce(func.sum(OrderItem.quantity), 0).label('sold'),
        func.coalesce(func.sum(OrderItem.quantity * OrderItem.price), 0).label('revenue'),
    ).outerjoin(OrderItem, OrderItem.product_id == Product.id) \
     .outerjoin(Order, (Order.id == OrderItem.order_id)
                       & (Order.created_at >= start)
                       & (Order.created_at < end)
                       & (Order.status.in_(COMPLETED_ORDER_STATUSES))) \
     .outerjoin(Category, Category.id == Product.main_category_id) \
     .filter(Product.store_id == store_id, Product.is_archived.is_(False)) \
     .group_by(Product.id, Product.name, Category.name, Product.stock_quantity, Product.price) \
     .order_by(func.sum(OrderItem.quantity * OrderItem.price).desc().nullslast()) \
     .all()

    out_rows = []
    low_stock = 0
    out_of_stock = 0
    for r in rows:
        stock = int(r.stock_quantity or 0)
        if stock == 0:
            stock_label = 'Out of Stock'
            out_of_stock += 1
        elif stock <= 10:
            stock_label = 'Low Stock'
            low_stock += 1
        else:
            stock_label = 'Available'
        out_rows.append([
            r.name,
            r.category or 'Uncategorized',
            int(r.sold or 0),
            float(r.revenue or 0),
            stock,
            float(r.price or 0),
            stock_label,
        ])
    summary = [
        ('Total Products', f"{len(out_rows):,}"),
        ('Low Stock', f"{low_stock:,}"),
        ('Out of Stock', f"{out_of_stock:,}"),
        ('Units Sold (Period)', f"{sum(r[2] for r in out_rows):,}"),
    ]
    return {
        'key': 'products',
        'title': REPORT_TYPE_LABELS['products'],
        'columns': ['Product', 'Category', 'Units Sold', 'Revenue (₱)', 'Stock', 'Price (₱)', 'Status'],
        'rows': out_rows,
        'summary': summary,
    }


def _revenue_section(store_id, start, end):
    daily = db.session.query(
        func.date(Order.created_at).label('d'),
        func.count(Order.id).label('orders'),
        func.coalesce(func.sum(Order.total_amount), 0).label('rev'),
    ).filter(
        Order.store_id == store_id,
        Order.status.in_(COMPLETED_ORDER_STATUSES),
        Order.created_at >= start,
        Order.created_at < end,
    ).group_by('d').order_by('d').all()

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
              .filter(Rider.store_id == store_id)
              .order_by(Rider.created_at.asc())
              .all())

    rows = []
    total_assigned = 0
    total_delivered = 0
    total_cancelled = 0
    on_time_values = []

    for rider in riders:
        rider_orders = [o for o in (rider.orders or [])
                        if o.created_at and start <= o.created_at < end]
        assigned = len(rider_orders)
        delivered_orders = [o for o in rider_orders if (o.status or '').lower() == 'delivered']
        cancelled = sum(1 for o in rider_orders if (o.status or '').lower() == 'cancelled')

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
            rider.user.email if rider.user else '',
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
        Order.status.in_(COMPLETED_ORDER_STATUSES),
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
        Order.status == 'delivered',
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
        ['Highlight', 'Top Customer', top_customer_name, f"{peso(top_customer_spent)} in delivered sales"],
        ['Highlight', 'Top Rider', top_rider_name, f"{top_rider_delivered:,} delivered orders"],
        ['Highlight', 'Top Products', top_products_label, 'Top 3 by delivered revenue'],
    ]

    # Month-by-month breakdown within selected range
    cursor = datetime(start.year, start.month, 1)
    while cursor < end:
        next_month = (cursor + timedelta(days=32)).replace(day=1)
        b_start = cursor if cursor >= start else start
        b_end = next_month if next_month <= end else end

        m_online_rev = _online_revenue(store_id, b_start, b_end)
        m_pos_rev = _pos_revenue(store_id, b_start, b_end)
        m_total_rev = m_online_rev + m_pos_rev
        m_orders = _online_order_count(store_id, b_start, b_end) + _pos_order_count(store_id, b_start, b_end)
        m_avg = (m_total_rev / m_orders) if m_orders else 0.0

        rows.append([
            'Month',
            cursor.strftime('%b %Y'),
            m_total_rev,
            f"Orders {m_orders:,} · Avg {peso(m_avg)}",
        ])

        cursor = next_month

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
        'period': period,
        'period_label': label,
        'period_start': start,
        'period_end': end,
        'types': types,
        'sections': sections,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PDF rendering (reportlab)
# ─────────────────────────────────────────────────────────────────────────────

def render_pdf(payload: dict) -> bytes:
    """Render a payload from :func:`build_report_payload` into a PDF (bytes)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, KeepTogether, Image as RLImage,
    )
    from reportlab.graphics.shapes import Drawing, Circle, String
    from xml.sax.saxutils import escape as _xml_escape

    store: Store = payload['store']
    sections = payload['sections']
    period_label = payload['period_label']
    requested_by = payload.get('requested_by') or 'System User'

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title='E-FLORA Report',
        author='E-FLORA',
    )

    base = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'EFloraTitle', parent=base['Title'],
        fontName='Helvetica-Bold', fontSize=21,
        textColor=colors.HexColor('#2c2520'),
        spaceAfter=2, alignment=0,
    )
    subtitle_style = ParagraphStyle(
        'EFloraSubtitle', parent=base['Normal'],
        fontName='Helvetica', fontSize=10,
        textColor=colors.HexColor('#9a8d85'),
        spaceAfter=10,
    )
    meta_style = ParagraphStyle(
        'EFloraMeta', parent=base['Normal'],
        fontName='Helvetica', fontSize=9.5,
        textColor=colors.HexColor('#6b4c3b'),
        leading=12,
        spaceAfter=2,
    )
    section_style = ParagraphStyle(
        'EFloraSection', parent=base['Heading2'],
        fontName='Helvetica-Bold', fontSize=15,
        textColor=colors.HexColor('#b5445a'),
        spaceBefore=10, spaceAfter=8,
    )
    summary_style = ParagraphStyle(
        'EFloraSummary', parent=base['Normal'],
        fontName='Helvetica', fontSize=9,
        textColor=colors.HexColor('#6b4c3b'),
        spaceAfter=6,
    )
    empty_style = ParagraphStyle(
        'EFloraEmpty', parent=base['Italic'],
        fontName='Helvetica-Oblique', fontSize=10,
        textColor=colors.HexColor('#9a8d85'),
        spaceAfter=10,
    )
    header_cell_style = ParagraphStyle(
        'EFloraHeaderCell', parent=base['Normal'],
        fontName='Helvetica-Bold', fontSize=8.5,
        textColor=colors.HexColor('#faf6f0'),
        leading=10, wordWrap='CJK',
    )
    body_cell_style = ParagraphStyle(
        'EFloraBodyCell', parent=base['Normal'],
        fontName='Helvetica', fontSize=8.2,
        textColor=colors.HexColor('#2c2520'),
        leading=10, wordWrap='CJK',
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

    # System logo (real file) with fallback mark.
    default_system_logo = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', 'static', 'images', 'eflora-flower-logo.png')
    )
    system_logo_src = payload.get('system_logo_path')
    if not system_logo_src and os.path.exists(default_system_logo):
        system_logo_src = default_system_logo
    logo = _load_pdf_image(system_logo_src, 42, 42)
    if logo is None:
        logo = Drawing(28, 28)
        logo.add(Circle(14, 14, 12, fillColor=colors.HexColor('#f2c4ce'), strokeColor=colors.HexColor('#b5445a'), strokeWidth=1.1))
        logo.add(String(14, 10.5, 'EF', fontName='Helvetica-Bold', fontSize=10, fillColor=colors.HexColor('#2c2520'), textAnchor='middle'))

    # Submitted store logo (Cloudinary URL/property), if any.
    store_logo_src = payload.get('store_logo_url') or getattr(store, 'logo_url', None)
    store_logo = _load_pdf_image(store_logo_src, 42, 42)
    header_tbl = Table(
        [[logo, Paragraph('E-FLORA — Business Report', title_style), store_logo or '']],
        colWidths=[56, 407, 56],
        hAlign='LEFT',
    )
    header_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_tbl)
    label_map = dict(REPORT_TYPE_LABELS)
    label_map.update(ADMIN_REPORT_TYPE_LABELS)
    type_names = ', '.join(label_map.get(t, str(t).replace('_', ' ').title()) for t in payload['types']) or 'All'
    generated_pht = datetime.now(PHT).strftime('%b %d, %Y %I:%M %p PHT')
    story.append(Spacer(1, 2))
    meta_tbl = Table(
        [[
            Paragraph(f"<b>Store:</b> {store.name}", meta_style),
            Paragraph(f"<b>Requested by:</b> {requested_by}", meta_style),
        ], [
            Paragraph(f"<b>Period:</b> {period_label}", meta_style),
            Paragraph(f"<b>Generated:</b> {generated_pht}", meta_style),
        ]],
        colWidths=[258, 258],
        hAlign='LEFT',
    )
    meta_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
    ]))
    story.append(meta_tbl)
    story.append(Paragraph(f"<b>Sections:</b> {type_names}", subtitle_style))

    for idx, sec in enumerate(sections):
        if idx > 0:
            story.append(PageBreak())
        story.append(Paragraph(sec['title'], section_style))

        # Summary block
        if sec.get('summary'):
            summary_html = ' &nbsp;|&nbsp; '.join(
                f"<b>{k}:</b> {v}" for k, v in sec['summary']
            )
            story.append(Paragraph(summary_html, summary_style))

        rows = sec['rows']
        if not rows:
            story.append(Paragraph('No data found for this period.', empty_style))
            continue

        # Build table
        header = sec['columns']
        # Format numeric cells nicely for PDF
        formatted_rows = []
        for r in rows:
            new_r = []
            for cell in r:
                if isinstance(cell, float):
                    new_r.append(f"{cell:,.2f}")
                elif isinstance(cell, Decimal):
                    new_r.append(f"{float(cell):,.2f}")
                else:
                    new_r.append(str(cell))
            formatted_rows.append(new_r)

        # Build wrapped Paragraph cells to prevent text overlap.
        wrapped_header = [Paragraph(_xml_escape(str(h)), header_cell_style) for h in header]
        wrapped_rows = [
            [Paragraph(_xml_escape(str(c)), body_cell_style) for c in row]
            for row in formatted_rows
        ]
        table_data = [wrapped_header] + wrapped_rows

        # Full-width table with adaptive column sizes for long fields.
        col_count = max(1, len(header))
        sample_rows = formatted_rows[:60] if formatted_rows else []
        weights = []
        for i in range(col_count):
            h = str(header[i]) if i < len(header) else ''
            col_values = [str(r[i]) for r in sample_rows if i < len(r)]
            max_chars = max([len(h)] + [len(v) for v in col_values]) if (col_values or h) else 10
            weight = min(max(1.0, max_chars / 11.0), 2.6)
            h_low = h.lower()
            if any(k in h_low for k in ('date', 'customer', 'name', 'status')):
                weight += 0.35
            elif any(k in h_low for k in ('amount', 'revenue', 'price', 'total', 'avg', 'order')):
                weight += 0.15
            weights.append(weight)
        total_weight = sum(weights) or float(col_count)
        full_width_col_sizes = [(w / total_weight) * doc.width for w in weights]
        table = Table(table_data, colWidths=full_width_col_sizes, repeatRows=1, hAlign='LEFT')
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c2520')),
            ('TEXTCOLOR',  (0, 0), (-1, 0), colors.HexColor('#faf6f0')),
            ('FONTNAME',   (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',   (0, 0), (-1, 0), 8.5),
            ('ALIGN',      (0, 0), (-1, 0), 'LEFT'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('TOPPADDING',    (0, 0), (-1, 0), 6),

            ('FONTNAME',  (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE',  (0, 1), (-1, -1), 8.2),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#2c2520')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1),
                [colors.HexColor('#fffdf9'), colors.HexColor('#faf6f0')]),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#d6cfc8')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('WORDWRAP', (0, 0), (-1, -1), 'CJK'),
            ('LEFTPADDING',  (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 1), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ]))
        story.append(table)

    if not sections:
        story.append(Paragraph('No report types selected.', empty_style))

    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#9a8d85'))
        text = (f"E-FLORA · {store.name} · Page {doc_.page} · "
                f"Generated {datetime.now(PHT).strftime('%Y-%m-%d %I:%M %p PHT')}")
        canvas.drawCentredString(A4[0] / 2, 8 * mm, text)
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
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M')

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
        Order.status.in_(COMPLETED_ORDER_STATUSES),
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
        Order.status.in_(COMPLETED_ORDER_STATUSES),
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
    rows = db.session.query(
        Product.id,
        Product.name,
        Category.name.label('category_name'),
        func.coalesce(func.sum(OrderItem.quantity), 0).label('qty'),
        func.coalesce(func.sum(OrderItem.quantity * OrderItem.price), 0).label('revenue'),
    ).join(OrderItem, OrderItem.product_id == Product.id) \
     .join(Order, Order.id == OrderItem.order_id) \
     .outerjoin(Category, Category.id == Product.main_category_id) \
     .filter(
        Order.status.in_(COMPLETED_ORDER_STATUSES),
        Order.created_at >= start,
        Order.created_at < end,
     ).group_by(Product.id, Product.name, Category.name) \
      .order_by(func.sum(OrderItem.quantity * OrderItem.price).desc()) \
      .limit(limit).all()

    return [{
        'id': r.id,
        'name': r.name,
        'category': r.category_name or 'Uncategorized',
        'quantity': int(r.qty or 0),
        'revenue': _to_float(r.revenue),
    } for r in rows]


def _platform_top_stores(start, end, limit=5):
    """Top stores by delivered revenue in [start, end)."""
    rows = db.session.query(
        Store.id,
        Store.name,
        func.coalesce(func.sum(Order.total_amount), 0).label('revenue'),
        func.count(Order.id).label('orders'),
    ).join(Order, Order.store_id == Store.id) \
     .filter(
        Order.status.in_(COMPLETED_ORDER_STATUSES),
        Order.created_at >= start,
        Order.created_at < end,
     ).group_by(Store.id, Store.name) \
      .order_by(func.sum(Order.total_amount).desc()) \
      .limit(limit).all()

    # Store.logo_url is a Python @property (not a SQL column), so resolve it
    # after the aggregate query using ORM instances.
    store_ids = [int(r.id) for r in rows]
    store_map = {}
    if store_ids:
        for s in Store.query.filter(Store.id.in_(store_ids)).all():
            store_map[s.id] = s

    return [{
        'id': r.id,
        'name': r.name,
        'logo_url': (store_map.get(r.id).logo_url if store_map.get(r.id) else None),
        'revenue': _to_float(r.revenue),
        'orders': int(r.orders or 0),
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
    for status, count in rows:
        key = (status or 'pending').lower()
        out[key] = (out.get(key) or 0) + int(count or 0)
    return out


def _platform_sales_by_category(start, end):
    rows = db.session.query(
        Category.name,
        func.coalesce(func.sum(OrderItem.quantity * OrderItem.price), 0).label('revenue'),
    ).join(Product, Product.main_category_id == Category.id) \
     .join(OrderItem, OrderItem.product_id == Product.id) \
     .join(Order, Order.id == OrderItem.order_id) \
     .filter(
        Order.status.in_(COMPLETED_ORDER_STATUSES),
        Order.created_at >= start,
        Order.created_at < end,
     ).group_by(Category.name) \
      .order_by(func.sum(OrderItem.quantity * OrderItem.price).desc()) \
      .all()
    return [{'name': r[0] or 'Uncategorized', 'revenue': _to_float(r[1])} for r in rows]


def _platform_peak_hours(start, end):
    rows = db.session.query(
        func.extract('hour', Order.created_at).label('h'),
        func.count(Order.id),
    ).filter(
        Order.created_at >= start,
        Order.created_at < end,
    ).group_by('h').all()

    by_hour = defaultdict(int)
    for hour, count in rows:
        by_hour[int(hour or 0)] += int(count or 0)

    buckets = [
        ('8AM',  range(7, 10)),
        ('10AM', range(10, 12)),
        ('12PM', range(12, 14)),
        ('2PM',  range(14, 16)),
        ('4PM',  range(16, 18)),
        ('6PM',  range(18, 20)),
        ('8PM',  range(20, 23)),
    ]
    return [{'label': lbl, 'count': sum(by_hour[h] for h in span)} for lbl, span in buckets]


def _platform_revenue_series(start, end):
    rows = db.session.query(
        func.date(Order.created_at).label('d'),
        func.coalesce(func.sum(Order.total_amount), 0).label('rev'),
        func.count(Order.id).label('orders'),
    ).filter(
        Order.status.in_(COMPLETED_ORDER_STATUSES),
        Order.created_at >= start,
        Order.created_at < end,
    ).group_by('d').order_by('d').all()

    by_day = {r.d: (_to_float(r.rev), int(r.orders or 0)) for r in rows}

    days = (end - start).days or 1
    if days > 31:
        return _platform_bucketed_revenue(start, end, buckets=12)

    labels, revenues, order_counts = [], [], []
    cur = start.date()
    end_d = end.date()
    while cur < end_d:
        rev, oc = by_day.get(cur, (0.0, 0))
        labels.append(cur.strftime('%b %d'))
        revenues.append(rev)
        order_counts.append(oc)
        cur += timedelta(days=1)
    return {'labels': labels, 'revenue': revenues, 'orders': order_counts}


def _platform_bucketed_revenue(start, end, buckets=12):
    span = (end - start).total_seconds()
    if span <= 0:
        return {'labels': [], 'revenue': [], 'orders': []}
    step = span / buckets
    edges = [start + timedelta(seconds=step * i) for i in range(buckets + 1)]

    rows = db.session.query(
        Order.created_at,
        Order.total_amount,
    ).filter(
        Order.status.in_(COMPLETED_ORDER_STATUSES),
        Order.created_at >= start,
        Order.created_at < end,
    ).all()

    rev = [0.0] * buckets
    cnt = [0] * buckets
    for ts, amt in rows:
        for i in range(buckets):
            if edges[i] <= ts < edges[i + 1]:
                rev[i] += _to_float(amt)
                cnt[i] += 1
                break
    labels = [edges[i].strftime('%b %d') for i in range(buckets)]
    return {'labels': labels, 'revenue': rev, 'orders': cnt}


def _platform_delivery_performance(start, end):
    delivered = db.session.query(Order).filter(
        Order.status == 'delivered',
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
    for o in delivered:
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
    on_time_rate = round((on_time / len(delivered)) * 100, 1) if delivered else 0.0
    cancel_rate = round((cancelled / total) * 100, 1) if total else 0.0

    series_days = []
    series_rates = []
    end_d = end.date()
    for i in range(7):
        d = end_d - timedelta(days=7 - i)
        days_orders = [o for o in delivered if o.delivered_at and o.delivered_at.date() == d]
        if days_orders:
            ok = sum(
                1 for o in days_orders
                if (o.confirmed_at and (o.delivered_at - o.confirmed_at).total_seconds() / 60 <= 60)
                or (not o.confirmed_at and (o.delivered_at - o.created_at).total_seconds() / 60 <= 90)
            )
            series_rates.append(round((ok / len(days_orders)) * 100, 1))
        else:
            series_rates.append(0)
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

    avg_order = (total_rev / total_orders) if total_orders else 0.0
    new_customers = _platform_new_customer_count(start, end)

    prev_rev = _platform_online_revenue(prev_start, prev_end) + _platform_pos_revenue(prev_start, prev_end)
    prev_orders = _platform_online_order_count(prev_start, prev_end) + _platform_pos_order_count(prev_start, prev_end)
    prev_avg = (prev_rev / prev_orders) if prev_orders else 0.0
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
            'completed_orders': completed_online,
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
    orders = (Order.query
              .filter(Order.created_at >= start,
                      Order.created_at < end)
              .order_by(Order.created_at.desc()).all())
    rows = []
    for o in orders:
        rows.append([
            f"#{o.id:05d}",
            o.store.name if getattr(o, 'store', None) else '—',
            o.customer.full_name if o.customer else 'Walk-in',
            o.created_at.strftime('%Y-%m-%d %H:%M') if o.created_at else '',
            sum(i.quantity or 0 for i in o.items),
            float(o.total_amount or 0),
            (o.status or 'pending').replace('_', ' ').title(),
            (o.payment_method or 'gcash').upper(),
        ])
    delivered = sum(1 for o in orders if o.status == 'delivered')
    cancelled = sum(1 for o in orders if o.status == 'cancelled')
    revenue = sum(float(o.total_amount or 0) for o in orders if o.status == 'delivered')
    summary = [
        ('Total Orders', f"{len(orders):,}"),
        ('Delivered', f"{delivered:,}"),
        ('Cancelled', f"{cancelled:,}"),
        ('Revenue (Delivered)', peso(revenue)),
    ]
    return {
        'key': 'orders',
        'title': 'Orders Report (All Stores)',
        'columns': ['Order ID', 'Store', 'Customer', 'Date', 'Items',
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
            r.email,
            int(r.order_count or 0),
            float(r.total_spent or 0),
            r.last_order.strftime('%Y-%m-%d') if r.last_order else '',
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
        'columns': ['Customer', 'Email', 'Orders', 'Total Spent (₱)', 'Last Order'],
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
                       & (Order.status.in_(COMPLETED_ORDER_STATUSES))
                       & (Order.created_at >= start)
                       & (Order.created_at < end)) \
     .group_by(Store.id, Store.name, Store.status, User.full_name, User.email) \
     .order_by(func.sum(Order.total_amount).desc().nullslast()) \
     .all()

    out_rows = []
    for r in rows:
        out_rows.append([
            r.name,
            (r.status or 'pending').replace('_', ' ').title(),
            r.owner_name or 'Unassigned',
            r.owner_email or '',
            int(r.orders or 0),
            float(r.revenue or 0),
        ])
    active = sum(1 for r in rows if (r.status or '').lower() == 'active')
    pending = sum(1 for r in rows if (r.status or '').lower() == 'pending')
    suspended = sum(1 for r in rows if (r.status or '').lower() == 'suspended')
    summary = [
        ('Total Stores', f"{len(out_rows):,}"),
        ('Active', f"{active:,}"),
        ('Pending', f"{pending:,}"),
        ('Suspended', f"{suspended:,}"),
        ('Combined Revenue', peso(sum(r[5] for r in out_rows))),
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
    rows = db.session.query(
        Product.id,
        Product.name,
        Store.name.label('store_name'),
        Category.name.label('category'),
        Product.stock_quantity,
        Product.price,
        func.coalesce(func.sum(OrderItem.quantity), 0).label('sold'),
        func.coalesce(func.sum(OrderItem.quantity * OrderItem.price), 0).label('revenue'),
    ).outerjoin(OrderItem, OrderItem.product_id == Product.id) \
     .outerjoin(Order, (Order.id == OrderItem.order_id)
                       & (Order.created_at >= start)
                       & (Order.created_at < end)
                       & (Order.status.in_(COMPLETED_ORDER_STATUSES))) \
     .outerjoin(Category, Category.id == Product.main_category_id) \
     .outerjoin(Store, Store.id == Product.store_id) \
     .filter(Product.is_archived.is_(False)) \
     .group_by(Product.id, Product.name, Store.name, Category.name,
               Product.stock_quantity, Product.price) \
     .order_by(func.sum(OrderItem.quantity * OrderItem.price).desc().nullslast()) \
     .all()

    out_rows = []
    low_stock = 0
    out_of_stock = 0
    for r in rows:
        stock = int(r.stock_quantity or 0)
        if stock == 0:
            stock_label = 'Out of Stock'
            out_of_stock += 1
        elif stock <= 10:
            stock_label = 'Low Stock'
            low_stock += 1
        else:
            stock_label = 'Available'
        out_rows.append([
            r.name,
            r.store_name or '—',
            r.category or 'Uncategorized',
            int(r.sold or 0),
            float(r.revenue or 0),
            stock,
            float(r.price or 0),
            stock_label,
        ])
    summary = [
        ('Total Products', f"{len(out_rows):,}"),
        ('Low Stock', f"{low_stock:,}"),
        ('Out of Stock', f"{out_of_stock:,}"),
        ('Units Sold (Period)', f"{sum(r[3] for r in out_rows):,}"),
    ]
    return {
        'key': 'products',
        'title': 'Products Report (All Stores)',
        'columns': ['Product', 'Store', 'Category', 'Units Sold',
                    'Revenue (₱)', 'Stock', 'Price (₱)', 'Status'],
        'rows': out_rows,
        'summary': summary,
    }


def _admin_revenue_section(start, end):
    daily = db.session.query(
        func.date(Order.created_at).label('d'),
        func.count(Order.id).label('orders'),
        func.coalesce(func.sum(Order.total_amount), 0).label('rev'),
    ).filter(
        Order.status.in_(COMPLETED_ORDER_STATUSES),
        Order.created_at >= start,
        Order.created_at < end,
    ).group_by('d').order_by('d').all()

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
            r.email,
            (r.role or 'customer').title(),
            r.created_at.strftime('%Y-%m-%d') if r.created_at else '',
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
        'columns': ['Name', 'Email', 'Role', 'Joined', 'Orders'],
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
        Order.status.in_(COMPLETED_ORDER_STATUSES),
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
        ['Highlight', 'Top Store', top_store_name, f"{peso(top_store_rev)} in delivered sales"],
        ['Highlight', 'Top Products', top_products_label, 'Top 3 by delivered revenue'],
    ]

    cursor = datetime(start.year, start.month, 1)
    while cursor < end:
        next_month = (cursor + timedelta(days=32)).replace(day=1)
        b_start = cursor if cursor >= start else start
        b_end = next_month if next_month <= end else end

        m_online_rev = _platform_online_revenue(b_start, b_end)
        m_pos_rev = _platform_pos_revenue(b_start, b_end)
        m_total_rev = m_online_rev + m_pos_rev
        m_orders = _platform_online_order_count(b_start, b_end) + _platform_pos_order_count(b_start, b_end)
        m_avg = (m_total_rev / m_orders) if m_orders else 0.0

        rows.append([
            'Month',
            cursor.strftime('%b %Y'),
            m_total_rev,
            f"Orders {m_orders:,} · Avg {peso(m_avg)}",
        ])

        cursor = next_month

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
        'sections': sections,
    }
