"""Customer order cancellation reason helpers (web + Flutter)."""

# Preset reasons shown as selectable chips (Shopee/Lazada-style).
CUSTOMER_CANCEL_REASONS = [
    {'code': 'changed_mind', 'label': 'I changed my mind'},
    {'code': 'ordered_by_mistake', 'label': 'Ordered by mistake'},
    {'code': 'wrong_details', 'label': 'Wrong item / address details'},
    {'code': 'delivery_time', 'label': 'Delivery time no longer works'},
    {'code': 'found_alternative', 'label': 'Found another store / product'},
    {'code': 'payment_issue', 'label': 'Payment / checkout issue'},
    {'code': 'other', 'label': 'Other'},
]

_VALID_CODES = {r['code'] for r in CUSTOMER_CANCEL_REASONS}
_LABEL_BY_CODE = {r['code']: r['label'] for r in CUSTOMER_CANCEL_REASONS}


def normalize_customer_cancel_reason(payload):
    """
    Validate cancel reason from JSON body.
    Returns (code, reason_text, error_message).
    error_message is None on success.
    """
    data = payload if isinstance(payload, dict) else {}
    code = (data.get('reason_code') or data.get('cancellation_reason_code') or '').strip().lower()
    details = (data.get('reason') or data.get('cancellation_reason') or data.get('reason_details') or '').strip()

    if not code or code not in _VALID_CODES:
        return None, None, 'Please select a cancellation reason.'

    if code == 'other':
        if len(details) < 5:
            return None, None, 'Please tell us specifically why you are cancelling (at least 5 characters).'
        if len(details) > 500:
            return None, None, 'Cancellation reason is too long (max 500 characters).'
        return code, details, None

    label = _LABEL_BY_CODE[code]
    # Optional extra note appended for presets
    if details:
        if len(details) > 500:
            return None, None, 'Additional details are too long (max 500 characters).'
        return code, f'{label}. {details}', None
    return code, label, None
