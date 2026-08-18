"""Store operating hours, delivery window, and same-day booking rules.

All "now / today" checks use Asia/Manila so Railway UTC does not shift
weekdays or hide/show slots incorrectly.
"""
from datetime import datetime, date, timedelta

import pytz

PHT = pytz.timezone('Asia/Manila')
DEFAULT_LEAD_TIME_HOURS = 1
MAX_LEAD_TIME_HOURS = 12
MAX_BOOKING_DAYS = 14


def now_pht():
    return datetime.now(PHT)


def today_pht():
    return now_pht().date()


def as_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
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
    }


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


def _slot_payload(start_h, start_m, end_h, end_m):
    return {
        'label': f'{format_hhmm_label(start_h, start_m)} - {format_hhmm_label(end_h, end_m)}',
        'value': f'{start_h:02d}:{start_m:02d}-{end_h:02d}:{end_m:02d}',
    }


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

    if is_today and order_cutoff:
        cutoff_at = _combine_pht(today, order_cutoff[0], order_cutoff[1])
        if now >= cutoff_at:
            result['time_slots'] = []
            result['block_reason'] = 'order_cutoff'
            return result

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
        bookable.append(_slot_payload(start_h, start_m, end_h, end_m))

    result['time_slots'] = bookable
    if not bookable:
        if lead_blocked_count and lead_hours > 0:
            result['block_reason'] = 'lead_time'
        elif started_count:
            result['block_reason'] = 'slots_passed'
        else:
            result['block_reason'] = 'closed'
    return result


def slot_values(result):
    return [slot['value'] for slot in (result or {}).get('time_slots') or []]


def validate_delivery_slot(store, requested_date, requested_time):
    """Return an error string if the slot cannot be booked, else None."""
    if not requested_date or not requested_time:
        return None

    target = as_date(requested_date)
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
    if not result.get('is_open') or reason == 'closed':
        return f'{store_name} is closed on the selected date.'
    if requested_time not in slots:
        return (
            f'Selected delivery time is no longer available for {store_name}. '
            'It may have passed or is inside the prep window.'
        )
    return None
