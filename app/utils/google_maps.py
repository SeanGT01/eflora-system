"""Google Geocoding helpers for the Flutter address pin (Laguna, PH)."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from flask import current_app


def _api_key():
    key = (
        (current_app.config.get('GOOGLE_MAPS_API_KEY') if current_app else None)
        or os.getenv('GOOGLE_MAPS_API_KEY', '')
    ).strip()
    if not key or 'your-google-maps' in key.lower():
        return ''
    return key


def google_maps_configured():
    return bool(_api_key())


def _get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'eflora/1.0'})
    with urllib.request.urlopen(req, timeout=12) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _component(components, *wanted):
    for item in components or []:
        types = item.get('types') or []
        if any(t in types for t in wanted):
            return (item.get('long_name') or '').strip()
    return ''


def _parse_result(result):
    comps = result.get('address_components') or []
    loc = ((result.get('geometry') or {}).get('location')) or {}
    street_no = _component(comps, 'street_number')
    route = _component(comps, 'route', 'premise')
    street = ' '.join(p for p in (street_no, route) if p).strip()
    names = [c.get('long_name') or '' for c in comps]
    return {
        'formatted_address': result.get('formatted_address') or '',
        'street': street,
        'barangay': _component(
            comps,
            'sublocality_level_1',
            'sublocality',
            'neighborhood',
            'administrative_area_level_3',
        ),
        'municipality': _component(
            comps,
            'locality',
            'administrative_area_level_2',
            'postal_town',
        ),
        'context': ', '.join(n for n in names if n.strip()),
        'lat': loc.get('lat'),
        'lng': loc.get('lng'),
        'place_id': result.get('place_id'),
    }


def reverse_geocode(lat, lng):
    key = _api_key()
    if not key:
        return None, 'Google Maps is not configured.'
    qs = urllib.parse.urlencode({
        'latlng': f'{lat},{lng}',
        'key': key,
        'language': 'en',
        'region': 'ph',
    })
    try:
        data = _get_json(f'https://maps.googleapis.com/maps/api/geocode/json?{qs}')
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return None, str(exc)
    if data.get('status') != 'OK' or not data.get('results'):
        return None, data.get('error_message') or data.get('status') or 'No address found.'
    return _parse_result(data['results'][0]), None


def search_places(query, limit=5):
    key = _api_key()
    if not key:
        return None, 'Google Maps is not configured.'
    q = (query or '').strip()
    if not q:
        return [], None
    if 'laguna' not in q.lower() and 'philippines' not in q.lower():
        q = f'{q}, Laguna, Philippines'
    qs = urllib.parse.urlencode({
        'address': q,
        'key': key,
        'language': 'en',
        'region': 'ph',
        'components': 'country:PH',
    })
    try:
        data = _get_json(f'https://maps.googleapis.com/maps/api/geocode/json?{qs}')
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return None, str(exc)
    if data.get('status') == 'ZERO_RESULTS':
        return [], None
    if data.get('status') != 'OK':
        return None, data.get('error_message') or data.get('status') or 'Search failed.'
    out = []
    for result in (data.get('results') or [])[:limit]:
        parsed = _parse_result(result)
        if parsed.get('lat') is None or parsed.get('lng') is None:
            continue
        out.append({
            'name': parsed['formatted_address'] or query,
            'lat': parsed['lat'],
            'lng': parsed['lng'],
            'place_id': parsed.get('place_id'),
        })
    return out, None
