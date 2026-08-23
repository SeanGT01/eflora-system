"""Public URL helpers for Search Console (canonicals, robots, sitemap)."""
from flask import current_app, request


NOINDEX_PREFIXES = (
    '/api/',
    '/my-account',
    '/dashboard',
    '/orders',
    '/cart',
    '/checkout',
    '/wishlist',
    '/settings',
    '/admin/',
    '/seller/',
    '/login',
    '/register',
    '/logout',
    '/home',
)

NOINDEX_EXACT = frozenset({
    '/login',
    '/register',
    '/logout',
    '/home',
    '/cart',
    '/checkout',
    '/orders',
    '/dashboard',
    '/my-account',
    '/wishlist',
    '/settings',
})


def site_base_url():
    configured = (current_app.config.get('APP_BASE_URL') or '').strip().rstrip('/')
    if configured:
        return configured
    return request.url_root.rstrip('/')


def canonical_path(path=None):
    path = path if path is not None else (request.path or '/')
    if not path.startswith('/'):
        path = '/' + path
    if path != '/' and path.endswith('/'):
        path = path.rstrip('/')
    return path or '/'


def canonical_url(path=None):
    return f'{site_base_url()}{canonical_path(path)}'


def robots_directive(path=None):
    path = canonical_path(path)
    if path in NOINDEX_EXACT:
        return 'noindex, nofollow'
    for prefix in NOINDEX_PREFIXES:
        if prefix.endswith('/'):
            if path == prefix.rstrip('/') or path.startswith(prefix):
                if path.startswith('/seller/signup'):
                    return 'noindex, follow'
                return 'noindex, nofollow'
        elif path == prefix or path.startswith(prefix + '/'):
            return 'noindex, nofollow'
    return 'index, follow'


def template_seo_context():
    return {
        'seo_canonical_url': canonical_url(),
        'seo_robots': robots_directive(),
    }
