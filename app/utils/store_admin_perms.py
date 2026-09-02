"""Page permissions for invited store admins (owner-managed)."""
from flask import jsonify, request, session, redirect, url_for, flash

PERM_KEYS = (
    'products',
    'archive',
    'inventory',
    'orders',
    'riders',
    'pos',
    'store_settings',
)

PERM_FIELDS = (
    ('products', 'Products', 'Add, edit, delete, and change catalog items'),
    ('archive', 'Archive', 'Restore or permanently delete archived products'),
    ('inventory', 'Inventory', 'Add or reduce stock'),
    ('orders', 'Orders', 'Update order status and approve payments'),
    ('riders', 'Riders', 'Invite and manage delivery riders'),
    ('pos', 'POS System', 'Charge sales and void POS orders'),
    ('store_settings', 'Store settings', 'Change hours, payments, delivery, and store profile'),
)


def default_permissions():
    return {key: True for key in PERM_KEYS}


def normalize_permissions(raw):
    out = default_permissions()
    if isinstance(raw, dict):
        for key in PERM_KEYS:
            if key in raw:
                out[key] = bool(raw[key])
    return out


def _matches_prefix(path, prefix):
    return path == prefix or path.startswith(prefix + '/')


def _path_perm(path):
    p = (path or '').rstrip('/') or '/'
    if _matches_prefix(p, '/seller/products') and (
        '/reduce-stock' in p or '/add-stock' in p or '/stock-history' in p
    ):
        return 'inventory'
    if _matches_prefix(p, '/seller/products') and '/archive-choice' in p:
        return 'archive'
    rules = (
        ('/seller/archive', 'archive'),
        ('/api/v1/seller/archive', 'archive'),
        ('/seller/inventory', 'inventory'),
        ('/seller/orders', 'orders'),
        ('/api/seller/orders', 'orders'),
        ('/seller/riders', 'riders'),
        ('/api/seller/riders', 'riders'),
        ('/seller/pos', 'pos'),
        ('/api/seller/pos', 'pos'),
        ('/seller/store-settings', 'store_settings'),
        ('/api/seller/store', 'store_settings'),
        ('/seller/products', 'products'),
        ('/api/seller/products', 'products'),
        ('/api/seller/variants', 'products'),
        ('/api/store/categories', 'products'),
        ('/api/v1/cloudinary/product', 'products'),
        ('/api/v1/cloudinary/variant', 'products'),
        ('/api/v1/cloudinary/upload', 'products'),
        ('/api/v1/cloudinary/gcash', 'store_settings'),
    )
    for prefix, key in rules:
        if _matches_prefix(p, prefix):
            return key
    return None


def store_admin_home_redirect():
    return redirect(url_for('templates.seller_pos'))


def current_store_admin_permissions(user_id=None):
    from app.models import StoreAdmin
    from app.templates_routes import _seller_portal_manageable_store

    uid = user_id if user_id is not None else session.get('user_id')
    if session.get('role') != 'store_admin' or not uid:
        return default_permissions()
    store = _seller_portal_manageable_store(uid)
    if not store:
        return default_permissions()
    row = StoreAdmin.query.filter_by(
        user_id=uid, store_id=store.id, is_active=True, is_archived=False
    ).first()
    if not row:
        return default_permissions()
    return normalize_permissions(row.permissions)


def has_store_admin_perm(key, user_id=None):
    if session.get('role') != 'store_admin':
        return True
    return bool(current_store_admin_permissions(user_id).get(key, True))


_WRITE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


def deny_if_forbidden(path=None):
    if session.get('role') != 'store_admin':
        return None
    if request.method not in _WRITE_METHODS:
        return None
    key = _path_perm(path if path is not None else request.path)
    if not key or has_store_admin_perm(key):
        return None
    labels = dict(PERM_FIELDS)
    message = f'You can view {labels.get(key, key)}, but you do not have permission to make changes.'
    wants_json = (
        request.path.startswith('/api/')
        or request.is_json
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or (request.accept_mimetypes.best or '').startswith('application/json')
    )
    if wants_json:
        return jsonify({'error': message}), 403
    flash(message, 'warning')
    ref = request.referrer or ''
    if ref.startswith(request.host_url):
        return redirect(ref)
    return redirect(url_for('templates.seller_dashboard'))
