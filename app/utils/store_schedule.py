"""Store operating hours, delivery window, and same-day booking rules.

All "now / today" checks use Asia/Manila so Railway UTC does not shift
weekdays or hide/show slots incorrectly.
"""
from datetime import datetime, date, timedelta
import re

import pytz

PHT = pytz.timezone('Asia/Manila')
DEFAULT_LEAD_TIME_HOURS = 1
MAX_LEAD_TIME_HOURS = 12
MAX_BOOKING_DAYS = 14
DEFAULT_MAX_ORDERS_PER_SLOT = 4


def now_pht():
    return datetime.now(PHT)


def today_pht():
    return now_pht().date()


def as_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value.strip(), '%Y-%m-%d').date()
        except Exception:
            return None
    return value


def parse_hhmm(value):
    raw = str(value or '').strip()
    if not raw or ':' not in raw:
        return None
    try:
        hour_s, minute_s = raw.split(':', 1)
        hour, minute = int(hour_s), int(minute_s)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    except (TypeError, ValueError):
        return None
    return None


def format_hhmm_label(hour, minute):
    period = 'AM' if hour < 12 else 'PM'
    display_h = hour % 12 or 12
    if minute == 0:
        return f'{display_h}:00 {period}'
    return f'{display_h}:{minute:02d} {period}'


def format_hhmm_value(value):
    parsed = parse_hhmm(value)
    if not parsed:
        return None
    return format_hhmm_label(*parsed)


def normalize_slot_key(val):
    """Normalize any 12h or 24h slot string to canonical HH:MM-HH:MM format for matching."""
    if not val:
        return None
    raw = str(val).strip()
    m24 = re.match(r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$", raw)
    if m24:
        h1, m1, h2, m2 = int(m24.group(1)), int(m24.group(2)), int(m24.group(3)), int(m24.group(4))
        return f"{h1:02d}:{m1:02d}-{h2:02d}:{m2:02d}"
    m12 = re.match(
        r"^(\d{1,2}):(\d{2})\s*([AaPp][Mm])\s*-\s*(\d{1,2}):(\d{2})\s*([AaPp][Mm])$",
        raw,
    )
    if m12:
        try:
            h1, m1, p1 = int(m12.group(1)), int(m12.group(2)), m12.group(3).upper()
            h2, m2, p2 = int(m12.group(4)), int(m12.group(5)), m12.group(6).upper()
            if p1 == 'PM' and h1 != 12:
                h1 += 12
            elif p1 == 'AM' and h1 == 12:
                h1 = 0
            if p2 == 'PM' and h2 != 12:
                h2 += 12
            elif p2 == 'AM' and h2 == 12:
                h2 = 0
            return f"{h1:02d}:{m1:02d}-{h2:02d}:{m2:02d}"
        except Exception:
            return None
    return raw


def format_store_hours_parts(schedule):
    """Labeled 12-hour PH store-open vs delivery window for dashboard Store Info."""
    schedule = schedule or {}
    blocks = []
    seen = set()
    for entry in schedule.get('schedules') or []:
        open_l = format_hhmm_value(entry.get('open'))
        close_l = format_hhmm_value(entry.get('close'))
        if not open_l or not close_l:
            continue
        key = (open_l, close_l)
        if key in seen:
            continue
        seen.add(key)
        blocks.append(f'{open_l} – {close_l}')
    open_hours = None
    if len(blocks) == 1:
        open_hours = f'{blocks[0]} PHT'
    elif len(blocks) > 1:
        open_hours = f"{'; '.join(blocks)} PHT"
    start = format_hhmm_value(schedule.get('delivery_start'))
    end = format_hhmm_value(schedule.get('delivery_cutoff'))
    delivery_hours = f'{start} – {end} PHT' if start and end else None
    return {
        'open': open_hours,
        'delivery': delivery_hours,
    }


def format_store_hours_display(schedule):
    parts = format_store_hours_parts(schedule)
    bits = []
    if parts.get('open'):
        bits.append(f"Store open {parts['open']}")
    if parts.get('delivery'):
        bits.append(f"Delivery {parts['delivery']}")
    return ' · '.join(bits) if bits else 'Not set'


def _combine_pht(day, hour, minute):
    return PHT.localize(datetime(day.year, day.month, day.day, hour, minute, 0))


def _lead_time_hours(schedule):
    try:
        hours = int(schedule.get('lead_time_hours', DEFAULT_LEAD_TIME_HOURS))
    except (TypeError, ValueError):
        hours = DEFAULT_LEAD_TIME_HOURS
    return max(0, min(MAX_LEAD_TIME_HOURS, hours))


def open_days_from_schedule(schedule):
    days = set()
    for entry in (schedule or {}).get('schedules') or []:
        for day in entry.get('days') or []:
            name = str(day).lower().strip()
            if name:
                days.add(name)
    weekday_order = (
        'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'
    )
    return [day for day in weekday_order if day in days]


def sanitize_store_schedule(payload):
    """Keep only recognized schedule fields with safe values."""
    if not isinstance(payload, dict):
        return None
    schedules = []
    for entry in payload.get('schedules') or []:
        if not isinstance(entry, dict):
            continue
        open_t = parse_hhmm(entry.get('open'))
        close_t = parse_hhmm(entry.get('close'))
        days = [
            str(day).lower().strip()
            for day in (entry.get('days') or [])
            if str(day).strip()
        ]
        if not open_t or not close_t or not days:
            continue
        if open_t >= close_t:
            continue
        schedules.append({
            'days': days,
            'open': f'{open_t[0]:02d}:{open_t[1]:02d}',
            'close': f'{close_t[0]:02d}:{close_t[1]:02d}',
        })
    try:
        slot_duration = int(payload.get('slot_duration') or 2)
    except (TypeError, ValueError):
        slot_duration = 2
    lead_hours = _lead_time_hours(payload)
    delivery_start = parse_hhmm(payload.get('delivery_start'))
    delivery_cutoff = parse_hhmm(payload.get('delivery_cutoff'))
    order_cutoff = parse_hhmm(payload.get('order_cutoff'))
    allow_same_day = payload.get('allow_same_day')
    if allow_same_day is None:
        allow_same_day = True
    else:
        allow_same_day = bool(allow_same_day)

    limit_orders_raw = payload.get('limit_orders_per_slot')
    max_orders_raw = payload.get('max_orders_per_slot')
    parsed_max_orders = None
    if max_orders_raw is not None and str(max_orders_raw).strip() != '':
        try:
            parsed_max_orders = max(1, min(100, int(max_orders_raw)))
        except (TypeError, ValueError):
            parsed_max_orders = None

    if limit_orders_raw is None:
        limit_orders_bool = parsed_max_orders is not None
    else:
        limit_orders_bool = bool(limit_orders_raw)

    if limit_orders_bool and parsed_max_orders is None:
        parsed_max_orders = DEFAULT_MAX_ORDERS_PER_SLOT
    elif not limit_orders_bool:
        parsed_max_orders = None

    if (delivery_start and not delivery_cutoff) or (delivery_cutoff and not delivery_start):
        delivery_start = delivery_cutoff = None
    if delivery_start and delivery_cutoff and delivery_start >= delivery_cutoff:
        delivery_start = delivery_cutoff = None
    return {
        'schedules': schedules,
        'slot_duration': max(1, min(12, slot_duration)),
        'delivery_start': (
            f'{delivery_start[0]:02d}:{delivery_start[1]:02d}' if delivery_start else None
        ),
        'delivery_cutoff': (
            f'{delivery_cutoff[0]:02d}:{delivery_cutoff[1]:02d}' if delivery_cutoff else None
        ),
        'order_cutoff': (
            f'{order_cutoff[0]:02d}:{order_cutoff[1]:02d}' if order_cutoff else None
        ),
        'lead_time_hours': lead_hours,
        'allow_same_day': allow_same_day,
        'limit_orders_per_slot': limit_orders_bool,
        'max_orders_per_slot': parsed_max_orders,
    }


def store_hours_span(schedules):
    """Earliest open and latest close across configured time blocks."""
    opens = []
    closes = []
    for entry in schedules or []:
        open_t = parse_hhmm(entry.get('open'))
        close_t = parse_hhmm(entry.get('close'))
        if not open_t or not close_t or open_t >= close_t:
            continue
        opens.append(open_t)
        closes.append(close_t)
    if not opens:
        return None, None
    return min(opens), max(closes)


def schedule_constraint_error(cleaned):
    """Return a user-facing error if delivery/cutoff times fall outside store hours."""
    if not isinstance(cleaned, dict):
        return None
    schedules = cleaned.get('schedules') or []
    delivery_start = parse_hhmm(cleaned.get('delivery_start'))
    delivery_cutoff = parse_hhmm(cleaned.get('delivery_cutoff'))
    order_cutoff = parse_hhmm(cleaned.get('order_cutoff'))
    earliest, latest = store_hours_span(schedules)

    if not earliest:
        if delivery_start or delivery_cutoff or order_cutoff:
            return 'Set store operating hours before setting a delivery window or same-day cutoff.'
        return None

    open_label = format_hhmm_label(*earliest)
    close_label = format_hhmm_label(*latest)

    if delivery_start or delivery_cutoff:
        if not delivery_start or not delivery_cutoff:
            return 'Please set both delivery start and cutoff time, or leave both blank.'
        if delivery_start >= delivery_cutoff:
            return 'Delivery cutoff must be after delivery start.'
        if delivery_start < earliest:
            return 'Delivery start must be at or after store opening (%s).' % open_label
        if delivery_cutoff > latest:
            return 'Delivery end must be at or before store closing (%s).' % close_label

    if order_cutoff:
        if order_cutoff < earliest or order_cutoff > latest:
            return 'Same-day cutoff must be within store hours (%s – %s).' % (
                open_label, close_label,
            )
        if delivery_cutoff and order_cutoff > delivery_cutoff:
            return 'Same-day cutoff must be at or before the delivery window end.'
    return None


def has_configured_schedule(store):
    schedule = (getattr(store, 'store_schedule', None) or {}) if store else {}
    return bool(schedule.get('schedules'))


def _clip_range(open_h, open_m, close_h, close_m, delivery_start, delivery_cutoff):
    if delivery_start:
        ds_h, ds_m = delivery_start
        if (ds_h, ds_m) > (open_h, open_m):
            open_h, open_m = ds_h, ds_m
    if delivery_cutoff:
        dc_h, dc_m = delivery_cutoff
        if (dc_h, dc_m) < (close_h, close_m):
            close_h, close_m = dc_h, dc_m
    if (open_h, open_m) >= (close_h, close_m):
        return None
    return open_h, open_m, close_h, close_m


def _iter_raw_slots(schedule, target_date):
    day_name = datetime(target_date.year, target_date.month, target_date.day).strftime('%A').lower()
    try:
        slot_duration = int(schedule.get('slot_duration') or 2)
    except (TypeError, ValueError):
        slot_duration = 2
    slot_duration = max(1, min(12, slot_duration))
    delivery_start = parse_hhmm(schedule.get('delivery_start'))
    delivery_cutoff = parse_hhmm(schedule.get('delivery_cutoff'))

    slots = []
    for entry in schedule.get('schedules') or []:
        days = [str(d).lower() for d in (entry.get('days') or [])]
        if day_name not in days:
            continue
        open_parsed = parse_hhmm(entry.get('open'))
        close_parsed = parse_hhmm(entry.get('close'))
        if not open_parsed or not close_parsed:
            continue
        clipped = _clip_range(
            open_parsed[0], open_parsed[1],
            close_parsed[0], close_parsed[1],
            delivery_start, delivery_cutoff,
        )
        if not clipped:
            continue
        open_h, open_m, close_h, close_m = clipped
        current_h, current_m = open_h, open_m
        while True:
            end_h = current_h + slot_duration
            end_m = current_m
            if end_h > close_h or (end_h == close_h and end_m > close_m):
                remaining = (close_h - current_h) + (close_m - current_m) / 60.0
                if remaining > 0:
                    end_h, end_m = close_h, close_m
                else:
                    break
            slots.append((current_h, current_m, end_h, end_m))
            current_h, current_m = end_h, end_m
            if current_h >= close_h and current_m >= close_m:
                break
    return slots, day_name, slot_duration


def _slot_payload(start_h, start_m, end_h, end_m, is_full=False, booked_count=0, max_orders=None):
    raw_label = f'{format_hhmm_label(start_h, start_m)} - {format_hhmm_label(end_h, end_m)}'
    return {
        'label': f'{raw_label} (Fully Booked)' if is_full else raw_label,
        'raw_label': raw_label,
        'value': f'{start_h:02d}:{start_m:02d}-{end_h:02d}:{end_m:02d}',
        'is_full': is_full,
        'booked_count': booked_count,
        'max_orders': max_orders,
    }


def _get_slot_order_counts(store_id, target_date):
    """Return dict of {canonical_slot_value: count} of active (uncancelled) orders."""
    counts = {}
    if not store_id or not target_date:
        return counts
    try:
        from app.models import Order
        from sqlalchemy import func
        rows = (
            Order.query.with_entities(
                Order.requested_delivery_time,
                func.count(Order.id)
            )
            .filter(
                Order.store_id == store_id,
                Order.requested_delivery_date == target_date,
                Order.status != 'cancelled',
                Order.requested_delivery_time.isnot(None)
            )
            .group_by(Order.requested_delivery_time)
            .all()
        )
        for raw_val, cnt in rows:
            norm = normalize_slot_key(raw_val)
            if norm:
                counts[norm] = counts.get(norm, 0) + cnt
    except Exception:
        pass
    return counts


def build_store_time_slots(store, target_date=None):
    """Return bookable slots for a calendar date in Philippine time."""
    schedule = (getattr(store, 'store_schedule', None) or {}) if store else {}
    target = as_date(target_date) or today_pht()
    now = now_pht()
    today = now.date()
    is_today = target == today
    lead_hours = _lead_time_hours(schedule)
    order_cutoff = parse_hhmm(schedule.get('order_cutoff'))
    delivery_start = schedule.get('delivery_start')
    delivery_cutoff = schedule.get('delivery_cutoff')
    open_days = open_days_from_schedule(schedule)
    configured = bool(schedule.get('schedules'))
    limit_orders_enabled = bool(schedule.get('limit_orders_per_slot'))
    max_orders_per_slot = schedule.get('max_orders_per_slot')
    try:
        max_orders_per_slot = int(max_orders_per_slot) if max_orders_per_slot is not None else None
    except (TypeError, ValueError):
        max_orders_per_slot = None

    result = {
        'success': True,
        'time_slots': [],
        'is_open': False,
        'has_schedule': configured,
        'day': datetime(target.year, target.month, target.day).strftime('%A').lower(),
        'open_days': open_days,
        'slot_duration': int(schedule.get('slot_duration') or 2) if configured else None,
        'delivery_start': delivery_start,
        'delivery_cutoff': delivery_cutoff,
        'order_cutoff': schedule.get('order_cutoff'),
        'lead_time_hours': lead_hours,
        'allow_same_day': bool(schedule.get('allow_same_day', True) if schedule.get('allow_same_day') is not None else True),
        'limit_orders_per_slot': limit_orders_enabled,
        'max_orders_per_slot': max_orders_per_slot,
        'block_reason': None,
    }

    if not configured:
        result['block_reason'] = 'no_schedule'
        return result

    raw_slots, day_name, slot_duration = _iter_raw_slots(schedule, target)
    result['day'] = day_name
    result['slot_duration'] = slot_duration

    if not raw_slots:
        result['block_reason'] = 'closed'
        return result

    result['is_open'] = True

    if is_today and not result['allow_same_day']:
        result['time_slots'] = []
        result['block_reason'] = 'same_day_disabled'
        return result

    if is_today and order_cutoff:
        cutoff_at = _combine_pht(today, order_cutoff[0], order_cutoff[1])
        if now >= cutoff_at:
            result['time_slots'] = []
            result['block_reason'] = 'order_cutoff'
            return result

    slot_counts = {}
    if limit_orders_enabled and max_orders_per_slot and getattr(store, 'id', None):
        slot_counts = _get_slot_order_counts(store.id, target)

    earliest_start = now + timedelta(hours=lead_hours)
    bookable = []
    started_count = 0
    lead_blocked_count = 0
    for start_h, start_m, end_h, end_m in raw_slots:
        start_at = _combine_pht(target, start_h, start_m)
        if start_at <= now:
            started_count += 1
            continue
        if start_at < earliest_start:
            lead_blocked_count += 1
            continue
        canonical_val = f'{start_h:02d}:{start_m:02d}-{end_h:02d}:{end_m:02d}'
        booked = slot_counts.get(canonical_val, 0)
        is_full = bool(limit_orders_enabled and max_orders_per_slot and booked >= max_orders_per_slot)
        bookable.append(
            _slot_payload(
                start_h, start_m, end_h, end_m,
                is_full=is_full,
                booked_count=booked,
                max_orders=max_orders_per_slot if limit_orders_enabled else None
            )
        )

    result['time_slots'] = bookable
    if not bookable:
        if lead_blocked_count and lead_hours > 0:
            result['block_reason'] = 'lead_time'
        elif started_count:
            result['block_reason'] = 'slots_passed'
        else:
            result['block_reason'] = 'closed'
    elif limit_orders_enabled and max_orders_per_slot and all(s.get('is_full') for s in bookable):
        result['block_reason'] = 'slots_full'
    return result


def slot_values(result, include_full=False):
    return [
        slot['value']
        for slot in (result or {}).get('time_slots') or []
        if include_full or not slot.get('is_full')
    ]


def validate_delivery_slot(store, requested_date, requested_time):
    """Return an error string if the slot cannot be booked, else None."""
    if not requested_date or not requested_time:
        return None

    target = as_date(requested_date)
    if not target:
        return 'Invalid delivery date provided.'
    today = today_pht()
    if target < today:
        return 'Selected delivery date has already passed.'
    if target > today + timedelta(days=MAX_BOOKING_DAYS):
        return 'Selected delivery date must be within 14 days from today.'

    result = build_store_time_slots(store, target)
    store_name = getattr(store, 'name', None) or 'This store'
    reason = result.get('block_reason')
    slots = slot_values(result)

    if not result.get('has_schedule'):
        return f'{store_name} has not configured delivery hours yet.'
    if reason == 'same_day_disabled':
        return f'{store_name} does not offer same-day delivery. Please choose another delivery date.'
    if reason == 'order_cutoff':
        cutoff_label = format_hhmm_value(result.get('order_cutoff')) or 'the cutoff'
        return (
            f'Same-day ordering for {store_name} closed at {cutoff_label}. '
            'Please choose another open day.'
        )
    if reason == 'lead_time':
        hours = result.get('lead_time_hours') or DEFAULT_LEAD_TIME_HOURS
        unit = 'hour' if hours == 1 else 'hours'
        return (
            f'Please book at least {hours} {unit} in advance for {store_name}. '
            'Choose a later slot or another date.'
        )
    if reason == 'slots_passed':
        return f'All delivery slots for {store_name} have already passed. Please choose another date.'
    if reason == 'slots_full':
        return f'All delivery slots for {store_name} on the selected date are fully booked. Please choose another date.'
    if not result.get('is_open') or reason == 'closed':
        return f'{store_name} is closed on the selected date.'

    target_slot = next((s for s in (result.get('time_slots') or []) if s.get('value') == requested_time), None)
    if target_slot and target_slot.get('is_full'):
        slot_label = target_slot.get('raw_label') or target_slot.get('label') or requested_time
        return (
            f'The selected delivery window ({slot_label}) is now fully booked for {store_name}. '
            'Please select another delivery time slot or date.'
        )

    if requested_time not in slots:
        return (
            f'Selected delivery time is no longer available for {store_name}. '
            'It may have passed or is inside the prep window.'
        )
    return None
