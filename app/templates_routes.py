# app/templates_routes.py - FIXED VERSION
from datetime import datetime, timedelta
from collections import defaultdict
from flask import Blueprint, app, flash, json, make_response, render_template, jsonify, request, session, redirect, url_for, current_app
from app.archive_routes import get_seller_store
from app.models import MunicipalityBoundary, OrderItem, ProductVariant, User, Store, Rider, Product, Order, SellerApplication, Cart, CartItem, ProductImage, POSOrder, POSOrderItem, Testimonial, HomePageTestimonial, SupportFAQ, SavedReport, ProductRating, StoreRating, MunicipalityBoundary, GCashQR, StockReduction, RiderOTP, RiderLocation, Notification, Category, CustomerOTP, SellerSignupOTP, AccountBan, StorePaymentSetting, Conversation, PasswordResetOTP, ProductAddonGroup, ProductAddonOption, CartItemAddon, OrderItemAddon, WishlistItem
from app.extensions import db
import os
from werkzeug.utils import secure_filename
from functools import wraps
from decimal import Decimal
from sqlalchemy import or_, inspect, text
from sqlalchemy.exc import ProgrammingError, OperationalError, IntegrityError
import uuid
import time
import jwt
import re
import pytz
#from PIL import Image
import io
from flask import send_file
from app.laguna_addresses import get_municipalities, get_barangays, get_coordinates, format_address, LAGUNA_ADDRESSES
from app.models import UserAddress

from app.utils.cloudinary_helper import upload_to_cloudinary, delete_from_cloudinary
# app/templates_routes.py - Add these imports at the top
from flask_wtf.csrf import generate_csrf
from sqlalchemy.orm import joinedload, selectinload

# Import the extensions from app (they're initialized in __init__.py)
from app import limiter
templates_bp = Blueprint('templates', __name__)

PH_MOBILE_REGEX = re.compile(r'^(?:\+63|0)9\d{9}$')
PHT = pytz.timezone('Asia/Manila')


def _sync_product_addon_groups(product, groups_data, delete_cloudinary_fn=None):
    """
    Create/update/delete ProductAddonGroup + ProductAddonOption from seller JSON.
    groups_data: list of {id?, name, sort_order?, is_active?, _delete?, options: [...]}
    option: {id?, name, price, stock_quantity, is_available?, show_in_you_may_also_like?,
             cloudinary_public_id?, cloudinary_url?, _delete?, _remove_image?}
    """
    if groups_data is None:
        return

    if not isinstance(groups_data, list):
        raise ValueError('addon_groups must be a list')

    delete_fn = delete_cloudinary_fn or delete_from_cloudinary
    kept_group_ids = []

    for g_idx, group_data in enumerate(groups_data):
        if not isinstance(group_data, dict):
            continue

        group_id = group_data.get('id')
        if group_data.get('_delete') and group_id:
            group = ProductAddonGroup.query.filter_by(id=group_id, product_id=product.id).first()
            if group:
                for opt in list(group.options):
                    if opt.image_public_id:
                        delete_fn(opt.image_public_id)
                db.session.delete(group)
            continue

        name = (group_data.get('name') or '').strip()
        if not name:
            continue

        if group_id:
            group = ProductAddonGroup.query.filter_by(id=group_id, product_id=product.id).first()
            if not group:
                continue
            group.name = name
            group.sort_order = int(group_data.get('sort_order', g_idx) or g_idx)
            group.is_active = bool(group_data.get('is_active', True))
            group.updated_at = datetime.utcnow()
        else:
            group = ProductAddonGroup(
                product_id=product.id,
                name=name,
                sort_order=int(group_data.get('sort_order', g_idx) or g_idx),
                is_active=bool(group_data.get('is_active', True)),
            )
            db.session.add(group)
            db.session.flush()

        kept_group_ids.append(group.id)
        kept_option_ids = []
        options_data = group_data.get('options') or []

        for o_idx, opt_data in enumerate(options_data):
            if not isinstance(opt_data, dict):
                continue

            opt_id = opt_data.get('id')
            if opt_data.get('_delete') and opt_id:
                opt = ProductAddonOption.query.filter_by(id=opt_id, group_id=group.id).first()
                if opt:
                    if opt.image_public_id:
                        delete_fn(opt.image_public_id)
                    db.session.delete(opt)
                continue

            opt_name = (opt_data.get('name') or '').strip()
            if not opt_name:
                continue

            try:
                price = Decimal(str(opt_data.get('price', 0) or 0))
            except Exception:
                price = Decimal('0')
            try:
                stock = int(opt_data.get('stock_quantity', 0) or 0)
            except (TypeError, ValueError):
                stock = 0

            show_ymal = bool(opt_data.get('show_in_you_may_also_like', False))
            is_available = bool(opt_data.get('is_available', True))

            if opt_data.get('_remove_image') and not opt_data.get('cloudinary_public_id'):
                raise ValueError(f'Add-on option "{opt_name}" requires an image')

            if opt_id:
                opt = ProductAddonOption.query.filter_by(id=opt_id, group_id=group.id).first()
                if not opt:
                    continue
                opt.name = opt_name
                opt.price = price
                # Stock is managed only via Inventory Add/Reduce — do not overwrite here
                opt.sort_order = int(opt_data.get('sort_order', o_idx) or o_idx)
                opt.is_available = is_available
                opt.show_in_you_may_also_like = show_ymal
                opt.updated_at = datetime.utcnow()

                if opt_data.get('cloudinary_public_id'):
                    if opt.image_public_id and opt.image_public_id != opt_data['cloudinary_public_id']:
                        delete_fn(opt.image_public_id)
                    opt.image_public_id = opt_data['cloudinary_public_id']
                    opt.image_url = opt_data.get('cloudinary_url')
                    opt.image_filename = f"addon_{opt_data['cloudinary_public_id']}.jpg"

                if not (opt.image_url or '').strip():
                    raise ValueError(f'Add-on option "{opt_name}" requires an image')
            else:
                if not opt_data.get('cloudinary_public_id') or not opt_data.get('cloudinary_url'):
                    raise ValueError(f'Add-on option "{opt_name}" requires an image')
                opt = ProductAddonOption(
                    group_id=group.id,
                    name=opt_name,
                    price=price,
                    stock_quantity=max(0, stock),
                    sort_order=int(opt_data.get('sort_order', o_idx) or o_idx),
                    is_available=is_available,
                    show_in_you_may_also_like=show_ymal,
                    image_public_id=opt_data.get('cloudinary_public_id'),
                    image_url=opt_data.get('cloudinary_url'),
                    image_filename=f"addon_{opt_data['cloudinary_public_id']}.jpg",
                )
                db.session.add(opt)
                db.session.flush()

            kept_option_ids.append(opt.id)

        for existing_opt in list(group.options):
            if existing_opt.id not in kept_option_ids:
                if existing_opt.image_public_id:
                    delete_fn(existing_opt.image_public_id)
                db.session.delete(existing_opt)

        db.session.flush()
        # If every remaining option is deactivated, deactivate the group too
        remaining = ProductAddonOption.query.filter_by(group_id=group.id).all()
        if remaining and all(not bool(o.is_available) for o in remaining):
            group.is_active = False
            group.updated_at = datetime.utcnow()

    for existing_group in list(product.addon_groups):
        if existing_group.id not in kept_group_ids:
            for opt in list(existing_group.options):
                if opt.image_public_id:
                    delete_fn(opt.image_public_id)
            db.session.delete(existing_group)


def _recover_db_session():
    """Drop a dead pooled connection so the next query gets a fresh one."""
    try:
        db.session.rollback()
    except Exception:
        pass
    try:
        db.session.remove()
    except Exception:
        pass


def _with_db_retry(fn, attempts=2):
    """Retry once on Railway/proxy 'server closed the connection' errors."""
    last_exc = None
    for attempt in range(attempts):
        try:
            return fn()
        except OperationalError as exc:
            last_exc = exc
            current_app.logger.warning(
                'DB OperationalError (attempt %s/%s): %s',
                attempt + 1, attempts, exc,
            )
            _recover_db_session()
            if attempt + 1 >= attempts:
                raise
    raise last_exc


def _password_strength_error(password):
    pw = password or ''
    if len(pw) < 8:
        return 'Password must be at least 8 characters'
    if not re.search(r'[a-z]', pw):
        return 'Password must include at least one lowercase letter'
    if not re.search(r'[A-Z]', pw):
        return 'Password must include at least one uppercase letter'
    if not re.search(r'[^A-Za-z0-9]', pw):
        return 'Password must include at least one special character'
    return None


def _normalize_ph_mobile(phone_raw):
    """Normalize PH mobile to 09XXXXXXXXX. Returns None for blank input."""
    phone = (phone_raw or '').strip()
    if not phone:
        return None

    compact = re.sub(r'[\s\-()]', '', phone)
    if compact.startswith('+63'):
        compact = '0' + compact[3:]
    elif compact.startswith('63') and len(compact) == 12:
        compact = '0' + compact[2:]

    return compact


def _ensure_home_page_testimonials_table():
    """If Alembic has not been applied yet, create the table from the ORM (safe no-op when it exists)."""
    from sqlalchemy import inspect

    try:
        if inspect(db.engine).has_table('home_page_testimonials'):
            return True
        HomePageTestimonial.__table__.create(db.engine, checkfirst=True)
        try:
            current_app.logger.info('Created missing table home_page_testimonials from model')
        except RuntimeError:
            pass
        return True
    except Exception as exc:
        try:
            current_app.logger.warning('Could not ensure home_page_testimonials table: %s', exc)
        except RuntimeError:
            pass
        return False


def _ensure_home_page_testimonials_schema():
    """Compatibility no-op for current testimonial schema."""
    return True


def _ensure_support_faqs_table():
    """Create support_faqs from ORM if migration wasn't run yet."""
    from sqlalchemy import inspect

    try:
        if inspect(db.engine).has_table('support_faqs'):
            return True
        SupportFAQ.__table__.create(db.engine, checkfirst=True)
        try:
            current_app.logger.info('Created missing table support_faqs from model')
        except RuntimeError:
            pass
        return True
    except Exception as exc:
        try:
            current_app.logger.warning('Could not ensure support_faqs table: %s', exc)
        except RuntimeError:
            pass
        return False


def _ensure_store_payment_settings_table():
    """Create store_payment_settings from ORM if migration wasn't run yet."""
    from sqlalchemy import inspect

    try:
        if inspect(db.engine).has_table('store_payment_settings'):
            return True
        StorePaymentSetting.__table__.create(db.engine, checkfirst=True)
        return True
    except Exception:
        return False


def _ensure_account_bans_table():
    """Create account_bans from ORM if migration wasn't run yet."""
    from sqlalchemy import inspect

    try:
        if inspect(db.engine).has_table('account_bans'):
            return True
        AccountBan.__table__.create(db.engine, checkfirst=True)
        try:
            current_app.logger.info('Created missing table account_bans from model')
        except RuntimeError:
            pass
        return True
    except Exception as exc:
        try:
            current_app.logger.warning('Could not ensure account_bans table: %s', exc)
        except RuntimeError:
            pass
        return False


def _ensure_saved_reports_table():
    """Create saved_reports from ORM if migration wasn't run yet."""
    from sqlalchemy import inspect

    try:
        if inspect(db.engine).has_table('saved_reports'):
            return True
        SavedReport.__table__.create(db.engine, checkfirst=True)
        try:
            current_app.logger.info('Created missing table saved_reports from model')
        except RuntimeError:
            pass
        return True
    except Exception as exc:
        try:
            current_app.logger.warning('Could not ensure saved_reports table: %s', exc)
        except RuntimeError:
            pass
        return False


# Configure upload folder
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


# In templates_routes.py, make sure you have this context processor
@templates_bp.context_processor
def inject_csrf_token():
    """Inject CSRF token into all templates"""
    from flask_wtf.csrf import generate_csrf
    return dict(csrf_token=generate_csrf)


# ═════════════════════════════════════════════════════════════════════════════
# AUTHENTICATION HELPER - Supports both Flask Sessions & JWT Tokens
# ═════════════════════════════════════════════════════════════════════════════
def get_authenticated_user_id():
    """
    Get user ID from either:
    1. Flask session (for web browsers)
    2. JWT token in Authorization header (for mobile apps)
    
    Returns: user_id (int) or None if not authenticated
    """
    # Try session first (for web)
    if 'user_id' in session:
        return session['user_id']
    
    # Try JWT token (for mobile apps like Flutter)
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]  # Remove 'Bearer ' prefix
        try:
            from flask_jwt_extended import decode_token
            payload = decode_token(token)
            # Extract user_id from token claims
            user_id = payload.get('user_id') or payload.get('sub')
            if user_id:
                # Convert string user_id to int if needed
                try:
                    return int(user_id)
                except (ValueError, TypeError):
                    return None
        except Exception as e:
            print(f"⚠️ JWT validation failed: {e}")
    
    return None


def _serialize_customer_order(
    order,
    rated_item_ids=None,
    store_rated=None,
    store_rating_value=None,
    product_rating_values=None,
    item_ratings=None,
):
    """Shape order data for the customer account order UI.

    When listing many orders, pass rated_item_ids / store_rated / rating values
    to avoid N+1 queries.
    """
    items_payload = []
    total_quantity = 0
    product_vals = list(product_rating_values or [])
    store_val = store_rating_value
    ratings_by_item = dict(item_ratings or {})

    if order.status in ('delivered', 'completed'):
        if rated_item_ids is None or product_rating_values is None or item_ratings is None:
            try:
                ratings = ProductRating.query.filter_by(order_id=order.id).all()
                if rated_item_ids is None:
                    rated_item_ids = {r.order_item_id for r in ratings if r.order_item_id}
                if product_rating_values is None:
                    product_vals = [int(r.rating) for r in ratings if r.rating]
                if item_ratings is None:
                    ratings_by_item = {
                        r.order_item_id: int(r.rating)
                        for r in ratings
                        if r.order_item_id is not None and r.rating is not None
                    }
            except Exception:
                if rated_item_ids is None:
                    rated_item_ids = set()
                if product_rating_values is None:
                    product_vals = []
                if item_ratings is None:
                    ratings_by_item = {}
        if store_rated is None:
            try:
                store_row = StoreRating.query.filter_by(
                    order_id=order.id, customer_id=order.customer_id
                ).first()
                store_rated_flag = store_row is not None
                if store_rating_value is None:
                    store_val = int(store_row.rating) if store_row and store_row.rating else None
            except Exception:
                store_rated_flag = False
                if store_rating_value is None:
                    store_val = None
        else:
            store_rated_flag = bool(store_rated)
            if store_rating_value is None and store_rated_flag:
                try:
                    store_row = StoreRating.query.filter_by(
                        order_id=order.id, customer_id=order.customer_id
                    ).first()
                    store_val = int(store_row.rating) if store_row and store_row.rating else None
                except Exception:
                    store_val = None
    else:
        rated_item_ids = set()
        store_rated_flag = True  # N/A for non-delivered; treat as satisfied for all_rated
        store_val = None
        product_vals = []
        ratings_by_item = {}

    for item in order.items:
        quantity = item.quantity or 0
        unit_price = float(item.price or 0)
        total_quantity += quantity
        addons_list = [a.to_dict() for a in (item.addons or [])]
        addons_sum = float(item.addons_total or 0)
        item_rating = ratings_by_item.get(item.id)
        if item_rating is not None:
            item_rating = max(1, min(5, int(item_rating)))

        items_payload.append({
            'id': item.id,
            'product_id': item.product_id,
            'variant_id': item.variant_id,
            'product_name': item.product.name if item.product else 'Product',
            'name': item.product.name if item.product else 'Product',
            'variant_name': item.variant.name if item.variant else None,
            'quantity': quantity,
            'price': unit_price,
            'total': float(quantity * unit_price) + addons_sum,
            'product_image_url': item.product_image,
            'image_url': item.product_image,
            'is_rated': item.id in rated_item_ids,
            'rating': item_rating,
            'addons': addons_list,
            'addons_total': addons_sum,
        })

    n_items = len(order.items) if order.items else 0
    products_all_rated = (len(rated_item_ids) >= n_items) if n_items else True
    if order.status in ('delivered', 'completed'):
        all_rated = bool(store_rated_flag) and products_all_rated
    else:
        all_rated = True

    avg_product_rating = None
    if product_vals:
        avg_product_rating = round(sum(product_vals) / len(product_vals), 1)

    # Card display: prefer store rating, else rounded product average.
    customer_rating = None
    if store_val is not None:
        customer_rating = max(1, min(5, int(store_val)))
    elif avg_product_rating is not None:
        customer_rating = max(1, min(5, int(round(avg_product_rating))))

    return {
        'id': order.id,
        'order_number': f'ORD-{order.id:05d}',
        'status': order.status,
        'payment_method': order.payment_method,
        'payment_status': order.payment_status,
        'subtotal_amount': float(order.subtotal_amount or 0),
        'delivery_fee': float(order.delivery_fee or 0),
        'distance_km': order.distance_km,
        'total_amount': float(order.total_amount or 0),
        'delivery_address': order.delivery_address,
        'delivery_notes': order.delivery_notes,
        'payment_proof_url': order.payment_proof_url,
        'done_preparing_proof_url': order.done_preparing_proof_url,
        'delivery_proof_url': order.delivery_proof_url,
        'delivery_proof_2_url': order.delivery_proof_2_url,
        'created_at': order.created_at.isoformat() if order.created_at else None,
        'updated_at': order.updated_at.isoformat() if order.updated_at else None,
        'requested_delivery_date': order.requested_delivery_date.isoformat()
        if getattr(order, 'requested_delivery_date', None)
        else None,
        'requested_delivery_time': getattr(order, 'requested_delivery_time', None),
        'store_id': order.store_id,
        'store_name': order.store.name if order.store else 'Store',
        'store_logo': order.store.logo_url if order.store else None,
        'store_contact': order.store.contact_number if order.store else None,
        'rider_id': order.rider_id,
        'rider_name': (
            order.assigned_rider.user.full_name
            if getattr(order, 'assigned_rider', None) and order.assigned_rider.user
            else None
        ),
        'rider_vehicle': (
            order.assigned_rider.vehicle_type
            if getattr(order, 'assigned_rider', None)
            else None
        ),
        'item_count': total_quantity,
        'items': items_payload,
        'store_rated': bool(store_rated_flag),
        'all_rated': all_rated,
        'rated_count': len(rated_item_ids),
        'store_rating_value': int(store_val) if store_val is not None else None,
        'avg_product_rating': avg_product_rating,
        'customer_rating': customer_rating,
        'cancellation_reason_code': getattr(order, 'cancellation_reason_code', None),
        'cancellation_reason': getattr(order, 'cancellation_reason', None),
        'cancelled_at': order.cancelled_at.isoformat()
        if getattr(order, 'cancelled_at', None)
        else None,
    }


def _ensure_order_fulfillment_columns():
    """Backfill missing order proof/status columns when migrations are pending."""
    required = {
        'done_preparing_proof': "ALTER TABLE orders ADD COLUMN done_preparing_proof VARCHAR(255)",
        'done_preparing_proof_public_id': "ALTER TABLE orders ADD COLUMN done_preparing_proof_public_id VARCHAR(255)",
        'done_preparing_proof_url': "ALTER TABLE orders ADD COLUMN done_preparing_proof_url VARCHAR(500)",
        'completed_at': "ALTER TABLE orders ADD COLUMN completed_at TIMESTAMP",
        'cancellation_reason_code': "ALTER TABLE orders ADD COLUMN cancellation_reason_code VARCHAR(50)",
        'cancellation_reason': "ALTER TABLE orders ADD COLUMN cancellation_reason TEXT",
        'cancelled_at': "ALTER TABLE orders ADD COLUMN cancelled_at TIMESTAMP",
    }
    try:
        cols = {c['name'] for c in inspect(db.engine).get_columns('orders')}
        for column_name, stmt in required.items():
            if column_name in cols:
                continue
            try:
                db.session.execute(text(stmt))
                db.session.commit()
            except Exception as col_exc:
                db.session.rollback()
                msg = str(col_exc).lower()
                if 'duplicate column' in msg or 'already exists' in msg:
                    continue
                current_app.logger.warning('Could not add orders.%s: %s', column_name, col_exc)
        refreshed = {c['name'] for c in inspect(db.engine).get_columns('orders')}
        return all(col in refreshed for col in required.keys())
    except Exception as exc:
        db.session.rollback()
        current_app.logger.warning('Failed ensuring order fulfillment columns: %s', exc)
        return False


def _ensure_pos_order_item_line_columns():
    """Add line_name / line_image_url / addon_option_id for accurate POS add-on display."""
    required = {
        'line_name': "ALTER TABLE pos_order_items ADD COLUMN line_name VARCHAR(255)",
        'line_image_url': "ALTER TABLE pos_order_items ADD COLUMN line_image_url VARCHAR(500)",
        'addon_option_id': (
            "ALTER TABLE pos_order_items ADD COLUMN addon_option_id INTEGER "
            "REFERENCES product_addon_options(id) ON DELETE SET NULL"
        ),
    }
    try:
        cols = {c['name'] for c in inspect(db.engine).get_columns('pos_order_items')}
        for column_name, stmt in required.items():
            if column_name in cols:
                continue
            try:
                db.session.execute(text(stmt))
                db.session.commit()
            except Exception as col_exc:
                db.session.rollback()
                msg = str(col_exc).lower()
                if 'duplicate column' in msg or 'already exists' in msg:
                    continue
                # Some DBs reject REFERENCES in ADD COLUMN; retry without FK
                if column_name == 'addon_option_id':
                    try:
                        db.session.execute(text(
                            "ALTER TABLE pos_order_items ADD COLUMN addon_option_id INTEGER"
                        ))
                        db.session.commit()
                        continue
                    except Exception as retry_exc:
                        db.session.rollback()
                        msg2 = str(retry_exc).lower()
                        if 'duplicate column' in msg2 or 'already exists' in msg2:
                            continue
                        current_app.logger.warning(
                            'Could not add pos_order_items.%s: %s', column_name, retry_exc
                        )
                        continue
                current_app.logger.warning(
                    'Could not add pos_order_items.%s: %s', column_name, col_exc
                )
        refreshed = {c['name'] for c in inspect(db.engine).get_columns('pos_order_items')}
        return all(col in refreshed for col in required.keys())
    except Exception as exc:
        db.session.rollback()
        current_app.logger.warning('Failed ensuring pos_order_items line columns: %s', exc)
        return False


@templates_bp.route('/health')
@limiter.exempt
def health_check():
    return jsonify({'status': 'ok'}), 200


@templates_bp.route('/debug/test-email')
@limiter.exempt
def debug_test_email():
    """Temporary endpoint to diagnose SMTP issues on Railway."""
    import smtplib
    import socket
    result = {
        'mail_server': current_app.config.get('MAIL_SERVER', ''),
        'mail_port': current_app.config.get('MAIL_PORT', ''),
        'mail_use_tls': current_app.config.get('MAIL_USE_TLS', False),
        'mail_use_ssl': current_app.config.get('MAIL_USE_SSL', False),
        'mail_username': current_app.config.get('MAIL_USERNAME', ''),
        'mail_password_set': bool(current_app.config.get('MAIL_PASSWORD')),
        'mail_default_sender': current_app.config.get('MAIL_DEFAULT_SENDER', ''),
    }
    
    server = result['mail_server']
    port = result['mail_port']
    
    # Test DNS resolution (IPv4 only)
    try:
        all_addrs = socket.getaddrinfo(server, port)
        ipv4_addrs = [a for a in all_addrs if a[0] == socket.AF_INET]
        ipv6_addrs = [a for a in all_addrs if a[0] == socket.AF_INET6]
        result['dns_resolved'] = True
        result['ipv4_addrs'] = [str(a[4]) for a in ipv4_addrs]
        result['ipv6_addrs'] = [str(a[4]) for a in ipv6_addrs]
        result['using_ipv4'] = str(ipv4_addrs[0][4]) if ipv4_addrs else 'none'
    except Exception as e:
        result['dns_resolved'] = False
        result['dns_error'] = str(e)
        return jsonify(result), 200
    
    # Test SMTP connection forcing IPv4
    try:
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(15)
        
        # Force IPv4 for this connection
        ipv4_ip = ipv4_addrs[0][4][0] if ipv4_addrs else server
        
        if result['mail_use_ssl']:
            smtp = smtplib.SMTP_SSL(ipv4_ip, port, timeout=15)
        else:
            smtp = smtplib.SMTP(ipv4_ip, port, timeout=15)
        
        smtp.ehlo()
        
        if result['mail_use_tls'] and not result['mail_use_ssl']:
            smtp.starttls()
            smtp.ehlo()
        
        result['smtp_connected'] = True
        
        # Test login
        username = current_app.config.get('MAIL_USERNAME', '')
        password = current_app.config.get('MAIL_PASSWORD', '')
        if username and password:
            try:
                smtp.login(username, password)
                result['smtp_login'] = True
            except Exception as e:
                result['smtp_login'] = False
                result['smtp_login_error'] = str(e)
        
        smtp.quit()
        socket.setdefaulttimeout(old_timeout)
        
    except Exception as e:
        result['smtp_connected'] = False
        result['smtp_error'] = str(e)
    
    return jsonify(result), 200


def _store_fulfillment_stats(store_ids):
    """One grouped query for delivered/completed vs total orders per store."""
    stats = {int(sid): (0, 0) for sid in store_ids or []}
    if not store_ids:
        return stats
    rows = (
        db.session.query(
            Order.store_id,
            Order.status,
            db.func.count(Order.id),
        )
        .filter(Order.store_id.in_(list(store_ids)))
        .group_by(Order.store_id, Order.status)
        .all()
    )
    totals = defaultdict(int)
    fulfilled = defaultdict(int)
    for store_id, status, count in rows:
        count = int(count or 0)
        totals[store_id] += count
        if status in ('delivered', 'completed'):
            fulfilled[store_id] += count
    for sid in list(stats):
        stats[sid] = (totals.get(sid, 0), fulfilled.get(sid, 0))
    return stats


def _apply_store_performance(store_data, total_orders, delivered_or_completed):
    fulfillment_score = (
        (delivered_or_completed / total_orders) * 5.0
        if total_orders > 0 else 0.0
    )
    store_data['performance_score'] = max(0.0, min(5.0, round(fulfillment_score, 1)))
    store_data['performance_fulfilled_count'] = int(delivered_or_completed)
    store_data['performance_order_count'] = int(total_orders)
    return store_data


def _store_rating_stats(store_ids):
    """Average post-order StoreRating per store: {store_id: (avg, count)}."""
    stats = {int(sid): (0.0, 0) for sid in store_ids or []}
    if not store_ids:
        return stats
    rows = (
        db.session.query(
            StoreRating.store_id,
            db.func.avg(StoreRating.rating),
            db.func.count(StoreRating.id),
        )
        .filter(StoreRating.store_id.in_(list(store_ids)))
        .group_by(StoreRating.store_id)
        .all()
    )
    for store_id, avg_rating, review_count in rows:
        stats[int(store_id)] = (
            round(float(avg_rating or 0), 1),
            int(review_count or 0),
        )
    return stats


def _apply_store_card_rating(store_data, avg_rating, review_count):
    store_data['avg_rating'] = float(avg_rating or 0)
    store_data['review_count'] = int(review_count or 0)
    return store_data


def _public_storefront_sellable_filter():
    """Public storefront stock rule: main stock or any sellable variant stock."""
    variant_in_stock_exists = db.session.query(ProductVariant.id).filter(
        ProductVariant.product_id == Product.id,
        ProductVariant.is_available == True,
        ProductVariant.stock_quantity > 0
    ).exists()
    return db.or_(
        Product.stock_quantity > 0,
        variant_in_stock_exists
    )


def _public_storefront_product_base_query(require_sellable=False):
    """Products eligible for the public storefront: active store, not archived, and available.

    When require_sellable=True (landing / browse catalog), hide products that have
    no main stock and no sellable variant stock. Store detail pages keep OOS products.
    """
    q = (
        Product.query
        .join(Store, Product.store_id == Store.id)
        .options(
            joinedload(Product.store),
            joinedload(Product.main_category),
            joinedload(Product.store_category),
            selectinload(Product.images),
            selectinload(Product.variants),
        )
        .filter(
            Product.is_archived == False,
            Product.is_available == True,
            Store.status == 'active',
        )
    )
    if require_sellable:
        q = q.filter(_public_storefront_sellable_filter())
    return q


def _product_list_for_storefront(orm_products):
    """Match landing-page dict shape (store_name, nested categories) for Jinja cards."""
    from app.addon_helpers import ymal_addon_option_dicts

    product_list = []
    product_ids = [p.id for p in orm_products if getattr(p, 'id', None) is not None]

    # Per-option aggregates: card shows Standard (main) only; variants stay separate.
    # variant_ratings keys: "main" | "<variant_id>" → {avg, count}
    # overall_* = all ratings for the product (main + variants) for reference if needed.
    rating_map = {}          # product_id → (main_avg, main_count)
    overall_map = {}         # product_id → (overall_avg, overall_count)
    variant_ratings_map = {} # product_id → {key: {avg, count}}

    if product_ids:
        overall_rows = (
            db.session.query(
                ProductRating.product_id,
                db.func.avg(ProductRating.rating),
                db.func.count(ProductRating.id),
            )
            .filter(ProductRating.product_id.in_(product_ids))
            .group_by(ProductRating.product_id)
            .all()
        )
        for product_id, avg_rating, review_count in overall_rows:
            overall_map[product_id] = (
                round(float(avg_rating or 0), 1),
                int(review_count or 0),
            )

        option_rows = (
            db.session.query(
                ProductRating.product_id,
                ProductRating.variant_id,
                db.func.avg(ProductRating.rating),
                db.func.count(ProductRating.id),
            )
            .filter(ProductRating.product_id.in_(product_ids))
            .group_by(ProductRating.product_id, ProductRating.variant_id)
            .all()
        )
        for product_id, variant_id, avg_rating, review_count in option_rows:
            key = str(variant_id) if variant_id else 'main'
            bucket = {
                'avg': round(float(avg_rating or 0), 1),
                'count': int(review_count or 0),
            }
            variant_ratings_map.setdefault(product_id, {})[key] = bucket
            if key == 'main':
                rating_map[product_id] = (bucket['avg'], bucket['count'])

    ymal_by_store = {}
    for product in orm_products:
        product_dict = product.to_dict()
        if product.store:
            product_dict['store_name'] = product.store.name
        else:
            product_dict['store_name'] = 'Unknown Store'
        if product.main_category:
            product_dict['main_category'] = {
                'id': product.main_category.id,
                'name': product.main_category.name,
                'slug': product.main_category.slug
            }
        if product.store_category:
            product_dict['store_category'] = {
                'id': product.store_category.id,
                'name': product.store_category.name,
                'slug': product.store_category.slug
            }
        # Listing card = Standard / main-product ratings only (not variants)
        avg_rating, review_count = rating_map.get(product.id, (0.0, 0))
        overall_avg, overall_count = overall_map.get(product.id, (0.0, 0))
        product_dict['avg_rating'] = avg_rating
        product_dict['review_count'] = review_count
        product_dict['overall_avg_rating'] = overall_avg
        product_dict['overall_review_count'] = overall_count
        product_dict['variant_ratings'] = variant_ratings_map.get(product.id) or {}
        store_id = getattr(product, 'store_id', None)
        if store_id not in ymal_by_store:
            ymal_by_store[store_id] = ymal_addon_option_dicts(product) if store_id else []
        product_dict['ymal_addon_options'] = list(ymal_by_store.get(store_id) or [])
        product_list.append(product_dict)
    return product_list


def _normalize_place_name(value):
    """Case/accent-insensitive place comparison for municipality matching."""
    import unicodedata
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return ' '.join(text.casefold().split())


def _get_default_customer_address(user_id):
    if not user_id:
        return None
    return (
        UserAddress.query.filter_by(user_id=user_id)
        .order_by(UserAddress.is_default.desc(), UserAddress.created_at.desc())
        .first()
    )


def _store_delivery_match(store, address):
    """Evaluate whether a store can deliver to the given user address.

    Used for storefront filtering: when Browse outside area is off, only
    stores that truly cover the customer's default address should appear.
    """
    if not store or not address:
        return {'can_deliver': False, 'reason': 'Set your default address to check delivery coverage.'}

    address_municipality = _normalize_place_name(address.municipality)
    has_coords = address.latitude is not None and address.longitude is not None
    method = (store.delivery_method or 'radius').strip().casefold()

    try:
        if method == 'municipality':
            selected = store.selected_municipalities or []
            if selected:
                if not address_municipality:
                    return {
                        'can_deliver': False,
                        'reason': 'Your address is missing a municipality.',
                    }
                matched = any(
                    _normalize_place_name(name) == address_municipality
                    for name in selected
                )
                if not matched:
                    return {
                        'can_deliver': False,
                        'reason': f"{store.name} does not deliver to {address.municipality}.",
                    }
                return {'can_deliver': True, 'reason': None}

            # No municipality list — fall back to polygon coverage when available.
            if has_coords and (
                store.municipality_delivery_area is not None
                or store.delivery_area is not None
            ):
                try:
                    if store.can_deliver_to(address.latitude, address.longitude):
                        return {'can_deliver': True, 'reason': None}
                    return {
                        'can_deliver': False,
                        'reason': 'Outside this store delivery zone.',
                    }
                except Exception:
                    return {
                        'can_deliver': False,
                        'reason': 'Could not validate delivery coverage right now.',
                    }

            return {
                'can_deliver': False,
                'reason': 'Store has no delivery municipalities configured.',
            }

        if not has_coords:
            return {'can_deliver': False, 'reason': 'Your default address is missing map coordinates.'}

        distance = store.calculate_distance(address.latitude, address.longitude)
        if distance is None or distance == float('inf'):
            return {'can_deliver': False, 'reason': 'Store location is incomplete for delivery matching.'}

        max_distance = float(store.max_delivery_distance or 0)
        if max_distance and distance > max_distance:
            return {'can_deliver': False, 'reason': 'Outside delivery distance.'}

        if method == 'radius':
            radius_limit = float(store.delivery_radius_km or max_distance or 0)
            if not radius_limit:
                return {
                    'can_deliver': False,
                    'reason': 'Store has no delivery radius configured.',
                }
            if distance > radius_limit:
                return {'can_deliver': False, 'reason': 'Outside delivery distance.'}
            return {'can_deliver': True, 'reason': None}

        # Zone / custom polygon coverage
        has_area = (
            store.zone_delivery_area is not None
            or store.delivery_area is not None
            or store.municipality_delivery_area is not None
        )
        if has_area:
            try:
                if not store.can_deliver_to(address.latitude, address.longitude):
                    return {
                        'can_deliver': False,
                        'reason': 'Outside this store delivery zone.',
                    }
                return {'can_deliver': True, 'reason': None}
            except Exception:
                return {
                    'can_deliver': False,
                    'reason': 'Could not validate delivery coverage right now.',
                }

        # No geometry configured — only allow if a max distance already passed above.
        if max_distance:
            return {'can_deliver': True, 'reason': None}

        return {
            'can_deliver': False,
            'reason': 'Store has no delivery area configured.',
        }
    except Exception:
        return {'can_deliver': False, 'reason': 'Could not validate delivery coverage right now.'}


@templates_bp.route('/googlea5dba4f15d616309.html')
def google_site_verification():
    """Google Search Console HTML-file ownership check (keep after verify)."""
    return (
        'google-site-verification: googlea5dba4f15d616309.html\n',
        200,
        {'Content-Type': 'text/html; charset=UTF-8'},
    )


@templates_bp.route('/')
@limiter.limit("5 per minute")
def index():
    """Show the e-commerce landing page to everyone"""
    try:
        # Get all main categories from database for the navigation
        from app.models import Category
        main_categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()

        current_user_id = session.get('user_id')
        is_customer = session.get('role') == 'customer' and current_user_id
        customer_address = _get_default_customer_address(current_user_id) if is_customer else None

        browse_all_arg = request.args.get('browse_all')
        if browse_all_arg is not None:
            session['storefront_browse_all'] = browse_all_arg == '1'
        browse_all_mode = bool(session.get('storefront_browse_all', False))
        location_filter_on = bool(is_customer and customer_address and not browse_all_mode)

        # Over-fetch when filtering so the featured strip still fills with in-range items.
        product_fetch_limit = 200 if location_filter_on else 40
        products = (
            _public_storefront_product_base_query(require_sellable=True)
            .order_by(Product.created_at.desc())
            .limit(product_fetch_limit)
            .all()
        )
        product_delivery_map = {}
        if is_customer and customer_address:
            for product in products:
                delivery = _store_delivery_match(product.store, customer_address)
                product_delivery_map[product.id] = delivery

        if location_filter_on:
            products = [
                p for p in products
                if product_delivery_map.get(p.id, {}).get('can_deliver')
            ]

        # Only the featured grid is rendered on this route.  Serializing the
        # full over-fetch here loaded every image and variant before discarding
        # most of them.
        products = products[:12]
        product_list = _product_list_for_storefront(products)
        for pd in product_list:
            delivery = product_delivery_map.get(
                pd.get('id'),
                {'can_deliver': True, 'reason': None},
            )
            if is_customer and customer_address:
                pd['can_deliver_to_customer'] = bool(delivery.get('can_deliver'))
                pd['delivery_block_reason'] = delivery.get('reason')
            else:
                pd['can_deliver_to_customer'] = True
                pd['delivery_block_reason'] = None

        # Get active stores - logo_url property now handles seller_application lookup by seller_id
        store_fetch_limit = 80 if location_filter_on else 40
        stores = Store.query\
            .filter_by(status='active')\
            .order_by(Store.created_at.desc())\
            .limit(store_fetch_limit)\
            .all()

        if location_filter_on:
            stores = [
                store for store in stores
                if _store_delivery_match(store, customer_address).get('can_deliver')
            ]
        stores = stores[:12]
        store_ids = [store.id for store in stores]
        fulfillment_map = _store_fulfillment_stats(store_ids)
        rating_map = _store_rating_stats(store_ids)

        store_list = []
        for store in stores:
            store_data = store.to_dict()
            store_data['can_deliver_to_customer'] = True
            store_data['delivery_block_reason'] = None

            if is_customer:
                delivery = _store_delivery_match(store, customer_address)
                store_data['can_deliver_to_customer'] = bool(delivery.get('can_deliver'))
                store_data['delivery_block_reason'] = delivery.get('reason')

            total_orders, delivered_or_completed = fulfillment_map.get(store.id, (0, 0))
            _apply_store_performance(store_data, total_orders, delivered_or_completed)
            avg_rating, review_count = rating_map.get(store.id, (0.0, 0))
            _apply_store_card_rating(store_data, avg_rating, review_count)
            store_list.append(store_data)

        # Format categories for the template (for featured categories section)
        featured_categories = []
        for cat in main_categories:
            featured_categories.append({
                'id': cat.id,
                'name': cat.name,
                'slug': cat.slug,
                'icon': cat.icon or 'flower-line',  # Default icon if none
                'description': cat.description,
                'image_url': cat.image_url
            })
        try:
            _ensure_home_page_testimonials_table()
            _ensure_home_page_testimonials_schema()
            home_testimonials = (
                HomePageTestimonial.query.filter_by(is_approved=True)
                .order_by(HomePageTestimonial.created_at.desc())
                .limit(12)
                .all()
            )
        except Exception as testimonial_err:
            current_app.logger.warning('Home testimonials query skipped: %s', testimonial_err)
            db.session.rollback()
            home_testimonials = []

        home_testimonial_author_name = None
        home_testimonial_can_submit = False
        home_testimonial_lock_reason = None
        home_testimonial_existing = None
        if session.get('user_id'):
            _author = User.query.get(session['user_id'])
            if _author and _author.full_name:
                home_testimonial_author_name = _author.full_name.strip()
                has_order = (
                    db.session.query(Order.id)
                    .filter(
                        Order.customer_id == _author.id,
                        Order.status.in_(['delivered', 'completed'])
                    )
                    .first() is not None
                )
                if has_order:
                    home_testimonial_can_submit = True
                    home_testimonial_existing = (
                        HomePageTestimonial.query
                        .filter(HomePageTestimonial.customer_name == home_testimonial_author_name)
                        .order_by(HomePageTestimonial.created_at.desc())
                        .first()
                    )
                else:
                    home_testimonial_lock_reason = 'You can review the website after placing at least one order.'

        return render_template(
            'index.html',
            products=product_list,
            stores=store_list,
            categories=featured_categories,  # For featured categories section
            main_categories=main_categories,   # For navigation menu
            now=datetime.now(),
            home_testimonials=home_testimonials,
            home_testimonial_author_name=home_testimonial_author_name,
            home_testimonial_can_submit=home_testimonial_can_submit,
            home_testimonial_lock_reason=home_testimonial_lock_reason,
            home_testimonial_existing=home_testimonial_existing.to_dict() if home_testimonial_existing else None,
            browse_all_mode=browse_all_mode,
            location_filter_enabled=bool(is_customer and customer_address and not browse_all_mode),
            customer_has_default_address=bool(customer_address),
            customer_location_label=(
                f"{customer_address.barangay}, {customer_address.municipality}"
                if customer_address and customer_address.barangay and customer_address.municipality
                else (
                    customer_address.municipality
                    if customer_address and customer_address.municipality
                    else None
                )
            ),
        )
    except Exception as e:
        print(f"ERROR loading landing page: {str(e)}")
        import traceback
        traceback.print_exc()
        try:
            db.session.rollback()
        except Exception:
            pass
        return render_template('index.html', 
                             products=[], 
                             stores=[], 
                             categories=[],
                             main_categories=[],
                             home_testimonials=[],
                             home_testimonial_author_name=None,
                             home_testimonial_can_submit=False,
                             home_testimonial_lock_reason=None,
                             home_testimonial_existing=None,
                             browse_all_mode=False,
                             location_filter_enabled=False,
                             customer_has_default_address=False,
                             customer_location_label=None)


@templates_bp.route('/home-testimonials', methods=['POST'])
@limiter.limit('20 per minute')
def submit_home_testimonial():
    """Persist a public home-page testimonial (shown when is_approved is True)."""
    if not request.is_json:
        return jsonify({'success': False, 'error': 'JSON body required'}), 400

    uid = session.get('user_id')
    if not uid:
        return jsonify({
            'success': False,
            'error': 'Please sign in to submit a testimonial. Your account name will be shown with your review.',
        }), 401

    user = User.query.get(uid)
    if not user or not user.full_name:
        return jsonify({'success': False, 'error': 'Account not found. Please sign in again.'}), 401

    name = (user.full_name or '').strip()
    if len(name) > 120:
        name = name[:120]

    has_order = (
        db.session.query(Order.id)
        .filter(
            Order.customer_id == uid,
            Order.status.in_(['delivered', 'completed'])
        )
        .first() is not None
    )
    if not has_order:
        return jsonify({
            'success': False,
            'error': 'You can review the website after placing at least one order.',
        }), 403

    data = request.get_json(silent=True) or {}
    comment = (data.get('comment') or '').strip()
    if 'rating' not in data:
        return jsonify({'success': False, 'error': 'Rating is required.'}), 400
    try:
        rating = int(data.get('rating'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Rating must be a number from 1 to 5.'}), 400
    if rating < 1 or rating > 5:
        return jsonify({'success': False, 'error': 'Rating must be between 1 and 5.'}), 400

    if len(comment) < 10 or len(comment) > 2000:
        return jsonify({'success': False, 'error': 'Testimonial must be between 10 and 2000 characters.'}), 400

    if not _ensure_home_page_testimonials_table():
        return jsonify({
            'success': False,
            'error': 'Could not create testimonials storage. Check database permissions or run: flask db upgrade',
        }), 503
    _ensure_home_page_testimonials_schema()

    row = (
        HomePageTestimonial.query
        .filter(HomePageTestimonial.customer_name == name)
        .order_by(HomePageTestimonial.created_at.desc())
        .first()
    )
    if row:
        row.customer_name = name
        row.rating = rating
        row.comment = comment
        mode = 'updated'
        status_code = 200
    else:
        row = HomePageTestimonial(
            customer_name=name,
            rating=rating,
            comment=comment,
            is_approved=True,
        )
        db.session.add(row)
        mode = 'created'
        status_code = 201
    try:
        db.session.commit()
    except (ProgrammingError, OperationalError) as ex:
        db.session.rollback()
        current_app.logger.exception('submit_home_testimonial DB error: %s', ex)
        err = str(getattr(ex, 'orig', ex)) or str(ex)
        if 'home_page_testimonials' in err and (
            'does not exist' in err
            or 'UndefinedTable' in err
            or 'no such table' in err.lower()
        ):
            return jsonify({
                'success': False,
                'error': 'Testimonials table is missing. Run: flask db upgrade (revision add_home_page_testimonials_001).',
            }), 503
        return jsonify({
            'success': False,
            'error': 'Database error while saving. Check server logs or run migrations.',
        }), 500
    except Exception as ex:
        db.session.rollback()
        current_app.logger.exception('submit_home_testimonial failed: %s', ex)
        err = str(getattr(ex, 'orig', ex)) or str(ex)
        if 'home_page_testimonials' in err and (
            'does not exist' in err
            or 'UndefinedTable' in err
            or 'no such table' in err.lower()
        ):
            return jsonify({
                'success': False,
                'error': 'Testimonials table is missing. Run: flask db upgrade (revision add_home_page_testimonials_001).',
            }), 503
        return jsonify({'success': False, 'error': 'Could not save your testimonial. Please try again later.'}), 500

    return jsonify({'success': True, 'id': row.id, 'mode': mode}), status_code


def seller_required(f):
    """Require user to be logged in as a seller with an accessible storefront."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('templates.login'))
        if session.get('role') != 'seller':
            return redirect(url_for('templates.dashboard'))
        # Admin-suspended storefronts cannot use seller tools.
        # Seller-chosen "inactive" still allows portal access (store is just hidden).
        if request.endpoint != 'templates.seller_store_suspended':
            if (
                _seller_portal_suspended_store(session['user_id'])
                and not _seller_portal_manageable_store(session['user_id'])
            ):
                return redirect(url_for('templates.seller_store_suspended'))
        return f(*args, **kwargs)
    return decorated


@templates_bp.route('/seller/products/<int:product_id>/archive-choice', methods=['POST'])
@seller_required
def product_archive_choice(product_id):
    """Handle seller's choice when deleting a product"""
    try:
        store = get_seller_store()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        data = request.get_json()
        action = data.get('action')  # 'archive', 'delete', 'cancel'
        
        if action == 'archive':
            product.archive(session['user_id'])
            db.session.commit()
            return jsonify({
                'success': True,
                'message': 'Product archived successfully',
                'archived': True
            }), 200
            
        elif action == 'delete':
            # Check again if still in carts
            carts_count = CartItem.query.filter_by(product_id=product_id).count()
            if carts_count > 0:
                return jsonify({
                    'error': f'Cannot delete. Product is in {carts_count} carts. Archive it instead.'
                }), 400
            
            # ===== FIX: DELETE FROM CLOUDINARY FIRST =====
            from app.utils.cloudinary_helper import delete_from_cloudinary
            
            # Delete product images from Cloudinary
            for image in product.images:
                if image.public_id:
                    delete_from_cloudinary(image.public_id)
                    print(f"🗑️ Deleted Cloudinary image: {image.public_id}")
            
            # Delete variant images from Cloudinary
            for variant in product.variants:
                if variant.image_public_id:
                    delete_from_cloudinary(variant.image_public_id)
                    print(f"🗑️ Deleted variant Cloudinary image: {variant.image_public_id}")
            
            # Now delete from database
            db.session.delete(product)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Product permanently deleted from database and Cloudinary'
            }), 200
            
        else:  # cancel
            return jsonify({
                'success': True,
                'message': 'Action cancelled'
            }), 200
            
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error in archive choice: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
# ===== HELPER FUNCTIONS =====
def _get_seller_store():
    """Return the seller's manageable store (active or self-hidden inactive)."""
    return _seller_portal_manageable_store(session.get('user_id'))

def _get_primary_image(product):
    """Return the URL path for the primary (or first) product image."""
    if not product.images:
        return None
    primary = next((img for img in product.images if img.is_primary), None)
    img = primary or product.images[0]
    return f'/static/uploads/products/{img.filename}'



# Add context processor to make user available to all templates
@templates_bp.context_processor
def inject_user():
    """Make user available to all templates"""
    user = None
    seller_orders_badge_count = 0
    pos_orders_badge_count = 0
    chat_unread_count = 0
    if session.get('user_id'):
        user_obj = User.query.get(session['user_id'])
        if user_obj:
            user = user_obj.to_dict()
            if session.get('role') == 'seller':
                active_store_ids = [
                    store.id for store in Store.query.filter(
                        Store.seller_id == session['user_id'],
                        Store.status.in_(('active', 'inactive')),
                    ).all()
                ]
                if active_store_ids:
                    seller_orders_badge_count = Order.query.filter(
                        Order.store_id.in_(active_store_ids),
                        or_(
                            Order.payment_status == 'pending_verification',
                            Order.status.in_(['pending', 'accepted', 'preparing']),
                        )
                    ).count()
                    pos_orders_badge_count = POSOrder.query.filter(
                        POSOrder.store_id.in_(active_store_ids),
                        POSOrder.is_seen_by_seller.is_(False)
                    ).count()

            # Seed chat FAB badge on every page render (seller/admin/customer)
            try:
                uid = user_obj.id
                role = user_obj.role
                if role == 'admin':
                    admin_ids = [
                        row[0] for row in db.session.query(User.id).filter_by(role='admin').all()
                    ] or [uid]
                    seller_total = db.session.query(
                        db.func.coalesce(db.func.sum(Conversation.seller_unread), 0)
                    ).filter(
                        Conversation.seller_id.in_(admin_ids),
                        Conversation.seller_deleted_at.is_(None),
                    ).scalar()
                else:
                    seller_total = db.session.query(
                        db.func.coalesce(db.func.sum(Conversation.seller_unread), 0)
                    ).filter(
                        Conversation.seller_id == uid,
                        Conversation.seller_deleted_at.is_(None),
                    ).scalar()
                customer_total = db.session.query(
                    db.func.coalesce(db.func.sum(Conversation.customer_unread), 0)
                ).filter(
                    Conversation.customer_id == uid,
                    Conversation.customer_deleted_at.is_(None),
                ).scalar()
                chat_unread_count = int(seller_total or 0) + int(customer_total or 0)
            except Exception:
                chat_unread_count = 0
    return dict(
        user=user,
        seller_orders_badge_count=seller_orders_badge_count,
        pos_orders_badge_count=pos_orders_badge_count,
        chat_unread_count=chat_unread_count,
        current_year=datetime.utcnow().year,
    )


@templates_bp.route('/seller/apply', methods=['GET', 'POST'])
def seller_apply():
    """GET → redirect to seller portal. POST → submit seller application (JSON)."""
    if request.method == 'GET':
        return redirect(url_for('templates.seller_signup_landing'))

    if 'user_id' not in session:
        return jsonify({'error': 'Please login first'}), 401
    
    try:
        # Get the user from database
        user = User.query.get(session['user_id'])
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get form data
        store_name = (request.form.get('store_name') or '').strip()
        store_description = (request.form.get('store_description') or '').strip()
        agree_terms = request.form.get('agree_terms')

        # Get Cloudinary data from form (uploaded by frontend)
        store_logo_public_id = request.form.get('store_logo_public_id')
        store_logo_url = request.form.get('store_logo_url')
        government_id_public_id = request.form.get('government_id_public_id')
        government_id_url = request.form.get('government_id_url')

        # Check if user already has a pending application
        existing_pending = SellerApplication.query.filter(
            SellerApplication.user_id == session['user_id'],
            SellerApplication.status.in_(['pending', 'resubmitted'])
        ).first()

        if existing_pending:
            # If there's an existing application, clean up the newly uploaded images
            from app.utils.cloudinary_helper import delete_from_cloudinary
            if store_logo_public_id:
                delete_from_cloudinary(store_logo_public_id)
            if government_id_public_id:
                delete_from_cloudinary(government_id_public_id)
            return jsonify({'error': 'You already have a pending application'}), 400

        # Rejected resubmission flow: keep same application record and only update rejected fields.
        latest_rejected = (
            SellerApplication.query.filter_by(user_id=session['user_id'], status='rejected')
            .order_by(SellerApplication.submitted_at.desc())
            .first()
        )
        if latest_rejected:
            rejection_details = latest_rejected.rejection_details or {}
            has_field_map = any(
                isinstance(v, dict) and bool(v.get('rejected'))
                for v in rejection_details.values()
            )

            updated_fields = []

            # If admin did not provide per-field flags, allow full edit fallback.
            if not has_field_map:
                if not store_name or not store_description:
                    return jsonify({'error': 'Please fill in store name and description.'}), 400
                if not store_logo_public_id or not store_logo_url:
                    return jsonify({'error': 'Store logo upload failed. Please try again.'}), 400
                if not government_id_public_id or not government_id_url:
                    return jsonify({'error': 'Government ID upload failed. Please try again.'}), 400

                latest_rejected.store_name = store_name
                latest_rejected.store_description = store_description
                latest_rejected.store_logo_public_id = store_logo_public_id
                latest_rejected.store_logo_url = store_logo_url
                latest_rejected.government_id_public_id = government_id_public_id
                latest_rejected.government_id_url = government_id_url
                updated_fields = ['all']
            else:
                def _is_rejected(field_name):
                    info = rejection_details.get(field_name)
                    return isinstance(info, dict) and bool(info.get('rejected'))

                if _is_rejected('store_name'):
                    if not store_name:
                        return jsonify({'error': 'Please provide an updated store name.'}), 400
                    latest_rejected.store_name = store_name
                    updated_fields.append('store_name')

                if _is_rejected('store_description'):
                    if not store_description:
                        return jsonify({'error': 'Please provide an updated store description.'}), 400
                    latest_rejected.store_description = store_description
                    updated_fields.append('store_description')

                if _is_rejected('store_logo'):
                    if not store_logo_public_id or not store_logo_url:
                        return jsonify({'error': 'Please upload a new store logo.'}), 400
                    latest_rejected.store_logo_public_id = store_logo_public_id
                    latest_rejected.store_logo_url = store_logo_url
                    updated_fields.append('store_logo')

                if _is_rejected('government_id'):
                    if not government_id_public_id or not government_id_url:
                        return jsonify({'error': 'Please upload a new government ID.'}), 400
                    latest_rejected.government_id_public_id = government_id_public_id
                    latest_rejected.government_id_url = government_id_url
                    updated_fields.append('government_id')

            if not updated_fields:
                return jsonify({'error': 'No rejected fields were updated.'}), 400

            latest_rejected.status = 'resubmitted'
            latest_rejected.admin_notes = None
            latest_rejected.rejection_details = None
            latest_rejected.reviewed_at = None
            latest_rejected.reviewed_by = None
            latest_rejected.submitted_at = datetime.utcnow()
            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Application updated and resubmitted successfully.',
                'resubmitted_fields': updated_fields,
            })

        # New application flow
        if not store_name or not store_description:
            return jsonify({'error': 'Please fill in all required fields'}), 400
        if not store_logo_public_id or not store_logo_url:
            return jsonify({'error': 'Store logo upload failed. Please try again.'}), 400
        if not government_id_public_id or not government_id_url:
            return jsonify({'error': 'Government ID upload failed. Please try again.'}), 400

        src = 'seller_portal' if user.role == 'seller' else 'customer_account'
        application = SellerApplication(
            user_id=session['user_id'],
            applicant_full_name=user.full_name,
            applicant_email=user.email,
            applicant_phone=user.phone,
            application_source=src,
            store_name=store_name,
            store_description=store_description,
            store_logo_public_id=store_logo_public_id,
            store_logo_url=store_logo_url,
            government_id_public_id=government_id_public_id,
            government_id_url=government_id_url,
            status='pending'
        )
        
        db.session.add(application)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Application submitted successfully! Admin will review your request.'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error submitting seller application: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@templates_bp.route('/seller/application/status')
def seller_application_status():
    """Check the status of a seller's application"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    application = SellerApplication.query.filter_by(
        user_id=session['user_id']
    ).order_by(SellerApplication.submitted_at.desc()).first()
    
    if not application:
        return jsonify({'status': 'none'})
    
    return jsonify({
        'status': application.status,
        'store_name': application.store_name,
        'store_description': application.store_description,
        'store_logo_url': application.store_logo_url,
        'government_id_url': application.government_id_url,
        'submitted_at': application.submitted_at.isoformat() if application.submitted_at else None,
        'admin_notes': application.admin_notes,
        'rejection_details': application.rejection_details
    })



@templates_bp.route('/api/account/<page>')
def account_content(page):
    """Return HTML content for different account pages"""
    try:
        # Get user data if logged in
        user = None
        if session.get('user_id'):
            user = User.query.get(session['user_id'])
        
        if page == 'profile':
            return render_template('account_parts/profile_content.html', 
                                 user=user.to_dict() if user else None)
        elif page == 'orders':
            return render_template('account_parts/orders_content.html', 
                                 user=user.to_dict() if user else None)
        elif page == 'wishlist':
            return render_template('account_parts/wishlist_content.html',
                                 user=user.to_dict() if user else None)
        elif page == 'settings':
            return redirect(url_for('templates.my_account', page='profile'))
        else:
            return '', 404
            
    except Exception as e:
        print(f"Error loading account page {page}: {str(e)}")
        return f'<div class="error">Error loading content: {str(e)}</div>', 500
# ============================================
# PROFILE MANAGEMENT ROUTES
# ============================================
@templates_bp.route('/api/account/profile/update', methods=['POST'])
def update_profile():
    """Update user profile information with Cloudinary avatar"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        user = User.query.get(session['user_id'])
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # DEBUG: Print what we're receiving
        print("\n" + "="*60)
        print("📝 PROFILE UPDATE REQUEST RECEIVED")
        print(f"👤 User ID: {user.id}")
        print(f"📋 Form data keys: {list(request.form.keys())}")
        
        # Get form data
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        birthday = request.form.get('birthday', '')
        gender = request.form.get('gender', '')
        
        print(f"📝 Form data: first_name={first_name}, last_name={last_name}, birthday={birthday}, gender={gender}")
        
        # Update full_name
        if first_name or last_name:
            user.full_name = f"{first_name} {last_name}".strip()
        
        # Login identity (email or phone) is set at registration and is not editable here.
        if birthday:
            from app.utils import parse_and_validate_birthday
            parsed_bday, bday_err = parse_and_validate_birthday(birthday)
            if bday_err:
                return jsonify({'success': False, 'error': bday_err}), 400
            if parsed_bday is not None:
                user.birthday = parsed_bday
        if gender:
            user.gender = gender
        
        # Handle avatar update from Cloudinary
        avatar_public_id = request.form.get('avatar_public_id')
        avatar_url = request.form.get('avatar_url')
        
        if avatar_public_id and avatar_url:
            print(f"📸 Avatar Cloudinary data received: public_id={avatar_public_id}")
            
            # Delete old avatar from Cloudinary if exists
            if user.avatar_public_id:
                from app.utils.cloudinary_helper import delete_from_cloudinary
                delete_from_cloudinary(user.avatar_public_id)
                print(f"🗑️ Deleted old avatar: {user.avatar_public_id}")
            
            # Update user with new Cloudinary data
            user.avatar_public_id = avatar_public_id
            user.avatar_url = avatar_url
            # Keep filename for reference (optional)
            user.avatar_filename = f"avatar_{avatar_public_id}.jpg"
        
        user.updated_at = datetime.utcnow()
        db.session.commit()
        print(f"✅ Database updated for user {user.id}")
        
        # Update session
        session['user_name'] = user.full_name
        
        # Generate the avatar URL for response
        user_dict = user.to_dict()
        print(f"✅ Returning user data with avatar_url: {user_dict.get('avatar_url')}")
        print("="*60 + "\n")
        
        return jsonify({
            'success': True,
            'message': 'Profile updated successfully',
            'user': user_dict
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error updating profile: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@templates_bp.route('/api/account/profile', methods=['GET'])
def get_profile():
    """Get user profile data"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        user = User.query.get(session['user_id'])
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({
            'success': True,
            'user': user.to_dict()
        })
        
    except Exception as e:
        print(f"Error fetching profile: {str(e)}")
        return jsonify({'error': 'Server error'}), 500


@templates_bp.route('/api/account/password/change', methods=['POST'])
def change_password():
    """Change user password"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        user = User.query.get(session['user_id'])
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get form data
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate
        if not all([current_password, new_password, confirm_password]):
            return jsonify({'error': 'All fields are required'}), 400
        
        if new_password != confirm_password:
            return jsonify({'error': 'New passwords do not match'}), 400
        
        pw_error = _password_strength_error(new_password)
        if pw_error:
            return jsonify({'error': pw_error}), 400
        
        # Verify current password
        if not user.check_password(current_password):
            return jsonify({'error': 'Current password is incorrect'}), 400
        
        # Update password
        user.set_password(new_password)
        user.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Password changed successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error changing password: {str(e)}")
        return jsonify({'error': 'Server error'}), 500

@templates_bp.route('/my-account')
def my_account():
    if not session.get('user_id'):
        return redirect(url_for('templates.login'))
    if session.get('role') == 'admin':
        return redirect(url_for('templates.admin_users'))

#Get the page parameter from URL (default to 'profile')
    page = request.args.get('page', 'profile')
    if page == 'settings':
        return redirect(url_for('templates.my_account', page='profile'))

#Get user data from database
    user = User.query.get(session['user_id'])
    if not user:
        return redirect(url_for('templates.logout'))

#Convert to dict for template
    user_data = user.to_dict()

#Get Mapbox token from environment variables
    mapbox_token = os.getenv('MAPBOX_PUBLIC_TOKEN', '')

#DEBUG: Print token to console to verify it's loaded
    print(f"🗺️ Mapbox token loaded for my-account: {mapbox_token[:15] if mapbox_token else 'NOT FOUND'}...")

#IMPORTANT: Render the template, don't return JSON!
    return render_template('my_account.html', 
                         user=user_data, 
                         active_page=page,
                         initial_page=page,
                         mapbox_token=mapbox_token)  # ✅ Add this line






# ── Wishlist (session / web) — register before catch-all ─────────────────────

@templates_bp.route('/api/account/wishlist/data', methods=['GET'])
def account_wishlist_data():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    from app.wishlist_helpers import list_wishlist_items
    items = list_wishlist_items(int(session['user_id']))
    return jsonify({'success': True, 'items': items, 'count': len(items)})


@templates_bp.route('/api/account/wishlist/product/<int:product_id>', methods=['GET'])
def account_wishlist_for_product(product_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    from app.wishlist_helpers import wishlist_variant_keys_for_product
    keys = wishlist_variant_keys_for_product(int(session['user_id']), product_id)
    return jsonify({'success': True, 'variant_ids': keys})


@templates_bp.route('/api/account/wishlist/toggle', methods=['POST'])
def account_wishlist_toggle():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    if session.get('role') != 'customer':
        return jsonify({'error': 'Customer access required'}), 403
    data = request.get_json(silent=True) or {}
    product_id = data.get('product_id')
    variant_id = data.get('variant_id')
    from app.wishlist_helpers import toggle_wishlist
    item, wished, err = toggle_wishlist(int(session['user_id']), product_id, variant_id)
    if err:
        return jsonify(err[0]), err[1]
    return jsonify({
        'success': True,
        'wished': wished,
        'item': item,
        'message': 'Added to wishlist' if wished else 'Removed from wishlist',
    })


@templates_bp.route('/api/account/wishlist/<int:item_id>', methods=['DELETE'])
def account_wishlist_remove(item_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    from app.wishlist_helpers import remove_wishlist_item
    ok, err = remove_wishlist_item(int(session['user_id']), item_id)
    if err:
        return jsonify(err[0]), err[1]
    return jsonify({'success': True, 'message': 'Removed from wishlist'})


@templates_bp.route('/api/account/<path:path>')
def catch_api_navigation(path):
    """Redirect any accidental navigation to API URLs back to the proper page"""
    print(f"⚠️ Warning: Someone navigated directly to API URL: /api/account/{path}")
    # Extract the page name
    page = path.split('/')[0]
    if page in ['profile', 'orders', 'wishlist']:
        return redirect(url_for('templates.my_account', page=page))
    return redirect(url_for('templates.my_account'))


@templates_bp.route('/home')
def home():
    """Customer home page (if you want a separate customer portal)"""
    if 'user_id' not in session:
        return redirect(url_for('templates.login'))
    
    if session.get('role') != 'customer':
        return redirect(url_for('templates.dashboard'))
    
    # Get customer-specific data
    customer_orders = Order.query.filter_by(
        customer_id=session['user_id']
    ).order_by(Order.created_at.desc()).limit(5).all()
    
    return render_template('customer_home.html', 
                         orders=[o.to_dict() for o in customer_orders])

@templates_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        role = session.get('role')
        if role == 'admin':
            return redirect(url_for('templates.admin_users'))
        if role == 'seller':
            u = User.query.get(session['user_id'])
            if u:
                return _seller_home_redirect(u.id)
            return redirect(url_for('templates.seller_signup_complete'))
        if role == 'rider':
            return redirect(url_for('templates.rider_dashboard'))
        return redirect(url_for('templates.index'))

    if request.method == 'POST':
        raw_id = (request.form.get('identifier') or request.form.get('email') or '').strip()
        password = request.form.get('password')
        
        # Find user by email or PH mobile
        user = _find_user_by_login_identifier_web(raw_id)
        
        # Check if user exists and password is correct
        if user and user.check_password(password):
            if (user.status or '').lower() == 'banned' and _ensure_account_bans_table():
                active_ban = AccountBan.query.filter_by(user_id=user.id, is_active=True).order_by(AccountBan.created_at.desc()).first()
                if active_ban and active_ban.banned_until and active_ban.banned_until <= datetime.utcnow():
                    active_ban.is_active = False
                    active_ban.lifted_at = datetime.utcnow()
                    user.status = 'active'
                    user.updated_at = datetime.utcnow()
                    db.session.commit()

            blocked_statuses = {'inactive', 'suspended', 'archived', 'deleted', 'banned'}
            if (user.status or '').lower() in blocked_statuses:
                return render_template(
                    'login.html',
                    error='This account is inactive. Please contact support.',
                    form_data={'identifier': raw_id or ''},
                    login_next=request.form.get('next') or request.args.get('next'),
                )

            # Set session
            session.permanent = True
            session['user_id'] = user.id
            session['user_name'] = user.full_name
            session['role'] = user.role
            session['email'] = user.email
            
            # Check for redirect URL (from query or hidden form field)
            next_url = request.form.get('next') or request.args.get('next')
            if next_url:
                return redirect(next_url)
            
            # One-time post-registration prompt for customer address setup.
            prompt_from_reg = request.args.get('prompt_address') == '1'
            if user.role == 'customer' and (session.pop('prompt_address_after_login', False) or prompt_from_reg):
                return redirect(url_for('templates.my_account', page='profile', prompt_address='1'))

            # Redirect based on role
            if user.role == 'admin':
                return redirect(url_for('templates.admin_users'))
            elif user.role == 'seller':
                return _seller_home_redirect(user.id)
            elif user.role == 'rider':
                return redirect(url_for('templates.rider_dashboard'))
            else:  # customer
                return redirect(url_for('templates.index'))
        else:
            return render_template(
                'login.html',
                error='Invalid email/phone or password',
                form_data={'identifier': raw_id or ''},
                login_next=request.form.get('next') or request.args.get('next'),
            )

    verified = request.args.get('verified') == '1'
    reset_ok = request.args.get('reset') == '1'
    prefill = (request.args.get('email') or request.args.get('identifier') or '').strip()
    if prefill:
        from app.utils.phone_utils import display_login_id, is_synthetic_account_email
        if is_synthetic_account_email(prefill):
            local, _, _ = prefill.partition('@')
            prefill = display_login_id(email=prefill, phone=local)
    form_data = {'identifier': prefill} if prefill else None
    return render_template(
        'login.html',
        verified=verified,
        reset_ok=reset_ok,
        form_data=form_data,
        login_next=request.args.get('next'),
    )


def _ensure_password_reset_otps_table_web():
    from sqlalchemy import inspect as sa_inspect, text
    try:
        if not sa_inspect(db.engine).has_table('password_reset_otps'):
            PasswordResetOTP.__table__.create(db.engine, checkfirst=True)
        cols = {c['name'] for c in sa_inspect(db.engine).get_columns('password_reset_otps')}
        if 'otp_channel' not in cols:
            with db.engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE password_reset_otps "
                    "ADD COLUMN IF NOT EXISTS otp_channel VARCHAR(10) DEFAULT 'email' NOT NULL"
                ))
        return True
    except Exception as exc:
        current_app.logger.warning('Could not ensure password_reset_otps: %s', exc)
        return False


def _find_user_by_phone_web(normalized_09):
    from app.utils.phone_utils import phone_lookup_variants
    if not normalized_09:
        return None
    variants = phone_lookup_variants(normalized_09)
    return User.query.filter(User.phone.in_(variants)).first()


def _find_user_by_login_identifier_web(raw):
    from app.utils.phone_utils import (
        is_synthetic_account_email,
        is_valid_ph_mobile,
        normalize_ph_mobile,
        phone_to_account_email,
    )

    raw = (raw or '').strip()
    if not raw:
        return None
    if '@' in raw:
        email = raw.lower()
        if is_synthetic_account_email(email):
            local, _, _ = email.partition('@')
            phone = normalize_ph_mobile(local)
            if phone:
                return _find_user_by_phone_web(phone) or User.query.filter_by(email=email).first()
        return User.query.filter_by(email=email).first()
    if is_valid_ph_mobile(raw):
        phone = normalize_ph_mobile(raw)
        synth_user = User.query.filter_by(email=phone_to_account_email(phone)).first()
        if synth_user:
            return synth_user
        return _find_user_by_phone_web(phone)
    return None


def _phone_taken_web(normalized_09, exclude_email=None):
    from app.utils.phone_utils import phone_to_account_email

    user = _find_user_by_phone_web(normalized_09)
    if not user:
        user = User.query.filter_by(email=phone_to_account_email(normalized_09)).first()
    if not user:
        return False
    if exclude_email and user.email == exclude_email:
        return False
    return True


@templates_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Step 1 — email → Gmail OTP, or PH phone → SMS OTP."""
    if session.get('user_id'):
        return redirect(url_for('templates.index'))

    prefill = (request.args.get('email') or request.args.get('identifier') or '').strip()

    if request.method == 'POST':
        from app.utils.otp_service import (
            DEFAULT_EXPIRY_MINUTES, RESEND_COOLDOWN_SECONDS,
            can_resend, new_otp_pair,
        )
        from app.utils.email_helper import send_password_reset_otp_email
        from app.utils.otp_delivery import deliver_otp, sync_hashed_otp_record
        from app.utils.phone_utils import (
            normalize_ph_mobile, is_valid_ph_mobile, mask_email, mask_phone,
            display_login_id, is_synthetic_account_email, phone_to_account_email,
        )

        identifier = (request.form.get('identifier') or request.form.get('email') or '').strip()
        if not identifier:
            return render_template(
                'forgot_password.html',
                error='Enter your email address or Philippine mobile number.',
                form_data={'identifier': identifier},
            )

        channel = None
        phone = None
        user = None
        email = None

        if '@' in identifier:
            email = identifier.lower()
            if is_synthetic_account_email(email) or '@' not in email or '.' not in email.split('@')[-1]:
                return render_template(
                    'forgot_password.html',
                    error='Please enter a valid email address or Philippine mobile number.',
                    form_data={'identifier': identifier},
                )
            user = User.query.filter_by(email=email).first()
            if not user:
                return render_template(
                    'forgot_password.html',
                    error='No account found with this email.',
                    form_data={'identifier': identifier},
                )
            channel = 'email'
        else:
            if not is_valid_ph_mobile(identifier):
                return render_template(
                    'forgot_password.html',
                    error='Enter a valid email or Philippine mobile (e.g. 09171234567).',
                    form_data={'identifier': identifier},
                )
            phone = normalize_ph_mobile(identifier)
            user = (
                User.query.filter_by(email=phone_to_account_email(phone)).first()
                or _find_user_by_phone_web(phone)
                or _find_user_by_login_identifier_web(phone)
            )
            if not user:
                return render_template(
                    'forgot_password.html',
                    error='No account found with this phone number.',
                    form_data={'identifier': identifier},
                )
            email = user.email
            phone = phone or normalize_ph_mobile(user.phone)
            if not phone and is_synthetic_account_email(user.email):
                local, _, _ = user.email.partition('@')
                phone = normalize_ph_mobile(local)
            channel = 'sms'

        if user.status != 'active':
            return render_template(
                'forgot_password.html',
                error='This account is not active. Please contact support.',
                form_data={'identifier': identifier},
            )

        if channel == 'sms' and not phone:
            return render_template(
                'forgot_password.html',
                error='This account has no mobile number on file for SMS reset.',
                form_data={'identifier': identifier},
            )

        login_id = display_login_id(email=user.email, phone=phone or user.phone)

        _ensure_password_reset_otps_table_web()
        plain_code, otp_hash, expires_at = new_otp_pair(DEFAULT_EXPIRY_MINUTES)
        record = PasswordResetOTP.query.filter_by(email=email).first()
        if record:
            allowed, retry_after = can_resend(record.last_sent_at, RESEND_COOLDOWN_SECONDS)
            if not allowed:
                session['pending_reset_email'] = email
                session['pending_reset_channel'] = channel
                session['pending_reset_dest'] = mask_phone(phone) if channel == 'sms' else mask_email(email)
                session['pending_reset_login_id'] = login_id
                return redirect(url_for('templates.forgot_password_verify', cooldown=retry_after))
            record.otp_hash = otp_hash
            record.otp_channel = channel
            record.expires_at = expires_at
            record.last_sent_at = datetime.utcnow()
            record.attempts = 0
            record.is_verified = False
            record.verified_at = None
        else:
            record = PasswordResetOTP(
                email=email,
                otp_hash=otp_hash,
                otp_channel=channel,
                expires_at=expires_at,
                last_sent_at=datetime.utcnow(),
            )
            db.session.add(record)
        db.session.commit()

        ok, fail, meta = deliver_otp(
            channel,
            otp_code=plain_code,
            email=email,
            phone=phone,
            email_sender_fn=send_password_reset_otp_email,
            email_sender_kwargs={'full_name': user.full_name, 'expiry_minutes': DEFAULT_EXPIRY_MINUTES},
            expiry_minutes=DEFAULT_EXPIRY_MINUTES,
            sms_purpose='password reset',
        )
        if not ok:
            return render_template(
                'forgot_password.html',
                error=(fail or {}).get('error') or 'Failed to send verification code.',
                error_code=(fail or {}).get('error_code'),
                form_data={'identifier': identifier},
            )
        sync_hashed_otp_record(record, meta, plain_code)

        session['pending_reset_email'] = email
        session['pending_reset_channel'] = channel
        session['pending_reset_dest'] = meta.get('destination_masked')
        session['pending_reset_login_id'] = login_id
        return redirect(url_for('templates.forgot_password_verify'))

    return render_template(
        'forgot_password.html',
        form_data={'identifier': prefill} if prefill else None,
    )


@templates_bp.route('/forgot-password/verify', methods=['GET', 'POST'])
def forgot_password_verify():
    """Step 2 — enter the 6-digit OTP (email or SMS)."""
    if session.get('user_id'):
        return redirect(url_for('templates.index'))

    email = session.get('pending_reset_email')
    if not email:
        flash('Please enter your email or phone to reset your password.', 'warning')
        return redirect(url_for('templates.forgot_password'))

    cooldown = request.args.get('cooldown', type=int) or 60
    channel = session.get('pending_reset_channel') or 'email'
    dest = session.get('pending_reset_dest') or email

    if request.method == 'POST':
        from app.utils.otp_service import MAX_VERIFY_ATTEMPTS, attempts_remaining, verify_otp

        _ensure_password_reset_otps_table_web()
        otp_code = (request.form.get('otp_code') or '').strip()
        record = PasswordResetOTP.query.filter_by(email=email).first()
        if not record:
            return render_template('forgot_password_verify.html',
                                   email=email, cooldown=0,
                                   otp_channel=channel, destination_masked=dest,
                                   error='No reset request found. Please start again.')

        if record.is_verified:
            session['reset_verified_email'] = email
            return redirect(url_for('templates.forgot_password_reset'))

        if record.is_expired():
            return render_template('forgot_password_verify.html',
                                   email=email, cooldown=0,
                                   otp_channel=channel, destination_masked=dest,
                                   error='OTP has expired. Please request a new code.')

        if (record.attempts or 0) >= MAX_VERIFY_ATTEMPTS:
            return render_template('forgot_password_verify.html',
                                   email=email, cooldown=0,
                                   otp_channel=channel, destination_masked=dest,
                                   error='Too many incorrect attempts. Please request a new code.')

        if not verify_otp(otp_code, record.otp_hash):
            record.attempts = (record.attempts or 0) + 1
            db.session.commit()
            remaining = attempts_remaining(record.attempts, MAX_VERIFY_ATTEMPTS)
            return render_template(
                'forgot_password_verify.html',
                email=email, cooldown=0,
                otp_channel=channel, destination_masked=dest,
                error=f'Invalid code. {remaining} attempt{"s" if remaining != 1 else ""} left.',
            )

        record.is_verified = True
        record.verified_at = datetime.utcnow()
        db.session.commit()
        session['reset_verified_email'] = email
        return redirect(url_for('templates.forgot_password_reset'))

    return render_template(
        'forgot_password_verify.html',
        email=email,
        cooldown=cooldown,
        otp_channel=channel,
        destination_masked=dest,
    )


@templates_bp.route('/forgot-password/resend-otp', methods=['POST'])
def forgot_password_resend_otp_web():
    """AJAX resend for the forgot-password verify page."""
    from app.utils.otp_service import (
        DEFAULT_EXPIRY_MINUTES, RESEND_COOLDOWN_SECONDS,
        can_resend, new_otp_pair,
    )
    from app.utils.email_helper import send_password_reset_otp_email
    from app.utils.otp_delivery import deliver_otp, normalize_otp_channel, sync_hashed_otp_record
    from app.utils.phone_utils import normalize_ph_mobile

    email = session.get('pending_reset_email')
    if not email:
        return jsonify({'success': False, 'error': 'Session expired. Please start again.'}), 400

    _ensure_password_reset_otps_table_web()
    user = User.query.filter_by(email=email).first()
    record = PasswordResetOTP.query.filter_by(email=email).first()
    if not user or not record:
        return jsonify({'success': False, 'error': 'No reset request found.'}), 404

    allowed, retry_after = can_resend(record.last_sent_at, RESEND_COOLDOWN_SECONDS)
    if not allowed:
        return jsonify({
            'success': False,
            'error': 'Please wait before requesting another code.',
            'retry_after_seconds': retry_after,
        }), 429

    channel = normalize_otp_channel(
        getattr(record, 'otp_channel', None) or session.get('pending_reset_channel'),
        default='email',
    ) or 'email'
    phone = normalize_ph_mobile(user.phone)
    if channel == 'sms' and not phone:
        return jsonify({
            'success': False,
            'error': 'This account has no mobile number on file for SMS reset.',
        }), 400

    plain_code, otp_hash, expires_at = new_otp_pair(DEFAULT_EXPIRY_MINUTES)
    record.otp_hash = otp_hash
    record.otp_channel = channel
    record.expires_at = expires_at
    record.last_sent_at = datetime.utcnow()
    record.attempts = 0
    record.is_verified = False
    record.verified_at = None
    db.session.commit()

    ok, fail, meta = deliver_otp(
        channel,
        otp_code=plain_code,
        email=email,
        phone=phone,
        email_sender_fn=send_password_reset_otp_email,
        email_sender_kwargs={'full_name': user.full_name, 'expiry_minutes': DEFAULT_EXPIRY_MINUTES},
        expiry_minutes=DEFAULT_EXPIRY_MINUTES,
        sms_purpose='password reset',
    )
    if not ok:
        return jsonify(fail), 503
    sync_hashed_otp_record(record, meta, plain_code)

    session['pending_reset_channel'] = channel
    session['pending_reset_dest'] = meta.get('destination_masked')
    return jsonify({
        'success': True,
        'message': f'A new verification code has been sent to {meta.get("destination_masked")}.',
        'otp_channel': channel,
        'destination_masked': meta.get('destination_masked'),
        'expires_in_seconds': DEFAULT_EXPIRY_MINUTES * 60,
    }), 200


@templates_bp.route('/forgot-password/reset', methods=['GET', 'POST'])
def forgot_password_reset():
    """Step 3 — set a new password after OTP verification."""
    if session.get('user_id'):
        return redirect(url_for('templates.index'))

    email = session.get('reset_verified_email') or session.get('pending_reset_email')
    if not email:
        flash('Please verify your email first.', 'warning')
        return redirect(url_for('templates.forgot_password'))

    from app.utils.phone_utils import display_login_id

    _ensure_password_reset_otps_table_web()
    record = PasswordResetOTP.query.filter_by(email=email).first()
    if not record or not record.is_verified:
        flash('Please verify the code sent to your email first.', 'warning')
        return redirect(url_for('templates.forgot_password_verify'))

    user_for_display = User.query.filter_by(email=email).first()
    login_id = (
        session.get('pending_reset_login_id')
        or display_login_id(
            email=email,
            phone=user_for_display.phone if user_for_display else None,
        )
    )

    if request.method == 'POST':
        new_password = request.form.get('new_password') or ''
        confirm_password = request.form.get('confirm_password') or ''

        if not new_password or not confirm_password:
            return render_template('forgot_password_reset.html',
                                   email=email, login_id=login_id,
                                   error='Both password fields are required.')
        if new_password != confirm_password:
            return render_template('forgot_password_reset.html',
                                   email=email, login_id=login_id,
                                   error='Passwords do not match.')
        pw_error = _password_strength_error(new_password)
        if pw_error:
            return render_template('forgot_password_reset.html',
                                   email=email, login_id=login_id, error=pw_error)

        user = User.query.filter_by(email=email).first()
        if not user:
            return render_template('forgot_password_reset.html',
                                   email=email, login_id=login_id,
                                   error='Account not found.')

        user.set_password(new_password)
        user.updated_at = datetime.utcnow()
        db.session.delete(record)
        db.session.commit()
        session.pop('pending_reset_email', None)
        session.pop('reset_verified_email', None)
        session.pop('pending_reset_login_id', None)
        session.pop('pending_reset_channel', None)
        session.pop('pending_reset_dest', None)
        return redirect(url_for('templates.login', reset=1, email=login_id))

    return render_template('forgot_password_reset.html', email=email, login_id=login_id)


@templates_bp.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('user_id'):
        return redirect(url_for('templates.index'))

    """
    Step 1 of OTP-verified customer registration.

    GET  → show the registration form.
    POST → validate fields, generate OTP, email it to the customer,
           store pending data in Flask session, redirect to /register/verify.
    """
    if request.method == 'POST':
        try:
            from werkzeug.security import generate_password_hash
            from app.utils.otp_service import (
                DEFAULT_EXPIRY_MINUTES, RESEND_COOLDOWN_SECONDS,
                can_resend, new_otp_pair,
            )
            from app.utils.email_helper import send_customer_otp_email
            from app.utils.otp_delivery import deliver_otp, sync_hashed_otp_record
            from app.utils.phone_utils import mask_email, mask_phone

            full_name        = (request.form.get('full_name')        or '').strip()
            identifier       = (request.form.get('identifier') or request.form.get('email') or '').strip()
            password         = (request.form.get('password')         or '')
            confirm_password = (request.form.get('confirm_password') or '')

            # ── Validation ────────────────────────────────────────────────
            if not all([full_name, identifier, password, confirm_password]):
                return render_template('register.html',
                                       error='All fields are required',
                                       form_data=request.form)

            if password != confirm_password:
                return render_template('register.html',
                                       error='Passwords do not match',
                                       form_data=request.form)

            pw_error = _password_strength_error(password)
            if pw_error:
                return render_template('register.html',
                                       error=pw_error,
                                       form_data=request.form)

            from app.utils.phone_utils import (
                is_synthetic_account_email,
                is_valid_ph_mobile,
                normalize_ph_mobile,
                phone_to_account_email,
                display_login_id,
            )

            email = None
            phone = None
            channel = 'email'
            if '@' in identifier:
                email = identifier.lower()
                if is_synthetic_account_email(email) or '@' not in email or '.' not in email.split('@')[-1]:
                    return render_template(
                        'register.html',
                        error='Enter a valid email address or Philippine mobile number.',
                        form_data=request.form,
                    )
                channel = 'email'
            elif is_valid_ph_mobile(identifier):
                phone = normalize_ph_mobile(identifier)
                email = phone_to_account_email(phone)
                channel = 'sms'
            else:
                return render_template(
                    'register.html',
                    error='Enter a valid email address or Philippine mobile number (e.g. 09171234567).',
                    form_data=request.form,
                )

            if User.query.filter_by(email=email).first():
                kind = 'phone number' if channel == 'sms' else 'email'
                return render_template(
                    'register.html',
                    error=f'This {kind} is already registered. Please sign in instead.',
                    form_data=request.form,
                )

            if phone and _phone_taken_web(phone, exclude_email=email):
                return render_template(
                    'register.html',
                    error='This phone number is already registered to another account.',
                    form_data=request.form,
                )

            # ── Generate / refresh OTP ────────────────────────────────────
            plain_code, otp_hash, expires_at = new_otp_pair(DEFAULT_EXPIRY_MINUTES)
            pending_data = {
                'full_name':     full_name,
                'password_hash': generate_password_hash(password),
                'phone':         phone,
                'otp_channel':   channel,
            }

            record = CustomerOTP.query.filter_by(email=email).first()
            if record:
                allowed, retry_after = can_resend(record.last_sent_at, RESEND_COOLDOWN_SECONDS)
                if not allowed:
                    session['pending_reg_email'] = email
                    session['pending_reg_channel'] = channel
                    session['pending_reg_dest'] = mask_phone(phone) if channel == 'sms' else mask_email(email)
                    return redirect(url_for('templates.register_verify',
                                           cooldown=retry_after))
                record.otp_hash      = otp_hash
                record.customer_data = pending_data
                record.expires_at    = expires_at
                record.last_sent_at  = datetime.utcnow()
                record.attempts      = 0
                record.is_verified   = False
                record.verified_at   = None
            else:
                record = CustomerOTP(
                    email         = email,
                    otp_hash      = otp_hash,
                    customer_data = pending_data,
                    expires_at    = expires_at,
                    last_sent_at  = datetime.utcnow(),
                )
                db.session.add(record)

            db.session.commit()

            ok, fail, meta = deliver_otp(
                channel,
                otp_code=plain_code,
                email=email,
                phone=phone,
                email_sender_fn=send_customer_otp_email,
                email_sender_kwargs={'full_name': full_name, 'expiry_minutes': DEFAULT_EXPIRY_MINUTES},
                expiry_minutes=DEFAULT_EXPIRY_MINUTES,
                sms_purpose='verification',
            )
            if not ok:
                return render_template(
                    'register.html',
                    error=(fail or {}).get('error') or 'Failed to send verification code.',
                    error_code=(fail or {}).get('error_code'),
                    form_data=request.form,
                )
            sync_hashed_otp_record(record, meta, plain_code)

            session['pending_reg_email'] = email
            session['pending_reg_channel'] = channel
            session['pending_reg_dest'] = meta.get('destination_masked')
            session['pending_reg_login_id'] = display_login_id(email=email, phone=phone)
            return redirect(url_for('templates.register_verify'))

        except Exception as e:
            try:
                db.session.rollback()
            except Exception:
                pass
            current_app.logger.error(f"Registration error: {e}")
            # Stale DB sockets are common on Railway; ask user to retry once.
            err_text = str(e).lower()
            if 'server closed the connection' in err_text or 'operationalerror' in err_text:
                return render_template(
                    'register.html',
                    error='Connection to the database was interrupted. Please try again.',
                    form_data=request.form,
                )
            return render_template('register.html',
                                   error='Registration failed. Please try again.',
                                   form_data=request.form)

    return render_template('register.html')


@templates_bp.route('/register/verify', methods=['GET', 'POST'])
def register_verify():
    """
    Step 2 of OTP-verified customer registration.

    GET  → show the OTP input page (email taken from session).
    POST → validate OTP, create User, auto-login, redirect to home.
    """
    from app.utils.otp_service import MAX_VERIFY_ATTEMPTS, attempts_remaining, verify_otp

    email = session.get('pending_reg_email')
    if not email:
        return redirect(url_for('templates.register'))

    channel = session.get('pending_reg_channel') or 'email'
    dest = session.get('pending_reg_dest') or email

    # GET — just render the form
    if request.method == 'GET':
        cooldown = request.args.get('cooldown', 0, type=int)
        return render_template('register_verify.html',
                               email=email,
                               cooldown=cooldown,
                               otp_channel=channel,
                               destination_masked=dest)

    # POST — verify OTP and create account
    otp_code = (request.form.get('otp_code') or '').strip()
    if not otp_code or len(otp_code) != 6 or not otp_code.isdigit():
        return render_template('register_verify.html',
                               email=email,
                               otp_channel=channel,
                               destination_masked=dest,
                               error='Please enter the 6-digit code.')

    record = CustomerOTP.query.filter_by(email=email).first()
    if not record:
        session.pop('pending_reg_email', None)
        return redirect(url_for('templates.register'))

    # Already verified (e.g. back-button replay)
    if record.is_verified:
        return _finalise_customer_registration(record, email)

    if record.is_expired():
        return render_template('register_verify.html',
                               email=email,
                               otp_channel=channel,
                               destination_masked=dest,
                               error='Your code has expired. Please request a new one.',
                               expired=True)

    if (record.attempts or 0) >= MAX_VERIFY_ATTEMPTS:
        return render_template('register_verify.html',
                               email=email,
                               otp_channel=channel,
                               destination_masked=dest,
                               error='Too many incorrect attempts. Please request a new code.',
                               locked=True)

    if not verify_otp(otp_code, record.otp_hash):
        record.attempts = (record.attempts or 0) + 1
        db.session.commit()
        left = attempts_remaining(record.attempts, MAX_VERIFY_ATTEMPTS)
        return render_template('register_verify.html',
                               email=email,
                               otp_channel=channel,
                               destination_masked=dest,
                               error=f'Invalid code. {left} attempt{"s" if left != 1 else ""} remaining.')

    # OTP correct — mark verified, create the user
    record.is_verified = True
    record.verified_at = datetime.utcnow()
    db.session.commit()
    return _finalise_customer_registration(record, email)


def _finalise_customer_registration(record, email):
    """Create the User row from the pending OTP data and send user to login."""
    from app.utils.phone_utils import display_login_id

    # Guard against duplicate registration (race condition or replay)
    if User.query.filter_by(email=email).first():
        db.session.delete(record)
        db.session.commit()
        session.pop('pending_reg_email', None)
        session.pop('pending_reg_channel', None)
        session.pop('pending_reg_dest', None)
        session.pop('pending_reg_login_id', None)
        return redirect(url_for('templates.login'))

    pending = record.customer_data or {}
    user = User(
        full_name     = pending.get('full_name', ''),
        email         = email,
        role          = 'customer',
        status        = 'active',
        phone         = pending.get('phone'),
    )
    user.password_hash = pending.get('password_hash', '')
    db.session.add(user)
    db.session.delete(record)  # single-use: consume the OTP row
    db.session.commit()

    login_id = session.pop('pending_reg_login_id', None) or display_login_id(
        email=user.email, phone=user.phone,
    )
    session.pop('pending_reg_email', None)
    session.pop('pending_reg_channel', None)
    session.pop('pending_reg_dest', None)
    # One-time UX flag: prompt address modal right after first login.
    session['prompt_address_after_login'] = True
    return redirect(url_for('templates.login', verified='1', email=login_id, prompt_address='1'))


@templates_bp.route('/register/resend-otp', methods=['POST'])
def register_resend_otp():
    """
    AJAX endpoint — re-issue an OTP for the pending registration.
    Returns JSON so the verify page can update the countdown without a full reload.
    """
    from app.utils.otp_service import (
        DEFAULT_EXPIRY_MINUTES, RESEND_COOLDOWN_SECONDS,
        can_resend, new_otp_pair,
    )
    from app.utils.email_helper import send_customer_otp_email
    from app.utils.otp_delivery import deliver_otp, normalize_otp_channel, sync_hashed_otp_record

    email = session.get('pending_reg_email')
    if not email:
        return jsonify({'success': False, 'error': 'Session expired. Please register again.'}), 400

    record = CustomerOTP.query.filter_by(email=email, is_verified=False).first()
    if not record:
        return jsonify({'success': False, 'error': 'No pending verification found.'}), 404

    allowed, retry_after = can_resend(record.last_sent_at, RESEND_COOLDOWN_SECONDS)
    if not allowed:
        return jsonify({
            'success': False,
            'error': 'Please wait before requesting another code.',
            'retry_after_seconds': retry_after,
        }), 429

    pending = record.customer_data or {}
    channel = normalize_otp_channel(
        pending.get('otp_channel') or session.get('pending_reg_channel'),
        default='email',
    ) or 'email'
    phone = pending.get('phone')

    plain_code, otp_hash, expires_at = new_otp_pair(DEFAULT_EXPIRY_MINUTES)
    record.otp_hash   = otp_hash
    record.expires_at = expires_at
    record.last_sent_at = datetime.utcnow()
    record.attempts   = 0
    db.session.commit()

    ok, fail, meta = deliver_otp(
        channel,
        otp_code=plain_code,
        email=email,
        phone=phone,
        email_sender_fn=send_customer_otp_email,
        email_sender_kwargs={'full_name': pending.get('full_name'), 'expiry_minutes': DEFAULT_EXPIRY_MINUTES},
        expiry_minutes=DEFAULT_EXPIRY_MINUTES,
        sms_purpose='verification',
    )
    if not ok:
        return jsonify(fail), 503
    sync_hashed_otp_record(record, meta, plain_code)

    session['pending_reg_channel'] = channel
    session['pending_reg_dest'] = meta.get('destination_masked')
    return jsonify({
        'success': True,
        'message': f'A new code has been sent to {meta.get("destination_masked")}.',
        'otp_channel': channel,
        'destination_masked': meta.get('destination_masked'),
        'resend_cooldown_seconds': RESEND_COOLDOWN_SECONDS,
    }), 200


def _seller_portal_active_store(user_id):
    if not user_id:
        return None
    return Store.query.filter(
        Store.seller_id == user_id,
        Store.status == 'active',
    ).first()


def _seller_portal_manageable_store(user_id):
    """Store the seller can still manage: visible (active) or self-hidden (inactive).

    Admin `suspended` is excluded so those sellers stay on the suspended screen.
    """
    if not user_id:
        return None
    return (
        Store.query.filter(
            Store.seller_id == user_id,
            Store.status.in_(('active', 'inactive')),
        )
        .order_by(Store.updated_at.desc().nullslast(), Store.id.desc())
        .first()
    )


def _seller_portal_suspended_store(user_id):
    """Storefront locked by admin (not seller-chosen inactive / hide from customers)."""
    return (
        Store.query.filter(
            Store.seller_id == user_id,
            Store.status == 'suspended',
        )
        .order_by(Store.updated_at.desc().nullslast(), Store.id.desc())
        .first()
    )


def _seller_home_redirect(user_id):
    """Where a logged-in seller should land after login / portal entry."""
    if _seller_portal_manageable_store(user_id):
        return redirect(url_for('templates.seller_products'))
    suspended = _seller_portal_suspended_store(user_id)
    if suspended:
        return redirect(url_for('templates.seller_store_suspended'))
    pend_app = SellerApplication.query.filter_by(
        user_id=user_id, status='pending'
    ).order_by(SellerApplication.submitted_at.desc()).first()
    if pend_app:
        return redirect(url_for('templates.seller_signup_status'))
    # Also treat resubmitted apps as in-review
    latest = _seller_portal_latest_application(user_id)
    if latest and latest.status in ('pending', 'resubmitted'):
        return redirect(url_for('templates.seller_signup_status'))
    return redirect(url_for('templates.seller_signup_complete'))


def _seller_portal_latest_application(user_id):
    return (
        SellerApplication.query.filter_by(user_id=user_id)
        .order_by(SellerApplication.submitted_at.desc())
        .first()
    )


def _finalize_seller_signup_from_otp(record, email):
    """Create seller user after OTP verification; log in and clear OTP row."""
    if User.query.filter_by(email=email).first():
        db.session.delete(record)
        db.session.commit()
        session.pop('pending_seller_reg_email', None)
        return redirect(url_for('templates.login'))

    pending = record.signup_data or {}
    user = User(
        full_name=pending.get('full_name', ''),
        email=email,
        role='seller',
        status='active',
        phone=pending.get('phone'),
    )
    user.password_hash = pending.get('password_hash', '')
    db.session.add(user)
    db.session.flush()
    db.session.delete(record)
    db.session.commit()

    session.pop('pending_seller_reg_email', None)
    session.permanent = True
    session['user_id'] = user.id
    session['user_name'] = user.full_name
    session['role'] = user.role
    session['email'] = user.email

    return redirect(url_for('templates.seller_signup_complete'))


@templates_bp.route('/seller/signup', methods=['GET'])
def seller_signup_landing():
    """Lazada-style seller portal entry: account step (Gmail OTP first)."""
    print("\n" + "=" * 60)
    print("🧭 SELLER SIGNUP LANDING HIT")
    print(f"Path: {request.path}")
    print(f"Session user_id: {session.get('user_id')}")
    print(f"Session role: {session.get('role')}")
    uid = session.get('user_id')
    if uid:
        user = User.query.get(uid)
        print(f"User found: {bool(user)}")
        if user:
            print(f"User role(db): {user.role}")
            if session.get('role') != user.role:
                print(f"⚠️ Session role mismatch. session={session.get('role')} db={user.role}. Syncing session role.")
                session['role'] = user.role
        if user and user.role == 'seller':
            print("Decision: seller -> _seller_home_redirect")
            print("=" * 60 + "\n")
            return _seller_home_redirect(user.id)
        if user and user.role == 'customer':
            # Keep this page directly accessible for customers to avoid redirect loops.
            print("Decision: customer -> render seller_signup_landing.html")
            print("=" * 60 + "\n")
            return render_template('seller_signup_landing.html')

    print("Decision: guest/unknown -> render seller_signup_landing.html")
    print("=" * 60 + "\n")
    return render_template('seller_signup_landing.html')


@templates_bp.route('/seller/signup/start', methods=['POST'])
def seller_signup_start():
    """Validate account fields, send Gmail OTP, redirect to verify step."""
    if session.get('user_id'):
        current_user = User.query.get(session.get('user_id'))
        role_label = (getattr(current_user, 'role', None) or session.get('role') or 'existing').strip()
        return render_template(
            'seller_signup_landing.html',
            error=(
                f"Email already exists"
            ),
            form_data=request.form,
        )

    try:
        from werkzeug.security import generate_password_hash
        from app.utils.otp_service import (
            DEFAULT_EXPIRY_MINUTES,
            RESEND_COOLDOWN_SECONDS,
            can_resend,
            new_otp_pair,
        )
        from app.utils.email_helper import send_seller_signup_otp_email
        from app.utils.otp_delivery import deliver_otp, sync_hashed_otp_record
        from app.utils.phone_utils import is_valid_ph_mobile, mask_email, mask_phone

        full_name = (request.form.get('full_name') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        phone_raw = (request.form.get('phone') or '').strip()
        phone = _normalize_ph_mobile(phone_raw) if phone_raw else None
        password = request.form.get('password') or ''
        confirm_password = request.form.get('confirm_password') or ''

        if not all([full_name, email, password, confirm_password]):
            return render_template(
                'seller_signup_landing.html',
                error='All fields are required.',
                form_data=request.form,
            )

        if password != confirm_password:
            return render_template(
                'seller_signup_landing.html',
                error='Passwords do not match.',
                form_data=request.form,
            )

        pw_error = _password_strength_error(password)
        if pw_error:
            return render_template(
                'seller_signup_landing.html',
                error=pw_error,
                form_data=request.form,
            )

        if phone_raw and (not phone or not is_valid_ph_mobile(phone_raw)):
            return render_template(
                'seller_signup_landing.html',
                error='Please enter a valid Philippine mobile number (e.g., 09171234567).',
                form_data=request.form,
            )

        # Smart channel: phone present → SMS, else email
        channel = 'sms' if phone else 'email'

        if phone and _phone_taken_web(phone, exclude_email=email):
            return render_template(
                'seller_signup_landing.html',
                error='This phone number is already registered to another account.',
                form_data=request.form,
            )

        existing = User.query.filter_by(email=email).first()
        if existing:
            if existing.role == 'customer':
                existing_msg = (
                    'This email is already registered as a customer account. '
                    'Please sign in to continue your seller application, or use a different email.'
                )
            else:
                existing_msg = (
                    f"This email is already registered as a {existing.role} account. "
                    'Please sign in, or use a different email.'
                )
            return render_template(
                'seller_signup_landing.html',
                error=existing_msg,
                form_data=request.form,
            )

        plain_code, otp_hash, expires_at = new_otp_pair(DEFAULT_EXPIRY_MINUTES)
        pending_data = {
            'full_name': full_name,
            'password_hash': generate_password_hash(password),
            'phone': phone,
            'otp_channel': channel,
        }

        record = SellerSignupOTP.query.filter_by(email=email).first()
        if record:
            allowed, retry_after = can_resend(record.last_sent_at, RESEND_COOLDOWN_SECONDS)
            if not allowed:
                session['pending_seller_reg_email'] = email
                session['pending_seller_reg_channel'] = channel
                session['pending_seller_reg_dest'] = mask_phone(phone) if channel == 'sms' else mask_email(email)
                return redirect(
                    url_for('templates.seller_signup_verify', cooldown=retry_after)
                )
            record.otp_hash = otp_hash
            record.signup_data = pending_data
            record.expires_at = expires_at
            record.last_sent_at = datetime.utcnow()
            record.attempts = 0
            record.is_verified = False
            record.verified_at = None
        else:
            record = SellerSignupOTP(
                email=email,
                otp_hash=otp_hash,
                signup_data=pending_data,
                expires_at=expires_at,
                last_sent_at=datetime.utcnow(),
            )
            db.session.add(record)

        db.session.commit()

        ok, fail, meta = deliver_otp(
            channel,
            otp_code=plain_code,
            email=email,
            phone=phone,
            email_sender_fn=send_seller_signup_otp_email,
            email_sender_kwargs={'full_name': full_name, 'expiry_minutes': DEFAULT_EXPIRY_MINUTES},
            expiry_minutes=DEFAULT_EXPIRY_MINUTES,
            sms_purpose='verification',
        )
        if not ok:
            db.session.rollback()
            return render_template(
                'seller_signup_landing.html',
                error=(fail or {}).get('error') or 'Failed to send verification code.',
                error_code=(fail or {}).get('error_code'),
                form_data=request.form,
            )
        sync_hashed_otp_record(record, meta, plain_code)

        session['pending_seller_reg_email'] = email
        session['pending_seller_reg_channel'] = channel
        session['pending_seller_reg_dest'] = meta.get('destination_masked')
        return redirect(url_for('templates.seller_signup_verify'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('seller_signup_start: %s', e)
        return render_template(
            'seller_signup_landing.html',
            error='Something went wrong. Please try again.',
            form_data=request.form,
        )


@templates_bp.route('/seller/signup/verify', methods=['GET', 'POST'])
def seller_signup_verify():
    from app.utils.otp_service import MAX_VERIFY_ATTEMPTS, attempts_remaining, verify_otp

    email = session.get('pending_seller_reg_email')
    if not email:
        return redirect(url_for('templates.seller_signup_landing'))

    channel = session.get('pending_seller_reg_channel') or 'email'
    dest = session.get('pending_seller_reg_dest') or email

    if request.method == 'GET':
        cooldown = request.args.get('cooldown', 0, type=int)
        return render_template(
            'seller_signup_verify.html',
            email=email,
            cooldown=cooldown,
            otp_channel=channel,
            destination_masked=dest,
        )

    otp_code = (request.form.get('otp_code') or '').strip()
    if not otp_code or len(otp_code) != 6 or not otp_code.isdigit():
        return render_template(
            'seller_signup_verify.html',
            email=email,
            otp_channel=channel,
            destination_masked=dest,
            error='Please enter the 6-digit code.',
        )

    record = SellerSignupOTP.query.filter_by(email=email).first()
    if not record:
        session.pop('pending_seller_reg_email', None)
        return redirect(url_for('templates.seller_signup_landing'))

    if record.is_verified:
        return _finalize_seller_signup_from_otp(record, email)

    if record.is_expired():
        return render_template(
            'seller_signup_verify.html',
            email=email,
            otp_channel=channel,
            destination_masked=dest,
            error='Your code has expired. Please request a new one.',
            expired=True,
        )

    if (record.attempts or 0) >= MAX_VERIFY_ATTEMPTS:
        return render_template(
            'seller_signup_verify.html',
            email=email,
            otp_channel=channel,
            destination_masked=dest,
            error='Too many incorrect attempts. Please request a new code.',
            locked=True,
        )

    if not verify_otp(otp_code, record.otp_hash):
        record.attempts = (record.attempts or 0) + 1
        db.session.commit()
        left = attempts_remaining(record.attempts, MAX_VERIFY_ATTEMPTS)
        return render_template(
            'seller_signup_verify.html',
            email=email,
            otp_channel=channel,
            destination_masked=dest,
            error=f'Invalid code. {left} attempt{"s" if left != 1 else ""} remaining.',
        )

    record.is_verified = True
    record.verified_at = datetime.utcnow()
    db.session.commit()
    return _finalize_seller_signup_from_otp(record, email)


@templates_bp.route('/seller/signup/resend-otp', methods=['POST'])
def seller_signup_resend_otp():
    from app.utils.otp_service import (
        DEFAULT_EXPIRY_MINUTES,
        RESEND_COOLDOWN_SECONDS,
        can_resend,
        new_otp_pair,
    )
    from app.utils.email_helper import send_seller_signup_otp_email
    from app.utils.otp_delivery import deliver_otp, normalize_otp_channel, sync_hashed_otp_record

    email = session.get('pending_seller_reg_email')
    if not email:
        return jsonify({'success': False, 'error': 'Session expired. Please start again.'}), 400

    record = SellerSignupOTP.query.filter_by(email=email, is_verified=False).first()
    if not record:
        return jsonify({'success': False, 'error': 'No pending verification found.'}), 404

    allowed, retry_after = can_resend(record.last_sent_at, RESEND_COOLDOWN_SECONDS)
    if not allowed:
        return jsonify(
            {
                'success': False,
                'error': 'Please wait before requesting another code.',
                'retry_after_seconds': retry_after,
            }
        ), 429

    pending = record.signup_data or {}
    channel = normalize_otp_channel(
        pending.get('otp_channel') or session.get('pending_seller_reg_channel'),
        default='email',
    ) or 'email'
    phone = pending.get('phone')

    plain_code, otp_hash, expires_at = new_otp_pair(DEFAULT_EXPIRY_MINUTES)
    record.otp_hash = otp_hash
    record.expires_at = expires_at
    record.last_sent_at = datetime.utcnow()
    record.attempts = 0
    db.session.commit()

    ok, fail, meta = deliver_otp(
        channel,
        otp_code=plain_code,
        email=email,
        phone=phone,
        email_sender_fn=send_seller_signup_otp_email,
        email_sender_kwargs={'full_name': pending.get('full_name'), 'expiry_minutes': DEFAULT_EXPIRY_MINUTES},
        expiry_minutes=DEFAULT_EXPIRY_MINUTES,
        sms_purpose='verification',
    )
    if not ok:
        return jsonify(fail), 503
    sync_hashed_otp_record(record, meta, plain_code)

    session['pending_seller_reg_channel'] = channel
    session['pending_seller_reg_dest'] = meta.get('destination_masked')
    return jsonify(
        {
            'success': True,
            'message': f'A new code has been sent to {meta.get("destination_masked")}.',
            'otp_channel': channel,
            'destination_masked': meta.get('destination_masked'),
            'resend_cooldown_seconds': RESEND_COOLDOWN_SECONDS,
        }
    ), 200


@templates_bp.route('/seller/signup/complete', methods=['GET'])
def seller_signup_complete():
    """Store details + documents (after Gmail OTP or signed-in customer)."""
    if not session.get('user_id'):
        return redirect(url_for('templates.login', next=url_for('templates.seller_signup_complete')))

    user = User.query.get(session['user_id'])
    if not user or user.role not in ('seller', 'customer'):
        return redirect(url_for('templates.dashboard'))

    if user.role == 'seller' and _seller_portal_manageable_store(user.id):
        return redirect(url_for('templates.seller_products'))

    if user.role == 'seller' and _seller_portal_suspended_store(user.id):
        return redirect(url_for('templates.seller_store_suspended'))

    latest = _seller_portal_latest_application(user.id)
    if latest and latest.status in ('pending', 'resubmitted'):
        return redirect(url_for('templates.seller_signup_status'))
    return render_template('seller_signup_complete.html', user=user, application=latest)


@templates_bp.route('/seller/suspended', methods=['GET'])
def seller_store_suspended():
    """Shown when the seller's storefront was locked by admin (suspended)."""
    if not session.get('user_id'):
        return redirect(url_for('templates.login', next=url_for('templates.seller_store_suspended')))

    user = User.query.get(session['user_id'])
    if not user or user.role != 'seller':
        return redirect(url_for('templates.index'))

    # If they were reactivated (or only self-hidden as inactive), send them back.
    if _seller_portal_manageable_store(user.id):
        return redirect(url_for('templates.seller_products'))

    store = _seller_portal_suspended_store(user.id)
    if not store:
        return _seller_home_redirect(user.id)

    return render_template(
        'seller_store_suspended.html',
        user=user,
        store=store,
    )


@templates_bp.route('/seller/signup/status', methods=['GET'])
def seller_signup_status():
    if not session.get('user_id'):
        return redirect(url_for('templates.login'))

    user = User.query.get(session['user_id'])
    if not user:
        return redirect(url_for('templates.index'))

    if user.role == 'seller' and _seller_portal_suspended_store(user.id) and not _seller_portal_manageable_store(user.id):
        return redirect(url_for('templates.seller_store_suspended'))

    latest = _seller_portal_latest_application(user.id)
    return render_template(
        'seller_signup_status.html',
        user=user,
        application=latest,
    )


@templates_bp.route('/api/account/orders/data')
def orders_data():
    """Return JSON data for orders"""
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session.get('user_id')
    _ensure_order_fulfillment_columns()

    orders = (
        Order.query
        .options(
            joinedload(Order.store),
            joinedload(Order.items).joinedload(OrderItem.product).joinedload(Product.images),
            joinedload(Order.items).joinedload(OrderItem.variant)
        )
        .filter_by(customer_id=user_id)
        .order_by(Order.created_at.desc())
        .all()
    )

    order_ids = [o.id for o in orders]
    rated_by_order = defaultdict(set)
    product_ratings_by_order = defaultdict(list)
    item_ratings_by_order = defaultdict(dict)
    store_rating_by_order = {}
    if order_ids:
        for pr in ProductRating.query.filter(ProductRating.order_id.in_(order_ids)).all():
            if pr.order_item_id is not None:
                rated_by_order[pr.order_id].add(pr.order_item_id)
                if pr.rating is not None:
                    item_ratings_by_order[pr.order_id][pr.order_item_id] = int(pr.rating)
            if pr.rating is not None:
                product_ratings_by_order[pr.order_id].append(int(pr.rating))
        for r in StoreRating.query.filter(StoreRating.order_id.in_(order_ids)).all():
            store_rating_by_order[r.order_id] = int(r.rating) if r.rating is not None else None

    orders_payload = []
    for order in orders:
        if order.status in ('delivered', 'completed'):
            rid = rated_by_order.get(order.id, set())
            sr = order.id in store_rating_by_order
            srv = store_rating_by_order.get(order.id)
            prv = product_ratings_by_order.get(order.id, [])
            irm = item_ratings_by_order.get(order.id, {})
        else:
            rid = set()
            sr = True
            srv = None
            prv = []
            irm = {}
        order_dict = _serialize_customer_order(
            order,
            rated_item_ids=rid,
            store_rated=sr,
            store_rating_value=srv,
            product_rating_values=prv,
            item_ratings=irm,
        )
        order_dict['date'] = order_dict['created_at']
        orders_payload.append(order_dict)

    resp = jsonify(orders_payload)
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp

@templates_bp.route('/api/account/orders/<int:order_id>')
def order_details(order_id):
    """Return specific order details"""
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session.get('user_id')
    _ensure_order_fulfillment_columns()
    order = (
        Order.query
        .options(
            joinedload(Order.store),
            joinedload(Order.items).joinedload(OrderItem.product).joinedload(Product.images),
            joinedload(Order.items).joinedload(OrderItem.variant)
        )
        .filter_by(id=order_id, customer_id=user_id)
        .first()
    )

    if not order:
        return jsonify({'error': 'Order not found'}), 404

    order_dict = _serialize_customer_order(order)
    order_dict['date'] = order_dict['created_at']
    return jsonify(order_dict)

@templates_bp.route('/api/account/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    """Cancel an order and restore reserved product stock."""
    if not session.get('user_id'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    user_id = session.get('user_id')
    order = Order.query.filter_by(id=order_id, customer_id=user_id).first()

    if not order:
        return jsonify({'success': False, 'message': 'Order not found'}), 404

    cancellable_statuses = {'pending'}
    if order.status not in cancellable_statuses:
        return jsonify({
            'success': False,
            'message': 'Only pending orders can be cancelled.'
        }), 400

    from app.order_cancel_reasons import normalize_customer_cancel_reason
    payload = request.get_json(silent=True) or {}
    reason_code, reason_text, reason_err = normalize_customer_cancel_reason(payload)
    if reason_err:
        return jsonify({'success': False, 'message': reason_err}), 400

    try:
        _ensure_order_fulfillment_columns()
        # Ensure add-on rows are loaded before stock restore
        _ = [(item.addons, item.product, item.variant) for item in (order.items or [])]
        order.restore_stock_on_cancel(user_id)
        order.status = 'cancelled'
        order.cancellation_reason_code = reason_code
        order.cancellation_reason = reason_text
        order.cancelled_at = datetime.utcnow()
        order.updated_at = datetime.utcnow()
        from app.utils.seller_notifications import notify_store_seller
        notify_store_seller(
            store_id=order.store_id,
            title='Order cancelled',
            message=f'Customer cancelled Order #{order.id}. Reason: {reason_text}',
            type='order_cancelled',
            reference_id=order.id,
        )
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

    return jsonify({
        'success': True,
        'message': 'Order cancelled successfully',
        'order': _serialize_customer_order(order),
    })


@templates_bp.route('/api/account/orders/<int:order_id>/complete', methods=['POST'])
def complete_order(order_id):
    """Allow customer to confirm delivered order as completed."""
    if not session.get('user_id'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    _ensure_order_fulfillment_columns()
    user_id = session.get('user_id')
    order = Order.query.filter_by(id=order_id, customer_id=user_id).first()
    if not order:
        return jsonify({'success': False, 'message': 'Order not found'}), 404
    if order.status != 'delivered':
        return jsonify({'success': False, 'message': 'Only delivered orders can be marked as completed.'}), 400

    order.set_status('completed')
    from app.utils.seller_notifications import notify_store_seller
    notify_store_seller(
        store_id=order.store_id,
        title='Order completed',
        message=f'Customer confirmed delivery for Order #{order.id}.',
        type='order_completed',
        reference_id=order.id,
    )
    db.session.commit()
    db.session.refresh(order)
    return jsonify({
        'success': True,
        'message': 'Order marked as completed.',
        'order': _serialize_customer_order(order),
    })


# ══════════════════════════════════════════════════════════════════════════
# PRODUCT RATINGS — Session auth (Web)
# ══════════════════════════════════════════════════════════════════════════

@templates_bp.route('/api/account/orders/<int:order_id>/ratings', methods=['GET'])
def get_order_ratings(order_id):
    """Get existing ratings for an order's items."""
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session.get('user_id')
    order = Order.query.filter_by(id=order_id, customer_id=user_id).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    ratings = ProductRating.query.filter_by(order_id=order_id, customer_id=user_id).all()
    ratings_map = {r.order_item_id: r.to_dict() for r in ratings if r.order_item_id is not None}

    store_row = StoreRating.query.filter_by(order_id=order_id, customer_id=user_id).first()

    return jsonify({
        'success': True,
        'ratings': ratings_map,
        'store_rating': store_row.to_dict() if store_row else None,
    })


@templates_bp.route('/api/account/orders/<int:order_id>/rate', methods=['POST'])
def submit_order_ratings(order_id):
    """Submit store and/or product ratings for a delivered or completed order."""
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session.get('user_id')
    order = Order.query.filter_by(id=order_id, customer_id=user_id).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    if order.status not in ('delivered', 'completed'):
        return jsonify({'error': 'Can only rate delivered or completed orders'}), 400

    data = request.get_json() or {}
    ratings_data = data.get('ratings') or []
    store_payload = data.get('store_rating')

    created = []
    created_store = False

    if store_payload and isinstance(store_payload, dict):
        rv = store_payload.get('rating')
        try:
            rv = int(rv) if rv is not None else None
        except (TypeError, ValueError):
            rv = None
        if rv is not None and 1 <= rv <= 5:
            existing_sr = StoreRating.query.filter_by(order_id=order_id, customer_id=user_id).first()
            if not existing_sr:
                comment_s = (store_payload.get('comment') or '').strip() if store_payload.get('comment') else None
                db.session.add(
                    StoreRating(
                        customer_id=user_id,
                        store_id=order.store_id,
                        order_id=order_id,
                        rating=rv,
                        comment=comment_s or None,
                    )
                )
                created_store = True

    for r in ratings_data:
        order_item_id = r.get('order_item_id')
        rating_value = r.get('rating')
        comment = r.get('comment', '').strip() if r.get('comment') else None

        if not order_item_id or not rating_value:
            continue
        if not (1 <= int(rating_value) <= 5):
            continue

        order_item = OrderItem.query.filter_by(id=order_item_id, order_id=order_id).first()
        if not order_item:
            continue

        existing = ProductRating.query.filter_by(
            customer_id=user_id, order_item_id=order_item_id
        ).first()

        if existing:
            continue

        new_rating = ProductRating(
            customer_id=user_id,
            product_id=order_item.product_id,
            variant_id=order_item.variant_id,
            order_id=order_id,
            order_item_id=order_item_id,
            rating=int(rating_value),
            comment=comment,
        )
        db.session.add(new_rating)
        created.append(new_rating)

    if not ratings_data and not created_store:
        return jsonify({'error': 'No ratings provided'}), 400

    if created or created_store:
        parts = []
        if created_store and store_payload:
            try:
                sr = int(store_payload.get('rating'))
                parts.append(f'store {sr}/5')
            except (TypeError, ValueError):
                parts.append('store')
        if created:
            parts.append(f'{len(created)} product rating(s)')
        summary = ', '.join(parts) if parts else 'new ratings'
        from app.utils.seller_notifications import notify_store_seller
        notify_store_seller(
            store_id=order.store_id,
            title='New rating received',
            message=f'Customer rated Order #{order.id} ({summary}).',
            type='new_rating',
            reference_id=order.id,
        )

    db.session.commit()

    parts = []
    if created_store:
        parts.append('store')
    if created:
        parts.append(f'{len(created)} product rating(s)')
    return jsonify({
        'success': True,
        'message': ', '.join(parts) if parts else 'Nothing new to save',
        'created': len(created),
        'store_created': created_store,
    })


@templates_bp.route('/api/products/<int:product_id>/ratings', methods=['GET'])
def get_product_ratings(product_id):
    """Get all ratings for a product (public)."""
    product = Product.query.get_or_404(product_id)

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 10, type=int), 50)

    ratings_query = ProductRating.query.filter_by(product_id=product_id)\
        .order_by(ProductRating.created_at.desc())

    total = ratings_query.count()
    ratings = ratings_query.offset((page - 1) * per_page).limit(per_page).all()

    # Calculate aggregates
    from sqlalchemy import func
    agg = db.session.query(
        func.avg(ProductRating.rating).label('avg'),
        func.count(ProductRating.id).label('count')
    ).filter_by(product_id=product_id).first()

    # Star distribution
    dist = db.session.query(
        ProductRating.rating, func.count(ProductRating.id)
    ).filter_by(product_id=product_id).group_by(ProductRating.rating).all()
    distribution = {str(i): 0 for i in range(1, 6)}
    for star, count in dist:
        distribution[str(star)] = count

    return jsonify({
        'success': True,
        'avg_rating': round(float(agg.avg or 0), 1),
        'total_ratings': agg.count or 0,
        'distribution': distribution,
        'ratings': [r.to_dict() for r in ratings],
        'page': page,
        'total_pages': (total + per_page - 1) // per_page,
    })


@templates_bp.route('/orders')
def orders():
    """Display user's orders"""
    if not session.get('user_id'):
        return redirect(url_for('templates.login'))
    
    user_id = session.get('user_id')
    page = request.args.get('page', 1, type=int)
    per_page = 10
    status = request.args.get('status', '')
    
    # Build query
    query = Order.query.filter_by(customer_id=user_id)
    
    if status:
        query = query.filter_by(status=status)
    
    # Get paginated orders
    orders_paginated = query.order_by(Order.created_at.desc()).paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    # Process orders with items
    orders_data = []
    for order in orders_paginated.items:
        order_dict = order.to_dict()
        
        # Get order items
        items = OrderItem.query.filter_by(order_id=order.id).all()
        order_dict['items'] = [item.to_dict() for item in items]
        
        # Get store name
        store = Store.query.get(order.store_id)
        if store:
            order_dict['store_name'] = store.name
            order_dict['store_contact'] = store.contact_number
        
        # Get rider info if assigned
        if order.rider_id:
            rider = Rider.query.get(order.rider_id)
            if rider and rider.user:
                order_dict['rider_name'] = rider.user.full_name
                order_dict['rider_vehicle'] = rider.vehicle_type
        
        orders_data.append(order_dict)
    
    # Calculate order statistics
    total_orders = Order.query.filter_by(customer_id=user_id).count()
    pending_orders = Order.query.filter_by(customer_id=user_id, status='pending').count()
    delivery_orders = Order.query.filter_by(customer_id=user_id, status='on_delivery').count()
    delivered_orders = Order.query.filter_by(customer_id=user_id, status='delivered').count()
    
    return render_template('orders.html',
                         orders=orders_data,
                         total_orders=total_orders,
                         pending_orders=pending_orders,
                         delivery_orders=delivery_orders,
                         delivered_orders=delivered_orders,
                         page=page,
                         total_pages=orders_paginated.pages,
                         status=status)


@templates_bp.route('/category/<path:category_identifier>')
def category(category_identifier):
    """Category page showing all products in a main category"""
    try:
        from app.models import Category
        # For base navigation ("All", "Fresh Flowers", etc.)
        main_categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()
        
        # Try to find by ID first (if it's a number)
        category = None
        if category_identifier.isdigit():
            category = Category.query.get(int(category_identifier))
        
        # If not found by ID or not a number, try by slug
        if not category:
            category = Category.query.filter_by(slug=category_identifier, is_active=True).first()
        
        if not category:
            flash('Category not found', 'error')
            return redirect(url_for('templates.index'))
        
        # Get all products in this main category
        products = Product.query.filter_by(
            main_category_id=category.id,
            is_available=True,
            is_archived=False
        ).join(Store).filter(Store.status == 'active').all()
        
        product_list = _product_list_for_storefront(products)
        
        return render_template('category.html',
                             category=category,
                             products=product_list,
                             category_identifier=category_identifier,
                             category_id=category.name,
                             categories=main_categories)
        
    except Exception as e:
        print(f"❌ Error loading category {category_identifier}: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Error loading category', 'error')
        return redirect(url_for('templates.index'))


@templates_bp.route('/contact')
def contact():
    """Contact page"""
    return render_template('contact.html')

@templates_bp.route('/faq')
def faq():
    """FAQ page"""
    return render_template('faq.html')

@templates_bp.route('/shipping')
def shipping():
    """Shipping policy page"""
    return render_template('shipping.html')

@templates_bp.route('/returns')
def returns():
    """Returns policy page"""
    return render_template('returns.html')

@templates_bp.route('/search')
def search():
    query = request.args.get('q', '')
    products = []
    if query:
        from sqlalchemy import or_
        from app.models import Category, StoreCategory
        term = f'%{query.strip()}%'
        raw = Product.query\
            .join(Store, Product.store_id == Store.id)\
            .outerjoin(Category, Product.main_category_id == Category.id)\
            .outerjoin(StoreCategory, Product.store_category_id == StoreCategory.id)\
            .filter(
                or_(
                    Product.name.ilike(term),
                    Category.name.ilike(term),
                    Category.slug.ilike(term),
                    StoreCategory.name.ilike(term),
                    StoreCategory.slug.ilike(term),
                ),
                Product.is_available == True,
                Product.is_archived == False,
                Store.status == 'active'
            ).all()
        products = _product_list_for_storefront(raw)

    return render_template('search.html', query=query, products=products)


@templates_bp.route('/categories')
def categories():
    """All categories page"""
    # Define your categories
    categories_list = [
        {'id': 'flowers', 'name': 'Fresh Flowers', 'icon': 'flower-line', 'count': 42},
        {'id': 'plants', 'name': 'Potted Plants', 'icon': 'plant-line', 'count': 28},
        {'id': 'bouquets', 'name': 'Bouquets', 'icon': 'bouquet-line', 'count': 35},
        {'id': 'succulents', 'name': 'Succulents', 'icon': 'cactus-line', 'count': 19},
    ]
    
    return render_template('categories.html', categories=categories_list)


@templates_bp.route('/browse')
def browse_products():
    """Public catalog: search and filters (storefront). Seller inventory uses /seller/products."""
    try:
        main_categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()
        current_user_id = session.get('user_id')
        is_customer = session.get('role') == 'customer' and current_user_id
        customer_address = _get_default_customer_address(current_user_id) if is_customer else None
        browse_all_arg = request.args.get('browse_all')
        if browse_all_arg is not None:
            session['storefront_browse_all'] = browse_all_arg == '1'
        browse_all_mode = bool(session.get('storefront_browse_all', False))
        location_filter_on = bool(is_customer and customer_address and not browse_all_mode)

        products = (
            _public_storefront_product_base_query(require_sellable=True)
            .order_by(Product.created_at.desc())
            .limit(500)
            .all()
        )

        product_delivery_map = {}
        if is_customer and customer_address:
            for product in products:
                delivery = _store_delivery_match(product.store, customer_address)
                product_delivery_map[product.id] = delivery

        if location_filter_on:
            products = [
                p for p in products
                if product_delivery_map.get(p.id, {}).get('can_deliver')
            ]

        product_list = _product_list_for_storefront(products)
        for pd in product_list:
            if is_customer and customer_address:
                delivery = product_delivery_map.get(
                    pd.get('id'),
                    {'can_deliver': False, 'reason': 'Delivery coverage unavailable.'},
                )
                pd['can_deliver_to_customer'] = bool(delivery.get('can_deliver'))
                pd['delivery_block_reason'] = delivery.get('reason')
            else:
                pd['can_deliver_to_customer'] = True
                pd['delivery_block_reason'] = None

        featured_categories = []
        for cat in main_categories:
            featured_categories.append({
                'id': cat.id,
                'name': cat.name,
                'slug': cat.slug,
                'icon': cat.icon or 'flower-line',
                'description': cat.description,
                'image_url': cat.image_url
            })
        initial_category = (request.args.get('category') or '').strip().lower()
        return render_template(
            'browse_products.html',
            products=product_list,
            categories=featured_categories,
            main_categories=main_categories,
            initial_category_filter=initial_category,
            browse_all_mode=browse_all_mode,
            customer_has_default_address=bool(customer_address),
        )
    except Exception as e:
        current_app.logger.exception('browse_products: %s', e)
        try:
            db.session.rollback()
        except Exception:
            pass
        return render_template(
            'browse_products.html',
            products=[],
            categories=[],
            main_categories=[],
            initial_category_filter='',
            browse_all_mode=False,
            customer_has_default_address=False,
        )


@templates_bp.route('/products')
def products():
    """Legacy URL used by marketing links; public catalog is /browse."""
    qs = request.query_string.decode('utf-8') if request.query_string else ''
    dest = url_for('templates.browse_products')
    if qs:
        dest = f'{dest}?{qs}'
    return redirect(dest, code=302)


@templates_bp.route('/product/<int:product_id>')
def product_detail(product_id):
    """Product detail page with category support"""
    try:
        product = Product.query.get_or_404(product_id)
        store = Store.query.get(product.store_id)
        
        # Allow anyone (including sellers) to view public product pages
        # This is NOT a seller-only page
        
        # Get all main categories for the navigation
        from app.models import Category
        main_categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()
        
        # Get related products - same main category
        related_products = Product.query.filter(
            Product.main_category_id == product.main_category_id,
            Product.store_id == product.store_id,
            Product.id != product_id,
            Product.is_available == True,
            Product.is_archived == False,
            _public_storefront_sellable_filter()
        ).limit(4).all()
        
        # Get add-on products - different main category but same store
        addon_products = []
        if product.main_category_id:
            addon_products = Product.query.filter(
                Product.store_id == product.store_id,
                Product.main_category_id != product.main_category_id,
                Product.id != product_id,
                Product.is_available == True,
                Product.is_archived == False,
                _public_storefront_sellable_filter()
            ).limit(8).all()
        
        # Convert products to dict format
        product_dict = product.to_dict()
        store_dict = store.to_dict() if store else None
        
        # Add main_category and store_category info to product_dict for template
        if product.main_category:
            product_dict['main_category'] = {
                'id': product.main_category.id,
                'name': product.main_category.name,
                'slug': product.main_category.slug
            }
        
        if product.store_category:
            product_dict['store_category'] = {
                'id': product.store_category.id,
                'name': product.store_category.name,
                'slug': product.store_category.slug
            }
        
        # Debug print
        print(f"\n🔍 PRODUCT DETAIL - ID: {product_id}")
        print(f"  Name: {product.name}")
        print(f"  Main Category: {product.main_category.name if product.main_category else 'None'}")
        print(f"  Store Category: {product.store_category.name if product.store_category else 'None'}")
        print(f"  Categories for nav: {len(main_categories)}")
        print(f"  Related products: {len(related_products)}")
        print(f"  Add-on products: {len(addon_products)}")
        print(f"  User role: {session.get('role', 'guest')}")
        print(f"  ✅ Rendering product_detail.html (public page accessible to all)")
        
        return render_template(
            'product_detail.html',
            product=product_dict,
            store=store_dict,
            main_categories=main_categories,  # Pass to base.html for navigation
            related_products=[p.to_dict() for p in related_products],
            addon_products=[p.to_dict() for p in addon_products]
        )
        
    except Exception as e:
        print(f"❌ Error loading product {product_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Product not found', 'error')
        return redirect(url_for('templates.browse_products'))
    
@templates_bp.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('templates.login'))
    if session.get('role') == 'seller':
        return redirect(url_for('templates.seller_dashboard'))

    if session.get('role') == 'admin':
        return _render_admin_dashboard()

    return render_template('dashboard.html', is_admin=False)


def _render_admin_dashboard():
    """Render the admin dashboard with platform-wide aggregates."""
    from sqlalchemy import func
    from datetime import date, timedelta
    from app.utils.report_service import period_range

    period = (request.args.get('period') or 'month').lower().strip()
    custom_from = request.args.get('from')
    custom_to = request.args.get('to')
    range_start, range_end, period_label = period_range(period, custom_from, custom_to)
    prev_start = range_start - (range_end - range_start)
    prev_end = range_start

    today = date.today()

    # Revenue KPI: online = delivered/completed, POS = all
    online_revenue = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(
        Order.status.in_(['delivered', 'completed']),
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).scalar() or 0
    pos_revenue = db.session.query(
        func.coalesce(func.sum(POSOrder.total_amount), 0)
    ).filter(
        POSOrder.created_at >= range_start,
        POSOrder.created_at < range_end,
    ).scalar() or 0
    revenue_this_month = float(online_revenue) + float(pos_revenue)

    prev_online_revenue = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(
        Order.status.in_(['delivered', 'completed']),
        Order.created_at >= prev_start,
        Order.created_at < prev_end,
    ).scalar() or 0
    prev_pos_revenue = db.session.query(
        func.coalesce(func.sum(POSOrder.total_amount), 0)
    ).filter(
        POSOrder.created_at >= prev_start,
        POSOrder.created_at < prev_end,
    ).scalar() or 0
    revenue_prev_month = float(prev_online_revenue) + float(prev_pos_revenue)

    revenue_change = 0
    if revenue_prev_month > 0:
        revenue_change = round(((revenue_this_month - revenue_prev_month) / revenue_prev_month) * 100, 1)

    # Orders KPI: ALL online statuses + all POS
    online_orders_this = Order.query.filter(
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).count()
    pos_orders_this = POSOrder.query.filter(
        POSOrder.created_at >= range_start,
        POSOrder.created_at < range_end,
    ).count()
    orders_this_month = online_orders_this + pos_orders_this

    online_orders_prev = Order.query.filter(
        Order.created_at >= prev_start,
        Order.created_at < prev_end,
    ).count()
    pos_orders_prev = POSOrder.query.filter(
        POSOrder.created_at >= prev_start,
        POSOrder.created_at < prev_end,
    ).count()
    orders_prev_month = online_orders_prev + pos_orders_prev
    orders_change = 0
    if orders_prev_month > 0:
        orders_change = round(((orders_this_month - orders_prev_month) / orders_prev_month) * 100, 1)

    # Customers KPI: new customer accounts registered in period
    customers_this_month = db.session.query(func.count(User.id)).filter(
        User.role == 'customer',
        User.created_at >= range_start,
        User.created_at < range_end,
    ).scalar() or 0
    customers_prev_month = db.session.query(func.count(User.id)).filter(
        User.role == 'customer',
        User.created_at >= prev_start,
        User.created_at < prev_end,
    ).scalar() or 0
    customers_change = 0
    if customers_prev_month > 0:
        customers_change = round(((customers_this_month - customers_prev_month) / customers_prev_month) * 100, 1)

    # Delivery rate: (delivered+completed) / (delivered+completed+cancelled)
    total_resolved = Order.query.filter(
        Order.status.in_(['delivered', 'completed', 'cancelled']),
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).count()
    delivered_this_month = Order.query.filter(
        Order.status.in_(['delivered', 'completed']),
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).count()
    delivery_rate = round((delivered_this_month / total_resolved * 100), 1) if total_resolved > 0 else 100.0

    # Top products: online delivered/completed + POS all
    top_products_query = db.session.query(
        Product.id,
        Product.name,
        ProductVariant.id.label('variant_id'),
        ProductVariant.name.label('variant_name'),
        Store.name.label('store_name'),
        Category.name.label('category_name'),
        func.coalesce(func.sum(OrderItem.quantity), 0).label('total_sold'),
    ).join(OrderItem, OrderItem.product_id == Product.id) \
     .join(Order, Order.id == OrderItem.order_id) \
     .outerjoin(ProductVariant, ProductVariant.id == OrderItem.variant_id) \
     .outerjoin(Store, Store.id == Product.store_id) \
     .outerjoin(Category, Category.id == Product.main_category_id) \
     .filter(
        Order.status.in_(['delivered', 'completed']),
        Order.created_at >= range_start,
        Order.created_at < range_end,
     ) \
     .group_by(Product.id, Product.name, ProductVariant.id, ProductVariant.name, Store.name, Category.name) \
     .order_by(func.sum(OrderItem.quantity).desc()) \
     .limit(5).all()

    top_products = [{
        'id': r.id,
        'name': f"{r.name} — {r.variant_name}" if r.variant_name else r.name,
        'store_name': r.store_name or '—',
        'category': r.category_name or 'General',
        'total_sold': int(r.total_sold or 0),
    } for r in top_products_query]

    # Recent orders: online (delivered/completed) + POS, merged and sorted
    online_recent_q = (Order.query
                       .filter(
                           Order.status.in_(['delivered', 'completed']),
                           Order.created_at >= range_start,
                           Order.created_at < range_end,
                       )
                       .order_by(Order.created_at.desc())
                       .limit(8).all())
    pos_recent_q = (POSOrder.query
                    .filter(
                        POSOrder.created_at >= range_start,
                        POSOrder.created_at < range_end,
                    )
                    .order_by(POSOrder.created_at.desc())
                    .limit(8).all())

    recent_orders_list = []
    for o in online_recent_q:
        cust_name = o.customer.full_name if o.customer else 'Walk-in'
        recent_orders_list.append({
            'id': o.id,
            'order_no': f"#{o.id:05d}",
            'customer_name': cust_name,
            'customer_initial': (cust_name[:1] or 'U').upper(),
            'store_name': o.store.name if getattr(o, 'store', None) else '—',
            'date': _fmt_pht(o.created_at) if o.created_at else '',
            'total': float(o.total_amount or 0),
            'status': o.status or 'pending',
            'type': 'online',
        })
    for p in pos_recent_q:
        recent_orders_list.append({
            'id': p.id,
            'order_no': f"#POS-{p.id:04d}",
            'customer_name': p.customer_name or 'Walk-in',
            'customer_initial': ((p.customer_name or 'W')[0]).upper(),
            'store_name': p.store.name if getattr(p, 'store', None) else '—',
            'date': _fmt_pht(p.created_at) if p.created_at else '',
            'total': float(p.total_amount or 0),
            'status': 'completed',
            'type': 'pos',
        })
    recent_orders_list.sort(key=lambda x: x['date'], reverse=True)
    recent_orders_list = recent_orders_list[:8]

    # Chart data: matches selected period range
    def _admin_build_chart(ds_start, ds_end):
        d_online = db.session.query(
            func.date(Order.created_at).label('day'),
            func.coalesce(func.sum(Order.total_amount), 0).label('revenue'),
            func.count(Order.id).label('order_count'),
        ).filter(
            Order.status.in_(['delivered', 'completed']),
            Order.created_at >= ds_start,
            Order.created_at < ds_end,
        ).group_by(func.date(Order.created_at)).all()

        d_pos = db.session.query(
            func.date(POSOrder.created_at).label('day'),
            func.coalesce(func.sum(POSOrder.total_amount), 0).label('revenue'),
            func.count(POSOrder.id).label('order_count'),
        ).filter(
            POSOrder.created_at >= ds_start,
            POSOrder.created_at < ds_end,
        ).group_by(func.date(POSOrder.created_at)).all()

        o_map = {row.day: (float(row.revenue or 0), int(row.order_count or 0)) for row in d_online}
        p_map = {row.day: (float(row.revenue or 0), int(row.order_count or 0)) for row in d_pos}
        days = max(1, (ds_end.date() - ds_start.date()).days)
        labels, revenues, order_counts = [], [], []
        for i in range(days):
            day_val = ds_start.date() + timedelta(days=i)
            o_rev, o_cnt = o_map.get(day_val, (0.0, 0))
            p_rev, p_cnt = p_map.get(day_val, (0.0, 0))
            labels.append(day_val.strftime('%b %d'))
            revenues.append(o_rev + p_rev)
            order_counts.append(o_cnt + p_cnt)
        return {'labels': labels, 'revenue': revenues, 'orders': order_counts}

    chart_data = _admin_build_chart(range_start, range_end)

    total_stores = db.session.query(func.count(Store.id)).scalar() or 0
    active_stores = db.session.query(func.count(Store.id)).filter(Store.status == 'active').scalar() or 0
    pending_stores = db.session.query(func.count(Store.id)).filter(Store.status == 'pending').scalar() or 0

    total_users = db.session.query(func.count(User.id)).scalar() or 0
    total_riders = db.session.query(func.count(Rider.id)).scalar() or 0
    active_riders = db.session.query(func.count(Rider.id)).filter(Rider.is_active.is_(True)).scalar() or 0
    pending_orders = Order.query.filter(
        Order.status.in_(['pending', 'preparing', 'accepted']),
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).count()

    avg_rating_row = db.session.query(
        func.coalesce(func.avg(ProductRating.rating), 0),
        func.count(ProductRating.id),
    ).first()
    avg_rating = round(float(avg_rating_row[0]), 1) if avg_rating_row else 0
    total_reviews = int(avg_rating_row[1]) if avg_rating_row else 0

    return render_template(
        'dashboard.html',
        is_admin=True,
        period=period,
        period_label=period_label,
        custom_from=custom_from,
        custom_to=custom_to,
        revenue_this_month=float(revenue_this_month),
        revenue_change=revenue_change,
        orders_this_month=orders_this_month,
        orders_change=orders_change,
        customers_this_month=customers_this_month,
        customers_change=customers_change,
        delivery_rate=delivery_rate,
        top_products=top_products,
        recent_orders=recent_orders_list,
        chart_data=chart_data,
        avg_rating=avg_rating,
        total_reviews=total_reviews,
        total_stores=total_stores,
        active_stores=active_stores,
        pending_stores=pending_stores,
        total_users=total_users,
        total_riders=total_riders,
        active_riders=active_riders,
        pending_orders=pending_orders,
    )


@templates_bp.route('/seller/dashboard')
def seller_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('templates.login'))
    if session.get('role') != 'seller':
        return redirect(url_for('templates.dashboard'))

    from sqlalchemy import func, case, extract
    from datetime import date, timedelta
    from app.utils.report_service import period_range

    user_id = session['user_id']
    store = _seller_portal_manageable_store(user_id)

    if not store:
        suspended = _seller_portal_suspended_store(user_id)
        if suspended:
            return redirect(url_for('templates.seller_store_suspended'))
        pend_app = SellerApplication.query.filter_by(
            user_id=user_id, status='pending'
        ).order_by(SellerApplication.submitted_at.desc()).first()
        if pend_app:
            return redirect(url_for('templates.seller_signup_status'))
        return redirect(url_for('templates.seller_signup_complete'))

    period = (request.args.get('period') or 'month').lower().strip()
    custom_from = request.args.get('from')
    custom_to = request.args.get('to')
    range_start, range_end, period_label = period_range(period, custom_from, custom_to)
    prev_start = range_start - (range_end - range_start)
    prev_end = range_start
    today = date.today()



    # ── KPI: Revenue this month (delivered orders) ──
    online_revenue_this = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(
        Order.store_id == store.id,
        Order.status.in_(['delivered', 'completed']),
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).scalar() or 0
    pos_revenue_this = db.session.query(
        func.coalesce(func.sum(POSOrder.total_amount), 0)
    ).filter(
        POSOrder.store_id == store.id,
        POSOrder.created_at >= range_start,
        POSOrder.created_at < range_end,
    ).scalar() or 0
    revenue_this_month = float(online_revenue_this) + float(pos_revenue_this)

    online_revenue_prev = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(
        Order.store_id == store.id,
        Order.status.in_(['delivered', 'completed']),
        Order.created_at >= prev_start,
        Order.created_at < prev_end,
    ).scalar() or 0
    pos_revenue_prev = db.session.query(
        func.coalesce(func.sum(POSOrder.total_amount), 0)
    ).filter(
        POSOrder.store_id == store.id,
        POSOrder.created_at >= prev_start,
        POSOrder.created_at < prev_end,
    ).scalar() or 0
    revenue_prev_month = float(online_revenue_prev) + float(pos_revenue_prev)

    revenue_change = 0
    if revenue_prev_month and float(revenue_prev_month) > 0:
        revenue_change = round(((float(revenue_this_month) - float(revenue_prev_month)) / float(revenue_prev_month)) * 100, 1)

    # ── KPI: Total orders (ALL online statuses + all POS) ──
    orders_this_month = Order.query.filter(
        Order.store_id == store.id,
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).count()
    orders_this_month += POSOrder.query.filter(
        POSOrder.store_id == store.id,
        POSOrder.created_at >= range_start,
        POSOrder.created_at < range_end,
    ).count()

    orders_prev_month = Order.query.filter(
        Order.store_id == store.id,
        Order.created_at >= prev_start,
        Order.created_at < prev_end,
    ).count()
    orders_prev_month += POSOrder.query.filter(
        POSOrder.store_id == store.id,
        POSOrder.created_at >= prev_start,
        POSOrder.created_at < prev_end,
    ).count()

    orders_change = 0
    if orders_prev_month > 0:
        orders_change = round(((orders_this_month - orders_prev_month) / orders_prev_month) * 100, 1)

    # ── KPI: Unique customers (delivered/completed orders only) ──
    customers_this_month = db.session.query(
        func.count(func.distinct(Order.customer_id))
    ).filter(
        Order.store_id == store.id,
        Order.status.in_(['delivered', 'completed']),
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).scalar() or 0

    customers_prev_month = db.session.query(
        func.count(func.distinct(Order.customer_id))
    ).filter(
        Order.store_id == store.id,
        Order.status.in_(['delivered', 'completed']),
        Order.created_at >= prev_start,
        Order.created_at < prev_end,
    ).scalar() or 0

    customers_change = 0
    if customers_prev_month > 0:
        customers_change = round(((customers_this_month - customers_prev_month) / customers_prev_month) * 100, 1)

    # ── KPI: Delivery rate (delivered+completed / delivered+completed+cancelled) ──
    total_resolved = Order.query.filter(
        Order.store_id == store.id,
        Order.status.in_(['delivered', 'completed', 'cancelled']),
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).count()

    delivered_this_month = Order.query.filter(
        Order.store_id == store.id,
        Order.status.in_(['delivered', 'completed']),
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).count()

    delivery_rate = round((delivered_this_month / total_resolved * 100), 1) if total_resolved > 0 else 100.0

    # ── Top products (online + POS, variant-level) ──
    online_top = db.session.query(
        Product.id,
        Product.name,
        ProductVariant.id.label('variant_id'),
        ProductVariant.name.label('variant_name'),
        Category.name.label('category_name'),
        func.coalesce(func.sum(OrderItem.quantity), 0).label('total_sold'),
    ).join(OrderItem, OrderItem.product_id == Product.id) \
     .join(Order, Order.id == OrderItem.order_id) \
     .outerjoin(ProductVariant, ProductVariant.id == OrderItem.variant_id) \
     .outerjoin(Category, Category.id == Product.main_category_id) \
     .filter(
        Product.store_id == store.id,
        Order.status.in_(['delivered', 'completed']),
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).group_by(Product.id, Product.name, ProductVariant.id, ProductVariant.name, Category.name).all()

    pos_top = db.session.query(
        Product.id,
        Product.name,
        ProductVariant.id.label('variant_id'),
        ProductVariant.name.label('variant_name'),
        Category.name.label('category_name'),
        func.coalesce(func.sum(POSOrderItem.quantity), 0).label('total_sold'),
    ).join(POSOrderItem, POSOrderItem.product_id == Product.id) \
     .join(POSOrder, POSOrder.id == POSOrderItem.pos_order_id) \
     .outerjoin(ProductVariant, ProductVariant.id == POSOrderItem.variant_id) \
     .outerjoin(Category, Category.id == Product.main_category_id) \
     .filter(
        Product.store_id == store.id,
        POSOrder.created_at >= range_start,
        POSOrder.created_at < range_end,
    ).group_by(Product.id, Product.name, ProductVariant.id, ProductVariant.name, Category.name).all()

    from collections import defaultdict
    tp_map = defaultdict(lambda: {'total_sold': 0, 'category': 'General', 'variant_name': None})
    for r in online_top:
        key = (r.id, r.variant_id)
        tp_map[key]['name'] = r.name
        tp_map[key]['variant_name'] = r.variant_name
        tp_map[key]['category'] = r.category_name or 'General'
        tp_map[key]['total_sold'] += int(r.total_sold or 0)
    for r in pos_top:
        key = (r.id, r.variant_id)
        tp_map[key]['name'] = r.name
        tp_map[key]['variant_name'] = r.variant_name
        tp_map[key]['category'] = r.category_name or 'General'
        tp_map[key]['total_sold'] += int(r.total_sold or 0)

    top_products = sorted(tp_map.values(), key=lambda x: x['total_sold'], reverse=True)[:5]
    for tp in top_products:
        if tp['variant_name']:
            tp['name'] = f"{tp['name']} — {tp['variant_name']}"
        del tp['variant_name']

    # ── Recent orders (online + POS, last 10 combined) ──
    online_recent = Order.query.filter(
        Order.store_id == store.id,
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).order_by(Order.created_at.desc()).limit(10).all()

    pos_recent = POSOrder.query.filter(
        POSOrder.store_id == store.id,
        POSOrder.created_at >= range_start,
        POSOrder.created_at < range_end,
    ).order_by(POSOrder.created_at.desc()).limit(10).all()

    recent_orders_list = []
    for o in online_recent:
        recent_orders_list.append({
            'id': o.id,
            'customer_name': o.customer.full_name if o.customer else 'Unknown',
            'customer_initial': (o.customer.full_name[0] if o.customer and o.customer.full_name else 'U'),
            'date': _fmt_pht(o.created_at) if o.created_at else '',
            'total': float(o.total_amount or 0),
            'status': o.status,
            'type': 'online',
        })
    for p in pos_recent:
        recent_orders_list.append({
            'id': p.id,
            'customer_name': p.customer_name or 'Walk-in',
            'customer_initial': ((p.customer_name or 'W')[0]).upper(),
            'date': _fmt_pht(p.created_at) if p.created_at else '',
            'total': float(p.total_amount or 0),
            'status': 'completed',
            'type': 'pos',
        })
    recent_orders_list.sort(key=lambda x: x['date'], reverse=True)
    recent_orders_list = recent_orders_list[:10]

    # ── Revenue chart data (matches selected period range) ──
    def _build_chart_dataset(store_id, ds_start, ds_end):
        online_daily = db.session.query(
            func.date(Order.created_at).label('day'),
            func.coalesce(func.sum(Order.total_amount), 0).label('revenue'),
            func.count(Order.id).label('order_count')
        ).filter(
            Order.store_id == store_id,
            Order.status.in_(['delivered', 'completed']),
            Order.created_at >= ds_start,
            Order.created_at < ds_end,
        ).group_by(func.date(Order.created_at)).all()

        pos_daily = db.session.query(
            func.date(POSOrder.created_at).label('day'),
            func.coalesce(func.sum(POSOrder.total_amount), 0).label('revenue'),
            func.count(POSOrder.id).label('order_count')
        ).filter(
            POSOrder.store_id == store_id,
            POSOrder.created_at >= ds_start,
            POSOrder.created_at < ds_end,
        ).group_by(func.date(POSOrder.created_at)).all()

        o_map = {row.day: (float(row.revenue or 0), int(row.order_count or 0)) for row in online_daily}
        p_map = {row.day: (float(row.revenue or 0), int(row.order_count or 0)) for row in pos_daily}

        days = max(1, (ds_end.date() - ds_start.date()).days)
        labels, rev, o_rev, p_rev, cnt, o_cnt, p_cnt = [], [], [], [], [], [], []
        for i in range(days):
            d = ds_start.date() + timedelta(days=i)
            labels.append(d.strftime('%b %d'))
            or_v, oc = o_map.get(d, (0.0, 0))
            pr_v, pc = p_map.get(d, (0.0, 0))
            o_rev.append(or_v); p_rev.append(pr_v); rev.append(or_v + pr_v)
            o_cnt.append(oc); p_cnt.append(pc); cnt.append(oc + pc)
        return {
            'labels': labels, 'revenue': rev,
            'online_revenue': o_rev, 'pos_revenue': p_rev,
            'orders': cnt, 'online_orders': o_cnt, 'pos_orders': p_cnt,
        }

    chart_data = _build_chart_dataset(store.id, range_start, range_end)

    # ── Performance metrics ──
    avg_rating_row = db.session.query(
        func.coalesce(func.avg(ProductRating.rating), 0),
        func.count(ProductRating.id)
    ).join(Product, Product.id == ProductRating.product_id) \
     .filter(Product.store_id == store.id).first()

    avg_rating = round(float(avg_rating_row[0]), 1) if avg_rating_row else 0
    total_reviews = int(avg_rating_row[1]) if avg_rating_row else 0

    store_avg_row = db.session.query(
        func.coalesce(func.avg(StoreRating.rating), 0),
        func.count(StoreRating.id),
    ).filter(StoreRating.store_id == store.id).first()
    store_avg_rating = round(float(store_avg_row[0]), 1) if store_avg_row else 0
    store_total_reviews = int(store_avg_row[1]) if store_avg_row else 0

    # Products count & low stock
    total_products = Product.query.filter_by(store_id=store.id, is_archived=False).count()
    low_stock_products = Product.query.filter(
        Product.store_id == store.id,
        Product.is_archived == False,
        Product.stock_quantity <= 5,
        Product.stock_quantity > 0
    ).all()

    out_of_stock = Product.query.filter(
        Product.store_id == store.id,
        Product.is_archived == False,
        Product.stock_quantity == 0
    ).count()

    # Active riders
    active_riders = Rider.query.filter_by(store_id=store.id, is_active=True).count()
    total_riders = Rider.query.filter_by(store_id=store.id).count()

    # Pending orders count
    pending_orders = Order.query.filter(
        Order.store_id == store.id,
        Order.status.in_(['pending', 'preparing', 'accepted']),
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).count()

    # POS revenue today
    pos_revenue_today = db.session.query(
        func.coalesce(func.sum(POSOrder.total_amount), 0)
    ).filter(
        POSOrder.store_id == store.id,
        func.date(POSOrder.created_at) == today
    ).scalar()

    pos_orders_today = POSOrder.query.filter(
        POSOrder.store_id == store.id,
        func.date(POSOrder.created_at) == today
    ).count()

    # ── Analytics: Order status distribution (selected range) ──
    status_dist_query = db.session.query(
        Order.status, func.count(Order.id)
    ).filter(
        Order.store_id == store.id,
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).group_by(Order.status).all()
    order_status_dist = {row[0]: row[1] for row in status_dist_query}

    # ── Analytics: Revenue by payment method (delivered/completed) ──
    payment_method_query = db.session.query(
        Order.payment_method,
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(
        Order.store_id == store.id,
        Order.status.in_(['delivered', 'completed']),
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).group_by(Order.payment_method).all()
    revenue_by_payment = {row[0] or 'unknown': float(row[1]) for row in payment_method_query}

    # ── Analytics: Sales by category (selected range, ONLINE + POS) ──
    online_category_sales_query = db.session.query(
        Category.name,
        func.coalesce(func.sum(OrderItem.quantity), 0).label('qty'),
        func.coalesce(func.sum(OrderItem.price * OrderItem.quantity), 0).label('rev')
    ).join(Product, Product.id == OrderItem.product_id) \
     .outerjoin(Category, Category.id == Product.main_category_id) \
     .join(Order, Order.id == OrderItem.order_id) \
     .filter(
        Product.store_id == store.id,
        Order.status.in_(['delivered', 'completed']),
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).group_by(Category.name).all()

    pos_category_sales_query = db.session.query(
        Category.name,
        func.coalesce(func.sum(POSOrderItem.quantity), 0).label('qty'),
        func.coalesce(func.sum(POSOrderItem.price * POSOrderItem.quantity), 0).label('rev')
    ).join(Product, Product.id == POSOrderItem.product_id) \
     .outerjoin(Category, Category.id == Product.main_category_id) \
     .join(POSOrder, POSOrder.id == POSOrderItem.pos_order_id) \
     .filter(
        Product.store_id == store.id,
        POSOrder.created_at >= range_start,
        POSOrder.created_at < range_end,
    ).group_by(Category.name).all()

    category_breakdown = {}

    for cat_name, qty, rev in online_category_sales_query:
        key = cat_name or 'Uncategorized'
        category_breakdown.setdefault(key, {
            'name': key,
            'online_qty': 0,
            'online_revenue': 0.0,
            'pos_qty': 0,
            'pos_revenue': 0.0,
        })
        category_breakdown[key]['online_qty'] += int(qty or 0)
        category_breakdown[key]['online_revenue'] += float(rev or 0)

    for cat_name, qty, rev in pos_category_sales_query:
        key = cat_name or 'Uncategorized'
        category_breakdown.setdefault(key, {
            'name': key,
            'online_qty': 0,
            'online_revenue': 0.0,
            'pos_qty': 0,
            'pos_revenue': 0.0,
        })
        category_breakdown[key]['pos_qty'] += int(qty or 0)
        category_breakdown[key]['pos_revenue'] += float(rev or 0)

    sales_by_category = []
    for row in category_breakdown.values():
        total_qty = row['online_qty'] + row['pos_qty']
        total_revenue = row['online_revenue'] + row['pos_revenue']
        row['qty'] = total_qty
        row['revenue'] = total_revenue
        sales_by_category.append(row)

    sales_by_category.sort(key=lambda x: (x['qty'], x['revenue']), reverse=True)
    sales_by_category = sales_by_category[:8]

    # ── Analytics: POS vs Online revenue (selected range) ──
    range_days = max(1, (range_end.date() - range_start.date()).days)
    pos_vs_online = {'labels': [], 'online': [], 'pos': []}
    for i in range(range_days):
        d = range_start.date() + timedelta(days=i)
        lbl = d.strftime('%b %d')
        online_rev = db.session.query(
            func.coalesce(func.sum(Order.total_amount), 0)
        ).filter(
            Order.store_id == store.id,
            Order.status.in_(['delivered', 'completed']),
            func.date(Order.created_at) == d
        ).scalar()
        pos_rev = db.session.query(
            func.coalesce(func.sum(POSOrder.total_amount), 0)
        ).filter(
            POSOrder.store_id == store.id,
            func.date(POSOrder.created_at) == d
        ).scalar()
        pos_vs_online['labels'].append(lbl)
        pos_vs_online['online'].append(float(online_rev))
        pos_vs_online['pos'].append(float(pos_rev))

    # ── Analytics: Rating distribution (1-5 stars, selected range) ──
    rating_dist_query = db.session.query(
        ProductRating.rating, func.count(ProductRating.id)
    ).join(Product, Product.id == ProductRating.product_id) \
     .filter(
        Product.store_id == store.id,
        ProductRating.created_at >= range_start,
        ProductRating.created_at < range_end,
     ) \
     .group_by(ProductRating.rating).all()
    rating_distribution = {int(r[0]): r[1] for r in rating_dist_query}

    store_rating_dist_query = db.session.query(
        StoreRating.rating, func.count(StoreRating.id)
    ).filter(
        StoreRating.store_id == store.id,
        StoreRating.created_at >= range_start,
        StoreRating.created_at < range_end,
    ).group_by(StoreRating.rating).all()
    store_rating_distribution = {int(r[0]): r[1] for r in store_rating_dist_query}

    # ── Analytics: Hourly order distribution (selected range) ──
    hourly_query = db.session.query(
        extract('hour', Order.created_at).label('hr'),
        func.count(Order.id)
    ).filter(
        Order.store_id == store.id,
        Order.status.in_(['delivered', 'completed']),
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).group_by(extract('hour', Order.created_at)).all()
    hourly_distribution = {int(r[0]): r[1] for r in hourly_query}

    # ── Analytics: Average order value trend (selected range) ──
    aov_query = db.session.query(
        func.date(Order.created_at).label('day'),
        func.avg(Order.total_amount).label('aov'),
        func.count(Order.id).label('cnt')
    ).filter(
        Order.store_id == store.id,
        Order.status.in_(['delivered', 'completed']),
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).group_by(func.date(Order.created_at)) \
     .order_by(func.date(Order.created_at)).all()
    aov_trend = {
        'labels': [],
        'values': [],
        'counts': []
    }
    for row in aov_query:
        day_val = row.day
        aov_trend['labels'].append(day_val.strftime('%b %d') if not isinstance(day_val, str) else day_val)
        aov_trend['values'].append(round(float(row.aov), 2))
        aov_trend['counts'].append(int(row.cnt))

    # ── Analytics: Customer retention (repeat vs new, selected range) ──
    all_customers = db.session.query(
        Order.customer_id,
        func.count(Order.id).label('order_count')
    ).filter(
        Order.store_id == store.id,
        Order.status.in_(['delivered', 'completed']),
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).group_by(Order.customer_id).all()

    new_customers = 0
    repeat_customers = 0
    for cust in all_customers:
        if cust.order_count > 1:
            repeat_customers += 1
        else:
            new_customers += 1
    total_unique_customers = len(all_customers)

    return render_template('seller_dashboard.html',
        store=store,
        period=period,
        period_label=period_label,
        custom_from=custom_from,
        custom_to=custom_to,
        revenue_this_month=float(revenue_this_month),
        revenue_change=revenue_change,
        orders_this_month=orders_this_month,
        orders_change=orders_change,
        customers_this_month=customers_this_month,
        customers_change=customers_change,
        delivery_rate=delivery_rate,
        top_products=top_products,
        recent_orders=recent_orders_list,
        chart_data=chart_data,
        avg_rating=avg_rating,
        total_reviews=total_reviews,
        store_avg_rating=store_avg_rating,
        store_total_reviews=store_total_reviews,
        total_products=total_products,
        low_stock_products=[p.to_dict() for p in low_stock_products],
        out_of_stock=out_of_stock,
        active_riders=active_riders,
        total_riders=total_riders,
        pending_orders=pending_orders,
        pos_revenue_today=float(pos_revenue_today),
        pos_orders_today=pos_orders_today,
        order_status_dist=order_status_dist,
        revenue_by_payment=revenue_by_payment,
        sales_by_category=sales_by_category,
        pos_vs_online=pos_vs_online,
        rating_distribution=rating_distribution,
        store_rating_distribution=store_rating_distribution,
        hourly_distribution=hourly_distribution,
        aov_trend=aov_trend,
        new_customers=new_customers,
        repeat_customers=repeat_customers,
        total_unique_customers=total_unique_customers,
    )

@templates_bp.route('/admin/users')
def admin_users():
    if session.get('role') != 'admin':
        return redirect(url_for('templates.dashboard'))
    return render_template('admin_users.html')

@templates_bp.route('/api/admin/users/list')
def api_admin_users_list():
    """List all users for admin user management tab."""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401

    users = User.query.order_by(User.created_at.desc()).all()
    payload = []

    for user in users:
        user_data = user.to_dict()
        user_data['store_count'] = Store.query.filter_by(seller_id=user.id).count()
        user_data['order_count'] = Order.query.filter_by(customer_id=user.id).count()
        payload.append(user_data)

    stats = {
        'total': len(payload),
        'active': sum(1 for u in payload if (u.get('status') or '').lower() == 'active'),
        'banned': sum(1 for u in payload if (u.get('status') or '').lower() == 'banned'),
        'deleted': sum(1 for u in payload if (u.get('status') or '').lower() == 'deleted'),
    }
    stats['inactive'] = max(0, stats['total'] - (stats['active'] + stats['banned'] + stats['deleted']))

    return jsonify({'users': payload, 'stats': stats}), 200


@templates_bp.route('/api/admin/users/<int:user_id>/details')
def api_admin_user_details(user_id):
    """Get full user details for admin modal."""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401

    user = User.query.get_or_404(user_id)
    stores = Store.query.filter_by(seller_id=user.id).all()

    return jsonify({
        'user': user.to_dict(),
        'meta': {
            'store_count': len(stores),
            'active_store_count': sum(1 for s in stores if s.status == 'active'),
            'order_count': Order.query.filter_by(customer_id=user.id).count(),
            'latest_store': stores[0].name if stores else None
        }
    }), 200


@templates_bp.route('/api/admin/users/<int:user_id>/ban', methods=['POST'])
def api_admin_user_ban(user_id):
    """Ban a user account with reason and optional duration."""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401

    if not _ensure_account_bans_table():
        return jsonify({'error': 'Unable to initialize ban records table'}), 500

    if session.get('user_id') == user_id:
        return jsonify({'error': 'You cannot ban your own account'}), 400

    user = User.query.get_or_404(user_id)
    if user.role == 'admin':
        return jsonify({'error': 'Admin accounts cannot be banned from this page'}), 400

    data = request.get_json() or {}
    reason = (data.get('reason') or '').strip()
    duration_value = data.get('duration_value')
    duration_unit = (data.get('duration_unit') or '').strip().lower()

    if not reason:
        return jsonify({'error': 'Ban reason is required'}), 400

    banned_until = None
    if duration_unit != 'permanent':
        try:
            duration_value = int(duration_value)
        except (TypeError, ValueError):
            return jsonify({'error': 'Duration must be a valid number'}), 400

        if duration_value <= 0:
            return jsonify({'error': 'Duration must be greater than zero'}), 400

        if duration_unit == 'hours':
            banned_until = datetime.utcnow() + timedelta(hours=duration_value)
        elif duration_unit == 'days':
            banned_until = datetime.utcnow() + timedelta(days=duration_value)
        elif duration_unit == 'weeks':
            banned_until = datetime.utcnow() + timedelta(weeks=duration_value)
        elif duration_unit == 'months':
            banned_until = datetime.utcnow() + timedelta(days=duration_value * 30)
        else:
            return jsonify({'error': 'Invalid duration unit'}), 400

    # Deactivate older active bans for this user.
    existing_bans = AccountBan.query.filter_by(user_id=user.id, is_active=True).all()
    for existing in existing_bans:
        existing.is_active = False
        existing.lifted_at = datetime.utcnow()
        existing.lifted_by = session.get('user_id')

    ban = AccountBan(
        user_id=user.id,
        reason=reason,
        banned_until=banned_until,
        is_active=True,
        banned_by=session.get('user_id')
    )

    user.status = 'banned'
    user.updated_at = datetime.utcnow()

    if user.role == 'seller':
        seller_store = Store.query.filter_by(seller_id=user.id).all()
        for store in seller_store:
            store.status = 'inactive'
            store.updated_at = datetime.utcnow()

    db.session.add(ban)
    db.session.commit()
    return jsonify({'success': True, 'message': 'User banned successfully'}), 200


@templates_bp.route('/api/admin/users/bans')
def api_admin_user_bans():
    """List active account bans for admin table."""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401

    if not _ensure_account_bans_table():
        return jsonify({'error': 'Unable to initialize ban records table'}), 500

    now = datetime.utcnow()
    expired = AccountBan.query.filter(
        AccountBan.is_active == True,
        AccountBan.banned_until.isnot(None),
        AccountBan.banned_until <= now
    ).all()
    for ban in expired:
        ban.is_active = False
        ban.lifted_at = now
        ban.lifted_by = session.get('user_id')
        if ban.user and (ban.user.status or '').lower() == 'banned':
            ban.user.status = 'active'
            ban.user.updated_at = now
    if expired:
        db.session.commit()

    bans = AccountBan.query.filter_by(is_active=True).order_by(AccountBan.created_at.desc()).all()
    payload = []
    for ban in bans:
        item = ban.to_dict()
        item['user_name'] = ban.user.full_name if ban.user else 'Unknown user'
        item['user_email'] = ban.user.email if ban.user else None
        item['banned_by_name'] = ban.banned_by_user.full_name if ban.banned_by_user else 'Admin'
        payload.append(item)

    return jsonify({'bans': payload}), 200


@templates_bp.route('/api/admin/users/<int:user_id>/unban', methods=['POST'])
def api_admin_user_unban(user_id):
    """Lift a user's active account ban."""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401

    if not _ensure_account_bans_table():
        return jsonify({'error': 'Unable to initialize ban records table'}), 500

    user = User.query.get_or_404(user_id)
    active_bans = AccountBan.query.filter_by(user_id=user.id, is_active=True).all()
    if not active_bans:
        return jsonify({'error': 'No active ban found for this user'}), 404

    now = datetime.utcnow()
    for ban in active_bans:
        ban.is_active = False
        ban.lifted_at = now
        ban.lifted_by = session.get('user_id')

    user.status = 'active'
    user.updated_at = now
    db.session.commit()
    return jsonify({'success': True, 'message': 'User has been unbanned'}), 200


@templates_bp.route('/api/admin/users/<int:user_id>/delete', methods=['DELETE'])
def api_admin_user_delete(user_id):
    """Delete a user when safe; fallback to soft-delete."""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401

    if session.get('user_id') == user_id:
        return jsonify({'error': 'You cannot delete your own account'}), 400

    user = User.query.get_or_404(user_id)
    if user.role == 'admin':
        return jsonify({'error': 'Admin accounts cannot be deleted from this page'}), 400

    # Always disable seller stores before delete/soft-delete.
    if user.role == 'seller':
        seller_store = Store.query.filter_by(seller_id=user.id).all()
        for store in seller_store:
            store.status = 'inactive'
            store.updated_at = datetime.utcnow()

    try:
        db.session.delete(user)
        db.session.commit()
        return jsonify({'success': True, 'message': 'User deleted permanently'}), 200
    except IntegrityError:
        db.session.rollback()
        # Keep relations intact, but lock the account as deleted.
        user.status = 'deleted'
        user.updated_at = datetime.utcnow()
        user.email = f"deleted_{user.id}_{int(time.time())}@deleted.local"
        user.full_name = f"Deleted User #{user.id}"
        user.phone = None
        user.role = 'customer'
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'User had linked records, so account was soft-deleted instead'
        }), 200
    except Exception as ex:
        db.session.rollback()
        return jsonify({'error': f'Failed to delete user: {str(ex)}'}), 500

@templates_bp.route('/api/admin/seller-applications')
def get_seller_applications():
    """Get all seller applications with user details"""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    applications = SellerApplication.query.order_by(SellerApplication.submitted_at.desc()).all()
    
    result = []
    for app in applications:
        app_dict = app.to_dict()
        # Add user details
        user = User.query.get(app.user_id)
        if user:
            app_dict['full_name'] = user.full_name
            app_dict['email'] = user.email
            app_dict['phone'] = user.phone
        result.append(app_dict)
    
    return jsonify({'applications': result})



@templates_bp.route('/api/admin/seller-applications/<int:app_id>/approve', methods=['POST'])
def approve_seller_application(app_id):
    """Approve a seller application and convert user to seller"""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        application = SellerApplication.query.get_or_404(app_id)
        user = User.query.get(application.user_id)

        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Update application status
        application.status = 'approved'
        application.reviewed_at = datetime.utcnow()
        application.reviewed_by = session['user_id']

        # Convert user role to seller
        user.role = 'seller'

        # ── KEY FIX: Check if seller already has a store (re-approval case) ──
        existing_store = Store.query.filter_by(seller_id=user.id).first()

        if existing_store:
            # Reactivate the existing store — keeps all products intact
            existing_store.status = 'active'
            existing_store.name = application.store_name
            existing_store.description = application.store_description
            existing_store.seller_application_id = application.id
            print(f"♻️ Reactivated existing store ID {existing_store.id} for user {user.id}")
        else:
            # First-time approval — create a new store
            store = Store(
                seller_id=user.id,
                name=application.store_name,
                description=application.store_description,
                address='Address pending - please update',
                status='active',
                seller_application_id=application.id
            )
            db.session.add(store)
            print(f"🆕 Created new store for user {user.id}")

        # Create approval notification
        notification = Notification(
            user_id=application.user_id,
            title='Seller Application Approved',
            message=f'Congratulations! Your seller application for "{application.store_name}" has been approved. You can now start selling!',
            type='seller_app_approved',
            reference_id=application.id
        )
        db.session.add(notification)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Application approved and seller account activated'
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error approving application: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/admin/seller-applications/<int:app_id>/reject', methods=['POST'])
def reject_seller_application(app_id):
    """Reject a seller application — deactivates store but preserves products"""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json()
        application = SellerApplication.query.get_or_404(app_id)

        application.status = 'rejected'
        application.admin_notes = data.get('admin_notes', '')
        application.rejection_details = data.get('rejection_details')
        application.reviewed_at = datetime.utcnow()
        application.reviewed_by = session['user_id']

        # ── KEY FIX: Deactivate store instead of ignoring it ──
        # This hides their products from public without deleting anything
        user = User.query.get(application.user_id)
        if user:
            src = application.application_source or 'customer_account'
            if src != 'seller_portal':
                user.role = 'customer'
            existing_store = Store.query.filter_by(seller_id=user.id).first()
            if existing_store:
                existing_store.status = 'inactive'
                print(f"🔒 Deactivated store ID {existing_store.id} for rejected user {user.id}")

        # Create notification for the applicant
        rejection_details = data.get('rejection_details', {})
        rejected_items = [k.replace('_', ' ').title() for k, v in rejection_details.items() if isinstance(v, dict) and v.get('rejected')]
        message = f'Your seller application for "{application.store_name}" was rejected.'
        if rejected_items:
            message += f' Issues: {", ".join(rejected_items)}.'
        message += ' Please review and resubmit.'

        notification = Notification(
            user_id=application.user_id,
            title='Seller Application Rejected',
            message=message,
            type='seller_app_rejected',
            reference_id=application.id
        )
        db.session.add(notification)

        db.session.commit()

        return jsonify({'success': True, 'message': 'Application rejected'})

    except Exception as e:
        db.session.rollback()
        print(f"Error rejecting application: {str(e)}")
        return jsonify({'error': str(e)}), 500

@templates_bp.route('/admin/stores')
def admin_stores():
    if session.get('role') != 'admin':
        return redirect(url_for('templates.dashboard'))

    from sqlalchemy import func
    user_id = session.get('user_id')

    stores = (Store.query
              .order_by(Store.created_at.desc().nullslast(), Store.id.desc())
              .all())

    rows = []
    counts = {
        'total': Store.query.count(),
        'active': Store.query.filter(Store.status == 'active').count(),
        'pending': Store.query.filter(Store.status == 'pending').count(),
        'suspended': Store.query.filter(
            Store.status.in_(('suspended', 'inactive'))
        ).count(),
    }
    total_revenue = 0.0

    for s in stores:
        revenue = db.session.query(
            func.coalesce(func.sum(Order.total_amount), 0)
        ).filter(
            Order.store_id == s.id,
            Order.status == 'delivered'
        ).scalar() or 0
        revenue = float(revenue)

        order_count = db.session.query(func.count(Order.id)).filter(
            Order.store_id == s.id
        ).scalar() or 0

        product_count = db.session.query(func.count(Product.id)).filter(
            Product.store_id == s.id,
            Product.is_archived.is_(False)
        ).scalar() or 0

        owner_name = s.seller.full_name if s.seller else 'Unassigned'
        owner_email = s.seller.email if s.seller else ''
        raw_status = (s.status or 'pending').lower()
        # Normalize legacy "inactive" to suspended for the admin UI.
        status_key = 'suspended' if raw_status == 'inactive' else raw_status

        rows.append({
            'id': s.id,
            'name': s.name,
            'description': s.description or '',
            'logo_url': s.logo_url,
            'status': status_key,
            'owner_name': owner_name,
            'owner_email': owner_email,
            'product_count': int(product_count),
            'order_count': int(order_count),
            'revenue': revenue,
            'revenue_display': f"₱{revenue:,.2f}",
            'created_at': _fmt_pht(s.created_at, '%b %d, %Y') if s.created_at else '—',
        })

        total_revenue += revenue

    return render_template(
        'admin_stores.html',
        stores=rows,
        store_counts=counts,
        total_platform_revenue=total_revenue,
        total_platform_revenue_display=f"₱{total_revenue:,.2f}",
    )


@templates_bp.route('/admin/testimonials')
def admin_testimonials():
    if session.get('role') != 'admin':
        return redirect(url_for('templates.dashboard'))
    return render_template('admin_testimonials.html')


@templates_bp.route('/admin/support')
def admin_support():
    if session.get('role') != 'admin':
        return redirect(url_for('templates.dashboard'))
    return render_template('admin_support.html')


# ═════════════════════════════════════════════════════════════════════════════
# ADMIN STORES API
# ═════════════════════════════════════════════════════════════════════════════

def _store_summary_dict(store: 'Store') -> dict:
    """Serialize a Store row plus computed counters for the admin UI."""
    from sqlalchemy import func as sa_func
    revenue = db.session.query(
        sa_func.coalesce(sa_func.sum(Order.total_amount), 0)
    ).filter(
        Order.store_id == store.id,
        Order.status == 'delivered'
    ).scalar() or 0
    revenue = float(revenue)

    order_count = db.session.query(sa_func.count(Order.id)).filter(
        Order.store_id == store.id
    ).scalar() or 0

    product_count = db.session.query(sa_func.count(Product.id)).filter(
        Product.store_id == store.id,
        Product.is_archived.is_(False)
    ).scalar() or 0

    return {
        'id': store.id,
        'name': store.name,
        'description': store.description or '',
        'address': store.address or '',
        'contact_number': store.contact_number or '',
        'logo_url': store.logo_url,
        'status': (
            'suspended'
            if (store.status or '').lower() == 'inactive'
            else (store.status or 'pending').lower()
        ),
        'owner': {
            'id': store.seller.id if store.seller else None,
            'full_name': store.seller.full_name if store.seller else 'Unassigned',
            'email': store.seller.email if store.seller else '',
            'phone': getattr(store.seller, 'phone', None) if store.seller else None,
        } if store.seller else {'id': None, 'full_name': 'Unassigned', 'email': '', 'phone': None},
        'stats': {
            'product_count': int(product_count),
            'order_count': int(order_count),
            'revenue': revenue,
            'revenue_display': f"₱{revenue:,.2f}",
        },
        'created_at': _fmt_pht(store.created_at, '%Y-%m-%d %I:%M %p') if store.created_at else None,
        'updated_at': _fmt_pht(store.updated_at, '%Y-%m-%d %I:%M %p') if store.updated_at else None,
    }


@templates_bp.route('/api/v1/admin/stores', methods=['GET'])
def api_admin_stores_list():
    """List all stores with summary stats (admin only)."""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        stores = (Store.query
                  .order_by(Store.created_at.desc().nullslast(), Store.id.desc())
                  .all())
        return jsonify({'stores': [_store_summary_dict(s) for s in stores]})
    except Exception as ex:
        current_app.logger.exception('api_admin_stores_list: %s', ex)
        return jsonify({'stores': [], 'error': 'Could not load stores'}), 500


@templates_bp.route('/api/v1/admin/stores/<int:store_id>', methods=['GET'])
def api_admin_store_detail(store_id):
    """Return full details for one store (admin only)."""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    store = Store.query.get_or_404(store_id)
    return jsonify({'store': _store_summary_dict(store)})


@templates_bp.route('/api/v1/admin/stores/<int:store_id>', methods=['PUT'])
def api_admin_store_update(store_id):
    """Update store details (name, description, address, contact, status)."""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    store = Store.query.get_or_404(store_id)
    data = request.get_json(silent=True) or {}

    if 'name' in data:
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'error': 'Name cannot be empty'}), 400
        store.name = name
    if 'description' in data:
        store.description = (data.get('description') or '').strip() or None
    if 'address' in data:
        store.address = (data.get('address') or '').strip() or store.address
    if 'contact_number' in data:
        store.contact_number = (data.get('contact_number') or '').strip() or None
    if 'status' in data:
        new_status = (data.get('status') or '').strip().lower()
        if new_status in ('pending', 'active', 'suspended'):
            store.status = new_status

    try:
        db.session.commit()
        return jsonify({'success': True, 'store': _store_summary_dict(store)})
    except Exception as ex:
        db.session.rollback()
        current_app.logger.exception('api_admin_store_update: %s', ex)
        return jsonify({'error': 'Could not update store'}), 500


@templates_bp.route('/api/v1/admin/stores/<int:store_id>/status', methods=['PUT'])
def api_admin_store_status(store_id):
    """Quick status toggle (active / suspended / pending)."""
    user_id = session.get('user_id')
    session_role = (session.get('role') or '').strip().lower()
    user = User.query.get(user_id) if user_id else None
    db_role = (user.role or '').strip().lower() if user else ''

    if not user_id or (session_role != 'admin' and db_role != 'admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    # Self-heal stale/missing session role if DB confirms admin.
    if db_role == 'admin' and session_role != 'admin':
        session['role'] = 'admin'

    store = Store.query.get_or_404(store_id)
    data = request.get_json(silent=True) or {}
    new_status = (data.get('status') or '').strip().lower()
    # Accept legacy "inactive" from older rows / UIs as suspended.
    if new_status == 'inactive':
        new_status = 'suspended'
    if new_status not in ('pending', 'active', 'suspended'):
        return jsonify({'error': 'Invalid status. Use pending, active, or suspended.'}), 400

    store.status = new_status
    store.updated_at = datetime.utcnow()

    # When approving a storefront, ensure the seller account is active.
    if new_status == 'active' and store.seller and (store.seller.status or '').lower() != 'active':
        store.seller.status = 'active'

    try:
        db.session.commit()
        return jsonify({
            'success': True,
            'status': store.status,
            'store': _store_summary_dict(store),
        })
    except Exception as ex:
        db.session.rollback()
        current_app.logger.exception('api_admin_store_status: %s', ex)
        return jsonify({'error': 'Could not update status'}), 500


@templates_bp.route('/api/v1/admin/stores/<int:store_id>', methods=['DELETE'])
def api_admin_store_delete(store_id):
    """Delete a store. Refuses deletion if there are order references that
    cannot be safely removed; admin should suspend instead in that case.
    """
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    store = Store.query.get_or_404(store_id)

    has_orders = db.session.query(Order.id).filter(Order.store_id == store.id).first()
    if has_orders:
        return jsonify({
            'error': 'Cannot delete a store with existing orders. Suspend the store instead.'
        }), 400

    try:
        db.session.delete(store)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as ex:
        db.session.rollback()
        current_app.logger.exception('api_admin_store_delete: %s', ex)
        return jsonify({'error': 'Could not delete store'}), 500


@templates_bp.route('/api/admin/support-faqs', methods=['GET'])
def api_admin_support_faqs_list():
    """List all support FAQs (admin only)."""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        _ensure_support_faqs_table()
        rows = SupportFAQ.query.order_by(SupportFAQ.updated_at.desc(), SupportFAQ.id.desc()).all()
        return jsonify({'faqs': [r.to_dict() for r in rows]})
    except Exception as ex:
        db.session.rollback()
        current_app.logger.exception('api_admin_support_faqs_list: %s', ex)
        return jsonify({'faqs': [], 'error': 'Could not load FAQs'}), 500


@templates_bp.route('/api/admin/support-faqs', methods=['POST'])
def api_admin_support_faqs_create():
    """Create support FAQ entry (admin only)."""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip()
    answer = (data.get('answer') or '').strip()
    if len(question) < 5 or len(question) > 255:
        return jsonify({'error': 'Question must be between 5 and 255 characters.'}), 400
    if len(answer) < 5 or len(answer) > 5000:
        return jsonify({'error': 'Answer must be between 5 and 5000 characters.'}), 400
    try:
        if not _ensure_support_faqs_table():
            return jsonify({'error': 'Could not prepare support FAQ storage.'}), 503
        row = SupportFAQ(question=question, answer=answer, is_active=True)
        db.session.add(row)
        db.session.commit()
        return jsonify({'success': True, 'faq': row.to_dict()}), 201
    except Exception as ex:
        db.session.rollback()
        current_app.logger.exception('api_admin_support_faqs_create: %s', ex)
        return jsonify({'error': 'Could not create FAQ.'}), 500


@templates_bp.route('/api/admin/support-faqs/<int:faq_id>', methods=['PUT'])
def api_admin_support_faqs_update(faq_id):
    """Update support FAQ entry (admin only)."""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip()
    answer = (data.get('answer') or '').strip()
    is_active = data.get('is_active', True)
    if len(question) < 5 or len(question) > 255:
        return jsonify({'error': 'Question must be between 5 and 255 characters.'}), 400
    if len(answer) < 5 or len(answer) > 5000:
        return jsonify({'error': 'Answer must be between 5 and 5000 characters.'}), 400
    try:
        row = SupportFAQ.query.get(faq_id)
        if not row:
            return jsonify({'error': 'FAQ not found.'}), 404
        row.question = question
        row.answer = answer
        row.is_active = bool(is_active)
        db.session.commit()
        return jsonify({'success': True, 'faq': row.to_dict()})
    except Exception as ex:
        db.session.rollback()
        current_app.logger.exception('api_admin_support_faqs_update: %s', ex)
        return jsonify({'error': 'Could not update FAQ.'}), 500


@templates_bp.route('/api/admin/support-faqs/<int:faq_id>', methods=['DELETE'])
def api_admin_support_faqs_delete(faq_id):
    """Delete support FAQ entry (admin only)."""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        row = SupportFAQ.query.get(faq_id)
        if not row:
            return jsonify({'error': 'FAQ not found.'}), 404
        db.session.delete(row)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as ex:
        db.session.rollback()
        current_app.logger.exception('api_admin_support_faqs_delete: %s', ex)
        return jsonify({'error': 'Could not delete FAQ.'}), 500


@templates_bp.route('/api/support-faqs', methods=['GET'])
def api_support_faqs_public():
    """Expose active support FAQs for chat quick-help bot."""
    try:
        _ensure_support_faqs_table()
        rows = (
            SupportFAQ.query
            .filter_by(is_active=True)
            .order_by(SupportFAQ.updated_at.desc(), SupportFAQ.id.desc())
            .limit(50)
            .all()
        )
        return jsonify({'faqs': [r.to_dict() for r in rows]})
    except Exception as ex:
        db.session.rollback()
        current_app.logger.exception('api_support_faqs_public: %s', ex)
        return jsonify({'faqs': []}), 200


@templates_bp.route('/api/admin/home-testimonials')
def api_admin_home_testimonials_list():
    """List all public home-page testimonials (newest first)."""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        rows = HomePageTestimonial.query.order_by(HomePageTestimonial.created_at.desc()).all()
        return jsonify({'testimonials': [r.to_dict() for r in rows]})
    except Exception as ex:
        current_app.logger.warning('api_admin_home_testimonials_list: %s', ex)
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'testimonials': [], 'warning': 'Could not load testimonials (table missing or DB error).'})


@templates_bp.route('/api/admin/home-testimonials/<int:tid>', methods=['DELETE'])
def api_admin_home_testimonial_delete(tid):
    """Delete a single home-page testimonial."""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        row = HomePageTestimonial.query.get(tid)
        if not row:
            return jsonify({'error': 'Not found'}), 404
        db.session.delete(row)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as ex:
        db.session.rollback()
        current_app.logger.exception('api_admin_home_testimonial_delete: %s', ex)
        return jsonify({'error': 'Could not delete testimonial.'}), 500


@templates_bp.route('/api/admin/home-testimonials/<int:tid>/visibility', methods=['POST'])
def api_admin_home_testimonial_visibility(tid):
    """Show or hide a home-page testimonial (is_approved controls public index)."""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    if 'is_approved' not in data:
        return jsonify({'error': 'JSON body must include is_approved (true or false).'}), 400
    val = data.get('is_approved')
    if val not in (True, False, 1, 0):
        return jsonify({'error': 'is_approved must be a boolean.'}), 400
    approved = bool(val)
    try:
        row = HomePageTestimonial.query.get(tid)
        if not row:
            return jsonify({'error': 'Not found'}), 404
        row.is_approved = approved
        db.session.commit()
        return jsonify({'success': True, 'is_approved': row.is_approved})
    except Exception as ex:
        db.session.rollback()
        current_app.logger.exception('api_admin_home_testimonial_visibility: %s', ex)
        return jsonify({'error': 'Could not update visibility.'}), 500


@templates_bp.route('/seller/products')
def seller_products():
    if session.get('role') != 'seller':
        return redirect(url_for('templates.dashboard'))
    user_id = session.get('user_id')
    if (
        _seller_portal_suspended_store(user_id)
        and not _seller_portal_manageable_store(user_id)
    ):
        return redirect(url_for('templates.seller_store_suspended'))

    store = _seller_portal_manageable_store(user_id)
    categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order.asc(), Category.name.asc()).all()
    if not store:
        return _seller_home_redirect(user_id)
    
    # Get ONLY NON-ARCHIVED products for this store
    products = Product.query.filter_by(
        store_id=store.id,
        is_archived=False  # ← ADD THIS LINE
    ).order_by(Product.created_at.desc()).all()
    
    # FIX: Convert products to dict for template
    product_list = [product.to_dict() for product in products]
    
    return render_template('products.html', products=product_list, categories=categories)


@templates_bp.route('/seller/inventory')
def seller_inventory():
    if session.get('role') != 'seller':
        return redirect(url_for('templates.dashboard'))
    user_id = session.get('user_id')
    if (
        _seller_portal_suspended_store(user_id)
        and not _seller_portal_manageable_store(user_id)
    ):
        return redirect(url_for('templates.seller_store_suspended'))

    store = _seller_portal_manageable_store(user_id)
    if not store:
        return _seller_home_redirect(user_id)

    products = Product.query.filter_by(
        store_id=store.id,
        is_archived=False
    ).order_by(Product.name.asc()).all()

    product_list = [product.to_dict(include_inactive_addons=True) for product in products]
    return render_template('seller_inventory.html', products=product_list)

def generate_short_filename(original_filename, product_id, index):
    """Generate a short, safe filename for images"""
    # Get file extension
    if '.' in original_filename:
        ext = original_filename.rsplit('.', 1)[1].lower()
    else:
        ext = 'jpg'  # default
    
    # Create a short unique name using timestamp + random string
    # Format: p{product_id}_{index}_{random}.{ext}
    # Example: p123_0_a1b2c3d4.jpg
    
    # Use last 6 digits of timestamp
    timestamp = str(int(time.time()))[-6:]
    # Use first 8 chars of random UUID
    random_str = uuid.uuid4().hex[:8]
    
    # Short filename: max length around 25-30 chars
    short_filename = f"p{product_id}_{index}_{timestamp}_{random_str}.{ext}"
    
    return short_filename


@templates_bp.route('/seller/products/create', methods=['POST'])
@seller_required
def create_product():
    """Create a new product with Cloudinary images (no local storage)"""
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        # Get seller's store
        store = Store.query.filter_by(seller_id=session.get('user_id')).first()
        if not store:
            return jsonify({'error': 'Store not found. Please create a store first.'}), 404
        
        print("\n" + "="*60)
        print("📝 CREATE PRODUCT REQUEST (Cloudinary Only)")
        print(f"Form keys: {list(request.form.keys())}")
        
        # Import Cloudinary helper
        from app.utils.cloudinary_helper import should_use_cloudinary
        use_cloudinary = should_use_cloudinary()
        
        if not use_cloudinary:
            return jsonify({'error': 'Cloudinary is not configured. Please check your environment variables.'}), 500
        
        # Get form data
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price')
        stock_quantity = request.form.get('stock_quantity')
        
        # ===== UPDATED: Get category fields =====
        main_category_id = request.form.get('main_category_id')
        store_category_id = request.form.get('store_category_id')
        
        is_available = request.form.get('is_available', 'false').lower() == 'true'
        has_variants = request.form.get('has_variants', 'false').lower() == 'true'
        special_price_raw = request.form.get('special_price') or None
        
        print(f"📦 Product data: name={name}, main_category_id={main_category_id}, store_category_id={store_category_id}, has_variants={has_variants}")
        
        # Validate required fields
        if not name or not name.strip():
            return jsonify({'error': 'Product name is required'}), 400
        if not price:
            return jsonify({'error': 'Price is required'}), 400
        if not stock_quantity:
            return jsonify({'error': 'Stock quantity is required'}), 400
        if not main_category_id:
            return jsonify({'error': 'Main category is required'}), 400
        
        # Convert price and stock quantity
        try:
            price_float = float(price)
            if price_float <= 0:
                return jsonify({'error': 'Price must be greater than 0'}), 400
        except ValueError:
            return jsonify({'error': 'Invalid price format'}), 400
        
        try:
            stock_int = int(stock_quantity)
            if stock_int < 0:
                return jsonify({'error': 'Stock quantity cannot be negative'}), 400
        except ValueError:
            return jsonify({'error': 'Invalid stock quantity format'}), 400
        
        # Validate main_category_id exists
        from app.models import Category
        main_category = Category.query.get(main_category_id)
        if not main_category:
            return jsonify({'error': 'Invalid main category'}), 400
        
        # Validate store_category_id if provided
        if store_category_id:
            from app.models import StoreCategory
            store_category = StoreCategory.query.filter_by(
                id=store_category_id,
                store_id=store.id,
                main_category_id=main_category_id
            ).first()
            if not store_category:
                return jsonify({'error': 'Invalid store subcategory'}), 400
        
        special_price_float = None
        if special_price_raw:
            try:
                sp = float(special_price_raw)
                special_price_float = sp if sp > 0 else None
            except ValueError:
                pass

        # Create new product with category fields
        product = Product(
            store_id=store.id,
            name=name.strip(),
            description=description.strip() if description else None,
            price=price_float,
            special_price=special_price_float,
            stock_quantity=stock_int,
            main_category_id=int(main_category_id),
            store_category_id=int(store_category_id) if store_category_id else None,
            is_available=is_available
        )
        
        db.session.add(product)
        db.session.flush()  # Get product ID
        
        print(f"Product created with ID: {product.id}")
        
        # ===== HANDLE CLOUDINARY IMAGES (ONLY) =====
        cloudinary_images_json = request.form.get('cloudinary_images')
        image_count = 0
        
        if not cloudinary_images_json:
            db.session.rollback()
            return jsonify({'error': 'No images provided. Please upload at least one product image.'}), 400
        
        try:
            cloudinary_images = json.loads(cloudinary_images_json)
            print(f"📸 Received {len(cloudinary_images)} Cloudinary images")
            
            if len(cloudinary_images) == 0:
                db.session.rollback()
                return jsonify({'error': 'At least one product image is required'}), 400
            
            for img_data in cloudinary_images:
                product_image = ProductImage(
                    product_id=product.id,
                    filename=f"cloudinary_{img_data['public_id']}.jpg",
                    public_id=img_data['public_id'],
                    cloudinary_url=img_data['url'],
                    is_primary=img_data.get('is_primary', False),
                    sort_order=img_data.get('sort_order', image_count)
                )
                db.session.add(product_image)
                image_count += 1
                print(f"  ✅ Added Cloudinary image: {img_data['public_id']}")
                
        except json.JSONDecodeError as e:
            print(f"Error parsing cloudinary_images: {e}")
            db.session.rollback()
            return jsonify({'error': 'Invalid image data format'}), 400

        # Respect selected main image index from UI when provided.
        main_image_index_raw = request.form.get('main_image_index')
        if main_image_index_raw is not None:
            try:
                main_image_index = int(main_image_index_raw)
                for img in product.images:
                    img.is_primary = (img.sort_order == main_image_index)
                print(f"Applied main image index: {main_image_index}")
            except (TypeError, ValueError):
                print(f"Invalid main_image_index: {main_image_index_raw}")

        # Ensure at least one image remains primary.
        if product.images and not any(img.is_primary for img in product.images):
            first_img = sorted(product.images, key=lambda x: x.sort_order)[0]
            first_img.is_primary = True
            print(f"Fallback primary image set to ID: {first_img.id}")
        
        # ===== HANDLE VARIANTS =====
        if has_variants:
            variants_json = request.form.get('variants')
            if variants_json:
                try:
                    variants_data = json.loads(variants_json)
                    print(f"🎯 Processing {len(variants_data)} variants")
                    
                    for idx, variant_data in enumerate(variants_data):
                        if variant_data.get('_delete'):
                            continue
                        
                        print(f"  Variant {idx}: {variant_data.get('name')}")
                        
                        v_special_price = None
                        if variant_data.get('special_price'):
                            try:
                                sp = float(variant_data['special_price'])
                                v_special_price = sp if sp > 0 else None
                            except (ValueError, TypeError):
                                pass

                        variant = ProductVariant(
                            product_id=product.id,
                            name=variant_data.get('name'),
                            price=Decimal(str(variant_data.get('price'))),
                            special_price=v_special_price,
                            stock_quantity=int(variant_data.get('stock_quantity', 0)),
                            sku=variant_data.get('sku'),
                            attributes=variant_data.get('attributes'),
                            sort_order=idx,
                            is_available=variant_data.get('is_available', True)
                        )
                        
                        # Handle Cloudinary variant image
                        if variant_data.get('cloudinary_public_id'):
                            variant.image_public_id = variant_data['cloudinary_public_id']
                            variant.image_url = variant_data['cloudinary_url']
                            variant.image_filename = f"variant_{variant_data['cloudinary_public_id']}.jpg"
                            print(f"    📸 Variant with Cloudinary image: {variant_data['cloudinary_public_id']}")
                        
                        db.session.add(variant)
                    
                except json.JSONDecodeError as e:
                    print(f"❌ JSON decode error: {e}")
                    db.session.rollback()
                    return jsonify({'error': 'Invalid variants data'}), 400
                except Exception as e:
                    print(f"❌ Error processing variants: {e}")
                    db.session.rollback()
                    return jsonify({'error': f'Error processing variants: {str(e)}'}), 400
        
        # ===== HANDLE ADD-ON GROUPS =====
        has_addons = request.form.get('has_addons', 'false').lower() == 'true'
        if has_addons:
            addon_groups_json = request.form.get('addon_groups')
            if addon_groups_json:
                try:
                    addon_groups_data = json.loads(addon_groups_json)
                    _sync_product_addon_groups(product, addon_groups_data)
                except json.JSONDecodeError:
                    db.session.rollback()
                    return jsonify({'error': 'Invalid add-on groups data'}), 400
                except Exception as e:
                    db.session.rollback()
                    return jsonify({'error': f'Error processing add-ons: {str(e)}'}), 400

        db.session.commit()
        print(f"✅ Product {product.id} created successfully with {image_count} Cloudinary images")
        print("="*60 + "\n")
        
        return jsonify({
            'success': True,
            'message': 'Product created successfully',
            'product': product.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error creating product: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 500
    


@templates_bp.route('/seller/products/<int:product_id>', methods=['GET', 'PUT', 'DELETE'])
@seller_required
def manage_product(product_id):
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        store = Store.query.filter_by(seller_id=session.get('user_id')).first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404

        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            return jsonify({'error': 'Product not found'}), 404

        # ── GET ───────────────────────────────────────────────────────────────
        if request.method == 'GET':
            print(f"\n📖 GET Product {product_id}")
            product_dict = product.to_dict(include_inactive_addons=True)
            print(f"✅ Returning product with {len(product_dict.get('variants', []))} variants")
            return jsonify({'success': True, 'product': product_dict})

       # ── PUT (UPDATE) ──────────────────────────────────────────────────────
        elif request.method == 'PUT':
            print("\n" + "="*60)
            print(f"📝 UPDATE PRODUCT {product_id} (Cloudinary Only)")
            print(f"Form keys: {list(request.form.keys())}")

            # Import Cloudinary helper
            from app.utils.cloudinary_helper import should_use_cloudinary, delete_from_cloudinary
            use_cloudinary = should_use_cloudinary()
            
            if not use_cloudinary:
                return jsonify({'error': 'Cloudinary is not configured. Please check your environment variables.'}), 500

            # Update basic fields
            if 'name' in request.form:
                product.name = request.form['name'].strip()
            if 'description' in request.form:
                product.description = request.form['description'].strip() or None
            if 'price' in request.form:
                try:
                    product.price = float(request.form['price'])
                except ValueError:
                    return jsonify({'error': 'Invalid price format'}), 400
            if 'special_price' in request.form:
                sp_raw = request.form['special_price']
                if sp_raw == '' or sp_raw is None:
                    product.special_price = None
                else:
                    try:
                        sp = float(sp_raw)
                        product.special_price = sp if sp > 0 else None
                    except ValueError:
                        pass
            if 'stock_quantity' in request.form:
                try:
                    product.stock_quantity = int(request.form['stock_quantity'])
                except ValueError:
                    return jsonify({'error': 'Invalid stock quantity format'}), 400
            
            # ===== UPDATED: Handle category fields =====
            if 'main_category_id' in request.form:
                main_category_id = request.form['main_category_id']
                if main_category_id:
                    from app.models import Category
                    main_category = Category.query.get(main_category_id)
                    if not main_category:
                        return jsonify({'error': 'Invalid main category'}), 400
                    product.main_category_id = int(main_category_id)
            
            if 'store_category_id' in request.form:
                store_category_id = request.form['store_category_id']
                if store_category_id:
                    from app.models import StoreCategory
                    store_category = StoreCategory.query.filter_by(
                        id=store_category_id,
                        store_id=store.id,
                        main_category_id=product.main_category_id
                    ).first()
                    if not store_category:
                        return jsonify({'error': 'Invalid store subcategory'}), 400
                    product.store_category_id = int(store_category_id)
                else:
                    product.store_category_id = None
            
            if 'is_available' in request.form:
                is_avail_str = request.form['is_available']
                product.is_available = is_avail_str.lower() in ['true', '1', 'yes']

            # ===== HANDLE PRODUCT IMAGES (CLOUDINARY ONLY) =====
            
            # Get images to keep/delete
            images_to_keep = []
            images_to_delete = []
            
            if 'images_to_keep' in request.form:
                try:
                    images_to_keep = json.loads(request.form['images_to_keep'])
                    print(f"📌 Images to keep: {images_to_keep}")
                except:
                    pass
            
            if 'images_to_delete' in request.form:
                try:
                    images_to_delete = json.loads(request.form['images_to_delete'])
                    print(f"🗑️ Images to delete: {images_to_delete}")
                except:
                    pass

            # Delete marked images from Cloudinary and database
            for img_id in images_to_delete:
                img = ProductImage.query.filter_by(id=img_id, product_id=product.id).first()
                if img:
                    if img.public_id:
                        delete_from_cloudinary(img.public_id)
                        print(f"  🗑️ Deleted from Cloudinary: {img.public_id}")
                    
                    db.session.delete(img)
                    print(f"  🗑️ Deleted image record {img_id}")

            # Handle new Cloudinary images
            cloudinary_images_json = request.form.get('cloudinary_images')
            if cloudinary_images_json:
                try:
                    cloudinary_images = json.loads(cloudinary_images_json)
                    print(f"📸 Received {len(cloudinary_images)} new Cloudinary images")
                    
                    for img_data in cloudinary_images:
                        product_image = ProductImage(
                            product_id=product.id,
                            filename=f"cloudinary_{img_data['public_id']}.jpg",
                            public_id=img_data['public_id'],
                            cloudinary_url=img_data['url'],
                            is_primary=img_data.get('is_primary', False),
                            sort_order=img_data.get('sort_order', 0)
                        )
                        db.session.add(product_image)
                        print(f"  ✅ Added new Cloudinary image: {img_data['public_id']}")
                            
                except json.JSONDecodeError as e:
                    print(f"❌ Error parsing cloudinary_images: {e}")

            # Handle replacement images
            replacement_images_json = request.form.get('replacement_images')
            if replacement_images_json:
                try:
                    replacement_images = json.loads(replacement_images_json)
                    print(f"🔄 Received {len(replacement_images)} replacement images")
                    
                    for img_data in replacement_images:
                        existing_id = img_data.get('existing_id')
                        if not existing_id:
                            print(f"  ❌ No existing_id in replacement data: {img_data}")
                            continue
                            
                        old_image = ProductImage.query.filter_by(
                            id=existing_id, 
                            product_id=product.id
                        ).first()
                        
                        if old_image:
                            print(f"  Replacing image ID {old_image.id} (public_id: {old_image.public_id})")
                            
                            if old_image.public_id:
                                if delete_from_cloudinary(old_image.public_id):
                                    print(f"    🗑️ Deleted old Cloudinary image: {old_image.public_id}")
                                else:
                                    print(f"    ⚠️ Failed to delete old Cloudinary image: {old_image.public_id}")
                            
                            old_image.public_id = img_data['public_id']
                            old_image.cloudinary_url = img_data['url']
                            old_image.filename = f"cloudinary_{img_data['public_id']}.jpg"
                            old_image.is_primary = img_data.get('is_primary', old_image.is_primary)
                            old_image.sort_order = img_data.get('sort_order', old_image.sort_order)
                            old_image.updated_at = datetime.utcnow()
                            
                            print(f"    ✅ Updated existing image record {old_image.id} with new Cloudinary image: {img_data['public_id']}")
                        else:
                            print(f"    ❌ Could not find existing image with ID: {existing_id}")
                            
                except json.JSONDecodeError as e:
                    print(f"❌ Error parsing replacement_images: {e}")
                except Exception as e:
                    print(f"❌ Error processing replacement images: {e}")

            # Respect selected main image index from UI for existing/new/replaced images.
            main_image_index_raw = request.form.get('main_image_index')
            if main_image_index_raw is not None:
                try:
                    main_image_index = int(main_image_index_raw)
                    active_images = ProductImage.query.filter_by(product_id=product.id).all()
                    for img in active_images:
                        img.is_primary = (img.sort_order == main_image_index)
                    print(f"🏷️ Applied main image index on edit: {main_image_index}")
                except (TypeError, ValueError):
                    print(f"⚠️ Invalid main_image_index on edit: {main_image_index_raw}")

            # Ensure one primary image if images remain.
            active_images = ProductImage.query.filter_by(product_id=product.id).all()
            if active_images and not any(img.is_primary for img in active_images):
                first_img = sorted(active_images, key=lambda x: x.sort_order)[0]
                first_img.is_primary = True
                print(f"🏷️ Fallback primary image on edit set to ID: {first_img.id}")

            # ===== HANDLE VARIANTS UPDATE =====
            has_variants = request.form.get('has_variants', 'false').lower() == 'true'
            print(f"🎯 Has variants: {has_variants}")

            if has_variants:
                variants_json = request.form.get('variants')
                if variants_json:
                    try:
                        variants_data = json.loads(variants_json)
                        print(f"📦 Variants data received: {len(variants_data)} variants")

                        kept_variant_ids = []

                        for idx, variant_data in enumerate(variants_data):
                            variant_id = variant_data.get('id')
                            
                            print(f"\n  Variant {idx}:")
                            print(f"    ID: {variant_id}")
                            print(f"    Name: {variant_data.get('name')}")
                            print(f"    Delete: {variant_data.get('_delete')}")
                            print(f"    Remove image: {variant_data.get('_remove_image')}")

                            # Handle deletion
                            if variant_data.get('_delete') and variant_id:
                                variant = ProductVariant.query.filter_by(
                                    id=variant_id, 
                                    product_id=product.id
                                ).first()
                                
                                if variant:
                                    if variant.image_public_id:
                                        delete_from_cloudinary(variant.image_public_id)
                                        print(f"      🗑️ Deleted variant image from Cloudinary")
                                    
                                    db.session.delete(variant)
                                    print(f"    ✅ Deleted variant {variant_id}")
                                continue

                            # Update existing or create new variant
                            if variant_id:
                                # Update existing
                                variant = ProductVariant.query.filter_by(
                                    id=variant_id, 
                                    product_id=product.id
                                ).first()
                                
                                if variant:
                                    variant.name = variant_data.get('name')
                                    variant.price = Decimal(str(variant_data.get('price')))
                                    # special_price
                                    v_sp_raw = variant_data.get('special_price')
                                    if v_sp_raw is not None and v_sp_raw != '':
                                        try:
                                            sp = float(v_sp_raw)
                                            variant.special_price = sp if sp > 0 else None
                                        except (ValueError, TypeError):
                                            pass
                                    else:
                                        variant.special_price = None
                                    variant.stock_quantity = int(variant_data.get('stock_quantity', 0))
                                    variant.sku = variant_data.get('sku')
                                    variant.attributes = variant_data.get('attributes')
                                    variant.sort_order = idx
                                    variant.is_available = variant_data.get('is_available', True)
                                    variant.updated_at = datetime.utcnow()
                                    
                                    print(f"    ✅ Updated existing variant {variant_id}")
                                    
                                    # Handle variant image removal
                                    if variant_data.get('_remove_image'):
                                        if variant.image_public_id:
                                            delete_from_cloudinary(variant.image_public_id)
                                            print(f"      🗑️ Removed variant image from Cloudinary")
                                        
                                        variant.image_public_id = None
                                        variant.image_url = None
                                        variant.image_filename = None
                                    
                                    # Handle new Cloudinary image
                                    if variant_data.get('cloudinary_public_id'):
                                        if variant.image_public_id:
                                            delete_from_cloudinary(variant.image_public_id)
                                        
                                        variant.image_public_id = variant_data['cloudinary_public_id']
                                        variant.image_url = variant_data['cloudinary_url']
                                        variant.image_filename = f"variant_{variant_data['cloudinary_public_id']}.jpg"
                                        print(f"      📸 Updated variant with Cloudinary image")
                                    
                                    kept_variant_ids.append(variant_id)
                            else:
                                # Create new variant
                                v_sp_new = None
                                v_sp_raw_new = variant_data.get('special_price')
                                if v_sp_raw_new is not None and v_sp_raw_new != '':
                                    try:
                                        sp = float(v_sp_raw_new)
                                        v_sp_new = sp if sp > 0 else None
                                    except (ValueError, TypeError):
                                        pass

                                variant = ProductVariant(
                                    product_id=product.id,
                                    name=variant_data.get('name'),
                                    price=Decimal(str(variant_data.get('price'))),
                                    special_price=v_sp_new,
                                    stock_quantity=int(variant_data.get('stock_quantity', 0)),
                                    sku=variant_data.get('sku'),
                                    attributes=variant_data.get('attributes'),
                                    sort_order=idx,
                                    is_available=variant_data.get('is_available', True)
                                )
                                
                                if variant_data.get('cloudinary_public_id'):
                                    variant.image_public_id = variant_data['cloudinary_public_id']
                                    variant.image_url = variant_data['cloudinary_url']
                                    variant.image_filename = f"variant_{variant_data['cloudinary_public_id']}.jpg"
                                    print(f"      📸 New variant with Cloudinary image")
                                
                                db.session.add(variant)
                                db.session.flush()
                                kept_variant_ids.append(variant.id)
                                print(f"    ✅ Created new variant {variant.id}")

                        # Delete variants that were not included in the update
                        existing_variants = ProductVariant.query.filter_by(
                            product_id=product.id
                        ).all()
                        
                        for existing_variant in existing_variants:
                            if existing_variant.id not in kept_variant_ids:
                                if existing_variant.image_public_id:
                                    delete_from_cloudinary(existing_variant.image_public_id)
                                    print(f"      🗑️ Deleted orphaned variant image from Cloudinary")
                                
                                db.session.delete(existing_variant)
                                print(f"    🗑️ Removed orphaned variant {existing_variant.id}")

                    except json.JSONDecodeError as e:
                        print(f"❌ JSON decode error: {e}")
                        db.session.rollback()
                        return jsonify({'error': 'Invalid variants data'}), 400
            else:
                # If has_variants is false, delete all variants
                print("🗑️ Deleting all variants (has_variants=false)")
                
                for variant in product.variants:
                    if variant.image_public_id:
                        delete_from_cloudinary(variant.image_public_id)
                        print(f"  🗑️ Deleted variant image from Cloudinary")
                    db.session.delete(variant)

            # ===== HANDLE ADD-ON GROUPS UPDATE =====
            has_addons = request.form.get('has_addons', 'false').lower() == 'true'
            if has_addons:
                addon_groups_json = request.form.get('addon_groups')
                if addon_groups_json:
                    try:
                        addon_groups_data = json.loads(addon_groups_json)
                        _sync_product_addon_groups(
                            product,
                            addon_groups_data,
                            delete_cloudinary_fn=delete_from_cloudinary,
                        )
                    except json.JSONDecodeError:
                        db.session.rollback()
                        return jsonify({'error': 'Invalid add-on groups data'}), 400
                    except Exception as e:
                        db.session.rollback()
                        return jsonify({'error': f'Error processing add-ons: {str(e)}'}), 400
            else:
                for group in list(product.addon_groups):
                    for opt in list(group.options):
                        if opt.image_public_id:
                            delete_from_cloudinary(opt.image_public_id)
                    db.session.delete(group)

            product.updated_at = datetime.utcnow()
            db.session.commit()
            
            print(f"✅ Product {product_id} updated successfully with Cloudinary")
            print("="*60 + "\n")
            
            return jsonify({
                'success': True,
                'message': 'Product updated successfully',
                'product': product.to_dict(include_inactive_addons=True)
            })

        # ── DELETE ────────────────────────────────────────────────────────────
        elif request.method == 'DELETE':
            print("\n" + "="*60)
            print(f"🗑️ DELETE PRODUCT {product_id}")

            if product.is_archived:
                return jsonify({
                    'success': True,
                    'archived': True,
                    'message': 'Product is already in archive'
                }), 200

            try:
                product.archive(session['user_id'])
                db.session.commit()

                print(f"📦 Product {product_id} archived instead of permanently deleting")
                print("="*60 + "\n")

                return jsonify({
                    'success': True,
                    'archived': True,
                    'message': 'Product moved to archive successfully',
                    'product': product.to_dict()
                }), 200

            except Exception as e:
                db.session.rollback()
                print(f"❌ Error archiving product: {str(e)}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'Failed to archive product: {str(e)}'}), 500

        return jsonify({'error': 'Method not allowed'}), 405

    except Exception as e:
        db.session.rollback()
        print(f"❌ Exception in manage_product: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500



@templates_bp.route('/seller/products/<int:product_id>/availability', methods=['PUT'])
def update_product_availability(product_id):
    """Update just the availability status of a product"""
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        # Get seller's store
        store = Store.query.filter_by(seller_id=session.get('user_id')).first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        data = request.get_json()
        if data is None:
            return jsonify({'error': 'Invalid JSON data'}), 400
            
        is_available = data.get('is_available')
        if is_available is None:
            return jsonify({'error': 'is_available field is required'}), 400
        
        product.is_available = bool(is_available)
        product.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Product {"available" if is_available else "unavailable"}',
            'product': product.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating availability: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500




# ═════════════════════════════════════════════════════════════════════════════
# STOCK REDUCTION AUDIT ENDPOINTS
# ═════════════════════════════════════════════════════════════════════════════

@templates_bp.route('/seller/products/<int:product_id>/reduce-stock', methods=['POST'])
def reduce_product_stock(product_id):
    """
    Record stock reduction with audit trail.
    Handles both main products and variants.
    
    Expected JSON payload:
    {
        "amount": 5,
        "reason": "damage",  # spoilage, damage, defect, other, pos_sale
        "reason_notes": "Damaged during shipping",
        "variant_id": 123,  # Optional, only for variants
        "addon_option_id": 45  # Optional, only for add-on options
    }
    """
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = session.get('user_id')
    
    try:
        # Get seller's store
        store = _seller_portal_manageable_store(user_id)
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        # Parse request data
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400
        
        # Validate inputs
        amount = data.get('amount')
        reason = data.get('reason')
        reason_notes = data.get('reason_notes', '')
        variant_id = data.get('variant_id')
        addon_option_id = data.get('addon_option_id')
        
        if not amount:
            return jsonify({'error': 'Reduction amount is required'}), 400
        
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            return jsonify({'error': 'Invalid reduction amount - must be integer'}), 400
        
        if not reason:
            return jsonify({'error': 'Reason for reduction is required'}), 400
        
        if reason not in StockReduction.REASONS:
            return jsonify({
                'error': f'Invalid reason. Must be one of: {", ".join(StockReduction.REASONS)}'
            }), 400

        if variant_id and addon_option_id:
            return jsonify({'error': 'Provide either variant_id or addon_option_id, not both'}), 400
        
        # Find the product first
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        # Handle add-on option reduction
        if addon_option_id:
            addon_opt = ProductAddonOption.query.get(addon_option_id)
            if (
                not addon_opt
                or not addon_opt.group
                or addon_opt.group.product_id != product.id
            ):
                return jsonify({'error': 'Add-on option not found'}), 404

            if amount > int(addon_opt.stock_quantity or 0):
                return jsonify({
                    'error': f'Cannot reduce by {amount}. Available: {addon_opt.stock_quantity}'
                }), 400

            addon_opt.stock_quantity = int(addon_opt.stock_quantity or 0) - amount
            addon_opt.updated_at = datetime.utcnow()

            reduction = StockReduction(
                product_id=product.id,
                variant_id=None,
                addon_option_id=addon_opt.id,
                reduction_amount=amount,
                reason=reason,
                reason_notes=reason_notes,
                reduced_by=user_id,
            )
            db.session.add(reduction)
            product.updated_at = datetime.utcnow()
            db.session.commit()

            return jsonify({
                'success': True,
                'message': f'Stock reduced by {amount} units for add-on {addon_opt.name}',
                'reduction': reduction.to_dict(),
                'product': product.to_dict(include_inactive_addons=True),
                'addon_option': addon_opt.to_dict(),
            }), 200

        # Handle variant reduction if variant_id is provided
        variant = None
        if variant_id:
            variant = ProductVariant.query.filter_by(id=variant_id, product_id=product.id).first()
            if not variant:
                return jsonify({'error': 'Variant not found'}), 404
            
            # Validate stock
            if amount > variant.stock_quantity:
                return jsonify({'error': f'Cannot reduce by {amount}. Available: {variant.stock_quantity}'}), 400
            
            # Reduce variant stock
            variant.stock_quantity -= amount
            variant.updated_at = datetime.utcnow()
            
            # Create audit entry
            reduction = StockReduction(
                product_id=product.id,
                variant_id=variant.id,
                reduction_amount=amount,
                reason=reason,
                reason_notes=reason_notes,
                reduced_by=user_id
            )
            db.session.add(reduction)
            
            print(f"✅ Variant stock reduction recorded:")
            print(f"   Product: {product.name} (ID: {product.id})")
            print(f"   Variant: {variant.name} (ID: {variant.id})")
            print(f"   Reduced by: {amount} units")
            print(f"   Reason: {reason}")
            print(f"   New variant stock: {variant.stock_quantity}")
            
            # Update product's updated_at timestamp
            product.updated_at = datetime.utcnow()
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Stock reduced by {amount} units for variant {variant.name}',
                'reduction': reduction.to_dict(),
                'product': product.to_dict(),
                'variant': variant.to_dict()
            }), 200
            
        else:
            # Reduce main product stock
            reduction = product.reduce_stock(amount, reason, user_id, reason_notes)
            db.session.commit()
            
            print(f"✅ Main product stock reduction recorded:")
            print(f"   Product: {product.name} (ID: {product.id})")
            print(f"   Reduced by: {amount} units")
            print(f"   Reason: {reason}")
            print(f"   New stock: {product.stock_quantity}")
            
            return jsonify({
                'success': True,
                'message': f'Stock reduced by {amount} units',
                'reduction': reduction.to_dict(),
                'product': product.to_dict()
            }), 200
        
    except ValueError as e:
        db.session.rollback()
        print(f"❌ Validation error: {str(e)}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error reducing stock: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@templates_bp.route('/seller/products/<int:product_id>/add-stock', methods=['POST'])
def add_product_stock(product_id):
    """
    Record stock addition with audit trail.
    Handles both main products and variants.
    
    Expected JSON payload:
    {
        "amount": 10,
        "reason": "restock",  # found_stock, receiving_error, restock
        "reason_notes": "Received new shipment",
        "variant_id": 123,  # Optional, only for variants
        "addon_option_id": 45  # Optional, only for add-on options
    }
    """
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = session.get('user_id')
    
    try:
        # Get seller's store
        store = _seller_portal_manageable_store(user_id)
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        # Parse request data
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400
        
        # Validate inputs
        amount = data.get('amount')
        reason = data.get('reason')
        reason_notes = data.get('reason_notes', '')
        variant_id = data.get('variant_id')
        addon_option_id = data.get('addon_option_id')
        
        if not amount:
            return jsonify({'error': 'Addition amount is required'}), 400
        
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            return jsonify({'error': 'Invalid addition amount - must be integer'}), 400
        
        if amount <= 0:
            return jsonify({'error': 'Addition amount must be positive'}), 400
        
        if not reason:
            return jsonify({'error': 'Reason for addition is required'}), 400
        
        if reason not in StockReduction.REASONS:
            return jsonify({
                'error': f'Invalid reason. Must be one of: {", ".join(StockReduction.REASONS)}'
            }), 400

        if variant_id and addon_option_id:
            return jsonify({'error': 'Provide either variant_id or addon_option_id, not both'}), 400
        
        # Find the product first
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            return jsonify({'error': 'Product not found'}), 404

        if addon_option_id:
            addon_opt = ProductAddonOption.query.get(addon_option_id)
            if (
                not addon_opt
                or not addon_opt.group
                or addon_opt.group.product_id != product.id
            ):
                return jsonify({'error': 'Add-on option not found'}), 404

            addon_opt.stock_quantity = int(addon_opt.stock_quantity or 0) + amount
            addon_opt.updated_at = datetime.utcnow()

            addition = StockReduction(
                product_id=product.id,
                variant_id=None,
                addon_option_id=addon_opt.id,
                reduction_amount=amount,
                reason=reason,
                reason_notes=reason_notes,
                reduced_by=user_id,
            )
            db.session.add(addition)
            product.updated_at = datetime.utcnow()
            db.session.commit()

            return jsonify({
                'success': True,
                'message': f'Stock added {amount} units for add-on {addon_opt.name}',
                'addition': addition.to_dict(),
                'product': product.to_dict(include_inactive_addons=True),
                'addon_option': addon_opt.to_dict(),
            }), 200
        
        # Handle variant addition if variant_id is provided
        variant = None
        if variant_id:
            variant = ProductVariant.query.filter_by(id=variant_id, product_id=product.id).first()
            if not variant:
                return jsonify({'error': 'Variant not found'}), 404
            
            # Add stock to variant
            variant.stock_quantity += amount
            variant.updated_at = datetime.utcnow()
            
            # Create audit entry for stock addition
            addition = StockReduction(
                product_id=product.id,
                variant_id=variant.id,
                reduction_amount=amount,  # Using the same field, positive for addition
                reason=reason,
                reason_notes=reason_notes,
                reduced_by=user_id
            )
            db.session.add(addition)
            
            print(f"✅ Variant stock addition recorded:")
            print(f"   Product: {product.name} (ID: {product.id})")
            print(f"   Variant: {variant.name} (ID: {variant.id})")
            print(f"   Added: {amount} units")
            print(f"   Reason: {reason}")
            print(f"   New variant stock: {variant.stock_quantity}")
            
            # Update product's updated_at timestamp
            product.updated_at = datetime.utcnow()
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Stock added {amount} units for variant {variant.name}',
                'addition': addition.to_dict(),
                'product': product.to_dict(),
                'variant': variant.to_dict()
            }), 200
            
        else:
            # Add stock to main product
            product.stock_quantity += amount
            product.updated_at = datetime.utcnow()
            
            # Create audit entry for stock addition
            addition = StockReduction(
                product_id=product.id,
                variant_id=None,
                reduction_amount=amount,  # Using the same field, positive for addition
                reason=reason,
                reason_notes=reason_notes,
                reduced_by=user_id
            )
            db.session.add(addition)
            db.session.commit()
            
            print(f"✅ Main product stock addition recorded:")
            print(f"   Product: {product.name} (ID: {product.id})")
            print(f"   Added: {amount} units")
            print(f"   Reason: {reason}")
            print(f"   New stock: {product.stock_quantity}")
            
            return jsonify({
                'success': True,
                'message': f'Stock added {amount} units',
                'addition': addition.to_dict(),
                'product': product.to_dict()
            }), 200
        
    except ValueError as e:
        db.session.rollback()
        print(f"❌ Validation error: {str(e)}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error adding stock: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@templates_bp.route('/seller/products/<int:product_id>/stock-history', methods=['GET'])
def get_stock_history(product_id):
    """
    Get audit log of all stock reductions for a product, variant, or add-on option.
    """
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = session.get('user_id')
    
    try:
        # Get seller's store
        store = _seller_portal_manageable_store(user_id)
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        # Try to find as a Product first
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        
        # If not found as product, try as variant
        variant = None
        if not product:
            variant = ProductVariant.query.filter_by(id=product_id).first()
            if variant:
                # Get the product this variant belongs to
                product = variant.product
                # Verify the product belongs to this seller's store
                if not product or product.store_id != store.id:
                    return jsonify({'error': 'Product not found'}), 404
            else:
                return jsonify({'error': 'Product not found'}), 404

        filter_variant_id = request.args.get('variant_id', type=int)
        filter_addon_option_id = request.args.get('addon_option_id', type=int)
        
        # Get reductions for main product (where variant_id and addon_option_id are NULL)
        main_reductions = StockReduction.query.filter_by(
            product_id=product.id, 
            variant_id=None,
            addon_option_id=None,
        ).order_by(StockReduction.created_at.desc()).all()
        
        # Get reductions for variants (where variant_id is NOT NULL)
        variant_q = StockReduction.query.filter(
            StockReduction.product_id == product.id,
            StockReduction.variant_id.isnot(None),
        )
        if filter_variant_id:
            variant_q = variant_q.filter(StockReduction.variant_id == filter_variant_id)
        variant_reductions = variant_q.order_by(StockReduction.created_at.desc()).all()

        # Add-on history: look up by owned option ids so restore/sale rows still
        # appear even if product_id was previously logged as the ordered product.
        owned_addon_ids = [
            int(o.id)
            for g in (product.addon_groups or [])
            for o in (g.options or [])
            if o and o.id
        ]
        if filter_addon_option_id:
            if owned_addon_ids and filter_addon_option_id not in owned_addon_ids:
                return jsonify({'error': 'Add-on option not found on this product'}), 404
            addon_q = StockReduction.query.filter(
                StockReduction.addon_option_id == filter_addon_option_id,
            )
        elif owned_addon_ids:
            addon_q = StockReduction.query.filter(
                StockReduction.addon_option_id.in_(owned_addon_ids),
            )
        else:
            addon_q = StockReduction.query.filter(
                StockReduction.product_id == product.id,
                StockReduction.addon_option_id.isnot(None),
            )
        addon_reductions = addon_q.order_by(StockReduction.created_at.desc()).all()

        # When scoped to a variant/add-on, hide unrelated main history
        if filter_variant_id or filter_addon_option_id:
            main_reductions = []
            if filter_variant_id:
                addon_reductions = []
            if filter_addon_option_id:
                variant_reductions = []
        
        # Calculate totals for main product
        main_total_reduced = sum(r.reduction_amount for r in main_reductions)
        
        # Calculate totals for variants
        variant_total_reduced = sum(r.reduction_amount for r in variant_reductions)
        addon_total_reduced = sum(r.reduction_amount for r in addon_reductions)
        
        # Get primary image for main product
        primary_image = None
        if product.images:
            primary_image_obj = next((img for img in product.images if img.is_primary), None)
            if not primary_image_obj:
                primary_image_obj = product.images[0] if product.images else None
            if primary_image_obj:
                primary_image = primary_image_obj.cloudinary_url or primary_image_obj.image_url
        
        # Build main product reductions data
        main_history = []
        for r in main_reductions:
            reduction_data = {
                'id': r.id,
                'product_id': r.product_id,
                'product_name': product.name,
                'product_image': primary_image,
                'reduction_amount': r.reduction_amount,
                'reason': r.reason,
                'reason_notes': r.reason_notes,
                'reduced_by': r.reduced_by,
                'reduced_by_user': r.reducer_user.full_name if r.reducer_user else None,
                'created_at': r.created_at.isoformat() if r.created_at else None,
                'updated_at': r.updated_at.isoformat() if r.updated_at else None
            }
            main_history.append(reduction_data)
        
        # Build variant reductions data
        variant_history = []
        for r in variant_reductions:
            # Get the variant from the variant_id field
            var = ProductVariant.query.filter_by(id=r.variant_id).first() if r.variant_id else None
            if var:
                variant_image = var.image_url  # Get variant's own image
                reduction_data = {
                    'id': r.id,
                    'product_id': r.product_id,
                    'variant_id': var.id,
                    'product_name': f"{product.name} - {var.name}",
                    'product_image': variant_image,  # Use variant image
                    'reduction_amount': r.reduction_amount,
                    'reason': r.reason,
                    'reason_notes': r.reason_notes,
                    'reduced_by': r.reduced_by,
                    'reduced_by_user': r.reducer_user.full_name if r.reducer_user else None,
                    'created_at': r.created_at.isoformat() if r.created_at else None,
                    'updated_at': r.updated_at.isoformat() if r.updated_at else None
                }
                variant_history.append(reduction_data)
            else:
                # Fallback if variant not found (shouldn't happen)
                reduction_data = {
                    'id': r.id,
                    'product_id': r.product_id,
                    'variant_id': r.variant_id,
                    'product_name': f"{product.name} - Variant {r.variant_id}",
                    'product_image': None,
                    'reduction_amount': r.reduction_amount,
                    'reason': r.reason,
                    'reason_notes': r.reason_notes,
                    'reduced_by': r.reduced_by,
                    'reduced_by_user': r.reducer_user.full_name if r.reducer_user else None,
                    'created_at': r.created_at.isoformat() if r.created_at else None,
                    'updated_at': r.updated_at.isoformat() if r.updated_at else None
                }
                variant_history.append(reduction_data)

        addon_history = []
        for r in addon_reductions:
            opt = r.addon_option or (
                ProductAddonOption.query.get(r.addon_option_id) if r.addon_option_id else None
            )
            if opt:
                group_name = opt.group.name if opt.group else 'Add-on'
                addon_history.append({
                    'id': r.id,
                    'product_id': r.product_id,
                    'addon_option_id': opt.id,
                    'product_name': f"{product.name} — {group_name}: {opt.name}",
                    'product_image': opt.image_url,
                    'reduction_amount': r.reduction_amount,
                    'reason': r.reason,
                    'reason_notes': r.reason_notes,
                    'reduced_by': r.reduced_by,
                    'reduced_by_user': r.reducer_user.full_name if r.reducer_user else None,
                    'created_at': r.created_at.isoformat() if r.created_at else None,
                    'updated_at': r.updated_at.isoformat() if r.updated_at else None,
                })
            else:
                addon_history.append({
                    'id': r.id,
                    'product_id': r.product_id,
                    'addon_option_id': r.addon_option_id,
                    'product_name': f"{product.name} — Add-on #{r.addon_option_id}",
                    'product_image': None,
                    'reduction_amount': r.reduction_amount,
                    'reason': r.reason,
                    'reason_notes': r.reason_notes,
                    'reduced_by': r.reduced_by,
                    'reduced_by_user': r.reducer_user.full_name if r.reducer_user else None,
                    'created_at': r.created_at.isoformat() if r.created_at else None,
                    'updated_at': r.updated_at.isoformat() if r.updated_at else None,
                })
        
        return jsonify({
            'success': True,
            'product': {
                'id': product.id,
                'name': product.name,
                'image': primary_image,
                'current_stock': product.stock_quantity
            },
            'main_product': {
                'total_reductions': main_total_reduced,
                'reduction_count': len(main_reductions)
            },
            'variants': {
                'total_reductions': variant_total_reduced,
                'reduction_count': len(variant_reductions)
            },
            'addons': {
                'total_reductions': addon_total_reduced,
                'reduction_count': len(addon_reductions)
            },
            'stock_history': {
                'main': main_history,
                'variants': variant_history,
                'addons': addon_history,
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Error retrieving stock history: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 500






# Add template filters
@templates_bp.app_template_filter('time_format')
def time_format(value):
    """Format datetime to readable time"""
    if not value:
        return ""
    
    # If value is a string, convert to datetime
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except:
            return value
    
    # Format the time
    return value.strftime('%I:%M %p')  # 12-hour format with AM/PM

@templates_bp.app_template_filter('date_format')
def date_format(value):
    """Format datetime to readable date"""
    if not value:
        return ""
    
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except:
            return value
    
    return value.strftime('%b %d, %Y')  # Feb 07, 2026

@templates_bp.route('/seller/orders')
def seller_orders():
    if session.get('role') != 'seller':
        return redirect(url_for('templates.dashboard'))
    _ensure_order_fulfillment_columns()

    def _load_page():
        # Get seller's store
        store = Store.query.filter_by(seller_id=session['user_id']).first()
        if not store:
            return None

        # Eager-load related rows — avoids N+1 lazy loads that often hit a
        # stale Railway connection mid-page render.
        orders = (
            Order.query
            .options(
                selectinload(Order.items).joinedload(OrderItem.product).selectinload(Product.images),
                selectinload(Order.items).joinedload(OrderItem.variant),
                selectinload(Order.items).selectinload(OrderItem.addons),
                joinedload(Order.customer),
                joinedload(Order.assigned_rider).joinedload(Rider.user),
            )
            .filter_by(store_id=store.id)
            .order_by(Order.created_at.desc())
            .all()
        )

        available_riders = (
            Rider.query
            .options(joinedload(Rider.user))
            .filter_by(store_id=store.id, is_active=True)
            .order_by(Rider.created_at.desc())
            .all()
        )

        orders_data = []
        for order in orders:
            order_dict = order.to_dict()
            order_dict['items'] = [item.to_dict() for item in order.items]
            order_dict['items_count'] = sum(item.quantity for item in order.items)
            _attach_seller_order_customer_contact(order_dict, order.customer)
            _apply_order_display_totals(order, order_dict)
            order_dict['payment_proof'] = order.payment_proof
            order_dict['rider_vehicle'] = order.assigned_rider.vehicle_type if order.assigned_rider else None

            if order.created_at:
                order_dict['date_formatted'] = _fmt_pht(order.created_at, '%Y-%m-%d')
                order_dict['time_formatted'] = _fmt_pht(order.created_at, '%I:%M %p').lstrip('0')
                order_dict['datetime_formatted'] = _fmt_pht(order.created_at, '%b %d, %Y %I:%M %p')
            else:
                order_dict['date_formatted'] = ''
                order_dict['time_formatted'] = ''
                order_dict['datetime_formatted'] = ''

            orders_data.append(order_dict)

        today = datetime.now(PHT).date()
        order_stats = {
            'total': len(orders_data),
            'today': sum(
                1
                for order in orders
                if order.created_at and _fmt_pht(order.created_at, '%Y-%m-%d') == today.strftime('%Y-%m-%d')
            ),
            'pending': sum(1 for order in orders if order.status == 'pending'),
            'payment_review': sum(1 for order in orders if order.payment_status == 'pending_verification'),
            'preparing': sum(1 for order in orders if order.status in ['accepted', 'preparing']),
            'on_delivery': sum(1 for order in orders if order.status == 'on_delivery'),
            'delivered': sum(1 for order in orders if order.status == 'delivered'),
            'completed': sum(1 for order in orders if order.status == 'completed'),
            'cancelled': sum(1 for order in orders if order.status == 'cancelled'),
            'revenue': float(sum(
                float(od.get('display_total') or od.get('total_amount') or 0)
                for od in orders_data
                if od.get('status') in ['delivered', 'completed']
            ))
        }

        riders_data = []
        for rider in available_riders:
            riders_data.append({
                'id': rider.id,
                'name': rider.user.full_name if rider.user else 'Rider',
                'vehicle': rider.vehicle_type,
                'is_active': rider.is_active
            })

        return {
            'orders': orders_data,
            'store': store.to_dict(),
            'order_stats': order_stats,
            'today_str': today.strftime('%Y-%m-%d'),
            'available_riders': riders_data,
        }

    try:
        page_data = _with_db_retry(_load_page)
    except OperationalError:
        current_app.logger.exception('seller_orders failed after DB retry')
        flash('Could not load orders — database connection dropped. Please try again.', 'error')
        return redirect(url_for('templates.seller_dashboard'))

    if not page_data:
        return redirect(url_for('templates.dashboard'))

    return render_template('seller_orders.html', **page_data)


def _customer_account_contact(customer):
    """Return the customer's signup contact (email or phone) for seller UIs."""
    from app.utils.phone_utils import customer_account_contact
    return customer_account_contact(customer)


def _attach_seller_order_customer_contact(order_dict, customer):
    contact = _customer_account_contact(customer)
    order_dict['customer_phone'] = customer.phone if customer else None
    order_dict['customer_email'] = (
        None if (not customer or contact['is_phone']) else getattr(customer, 'email', None)
    )
    order_dict['customer_contact'] = contact['value']
    order_dict['customer_contact_label'] = contact['label']
    return order_dict


def _order_amounts_including_addons(order):
    """Recompute subtotal/total from line items so structured add-ons are included."""
    items_sub = 0.0
    for item in (order.items or []):
        items_sub += float(item.price or 0) * int(item.quantity or 0)
        items_sub += float(item.addons_total or 0)
    delivery = float(order.delivery_fee or 0)
    api_sub = float(order.subtotal_amount or 0)
    api_total = float(order.total_amount or 0)
    if order.items:
        # Prefer item lines when they exceed a stale API subtotal (missing add-ons)
        sub = items_sub if items_sub >= api_sub - 0.009 else api_sub
        total = sub + delivery
        return sub, delivery, total
    return api_sub, delivery, api_total if api_total > 0 else (api_sub + delivery)


def _apply_order_display_totals(order, order_dict):
    sub, delivery, total = _order_amounts_including_addons(order)
    order_dict['subtotal_amount'] = sub
    order_dict['delivery_fee'] = delivery
    order_dict['total_amount'] = total
    order_dict['display_subtotal'] = sub
    order_dict['display_total'] = total
    return order_dict


def _serialize_seller_order_for_template(order):
    order_dict = order.to_dict()
    order_dict['items'] = [item.to_dict() for item in order.items]
    order_dict['items_count'] = sum(item.quantity for item in order.items)
    _attach_seller_order_customer_contact(order_dict, order.customer)
    _apply_order_display_totals(order, order_dict)
    order_dict['payment_proof'] = order.payment_proof
    order_dict['rider_vehicle'] = order.assigned_rider.vehicle_type if order.assigned_rider else None
    if order.created_at:
        order_dict['date_formatted'] = _fmt_pht(order.created_at, '%Y-%m-%d')
        order_dict['time_formatted'] = _fmt_pht(order.created_at, '%I:%M %p').lstrip('0')
        order_dict['datetime_formatted'] = _fmt_pht(order.created_at, '%b %d, %Y %I:%M %p')
    else:
        order_dict['date_formatted'] = ''
        order_dict['time_formatted'] = ''
        order_dict['datetime_formatted'] = ''
    return order_dict


@templates_bp.route('/api/seller/notifications', methods=['GET'])
def seller_notifications_api():
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session.get('user_id')
    notifications = Notification.query.filter_by(user_id=user_id)\
        .order_by(Notification.created_at.desc()).limit(20).all()
    unread_count = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    return jsonify({
        'notifications': [n.to_dict() for n in notifications],
        'unread_count': unread_count,
    }), 200


@templates_bp.route('/api/seller/notifications/read-all', methods=['POST'])
def seller_notifications_read_all_api():
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session.get('user_id')
    Notification.query.filter_by(user_id=user_id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True}), 200


@templates_bp.route('/api/seller/notifications/<int:notif_id>/read', methods=['POST'])
def seller_notification_read_api(notif_id):
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session.get('user_id')
    notif = Notification.query.filter_by(id=notif_id, user_id=user_id).first()
    if notif:
        notif.is_read = True
        db.session.commit()
    return jsonify({'success': True}), 200


@templates_bp.route('/api/seller/orders/<int:order_id>', methods=['GET'])
def seller_order_details_api(order_id):
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401
    _ensure_order_fulfillment_columns()

    store = Store.query.filter_by(seller_id=session['user_id']).first()
    if not store:
        return jsonify({'error': 'No active store found'}), 404

    order = (
        Order.query.options(
            selectinload(Order.items).joinedload(OrderItem.product).selectinload(Product.images),
            selectinload(Order.items).joinedload(OrderItem.variant),
            selectinload(Order.items).selectinload(OrderItem.addons),
            joinedload(Order.customer),
            joinedload(Order.assigned_rider).joinedload(Rider.user),
        )
        .filter_by(id=order_id, store_id=store.id)
        .first()
    )
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    return jsonify(_serialize_seller_order_for_template(order)), 200


@templates_bp.route('/api/seller/orders/<int:order_id>/status', methods=['PUT'])
def seller_order_status_api(order_id):
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401

    if not _ensure_order_fulfillment_columns():
        return jsonify({'error': 'Order fulfillment columns are not ready yet. Please refresh and try again.'}), 503
    store = Store.query.filter_by(seller_id=session['user_id']).first()
    if not store:
        return jsonify({'error': 'No active store found'}), 404

    order = Order.query.filter_by(id=order_id, store_id=store.id).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    if request.content_type and request.content_type.startswith('multipart/form-data'):
        data = request.form or {}
    else:
        data = request.get_json() or {}
    new_status = data.get('status')
    allowed_statuses = {'pending', 'accepted', 'preparing', 'done_preparing', 'on_delivery', 'delivered', 'cancelled'}

    if new_status not in allowed_statuses:
        return jsonify({'error': 'Invalid status'}), 400

    if new_status == 'done_preparing':
        proof_file = request.files.get('finished_product_image')
        if not proof_file or not proof_file.filename:
            return jsonify({'error': 'Finished product image is required before marking done preparing.'}), 400
        upload_result = upload_to_cloudinary(
            proof_file,
            folder=f"e-flowers/orders/{order.id}/done-preparing",
            transformation=current_app.config.get('CLOUDINARY_PRESETS', {}).get('product', {})
        )
        if not upload_result.get('success'):
            raw_error = str(upload_result.get('error', 'Failed to upload finished product image'))
            if 'File size too large' in raw_error:
                return jsonify({'error': 'Finished product image is too large. Maximum file size is 10MB.'}), 400
            return jsonify({'error': raw_error}), 400
        if order.done_preparing_proof_public_id:
            delete_from_cloudinary(order.done_preparing_proof_public_id)
        order.done_preparing_proof = secure_filename(proof_file.filename)
        order.done_preparing_proof_public_id = upload_result.get('public_id')
        order.done_preparing_proof_url = upload_result.get('url')

    previous_status = order.status
    if new_status == 'cancelled' and previous_status != 'cancelled':
        # Ensure add-on rows are loaded before stock restore / history audit
        _ = [(item.addons, item.product, item.variant) for item in (order.items or [])]
        order.restore_stock_on_cancel(session['user_id'])

    order.set_status(new_status)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Order status updated',
        'order': _serialize_seller_order_for_template(order)
    }), 200


@templates_bp.route('/api/seller/orders/<int:order_id>/verify-payment', methods=['PUT'])
def seller_order_verify_payment_api(order_id):
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401

    store = Store.query.filter_by(seller_id=session['user_id']).first()
    if not store:
        return jsonify({'error': 'No active store found'}), 404

    order = Order.query.filter_by(id=order_id, store_id=store.id).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    payment_status = (order.payment_status or '').lower()
    if payment_status == 'cod_pending':
        # COD approval flow: no receipt required, seller confirms and moves to preparing.
        order.payment_status = 'cod_approved'
        order.set_status('preparing')
    else:
        if not order.payment_proof_url:
            return jsonify({'error': 'No payment proof uploaded'}), 400
        # GCash verification flow.
        order.payment_status = 'verified'
        order.set_status('preparing')
    db.session.commit()

    current_app.logger.info(f"Order #{order_id} payment/COD approved, status changed to preparing")

    return jsonify({
        'success': True,
        'message': 'Order approved. Status changed to Preparing.',
        'order': _serialize_seller_order_for_template(order)
    }), 200


@templates_bp.route('/api/seller/orders/<int:order_id>/update-status', methods=['PUT'])
def seller_order_update_status(order_id):
    """Update order status (e.g., accepted → preparing)"""
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400

    new_status = data.get('status', '').strip()
    valid_statuses = ['preparing', 'on_delivery', 'delivered', 'cancelled']
    
    if new_status not in valid_statuses:
        return jsonify({'error': 'Invalid status'}), 400

    store = Store.query.filter_by(seller_id=session['user_id']).first()
    if not store:
        return jsonify({'error': 'No active store found'}), 404

    order = Order.query.filter_by(id=order_id, store_id=store.id).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    # Validate status transition
    current_status = order.status
    
    # Only allow transition from 'accepted' to 'preparing'
    if new_status == 'preparing' and current_status != 'accepted':
        return jsonify({'error': 'Order must be in accepted status to mark as preparing'}), 400

    if new_status == 'cancelled' and current_status != 'cancelled':
        _ = [(item.addons, item.product, item.variant) for item in (order.items or [])]
        order.restore_stock_on_cancel(session['user_id'])
    
    # Log status update
    order.set_status(new_status)
    db.session.commit()

    current_app.logger.info(f"Order #{order_id} status updated: {current_status} → {new_status}")

    return jsonify({
        'success': True,
        'message': f'Order status updated to {new_status.replace("_", " ").title()}',
        'order': _serialize_seller_order_for_template(order)
    }), 200

@templates_bp.route('/seller/riders')
def seller_riders():
    if session.get('role') != 'seller':
        return redirect(url_for('templates.dashboard'))
    return render_template('seller_riders.html')


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC RIDER EMAIL VERIFICATION (DEPRECATED — now uses OTP via seller dashboard)
# ═══════════════════════════════════════════════════════════════════════════════

@templates_bp.route('/verify-rider/<token>')
def verify_rider_token(token):
    """
    Deprecated — kept for backward compatibility with any old links still in inboxes.
    New flow uses OTP verified by the seller on the dashboard.
    """
    return render_template('rider_verify_result.html',
                           success=False,
                           message='This verification method is no longer supported. '
                                   'Please ask your seller to verify your account using the OTP code sent to your email.')


# ═══════════════════════════════════════════════════════════════════════════════
# RIDER PASSWORD SETUP (DEPRECATED — accounts now created with default password)
# ═══════════════════════════════════════════════════════════════════════════════

@templates_bp.route('/api/rider/set-password', methods=['POST'])
@limiter.limit('5 per minute')
def rider_set_password():
    """
    Deprecated — rider accounts are now created with a default password via OTP verification.
    """
    return jsonify({'error': 'This endpoint is no longer supported. Your account should already be created.'}), 410


# ═══════════════════════════════════════════════════════════════════════════════
# RIDER MANAGEMENT API (session-based, for web dashboard)
# ═══════════════════════════════════════════════════════════════════════════════

@templates_bp.route('/api/seller/riders', methods=['GET'])
def seller_riders_api():
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401

    store = _seller_portal_manageable_store(session['user_id'])
    if not store:
        return jsonify({'error': 'No active store found'}), 404

    riders = Rider.query.filter_by(store_id=store.id).all()

    riders_data = []
    for rider in riders:
        rider_dict = rider.to_dict()
        total_deliveries = Order.query.filter_by(rider_id=rider.id, status='delivered').count()
        active_delivery = Order.query.filter(
            Order.rider_id == rider.id,
            Order.status.in_(['on_delivery', 'accepted', 'preparing'])
        ).first()
        rider_dict['total_deliveries'] = total_deliveries
        rider_dict['has_active_delivery'] = active_delivery is not None
        rider_dict['active_order_id'] = active_delivery.id if active_delivery else None
        riders_data.append(rider_dict)

    pending_otps = RiderOTP.query.filter_by(
        store_id=store.id, is_verified=False
    ).filter(RiderOTP.expires_at > datetime.utcnow()).all()

    return jsonify({
        'success': True,
        'riders': riders_data,
        'pending_invitations': [otp.to_dict() for otp in pending_otps],
        'stats': {
            'total': sum(1 for r in riders if not r.is_archived),
            'active': sum(1 for r in riders if r.is_active and not r.is_archived),
            'inactive': sum(1 for r in riders if (not r.is_active) and not r.is_archived)
        }
    }), 200


@templates_bp.route('/api/seller/riders', methods=['POST'])
def seller_invite_rider_api():
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']
    user = User.query.get(user_id)
    store = _seller_portal_manageable_store(user_id)
    if not store:
        return jsonify({'error': 'No active store found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400

    full_name = (data.get('full_name') or '').strip()
    vehicle_type = data.get('vehicle_type', '')
    license_plate = (data.get('license_plate') or '').strip()
    from app.utils.otp_delivery import deliver_otp
    from app.utils.phone_utils import parse_email_or_phone_identifier

    if not full_name:
        return jsonify({'error': 'Full name is required'}), 400

    raw_id = data.get('identifier')
    if raw_id is None or str(raw_id).strip() == '':
        legacy_email = (data.get('email') or '').strip()
        legacy_phone = (data.get('phone') or '').strip()
        if legacy_email and legacy_phone:
            return jsonify({
                'error': 'Use either an email or a phone number — not both.',
            }), 400
        raw_id = legacy_phone or legacy_email or ''

    parsed, parse_err = parse_email_or_phone_identifier(raw_id)
    if parse_err:
        return jsonify({'error': parse_err}), 400

    email = parsed['email']
    phone = parsed['phone']
    channel = parsed['otp_channel']
    login_id = parsed['login_id']

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        existing_rider = Rider.query.filter_by(user_id=existing_user.id, store_id=store.id).first()
        if existing_rider:
            return jsonify({
                'error': 'This contact is already registered as a rider for your store',
            }), 409

    existing_otp = RiderOTP.query.filter_by(
        email=email, store_id=store.id, is_verified=False
    ).filter(RiderOTP.expires_at > datetime.utcnow()).first()
    if existing_otp:
        return jsonify({'error': 'An invitation is already pending for this contact.'}), 409

    from app.utils.email_helper import generate_otp_code, send_rider_otp_email
    from app.utils.otp_delivery import sync_plain_otp_record
    otp_code = generate_otp_code()

    rider_otp = RiderOTP(
        email=email,
        verification_token=otp_code,
        rider_data={
            'full_name': full_name,
            'phone': phone,
            'vehicle_type': vehicle_type,
            'license_plate': license_plate,
            'otp_channel': channel,
            'login_id': login_id,
        },
        store_id=store.id,
        created_by=user_id,
        expires_at=datetime.utcnow() + timedelta(minutes=10)
    )
    db.session.add(rider_otp)
    db.session.commit()

    ok, fail, meta = deliver_otp(
        channel,
        otp_code=otp_code,
        email=email,
        phone=phone,
        email_sender_fn=send_rider_otp_email,
        email_sender_kwargs={
            'store_name': store.name,
            'seller_name': user.full_name,
        },
        expiry_minutes=10,
        sms_purpose='rider verification',
    )
    if not ok:
        return jsonify({'error': (fail or {}).get('error') or 'Failed to send OTP.'}), 500
    sync_plain_otp_record(rider_otp, meta, otp_code)

    dest = meta.get('destination_masked') or login_id
    return jsonify({
        'success': True,
        'message': f'OTP sent to {dest}. Ask the rider for the 6-digit code.',
        'otp_id': rider_otp.id,
        'otp_channel': channel,
        'destination_masked': dest,
    }), 201


@templates_bp.route('/api/seller/riders/resend-invitation', methods=['POST'])
def seller_resend_rider_invitation_api():
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']
    user = User.query.get(user_id)
    store = _seller_portal_manageable_store(user_id)
    if not store:
        return jsonify({'error': 'No active store found'}), 404

    data = request.get_json()
    otp_id = data.get('otp_id')
    if not otp_id:
        return jsonify({'error': 'Invitation ID is required'}), 400

    rider_otp = RiderOTP.query.filter_by(id=otp_id, store_id=store.id, is_verified=False).first()
    if not rider_otp:
        return jsonify({'error': 'Invitation not found'}), 404

    from app.utils.email_helper import generate_otp_code, send_rider_otp_email
    from app.utils.otp_delivery import deliver_otp, normalize_otp_channel, sync_plain_otp_record
    new_otp = generate_otp_code()
    rider_otp.verification_token = new_otp
    rider_otp.expires_at = datetime.utcnow() + timedelta(minutes=10)
    db.session.commit()

    pending = rider_otp.rider_data or {}
    channel = normalize_otp_channel(pending.get('otp_channel'), default='email') or 'email'
    phone = pending.get('phone')
    ok, fail, meta = deliver_otp(
        channel,
        otp_code=new_otp,
        email=rider_otp.email,
        phone=phone,
        email_sender_fn=send_rider_otp_email,
        email_sender_kwargs={
            'store_name': store.name,
            'seller_name': user.full_name,
        },
        expiry_minutes=10,
        sms_purpose='rider verification',
    )
    if not ok:
        return jsonify({'error': (fail or {}).get('error') or 'Failed to resend OTP'}), 500
    sync_plain_otp_record(rider_otp, meta, new_otp)

    dest = meta.get('destination_masked') or rider_otp.email
    return jsonify({
        'success': True,
        'message': f'New OTP sent to {dest}',
        'otp_channel': channel,
        'destination_masked': dest,
    }), 200


@templates_bp.route('/api/seller/riders/verify-otp', methods=['POST'])
def seller_verify_rider_otp_api():
    """Seller verifies the OTP from the rider, creates the account with a default password"""
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']
    store = _seller_portal_manageable_store(user_id)
    if not store:
        return jsonify({'error': 'No active store found'}), 404

    data = request.get_json()
    otp_id = data.get('otp_id')
    otp_code = (data.get('otp_code') or '').strip()

    if not otp_id or not otp_code:
        return jsonify({'error': 'OTP ID and code are required'}), 400

    rider_otp = RiderOTP.query.filter_by(
        id=otp_id, store_id=store.id, is_verified=False
    ).first()

    if not rider_otp:
        return jsonify({'error': 'Invitation not found'}), 404

    if rider_otp.is_expired():
        return jsonify({'error': 'OTP has expired. Please resend a new one.'}), 400

    if rider_otp.verification_token != otp_code:
        return jsonify({'error': 'Invalid OTP code. Please try again.'}), 400

    # OTP is correct — create the rider account with a default password
    from app.utils.email_helper import generate_default_password, send_rider_credentials_email
    from app.utils.phone_utils import display_login_id, is_synthetic_account_email
    from app.utils.sms_helper import send_rider_credentials_sms

    rider_data = rider_otp.rider_data or {}
    account_email = rider_otp.email
    default_password = generate_default_password()
    login_id = rider_data.get('login_id') or display_login_id(
        email=account_email, phone=rider_data.get('phone')
    )

    # Find or create the User
    user_account = User.query.filter_by(email=account_email).first()

    if not user_account:
        user_account = User(
            full_name=rider_data['full_name'],
            email=account_email,
            phone=rider_data.get('phone'),
            role='rider',
            status='active'
        )
        user_account.set_password(default_password)
        db.session.add(user_account)
        db.session.flush()
    else:
        user_account.set_password(default_password)
        user_account.status = 'active'
        normalized_phone = _normalize_ph_mobile(rider_data.get('phone'))
        user_account.phone = normalized_phone if (normalized_phone and PH_MOBILE_REGEX.fullmatch(normalized_phone)) else None

    # Create Rider record if not exists
    existing_rider = Rider.query.filter_by(
        user_id=user_account.id, store_id=store.id
    ).first()

    if not existing_rider:
        new_rider = Rider(
            user_id=user_account.id,
            store_id=store.id,
            vehicle_type=rider_data.get('vehicle_type', ''),
            license_plate=rider_data.get('license_plate', ''),
            is_active=True
        )
        db.session.add(new_rider)

    # Mark OTP as verified and delete it
    rider_otp.is_verified = True
    db.session.delete(rider_otp)
    db.session.commit()

    credentials_channel = 'sms' if (
        is_synthetic_account_email(account_email) and rider_data.get('phone')
    ) else 'email'
    credentials_delivered = False
    if credentials_channel == 'sms':
        credentials_delivered = bool(send_rider_credentials_sms(
            phone=rider_data.get('phone'),
            full_name=rider_data['full_name'],
            default_password=default_password,
            store_name=store.name,
            login_id=login_id,
        ))
    else:
        credentials_delivered = bool(send_rider_credentials_email(
            recipient_email=account_email,
            full_name=rider_data['full_name'],
            default_password=default_password,
            store_name=store.name
        ))

    if credentials_delivered:
        message = (
            f'Rider account created for {rider_data["full_name"]}! '
            f'Credentials also sent to {login_id}.'
        )
    else:
        message = (
            f'Rider account created for {rider_data["full_name"]}! '
            f'Share the temporary password below with the rider '
            f'(auto-send to {login_id} failed).'
        )

    return jsonify({
        'success': True,
        'message': message,
        'full_name': rider_data['full_name'],
        'login_id': login_id,
        'temporary_password': default_password,
        'credentials_channel': credentials_channel,
        'credentials_delivered': credentials_delivered,
    }), 201


@templates_bp.route('/api/seller/riders/cancel-invitation', methods=['POST'])
def seller_cancel_rider_invitation_api():
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401

    store = _seller_portal_manageable_store(session['user_id'])
    if not store:
        return jsonify({'error': 'No active store found'}), 404

    data = request.get_json()
    otp_id = data.get('otp_id')
    if not otp_id:
        return jsonify({'error': 'OTP ID is required'}), 400

    rider_otp = RiderOTP.query.filter_by(id=otp_id, store_id=store.id, is_verified=False).first()
    if not rider_otp:
        return jsonify({'error': 'Invitation not found'}), 404

    db.session.delete(rider_otp)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Invitation cancelled'}), 200


@templates_bp.route('/api/seller/riders/<int:rider_id>', methods=['GET'])
def seller_rider_detail_api(rider_id):
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401

    store = _seller_portal_manageable_store(session['user_id'])
    if not store:
        return jsonify({'error': 'No active store found'}), 404

    rider = Rider.query.filter_by(id=rider_id, store_id=store.id).first()
    if not rider:
        return jsonify({'error': 'Rider not found'}), 404

    rider_dict = rider.to_dict()
    total_deliveries = Order.query.filter_by(rider_id=rider.id, status='delivered').count()
    recent_orders = Order.query.filter_by(rider_id=rider.id).order_by(Order.created_at.desc()).limit(10).all()

    rider_dict['total_deliveries'] = total_deliveries
    rider_dict['recent_orders'] = [o.to_dict() for o in recent_orders]

    return jsonify({'success': True, 'rider': rider_dict}), 200


@templates_bp.route('/api/seller/riders/<int:rider_id>', methods=['PUT'])
def seller_update_rider_api(rider_id):
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401

    store = _seller_portal_manageable_store(session['user_id'])
    if not store:
        return jsonify({'error': 'No active store found'}), 404

    rider = Rider.query.filter_by(id=rider_id, store_id=store.id).first()
    if not rider:
        return jsonify({'error': 'Rider not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400

    if 'vehicle_type' in data:
        rider.vehicle_type = data['vehicle_type']
    if 'license_plate' in data:
        rider.license_plate = data['license_plate']
    if 'is_active' in data:
        rider.is_active = bool(data['is_active'])

    if rider.user:
        if 'full_name' in data:
            rider.user.full_name = data['full_name']
        if 'phone' in data:
            normalized_phone = _normalize_ph_mobile(data.get('phone'))
            if normalized_phone and not PH_MOBILE_REGEX.fullmatch(normalized_phone):
                return jsonify({'error': 'Please enter a valid Philippine mobile number (e.g., 09171234567 or +639171234567).'}), 400
            rider.user.phone = normalized_phone

    rider.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'success': True, 'message': 'Rider updated successfully', 'rider': rider.to_dict()}), 200


@templates_bp.route('/api/seller/riders/<int:rider_id>/reset-password', methods=['POST'])
def seller_reset_rider_password_api(rider_id):
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401

    store = _seller_portal_manageable_store(session['user_id'])
    if not store:
        return jsonify({'error': 'No active store found'}), 404

    rider = Rider.query.filter_by(id=rider_id, store_id=store.id).first()
    if not rider or not rider.user:
        return jsonify({'error': 'Rider not found'}), 404

    from app.utils.email_helper import generate_default_password, send_rider_credentials_email
    from app.utils.phone_utils import display_login_id, is_synthetic_account_email
    from app.utils.sms_helper import send_rider_credentials_sms

    default_password = generate_default_password()
    rider.user.set_password(default_password)
    rider.user.status = 'active'
    db.session.commit()

    login_id = display_login_id(email=rider.user.email, phone=rider.user.phone)
    credentials_channel = 'sms' if (
        is_synthetic_account_email(rider.user.email) and rider.user.phone
    ) else 'email'
    credentials_delivered = False
    if credentials_channel == 'sms':
        credentials_delivered = bool(send_rider_credentials_sms(
            phone=rider.user.phone,
            full_name=rider.user.full_name,
            default_password=default_password,
            store_name=store.name,
            login_id=login_id,
        ))
    else:
        credentials_delivered = bool(send_rider_credentials_email(
            recipient_email=rider.user.email,
            full_name=rider.user.full_name,
            default_password=default_password,
            store_name=store.name,
        ))

    return jsonify({
        'success': True,
        'message': 'Temporary password reset. Share it with the rider.',
        'full_name': rider.user.full_name,
        'login_id': login_id,
        'temporary_password': default_password,
        'credentials_channel': credentials_channel,
        'credentials_delivered': credentials_delivered,
    }), 200


@templates_bp.route('/api/seller/riders/<int:rider_id>/status', methods=['PUT'])
def seller_rider_status_api(rider_id):
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401

    store = _seller_portal_manageable_store(session['user_id'])
    if not store:
        return jsonify({'error': 'No active store found'}), 404

    rider = Rider.query.filter_by(id=rider_id, store_id=store.id).first()
    if not rider:
        return jsonify({'error': 'Rider not found'}), 404

    data = request.get_json()
    if data and 'is_active' in data:
        rider.is_active = bool(data['is_active'])
        if rider.is_active:
            rider.is_archived = False

    rider.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Rider {"activated" if rider.is_active else "deactivated"}',
        'rider': rider.to_dict()
    }), 200


@templates_bp.route('/api/seller/riders/<int:rider_id>', methods=['DELETE'])
def seller_delete_rider_api(rider_id):
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401

    store = _seller_portal_manageable_store(session['user_id'])
    if not store:
        return jsonify({'error': 'No active store found'}), 404

    rider = Rider.query.filter_by(id=rider_id, store_id=store.id).first()
    if not rider:
        return jsonify({'error': 'Rider not found'}), 404

    active_delivery = Order.query.filter(
        Order.rider_id == rider.id,
        Order.status.in_(['on_delivery', 'accepted', 'preparing'])
    ).first()
    if active_delivery:
        return jsonify({'error': 'Cannot remove rider with active deliveries'}), 400

    # Soft-delete behavior: archive rider by deactivating instead of permanent removal
    rider.is_active = False
    rider.is_archived = True
    rider.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Rider archived successfully (set to inactive)',
        'rider': rider.to_dict(),
        'archived': True
    }), 200


# ─── Helper ───────────────────────────────────────────────────────────────────

def _get_seller_store():
    """Return the seller's manageable store (active or self-hidden inactive)."""
    return _seller_portal_manageable_store(session.get('user_id'))

@templates_bp.route('/seller/pos')
@seller_required
def seller_pos():
    """
    Render the POS interface with new category logic.
    Passes all available, in-stock products for the seller's store,
    organized by main categories and store-specific subcategories.
    """
    store = _get_seller_store()

    if not store:
        # Seller has no active store — bounce back with a flash
        flash('Please set up your store first.', 'warning')
        return redirect(url_for('templates.dashboard'))

    # Get all main categories for filtering
    from app.models import Category, StoreCategory
    
    # Get all main categories (global)
    main_categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()
    
    # Get store-specific subcategories for this store
    store_categories = StoreCategory.query.filter_by(
        store_id=store.id,
        is_active=True
    ).order_by(StoreCategory.sort_order).all()
    
    # Fetch all products for this store, ordered by main category then name
    products_query = (
        Product.query
        .options(
            selectinload(Product.images),
            selectinload(Product.variants),
            selectinload(Product.addon_groups).selectinload(ProductAddonGroup.options),
            joinedload(Product.main_category),
            joinedload(Product.store_category),
        )
        .filter_by(store_id=store.id, is_archived=False)
        .join(Category, Product.main_category_id == Category.id)
        .order_by(Category.sort_order.asc(), Product.name.asc())
        .all()
    )
    
    # Convert products to serializable format using to_dict() method
    # This will automatically include variants as dictionaries via ProductVariant.to_dict()
    products = []
    for product in products_query:
        product_dict = product.to_dict()
        # Add main category name for filtering
        if product.main_category:
            product_dict['main_category_name'] = product.main_category.name
            product_dict['main_category_slug'] = product.main_category.slug
            product_dict['main_category_id'] = product.main_category.id
        # Add store subcategory info if exists
        if product.store_category:
            product_dict['store_category_name'] = product.store_category.name
            product_dict['store_category_id'] = product.store_category.id
        products.append(product_dict)

    from app.addon_helpers import ymal_addon_option_dicts
    ymal_addon_options = ymal_addon_option_dicts(products_query[0]) if products_query else []
    
    # Organize products by main category for easier template access
    products_by_category = {}
    for cat in main_categories:
        cat_products = [p for p in products if p.get('main_category_id') == cat.id]
        if cat_products:
            products_by_category[cat.name] = cat_products
    
    # Group subcategories by main category
    subcategories_by_main = {}
    for sc in store_categories:
        if sc.main_category_id not in subcategories_by_main:
            subcategories_by_main[sc.main_category_id] = []
        subcategories_by_main[sc.main_category_id].append(sc.to_dict())

    return render_template(
        'seller_pos.html',
        store=store,
        products=products,
        main_categories=main_categories,
        store_categories=store_categories,
        products_by_category=products_by_category,
        subcategories_by_main=subcategories_by_main,
        ymal_addon_options=ymal_addon_options,
    )

@templates_bp.route('/seller/pos/order', methods=['POST'])
@seller_required
def pos_create_order():
    """
    Create a POS order and update stock quantities.
    Supports product variants and discounts.
    Returns JSON with the created order id.
    """
    store = _get_seller_store()
    if not store:
        return jsonify({'error': 'No active store found for your account.'}), 403

    user_id = session.get('user_id')
    
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Invalid JSON payload.'}), 400

    items_payload = data.get('items', [])
    if not items_payload:
        return jsonify({'error': 'Order must contain at least one item.'}), 400

    # ── Validate every item before touching the DB ────────────────────────────
    from app.addon_helpers import (
        resolve_structured_addon_selections,
        structured_addons_subtotal,
        decrement_addon_option_stock,
    )

    validated_items = []
    for entry in items_payload:
        product_id = entry.get('product_id')
        variant_id = entry.get('variant_id')  # May be None
        quantity   = int(entry.get('quantity', 1))
        unit_price = Decimal(str(entry.get('price', 0)))
        addon_raw  = entry.get('addons') or entry.get('addon_option_ids') or []

        if quantity < 1:
            return jsonify({'error': f'Quantity must be at least 1 (product id {product_id}).'}), 400

        # Check if product exists and belongs to store
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            return jsonify({'error': f'Product #{product_id} not found in your store.'}), 404

        if not product.is_available:
            return jsonify({'error': f'"{product.name}" is currently unavailable.'}), 400

        addons_only = bool(entry.get('addons_only'))

        # If variant_id is provided, validate variant
        if not addons_only and variant_id:
            variant = ProductVariant.query.filter_by(id=variant_id, product_id=product_id).first()
            if not variant:
                return jsonify({'error': f'Variant #{variant_id} not found for product "{product.name}".'}), 404
            
            if not variant.is_available:
                return jsonify({'error': f'Variant "{variant.name}" for "{product.name}" is currently unavailable.'}), 400
            
            if variant.stock_quantity < quantity:
                return jsonify({
                    'error': (
                        f'Insufficient stock for "{product.name}" - {variant.name}. '
                        f'Available: {variant.stock_quantity}, requested: {quantity}.'
                    )
                }), 400
        elif not addons_only:
            # Check main product stock
            if product.stock_quantity < quantity:
                return jsonify({
                    'error': (
                        f'Insufficient stock for "{product.name}". '
                        f'Available: {product.stock_quantity}, requested: {quantity}.'
                    )
                }), 400

        addon_lines, addon_err = resolve_structured_addon_selections(
            product, addon_raw, quantity_per_option=quantity
        )
        if addon_err:
            return addon_err

        if addons_only and not addon_lines:
            return jsonify({'error': 'Add-on only lines must include add-ons.'}), 400

        validated_items.append({
            'product': product,
            'variant_id': None if addons_only else variant_id,
            'quantity': quantity,
            'price': unit_price,
            'addon_lines': addon_lines or [],
            'addons_only': addons_only,
        })

    # ── Create POS order ───────────────────────────────────────────────────────
    _ensure_pos_order_item_line_columns()

    customer_name = data.get('customer_name', '').strip()
    customer_contact = data.get('customer_contact')
    payment_method = data.get('payment_method', 'cash')
    if payment_method not in ['cash', 'gcash']:
        return jsonify({'error': 'Invalid payment method. Allowed: cash, gcash'}), 400
    amount_given = Decimal(str(data.get('amount_given', 0)))
    change_amount = Decimal(str(data.get('change_amount', 0)))
    
    # ===== HANDLE DISCOUNT =====
    discount = Decimal(str(data.get('discount', 0)))
    if discount < 0:
        return jsonify({'error': 'Discount cannot be negative'}), 400
    # ===========================

    # Calculate subtotal (product lines + structured add-ons)
    subtotal = Decimal('0')
    for item in validated_items:
        if item.get('addons_only'):
            # Add-on-only: charge from resolved addon lines (or client unit × qty)
            addons_total = structured_addons_subtotal(item.get('addon_lines'))
            if addons_total > 0:
                subtotal += addons_total
            else:
                subtotal += item['price'] * item['quantity']
        else:
            subtotal += item['price'] * item['quantity']
            subtotal += structured_addons_subtotal(item.get('addon_lines'))
    total = subtotal - discount
    
    # Validate total is not negative
    if total < 0:
        return jsonify({'error': 'Discount cannot exceed subtotal'}), 400

    # Create the order with discount
    pos_order = POSOrder(
        store_id=store.id,
        total_amount=total,
        amount_given=amount_given,
        change_amount=change_amount,
        payment_method=payment_method,
        customer_name=customer_name,
        customer_contact=customer_contact,
        is_seen_by_seller=False,
        discount=discount  # Save the discount
    )
    db.session.add(pos_order)
    db.session.flush()  # Assign ID to pos_order without committing

    # ── Add items and update stock ─────────────────────────────────────────────
    try:
        for item in validated_items:
            addons_total = structured_addons_subtotal(item.get('addon_lines'))
            qty = Decimal(item['quantity'])
            extra_per_unit = (addons_total / qty) if qty else Decimal('0')

            line_name = None
            line_image_url = None
            addon_option_id = None
            product_id_for_row = item['product'].id
            addon_lines = item.get('addon_lines') or []

            if item.get('addons_only') and addon_lines:
                names = [str(l.get('name') or '').strip() for l in addon_lines if l.get('name')]
                line_name = ', '.join(n for n in names if n) or 'Add-on'
                first = addon_lines[0]
                line_image_url = (first.get('image_url') or '').strip() or None
                opt = first.get('option')
                if opt is not None:
                    addon_option_id = opt.id
                    if getattr(opt, 'group', None) and opt.group.product_id:
                        product_id_for_row = opt.group.product_id
                    if not line_image_url and getattr(opt, 'image_url', None):
                        line_image_url = opt.image_url
            elif addon_lines and not item.get('addons_only'):
                # Flower/variant line that also includes add-ons: keep product name;
                # append add-on names for clarity in order history
                addon_names = [str(l.get('name') or '').strip() for l in addon_lines if l.get('name')]
                addon_names = [n for n in addon_names if n]
                if addon_names:
                    base = item['product'].name
                    if item.get('variant_id'):
                        v = ProductVariant.query.get(item['variant_id'])
                        if v:
                            base = f'{base} - {v.name}'
                    line_name = f"{base} (+ {', '.join(addon_names)})"

            if item.get('addons_only'):
                # Unit price is the add-on price. Prefer client price; fall back to resolved lines.
                unit_price = item['price'] if item['price'] and item['price'] > 0 else extra_per_unit
                if (not unit_price or unit_price <= 0) and addon_lines:
                    unit_price = Decimal(str(addon_lines[0].get('price') or 0))
            else:
                # Flower/variant line: bake structured add-on cost into unit price for history totals
                unit_price = item['price'] + extra_per_unit

            pos_item = POSOrderItem(
                pos_order=pos_order,
                product_id=product_id_for_row,
                variant_id=item['variant_id'],
                quantity=item['quantity'],
                price=unit_price,
                line_name=line_name,
                line_image_url=line_image_url,
                addon_option_id=addon_option_id,
            )
            db.session.add(pos_item)

            # Update stock based on variant or product (skip for add-on-only lines)
            if not item.get('addons_only'):
                if item['variant_id']:
                    variant = ProductVariant.query.get(item['variant_id'])
                    variant.stock_quantity -= item['quantity']
                    
                    # Create StockReduction record for variant
                    stock_reduction = StockReduction(
                        product_id=item['product'].id,
                        variant_id=item['variant_id'],
                        reduction_amount=item['quantity'],
                        reason='pos_sale',
                        reason_notes=f'POS Sale - Order #{pos_order.id}',
                        reduced_by=user_id
                    )
                    db.session.add(stock_reduction)
                else:
                    item['product'].stock_quantity -= item['quantity']
                    
                    # Create StockReduction record for main product
                    stock_reduction = StockReduction(
                        product_id=item['product'].id,
                        variant_id=None,
                        reduction_amount=item['quantity'],
                        reason='pos_sale',
                        reason_notes=f'POS Sale - Order #{pos_order.id}',
                        reduced_by=user_id
                    )
                    db.session.add(stock_reduction)

            # Structured add-ons: include cost in order total (already) and decrement stock
            if item.get('addon_lines'):
                decrement_addon_option_stock(
                    item['addon_lines'],
                    user_id=user_id,
                    reason='pos_sale',
                    reason_notes=f'POS Sale add-on - Order #{pos_order.id}',
                )

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error creating POS order: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to process order: {str(e)}'}), 500

    return jsonify({
        'success': True,
        'pos_order_id': pos_order.id,
        'message': 'Order processed successfully.'
    }), 201

@templates_bp.route('/api/seller/pos/next-order-id')
@seller_required
def pos_next_order_id():
    store = _get_seller_store()
    if not store:
        return jsonify({'error': 'No active store found'}), 403
    
    last_order = POSOrder.query.filter_by(store_id=store.id).order_by(POSOrder.id.desc()).first()
    next_id = (last_order.id + 1) if last_order else 1000
    
    return jsonify({'next_id': next_id})


@templates_bp.route('/seller/pos/orders')
@seller_required
def pos_orders():
    store = _get_seller_store()
    if not store:
        flash('Please set up your store first.', 'warning')
        return redirect(url_for('templates.dashboard'))

    _ensure_pos_order_item_line_columns()

    # Mark unseen POS orders as seen once seller opens POS order history.
    POSOrder.query.filter_by(store_id=store.id, is_seen_by_seller=False).update(
        {'is_seen_by_seller': True}
    )
    db.session.commit()

    import pytz
    ph_tz = pytz.timezone('Asia/Manila')
    now_ph = datetime.now(ph_tz)
    today = now_ph.date()
    ph_date = db.func.date(POSOrder.created_at + db.text("INTERVAL '8 hours'"))

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    date_filter = request.args.get('date', 'today')
    payment_filter = request.args.get('payment', 'all')
    search_query = request.args.get('search', '')

    query = POSOrder.query.filter_by(store_id=store.id)

    if date_filter == 'today':
        query = query.filter(ph_date == today)
    elif date_filter == 'yesterday':
        yesterday = today - timedelta(days=1)
        query = query.filter(ph_date == yesterday)
    elif date_filter == 'this_week':
        start_of_week = today - timedelta(days=today.weekday())
        query = query.filter(ph_date >= start_of_week)
    elif date_filter == 'this_month':
        start_of_month = today.replace(day=1)
        query = query.filter(ph_date >= start_of_month)
    elif date_filter == 'custom':
        start_date_str = request.args.get('start_date', '')
        end_date_str = request.args.get('end_date', '')
        if start_date_str:
            try:
                query = query.filter(ph_date >= datetime.strptime(start_date_str, '%Y-%m-%d').date())
            except ValueError:
                pass
        if end_date_str:
            try:
                query = query.filter(ph_date <= datetime.strptime(end_date_str, '%Y-%m-%d').date())
            except ValueError:
                pass

    if payment_filter != 'all':
        query = query.filter_by(payment_method=payment_filter)

    if search_query:
        query = query.filter(
            db.or_(
                POSOrder.customer_name.ilike(f'%{search_query}%'),
                POSOrder.customer_contact.ilike(f'%{search_query}%'),
                POSOrder.id.cast(db.String).ilike(f'%{search_query}%')
            )
        )

    query = query.order_by(POSOrder.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    orders_data = []
    for order in pagination.items:
        d = order.to_dict()
        if order.created_at:
            utc_dt = pytz.utc.localize(order.created_at)
            ph_dt = utc_dt.astimezone(ph_tz)
            d['created_at_date'] = ph_dt.strftime('%Y-%m-%d')
            d['created_at'] = ph_dt.isoformat()
        else:
            d['created_at_date'] = None
        orders_data.append(d)

    summary = {
        'total_orders': POSOrder.query.filter_by(store_id=store.id).count(),
        'total_revenue': float(db.session.query(db.func.sum(POSOrder.total_amount))
            .filter(POSOrder.store_id == store.id).scalar() or 0),
        'cash_orders': POSOrder.query.filter_by(store_id=store.id, payment_method='cash').count(),
        'gcash_orders': POSOrder.query.filter_by(store_id=store.id, payment_method='gcash').count(),
        'card_orders': POSOrder.query.filter_by(store_id=store.id, payment_method='card').count(),
    }

    today_sales = float(db.session.query(db.func.sum(POSOrder.total_amount))
        .filter(POSOrder.store_id == store.id, ph_date == today).scalar() or 0)

    return render_template(
        'seller_pos_orders.html',
        store=store,
        orders=orders_data,
        pagination=pagination,
        summary=summary,
        today_sales=today_sales,
        current_filters={
            'date': date_filter,
            'payment': payment_filter,
            'search': search_query,
            'page': page
        }
    )


@templates_bp.route('/seller/pos/orders/<int:order_id>')
@seller_required
def pos_order_detail(order_id):
    """
    View details of a specific POS order.
    """
    store = _get_seller_store()
    if not store:
        flash('Please set up your store first.', 'warning')
        return redirect(url_for('templates.dashboard'))
    
    order = POSOrder.query.filter_by(id=order_id, store_id=store.id).first_or_404()
    
    return render_template(
        'seller_pos_order_detail.html',
        store=store,
        order=order.to_dict()
    )


@templates_bp.route('/seller/pos/orders/<int:order_id>/void', methods=['POST'])
@seller_required
def pos_void_order(order_id):
    """
    Void a POS order (admin only or within certain time limit).
    This reverses the stock changes.
    """
    store = _get_seller_store()
    if not store:
        return jsonify({'error': 'No active store found'}), 403
    
    order = POSOrder.query.filter_by(id=order_id, store_id=store.id).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    
    # Check if order can be voided (e.g., within 24 hours)
    time_limit = datetime.utcnow() - timedelta(hours=24)
    if order.created_at < time_limit:
        return jsonify({'error': 'Orders older than 24 hours cannot be voided'}), 400
    
    data = request.get_json(silent=True) or {}
    reason = data.get('reason', 'No reason provided')
    
    # Restore stock
    for item in order.items:
        if item.variant_id:
            variant = ProductVariant.query.get(item.variant_id)
            if variant:
                variant.stock_quantity += item.quantity
        else:
            product = Product.query.get(item.product_id)
            if product:
                product.stock_quantity += item.quantity
    
    # Mark order as voided - we'll add a status field if needed
    # For now, we'll just delete it, but better to add a 'status' field to POSOrder
    # order.status = 'voided'  # Add this field to POSOrder model
    
    # Log the void action in a separate table or just delete
    db.session.delete(order)
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Order voided successfully'
    })


# Optional: Add this to your POSOrder model if you want to keep voided orders
"""
Add to POSOrder model:
    status = db.Column(db.String(20), default='active')  # active, voided

Then modify the void function to:
    order.status = 'voided'
    db.session.commit()
"""


@templates_bp.route('/seller/pos/statistics')
@seller_required
def pos_statistics():
    """
    Get POS statistics for the seller's store.
    Returns JSON with sales data for charts.
    """
    store = _get_seller_store()
    if not store:
        return jsonify({'error': 'No active store found'}), 403
    
    # Get date range from query params
    days = request.args.get('days', 7, type=int)
    
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)
    
    # Get daily sales
    daily_sales = db.session.query(
        db.func.date(POSOrder.created_at).label('date'),
        db.func.count(POSOrder.id).label('order_count'),
        db.func.sum(POSOrder.total_amount).label('revenue')
    ).filter(
        POSOrder.store_id == store.id,
        db.func.date(POSOrder.created_at) >= start_date,
        db.func.date(POSOrder.created_at) <= end_date
    ).group_by(
        db.func.date(POSOrder.created_at)
    ).order_by(
        db.func.date(POSOrder.created_at)
    ).all()
    
    # Get payment method breakdown
    payment_breakdown = db.session.query(
        POSOrder.payment_method,
        db.func.count(POSOrder.id).label('count'),
        db.func.sum(POSOrder.total_amount).label('total')
    ).filter(
        POSOrder.store_id == store.id,
        db.func.date(POSOrder.created_at) >= start_date
    ).group_by(
        POSOrder.payment_method
    ).all()
    
    # Get top products
    top_products = db.session.query(
        Product.name,
        db.func.sum(POSOrderItem.quantity).label('total_quantity'),
        db.func.sum(POSOrderItem.quantity * POSOrderItem.price).label('total_revenue')
    ).join(
        POSOrderItem, POSOrderItem.product_id == Product.id
    ).join(
        POSOrder, POSOrder.id == POSOrderItem.pos_order_id
    ).filter(
        POSOrder.store_id == store.id,
        db.func.date(POSOrder.created_at) >= start_date
    ).group_by(
        Product.id
    ).order_by(
        db.desc('total_quantity')
    ).limit(10).all()
    
    return jsonify({
        'daily_sales': [{
            'date': str(row.date),
            'order_count': row.order_count,
            'revenue': float(row.revenue or 0)
        } for row in daily_sales],
        'payment_breakdown': [{
            'method': row.payment_method,
            'count': row.count,
            'total': float(row.total or 0)
        } for row in payment_breakdown],
        'top_products': [{
            'name': row.name,
            'quantity': row.total_quantity,
            'revenue': float(row.total_revenue or 0)
        } for row in top_products]
    })
'''
@templates_bp.route('/seller/pos/orders', methods=['GET'])
@seller_required
def pos_order_history():
    """
    DEPRECATED - Use /api/seller/pos/orders instead
    Keeping this commented out to avoid conflicts
    """
    return jsonify({'error': 'Use /api/seller/pos/orders instead'}), 410


'''



# ═════════════════════════════════════════════════════════════════════════════
# ANALYTICS + REPORTS — backed by app.utils.report_service
# ═════════════════════════════════════════════════════════════════════════════

def _resolve_report_store():
    """Return the seller's active store, or ``None`` if missing.

    Falls back to *any* store owned by the seller (so a brand-new store still
    in pending review can preview reports). Returns ``None`` only when the
    user truly has no store at all.
    """
    user_id = session.get('user_id')
    if not user_id:
        return None
    return (_seller_portal_manageable_store(user_id)
            or Store.query.filter_by(seller_id=user_id).first())


def _request_period_args():
    """Parse period args from request (used by both analytics + reports)."""
    period = (request.args.get('period') or request.form.get('period') or 'week').lower()
    fr = request.args.get('from') or request.form.get('from')
    to = request.args.get('to') or request.form.get('to')
    return period, fr, to


def _human_size(num_bytes: int) -> str:
    """Format bytes into a compact human-readable string."""
    size = float(num_bytes or 0)
    units = ['B', 'KB', 'MB', 'GB']
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(size)} {units[idx]}"
    return f"{size:.1f} {units[idx]}"


def _fmt_pht(dt: datetime, pattern: str = '%b %d, %Y %I:%M %p') -> str:
    """Format UTC-naive/aware datetimes in Philippine Time."""
    if not dt:
        return ''
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(PHT).strftime(pattern)


def _to_pht_iso(dt):
    """Serialize UTC-naive/aware datetimes as Asia/Manila ISO-8601 (+08:00)."""
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(PHT).isoformat()


def _ph_day_bounds_as_utc_naive(day):
    """PH calendar day [start, end] expressed as naive UTC for DB comparisons."""
    start_ph = PHT.localize(datetime.combine(day, datetime.min.time()))
    end_ph = PHT.localize(datetime.combine(day, datetime.max.time().replace(microsecond=0)))
    return (
        start_ph.astimezone(pytz.utc).replace(tzinfo=None),
        end_ph.astimezone(pytz.utc).replace(tzinfo=None),
    )


def _push_saved_report_entry(entry: dict) -> None:
    """Persist report metadata so it survives logout/login."""
    user_id = session.get('user_id')
    if not user_id:
        return

    if not _ensure_saved_reports_table():
        return

    row = SavedReport(
        user_id=user_id,
        name=entry.get('name') or 'Report',
        description=entry.get('description'),
        report_type=entry.get('type'),
        report_format=entry.get('format'),
        last_generated=entry.get('last_generated'),
        schedule=entry.get('schedule'),
        size=entry.get('size'),
    )
    db.session.add(row)
    db.session.commit()

    # Keep latest 30 entries per user.
    stale_rows = (SavedReport.query
                  .filter_by(user_id=user_id)
                  .order_by(SavedReport.created_at.desc(), SavedReport.id.desc())
                  .offset(30)
                  .all())
    if stale_rows:
        for stale in stale_rows:
            db.session.delete(stale)
        db.session.commit()


def _load_saved_reports_for_user(limit: int = 30):
    user_id = session.get('user_id')
    if not user_id:
        return []
    if not _ensure_saved_reports_table():
        return []
    rows = (SavedReport.query
            .filter_by(user_id=user_id)
            .order_by(SavedReport.created_at.desc(), SavedReport.id.desc())
            .limit(limit)
            .all())
    return [r.to_dict() for r in rows]


@templates_bp.route('/analytics')
def analytics():
    """Analytics dashboard — auto-switches between seller (per-store) and
    admin (platform-wide) modes based on session role.
    """
    if 'user_id' not in session:
        return redirect(url_for('templates.login'))

    period, fr, to = _request_period_args()

    if session.get('role') == 'admin':
        from app.utils.report_service import compute_admin_analytics
        ctx = compute_admin_analytics(period=period, custom_from=fr, custom_to=to)
        ctx['no_store'] = False
        ctx['is_admin'] = True
        return render_template('analytics.html', **ctx)

    store = _resolve_report_store()
    if not store:
        return render_template(
            'analytics.html',
            store=None,
            is_admin=False,
            period='week',
            period_label='—',
            totals={'revenue': 0, 'revenue_display': '₱0.00', 'orders': 0,
                    'avg_order': 0, 'avg_order_display': '₱0.00', 'new_customers': 0,
                    'all_customers': 0, 'all_products': 0, 'completed_orders': 0},
            deltas={'revenue_pct': None, 'orders_pct': None, 'avg_pct': None, 'new_pct': None},
            top_products=[], order_status={}, sales_by_category=[], peak_hours=[],
            revenue_series={'labels': [], 'revenue': [], 'orders': []},
            delivery={'on_time_rate': 0, 'avg_minutes': 0, 'cancellation_rate': 0,
                      'series': {'labels': [], 'rates': []}},
            recent_orders=[], rating={'average': 0, 'total': 0, 'distribution': {1:0,2:0,3:0,4:0,5:0}},
            reviews=[],
            no_store=True,
        )

    from app.utils.report_service import compute_analytics
    ctx = compute_analytics(store, period=period, custom_from=fr, custom_to=to)
    ctx['no_store'] = False
    ctx['is_admin'] = False
    return render_template('analytics.html', **ctx)


@templates_bp.route('/analytics/data')
def analytics_data():
    """JSON endpoint used when the user changes the period selector."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    period, fr, to = _request_period_args()

    if session.get('role') == 'admin':
        from app.utils.report_service import compute_admin_analytics
        ctx = compute_admin_analytics(period=period, custom_from=fr, custom_to=to)
    else:
        store = _resolve_report_store()
        if not store:
            return jsonify({'error': 'No store found for this seller'}), 404
        from app.utils.report_service import compute_analytics
        ctx = compute_analytics(store, period=period, custom_from=fr, custom_to=to)

    return jsonify({
        'period': ctx['period'],
        'period_label': ctx['period_label'],
        'totals': {
            'revenue': ctx['totals']['revenue'],
            'revenue_display': ctx['totals']['revenue_display'],
            'orders': ctx['totals']['orders'],
            'avg_order': ctx['totals']['avg_order'],
            'avg_order_display': ctx['totals']['avg_order_display'],
            'new_customers': ctx['totals']['new_customers'],
        },
        'deltas': ctx['deltas'],
        'top_products': ctx['top_products'],
        'order_status': ctx['order_status'],
        'sales_by_category': ctx['sales_by_category'],
        'peak_hours': ctx['peak_hours'],
        'revenue_series': ctx['revenue_series'],
        'delivery': {
            'on_time_rate': ctx['delivery']['on_time_rate'],
            'avg_minutes': ctx['delivery']['avg_minutes'],
            'cancellation_rate': ctx['delivery']['cancellation_rate'],
            'series': ctx['delivery']['series'],
        },
        'recent_orders': [{
            **o,
            'created_at': _fmt_pht(o.get('created_at')) if o.get('created_at') else '',
        } for o in ctx['recent_orders']],
        'rating': ctx['rating'],
    })


@templates_bp.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('templates.login'))
    return redirect(url_for('templates.my_account', page='profile'))

@templates_bp.route('/settings')
def settings():
    if 'user_id' not in session:
        return redirect(url_for('templates.login'))
    return render_template('settings.html')


@templates_bp.route('/reports')
def reports():
    """Reports landing page — multi-select report builder.

    Admins see the platform-wide catalogue (sales/orders/users/stores/etc.)
    while sellers see the original per-store catalogue.
    """
    if 'user_id' not in session:
        return redirect(url_for('templates.login'))

    is_admin = session.get('role') == 'admin'

    if is_admin:
        from app.utils.report_service import (
            ADMIN_REPORT_TYPES,
            ADMIN_REPORT_TYPE_LABELS,
            AdminScope,
        )
        store = AdminScope('All Stores')
        report_type_options = [
            {'value': key, 'label': ADMIN_REPORT_TYPE_LABELS[key]}
            for key in ADMIN_REPORT_TYPES
        ]
        return render_template(
            'reports.html',
            store=store,
            is_admin=True,
            report_type_options=report_type_options,
            report_types=ADMIN_REPORT_TYPES,
            saved_reports=_load_saved_reports_for_user(),
            report_templates=[],
        )

    from app.utils.report_service import REPORT_TYPES, REPORT_TYPE_LABELS
    store = _resolve_report_store()
    report_type_options = [
        {'value': key, 'label': REPORT_TYPE_LABELS[key]} for key in REPORT_TYPES
    ]
    return render_template(
        'reports.html',
        store=store,
        is_admin=False,
        report_type_options=report_type_options,
        report_types=REPORT_TYPES,
        saved_reports=_load_saved_reports_for_user(),
        report_templates=[],
    )


@templates_bp.route('/reports/preview', methods=['GET', 'POST'])
def reports_preview():
    """Return a JSON payload for the report preview pane (multi-select aware)."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    raw_types = (
        request.values.getlist('types[]')
        or request.values.getlist('types')
        or (request.get_json(silent=True) or {}).get('types')
        or []
    )
    period, fr, to = _request_period_args()

    if session.get('role') == 'admin':
        from app.utils.report_service import build_admin_report_payload
        payload = build_admin_report_payload(raw_types, period=period, custom_from=fr, custom_to=to)
    else:
        store = _resolve_report_store()
        if not store:
            return jsonify({'error': 'No store found for this seller'}), 404
        from app.utils.report_service import build_report_payload
        payload = build_report_payload(store, raw_types, period=period, custom_from=fr, custom_to=to)

    requester = User.query.get(session.get('user_id'))
    payload['requested_by'] = requester.full_name if requester else 'System User'
    payload['store_logo_url'] = getattr(payload.get('store'), 'logo_url', None)

    # Prefer a real system logo file if available.
    logo_candidates = [
        os.path.join(current_app.root_path, 'static', 'images', 'eflora-flower-logo.png'),
        os.path.join(current_app.root_path, 'static', 'images', 'app_logo.png'),
        os.path.join(current_app.root_path, 'static', 'uploads', 'app_logo.png'),
        os.path.abspath(os.path.join(current_app.root_path, '..', '..', 'eflowers_app', 'assets', 'images', 'app_logo.png')),
    ]
    payload['system_logo_path'] = next((p for p in logo_candidates if os.path.exists(p)), None)

    requester = User.query.get(session.get('user_id'))
    payload['requested_by'] = requester.full_name if requester else 'System User'
    payload['store_logo_url'] = getattr(payload.get('store'), 'logo_url', None)

    # Prefer a real system logo file if available.
    logo_candidates = [
        os.path.join(current_app.root_path, 'static', 'images', 'eflora-flower-logo.png'),
        os.path.join(current_app.root_path, 'static', 'images', 'app_logo.png'),
        os.path.join(current_app.root_path, 'static', 'uploads', 'app_logo.png'),
        os.path.abspath(os.path.join(current_app.root_path, '..', '..', 'eflowers_app', 'assets', 'images', 'app_logo.png')),
    ]
    payload['system_logo_path'] = next((p for p in logo_candidates if os.path.exists(p)), None)

    return jsonify({
        'period': payload['period'],
        'period_label': payload['period_label'],
        'types': payload['types'],
        'sections': [{
            'key': s['key'],
            'title': s['title'],
            'columns': s['columns'],
            'rows': [[
                f"{c:.2f}" if isinstance(c, float) else c for c in r
            ] for r in s['rows']],
            'summary': [list(t) for t in s['summary']],
            'row_count': len(s['rows']),
        } for s in payload['sections']],
    })


@templates_bp.route('/reports/generate', methods=['POST', 'GET'])
def reports_generate():
    """Generate a PDF or CSV/ZIP for the selected report types."""
    if 'user_id' not in session:
        return redirect(url_for('templates.login'))

    raw_types = (
        request.values.getlist('types[]')
        or request.values.getlist('types')
        or (request.get_json(silent=True) or {}).get('types')
        or []
    )
    fmt = (request.values.get('format')
           or (request.get_json(silent=True) or {}).get('format')
           or 'pdf').lower()
    period = (request.values.get('period')
              or (request.get_json(silent=True) or {}).get('period')
              or 'month').lower()
    fr = request.values.get('from') or (request.get_json(silent=True) or {}).get('from')
    to = request.values.get('to') or (request.get_json(silent=True) or {}).get('to')
    skip_save = str(
        request.values.get('skip_save')
        or (request.get_json(silent=True) or {}).get('skip_save')
        or ''
    ).strip().lower() in {'1', 'true', 'yes'}

    from app.utils.report_service import render_pdf, render_csv_bundle

    if session.get('role') == 'admin':
        from app.utils.report_service import build_admin_report_payload
        payload = build_admin_report_payload(raw_types, period=period, custom_from=fr, custom_to=to)
    else:
        store = _resolve_report_store()
        if not store:
            return jsonify({'error': 'No store found for this seller'}), 404
        from app.utils.report_service import build_report_payload
        payload = build_report_payload(store, raw_types, period=period, custom_from=fr, custom_to=to)

    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M')
    if fmt == 'pdf':
        pdf_bytes = render_pdf(payload)
        filename = f"eflora_report_{timestamp}.pdf"
        if not skip_save:
            _push_saved_report_entry({
                'name': filename,
                'description': f"{len(payload.get('sections', []))} section(s) · {payload.get('period_label', '')}",
                'type': ', '.join(payload.get('types', [])) or 'all',
                'format': 'pdf',
                'last_generated': datetime.now(PHT).strftime('%b %d, %Y %I:%M %p PHT'),
                'schedule': None,
                'size': _human_size(len(pdf_bytes)),
            })
        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    # csv / zip
    filename, data, mime = render_csv_bundle(payload)
    if not skip_save:
        _push_saved_report_entry({
            'name': filename,
            'description': f"{len(payload.get('sections', []))} section(s) · {payload.get('period_label', '')}",
            'type': ', '.join(payload.get('types', [])) or 'all',
            'format': 'excel' if mime == 'application/zip' else 'csv',
            'last_generated': datetime.now(PHT).strftime('%b %d, %Y %I:%M %p PHT'),
            'schedule': None,
            'size': _human_size(len(data)),
        })
    response = make_response(data)
    response.headers['Content-Type'] = mime
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@templates_bp.route('/reports/saved/<int:report_id>', methods=['DELETE'])
def delete_saved_report(report_id):
    """Delete one saved report row owned by the logged-in user."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    if not _ensure_saved_reports_table():
        return jsonify({'error': 'Storage not ready'}), 500

    row = SavedReport.query.filter_by(id=report_id, user_id=session['user_id']).first()
    if not row:
        return jsonify({'error': 'Saved report not found'}), 404
    try:
        db.session.delete(row)
        db.session.commit()
        return jsonify({'success': True})
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Could not delete saved report'}), 500

@templates_bp.route('/logout')
def logout():
    session.clear()
    response = redirect(url_for('templates.login'))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@templates_bp.route('/products/<int:product_id>')
def product_details(product_id):
    """Product detail page - updated with new category system"""
    try:
        product = Product.query.get_or_404(product_id)
        store = Store.query.get(product.store_id)
        
        # Get all main categories for the navigation
        from app.models import Category
        main_categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()
        
        # Convert product to dict to include variants with image_url
        product_dict = product.to_dict()
        
        # Add store info to product dict
        if store:
            product_dict['store'] = store.to_dict()
        
        # Add main_category and store_category info to product_dict for template
        if product.main_category:
            product_dict['main_category'] = {
                'id': product.main_category.id,
                'name': product.main_category.name,
                'slug': product.main_category.slug
            }
        
        if product.store_category:
            product_dict['store_category'] = {
                'id': product.store_category.id,
                'name': product.store_category.name,
                'slug': product.store_category.slug
            }
        
        # Related ("You might also like"): same store + same main category
        # Include out-of-stock so UI can grey them (stock check happens client-side + buy-now)
        related_products = Product.query.filter(
            Product.store_id == product.store_id,
            Product.main_category_id == product.main_category_id,
            Product.id != product_id,
            Product.is_available == True,
            Product.is_archived == False,
        ).order_by(
            Product.stock_quantity.desc(),
            Product.name.asc(),
        ).limit(8).all()

        # Convert related products to dict
        related_dicts = []
        for p in related_products:
            p_dict = p.to_dict()
            if p.main_category:
                p_dict['main_category'] = {
                    'id': p.main_category.id,
                    'name': p.main_category.name,
                    'slug': p.main_category.slug
                }
            # Explicit sellable stock for addon flow (main product stock)
            p_dict['stock_quantity'] = int(p.stock_quantity or 0)
            p_dict['ymal_type'] = 'related_product'
            related_dicts.append(p_dict)

        # Flagged structured add-on options also appear in YMAL
        from app.addon_helpers import ymal_addon_option_dicts
        ymal_addon_options = ymal_addon_option_dicts(product)

        # Add-ons: other products from same store, different main category
        addon_products = Product.query.filter(
            Product.store_id == product.store_id,
            Product.id != product_id,
            Product.is_available == True,
            Product.is_archived == False,
            _public_storefront_sellable_filter()
        )

        # If product has a main category, get products from different categories
        if product.main_category_id:
            addon_products = addon_products.filter(
                Product.main_category_id != product.main_category_id
            )

        addon_products = addon_products.limit(8).all()

        # Convert addon products to dict
        addon_dicts = []
        for p in addon_products:
            p_dict = p.to_dict()
            if p.main_category:
                p_dict['main_category'] = {
                    'id': p.main_category.id,
                    'name': p.main_category.name,
                    'slug': p.main_category.slug
                }
            addon_dicts.append(p_dict)
        
        # Debug print
        print(f"\n🔍 PRODUCT DETAILS - ID: {product_id}")
        print(f"  Name: {product.name}")
        print(f"  Main Category: {product.main_category.name if product.main_category else 'None'}")
        print(f"  Store Category: {product.store_category.name if product.store_category else 'None'}")
        print(f"  Add-on products: {len(addon_dicts)}")
        print(f"  Related products: {len(related_dicts)}")
        print(f"  Categories for nav: {len(main_categories)}")
        
        # Get product rating aggregates
        from sqlalchemy import func as sa_func
        rating_agg = db.session.query(
            sa_func.avg(ProductRating.rating).label('avg'),
            sa_func.count(ProductRating.id).label('count')
        ).filter_by(product_id=product_id).first()
        avg_rating = round(float(rating_agg.avg or 0), 1)
        total_ratings = rating_agg.count or 0

        # Per-variant rating aggregates  (variant_id=NULL → "main")
        variant_ratings = {}
        rows = db.session.query(
            ProductRating.variant_id,
            sa_func.avg(ProductRating.rating).label('avg'),
            sa_func.count(ProductRating.id).label('count')
        ).filter_by(product_id=product_id).group_by(ProductRating.variant_id).all()
        for row in rows:
            key = str(row.variant_id) if row.variant_id else 'main'
            variant_ratings[key] = {
                'avg': round(float(row.avg or 0), 1),
                'count': row.count or 0,
            }
        
        return render_template(
            'product_details.html',
            product=product_dict,
            addon_products=addon_dicts,
            related_products=related_dicts,
            ymal_addon_options=ymal_addon_options,
            main_categories=main_categories,
            avg_rating=avg_rating,
            total_ratings=total_ratings,
            variant_ratings=variant_ratings,
        )
        
    except Exception as e:
        print(f"❌ Error loading product {product_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Product not found', 'error')
        return redirect(url_for('templates.browse_products'))


@templates_bp.route('/checkout')
def checkout():
    """Checkout page"""
    if 'user_id' not in session:
        flash('Please login to checkout', 'warning')
        return redirect(url_for('templates.login'))
    role = session.get('role')
    if role in ('seller', 'admin'):
        flash('Checkout is not available for seller/admin accounts.', 'warning')
        return redirect(url_for('templates.index'))
    
    # Get user's cart
    cart = Cart.query.filter_by(user_id=session['user_id']).first()
    address = _get_default_customer_address(session.get('user_id'))
    if cart and cart.items:
        for item in cart.items:
            store = item.product.store if item.product else None
            delivery = _store_delivery_match(store, address)
            if not delivery.get('can_deliver'):
                flash(
                    f"Some cart items are outside your delivery area ({store.name if store else 'store'}). "
                    "Please switch to a deliverable address or remove those items.",
                    'warning',
                )
                return redirect(url_for('templates.index'))
    
    return render_template('checkout.html', cart=cart.to_dict() if cart else None)

def get_current_user():
    """Get current user from either session (web) or JWT token (Flutter)"""
    # Check session first (for web)
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            print(f"✅ User authenticated via session: {user.id}")
            return user
    
    # Check JWT token (for Flutter)
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        print(f"🔑 JWT Token received (first 20 chars): {token[:20]}...")
        
        try:
            from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt
            
            # Force verify the JWT
            verify_jwt_in_request()
            
            # Get claims and identity
            claims = get_jwt()
            user_id = get_jwt_identity()
            
            print(f"📋 JWT Claims: {claims}")
            print(f"👤 User ID from token: {user_id}")
            
            if user_id:
                user = User.query.get(int(user_id))
                if user:
                    print(f"✅ User authenticated via JWT: {user.id}")
                    return user
                else:
                    print("❌ User not found for ID from token")
            else:
                print("❌ No user_id in JWT token")
                
        except Exception as e:
            print(f"❌ JWT validation error: {str(e)}")
            # Try to manually decode to see what's in the token
            try:
                import jwt as pyjwt
                from flask import current_app
                
                # Try to decode without verification to see the payload
                unverified = pyjwt.decode(token, options={"verify_signature": False})
                print(f"🔍 Unverified token payload: {unverified}")
                print(f"🔍 Has 'sub' claim: {'sub' in unverified}")
            except Exception as e2:
                print(f"❌ Manual decode also failed: {e2}")
    
    print("❌ No valid authentication found")
    return None

@templates_bp.route('/api/debug/jwt-config', methods=['GET'])
def debug_jwt_config():
    """Debug endpoint to check JWT configuration"""
    from flask import current_app
    from flask_jwt_extended import create_access_token, decode_token
    
    # Check configuration
    config = {
        'JWT_SECRET_KEY': current_app.config.get('JWT_SECRET_KEY', 'NOT SET'),
        'JWT_IDENTITY_CLAIM': current_app.config.get('JWT_IDENTITY_CLAIM', 'NOT SET'),
        'JWT_ACCESS_TOKEN_EXPIRES': str(current_app.config.get('JWT_ACCESS_TOKEN_EXPIRES', 'NOT SET')),
    }
    
    # Create a test token
    test_token = create_access_token(
        identity='999',
        additional_claims={'test': 'value'}
    )
    
    # Decode it to see what's inside
    try:
        decoded = decode_token(test_token)
        token_info = {
            'has_sub': 'sub' in decoded,
            'sub_value': decoded.get('sub'),
            'all_claims': {k: v for k, v in decoded.items() if k not in ['exp', 'iat', 'jti']}
        }
    except Exception as e:
        token_info = {'error': str(e)}
    
    return jsonify({
        'config': config,
        'test_token_preview': test_token[:50] + '...',
        'test_token_info': token_info,
    })

@templates_bp.route('/api/debug/auth', methods=['GET'])
def debug_auth():
    """Debug endpoint to check authentication"""
    user = get_current_user()
    if user:
        return jsonify({
            'authenticated': True,
            'user_id': user.id,
            'method': 'session' if 'user_id' in session else 'jwt'
        })
    else:
        return jsonify({
            'authenticated': False,
            'session_exists': 'user_id' in session,
            'auth_header': request.headers.get('Authorization')
        })
    



@templates_bp.route('/api/cart/items', methods=['POST'])
@limiter.exempt
def add_to_cart():
    """Add item to cart - FIXED to handle variants"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401
    if user.role in ('seller', 'admin'):
        return jsonify({'error': 'Cart is not available for seller/admin accounts'}), 403
    
    try:
        data = request.get_json()
        product_id = data.get('product_id')
        variant_id = data.get('variant_id')  # ✅ Get variant_id from payload
        quantity = data.get('quantity', 1)
        addon_option_ids = data.get('addon_option_ids') or data.get('addon_selections') or []
        
        print(f"🛒 Adding to cart - User: {user.id}, Product: {product_id}, Variant: {variant_id}, Quantity: {quantity}")
        
        if not product_id:
            return jsonify({'error': 'Product ID is required'}), 400
        
        # Check if product exists
        product = Product.query.get(product_id)
        if not product:
            print(f"❌ Product not found: {product_id}")
            return jsonify({'error': 'Product not found'}), 404

        from app.addon_helpers import resolve_structured_addon_selections, sync_cart_item_addons
        struct_lines, struct_err = resolve_structured_addon_selections(
            product, addon_option_ids, quantity_per_option=1
        )
        if struct_err:
            return struct_err

        address = _get_default_customer_address(user.id)
        # New accounts often have no address yet (guest-cart transfer after
        # signup). Allow the line into the cart; checkout still enforces coverage.
        if address:
            delivery = _store_delivery_match(product.store, address)
            if not delivery.get('can_deliver'):
                return jsonify({
                    'error': delivery.get('reason') or 'This store cannot deliver to your default address.',
                    'code': 'OUTSIDE_DELIVERY_AREA'
                }), 400
        
        # If variant_id is provided, check variant exists and has stock
        variant = None
        if variant_id:
            variant = ProductVariant.query.get(variant_id)
            if not variant:
                return jsonify({'error': 'Variant not found'}), 404
            if variant.product_id != product_id:
                return jsonify({'error': 'Variant does not belong to this product'}), 400
            if variant.stock_quantity < quantity:
                return jsonify({'error': f'Only {variant.stock_quantity} of this variant available'}), 400
            print(f"📦 Variant: {variant.name}, Stock: {variant.stock_quantity}")
        else:
            # Check main product stock
            if product.stock_quantity < quantity:
                return jsonify({'error': f'Only {product.stock_quantity} available'}), 400
        
        print(f"📦 Product: {product.name}, Available: {product.is_available}")
        
        if not product.is_available:
            return jsonify({'error': 'Product is not available'}), 400
        
        # Get or create cart
        cart = Cart.query.filter_by(user_id=user.id).first()
        if not cart:
            print(f"🆕 Creating new cart for user: {user.id}")
            cart = Cart(user_id=user.id)
            db.session.add(cart)
            db.session.flush()
        
        # ✅ FIXED: Check if product/variant combination already in cart
        cart_item = CartItem.query.filter_by(
            cart_id=cart.id,
            product_id=product_id,
            variant_id=variant_id  # Include variant_id in the query!
        ).first()
        
        if cart_item:
            # Check total quantity against stock
            if variant:
                if variant.stock_quantity < (cart_item.quantity + quantity):
                    return jsonify({'error': f'Only {variant.stock_quantity} of this variant available total'}), 400
            else:
                if product.stock_quantity < (cart_item.quantity + quantity):
                    return jsonify({'error': f'Only {product.stock_quantity} available total'}), 400
                    
            print(f"🔄 Updating existing cart item from {cart_item.quantity} to {cart_item.quantity + quantity}")
            cart_item.quantity += quantity
            db.session.flush()
            sync_err = sync_cart_item_addons(cart_item, product, addon_option_ids)
            if sync_err:
                db.session.rollback()
                return sync_err
        else:
            print(f"➕ Adding new cart item with variant_id: {variant_id}")
            cart_item = CartItem(
                cart_id=cart.id,
                product_id=product_id,
                variant_id=variant_id,  # ✅ Save variant_id!
                quantity=quantity
            )
            db.session.add(cart_item)
            db.session.flush()
            sync_err = sync_cart_item_addons(cart_item, product, addon_option_ids)
            if sync_err:
                db.session.rollback()
                return sync_err
        
        db.session.commit()
        
        # ✅ Return the updated cart with proper structure
        cart_dict = cart.to_dict()
        print(f"✅ Item added successfully. Cart now has {len(cart_dict.get('items', []))} items")
        
        return jsonify({
            'success': True,
            'message': 'Item added to cart',
            'cart': cart_dict
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error adding to cart: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/cart', methods=['GET'])
@limiter.exempt
def get_cart():
    """Get cart - FIXED to include variant details and Cloudinary URLs"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        cart = Cart.query.filter_by(user_id=user.id).first()
        if not cart:
            cart = Cart(user_id=user.id)
            db.session.add(cart)
            db.session.commit()
        
        # Filter out archived products from cart
        active_items = []
        removed_count = 0
        
        for item in cart.items:
            if item.product and not item.product.is_archived:
                active_items.append(item)
            else:
                db.session.delete(item)
                removed_count += 1
        
        if removed_count > 0:
            db.session.commit()
        
        # ✅ Build cart data with variant details properly included
        cart_data = {
            'id': cart.id,
            'user_id': cart.user_id,
            'items': [],
            'created_at': cart.created_at.isoformat() if cart.created_at else None,
            'updated_at': cart.updated_at.isoformat() if cart.updated_at else None
        }
        
        total = 0
        for item in active_items:
            # Get product details
            product = item.product
            
            # Get variant details if exists
            variant = None
            if item.variant_id:
                variant = ProductVariant.query.get(item.variant_id)
            
            # Determine effective price (uses special_price when active)
            price = float(variant.effective_price) if variant else float(product.effective_price)
            
            # Determine name
            if variant:
                name = f"{variant.name} {product.name}"
            else:
                name = product.name
            
            # Get the full product dictionary (includes all image details)
            product_dict = product.to_dict()
            
            # Determine image URL (variant image takes precedence)
            image_url = None
            if variant and variant.image_url:
                image_url = variant.image_url
            elif product.images:
                primary = next((img for img in product.images if img.is_primary), product.images[0])
                # Use cloudinary_url if available, otherwise fallback to image_url
                image_url = primary.cloudinary_url if primary and primary.cloudinary_url else (
                    primary.image_url if hasattr(primary, 'image_url') else None
                )
            
            # Ensure product images have cloudinary_url in the response
            if 'images' in product_dict:
                for img in product_dict['images']:
                    # Make sure cloudinary_url is included
                    if 'cloudinary_url' not in img and 'image_url' in img:
                        img['cloudinary_url'] = img['image_url']
            
            original_price = float(variant.price) if variant else float(product.price)
            discount_pct = variant.discount_pct if variant else product.discount_pct

            item_dict = {
                'id': item.id,
                'product_id': product.id,
                'store_id': product.store_id,
                'variant_id': item.variant_id,
                'quantity': item.quantity,
                'is_selected': item.is_selected,
                'product': product_dict,  # Full product dict with all image data
                'store_name': product.store.name if product.store else None,
                'price': price,
                'original_price': original_price,
                'discount_pct': discount_pct,
                'name': name,
                'image_url': image_url,  # Top-level convenience field
                'subtotal': float(item.subtotal),
                'addons': [a.to_dict() for a in (item.addons or [])],
                'addons_total': float(item.addons_subtotal),
            }
            
            # Add variant details if exists (with full Cloudinary URLs)
            if variant:
                variant_dict = variant.to_dict()
                # Ensure variant image_url is included
                if variant.image_url and 'image_url' not in variant_dict:
                    variant_dict['image_url'] = variant.image_url
                item_dict['variant'] = variant_dict
            
            cart_data['items'].append(item_dict)
            total += item_dict['subtotal']
        
        cart_data['total'] = total
        cart_data['item_count'] = len(cart_data['items'])
        
        # Debug log to verify image URLs
        print(f"\n✅ Cart response for user {user.id}:")
        print(f"   Items: {len(cart_data['items'])}")
        for i, item in enumerate(cart_data['items']):
            print(f"   Item {i}: {item['name']}")
            if item.get('image_url'):
                print(f"      image_url: {item['image_url']}")
            if item['product'].get('images'):
                for j, img in enumerate(item['product']['images']):
                    print(f"      product.images[{j}]: cloudinary_url={img.get('cloudinary_url')}")
        
        return jsonify({
            'success': True,
            'cart': cart_data,
            'removed_count': removed_count,
            'message': f'{removed_count} item(s) removed as they are no longer available' if removed_count else None
        })
        
    except Exception as e:
        print(f"❌ Error getting cart: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@templates_bp.route('/api/cart/items/<int:item_id>', methods=['PUT'])
@limiter.exempt
def update_cart_item(item_id):
    """Update cart item quantity"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        data = request.get_json()
        quantity = data.get('quantity')
        
        print(f"🔄 Updating cart item - User: {user.id}, Item: {item_id}, New Quantity: {quantity}")
        
        if not quantity or quantity < 1:
            return jsonify({'error': 'Invalid quantity'}), 400
        
        cart_item = CartItem.query.get_or_404(item_id)
        
        # Verify ownership
        if cart_item.cart.user_id != user.id:
            print(f"❌ Unauthorized: Item belongs to user {cart_item.cart.user_id}, but request is from {user.id}")
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Check stock - use variant stock if variant_id is set
        if cart_item.variant_id and cart_item.variant:
            print(f"   📦 Variant: {cart_item.variant.name}, Stock: {cart_item.variant.stock_quantity}")
            if cart_item.variant.stock_quantity < quantity:
                return jsonify({'error': f'Only {cart_item.variant.stock_quantity} available'}), 400
        else:
            product = cart_item.product
            if product and product.stock_quantity < quantity:
                return jsonify({'error': f'Only {product.stock_quantity} available'}), 400
        
        cart_item.quantity = quantity
        db.session.commit()
        
        print(f"✅ Cart item updated successfully")
        
        return jsonify({
            'success': True,
            'message': 'Cart updated',
            'cart': cart_item.cart.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error updating cart: {str(e)}")
        return jsonify({'error': str(e)}), 500

@templates_bp.route('/api/cart/items/<int:item_id>/addons/<int:addon_option_id>', methods=['DELETE'])
@limiter.exempt
def remove_cart_item_addon(item_id, addon_option_id):
    """Remove a single structured add-on from a cart line."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401

    try:
        cart_item = CartItem.query.get_or_404(item_id)
        if cart_item.cart.user_id != user.id:
            return jsonify({'error': 'Unauthorized'}), 403

        row = CartItemAddon.query.filter_by(
            cart_item_id=cart_item.id,
            addon_option_id=addon_option_id,
        ).first()
        if not row:
            return jsonify({'error': 'Add-on not found on this cart item'}), 404

        db.session.delete(row)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Add-on removed',
            'cart': cart_item.cart.to_dict(),
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/cart/items/<int:item_id>', methods=['DELETE'])
@limiter.exempt
def remove_from_cart(item_id):
    """Remove item from cart"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        print(f"🗑️ Removing cart item - User: {user.id}, Item: {item_id}")
        
        cart_item = CartItem.query.get_or_404(item_id)
        
        # Verify ownership
        if cart_item.cart.user_id != user.id:
            print(f"❌ Unauthorized: Item belongs to user {cart_item.cart.user_id}, but request is from {user.id}")
            return jsonify({'error': 'Unauthorized'}), 403
        
        cart = cart_item.cart
        db.session.delete(cart_item)
        db.session.commit()
        
        print(f"✅ Item removed successfully")
        
        return jsonify({
            'success': True,
            'message': 'Item removed from cart',
            'cart': cart.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error removing from cart: {str(e)}")
        return jsonify({'error': str(e)}), 500

@templates_bp.route('/api/cart/clear', methods=['POST'])
@limiter.exempt
def clear_cart():
    """Clear all items from cart"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        print(f"🧹 Clearing cart for user: {user.id}")
        
        cart = Cart.query.filter_by(user_id=user.id).first()
        if cart:
            item_count = CartItem.query.filter_by(cart_id=cart.id).count()
            CartItem.query.filter_by(cart_id=cart.id).delete()
            db.session.commit()
            print(f"✅ Removed {item_count} items from cart")
        else:
            print(f"📭 No cart found for user")
        
        return jsonify({
            'success': True,
            'message': 'Cart cleared'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error clearing cart: {str(e)}")
        return jsonify({'error': str(e)}), 500




'''
@templates_bp.route('/api/product-image/<path:filename>')
def get_resized_product_image(filename):
    """Return a resized version of a product image with proper headers"""
    try:
        # Security: Prevent directory traversal
        if '..' in filename or filename.startswith('/'):
            return jsonify({'error': 'Invalid filename'}), 400
        
        # Construct the full path
        upload_folder = os.path.join(BASE_DIR, 'static', 'uploads', 'products')
        file_path = os.path.join(upload_folder, filename)
        
        # Check if file exists
        if not os.path.exists(file_path):
            print(f"❌ Image not found: {file_path}")
            return jsonify({'error': 'Image not found'}), 404
        
        # Get requested size from query parameters (default 150x150)
        width = request.args.get('w', 150, type=int)
        height = request.args.get('h', 150, type=int)
        
        # Limit maximum size to prevent timeout issues
        width = min(width, 400)  # Reduced from 800 to 400
        height = min(height, 400)  # Reduced from 800 to 400
        
        print(f"🖼️ Serving image: {filename} ({width}x{height})")
        
        # Check if we have a cached resized version
        cache_folder = os.path.join(upload_folder, 'cache')
        os.makedirs(cache_folder, exist_ok=True)
        cache_filename = f"{width}x{height}_{filename}"
        cache_path = os.path.join(cache_folder, cache_filename)
        
        # If cached version exists and is newer than original, serve it
        if os.path.exists(cache_path) and os.path.getmtime(cache_path) > os.path.getmtime(file_path):
            print(f"📦 Serving cached version: {cache_filename}")
            return send_file(
                cache_path,
                mimetype='image/png' if filename.lower().endswith('.png') else 'image/jpeg',
                as_attachment=False,
                download_name=f'thumb_{filename}',
                max_age=86400
            )
        
        # Open and resize image with timeout handling
        try:
            img = Image.open(file_path)
        except Exception as e:
            print(f"❌ Error opening image: {e}")
            return jsonify({'error': f'Cannot open image: {e}'}), 500
        
        # CREAM COLOR (AppColors.warmWhite in hex: #F5EDE6)
        CREAM_BG = (245, 237, 230)  # RGB values for warm white/cream
        
        # Handle PNG with transparency - ADD CREAM BACKGROUND
        if img.mode == 'RGBA':
            # Create cream background
            background = Image.new('RGBA', img.size, CREAM_BG + (255,))
            # Composite the image onto cream background
            background.paste(img, (0, 0), img)
            img = background.convert('RGB')
        elif img.mode in ('RGBA', 'LA') and filename.lower().endswith(('.jpg', '.jpeg')):
            # For JPEG conversion
            background = Image.new('RGB', img.size, CREAM_BG)
            background.paste(img, mask=img.split()[-1])
            img = background
        else:
            img = img.convert('RGB')
        
        # Resize with high-quality algorithm
        img.thumbnail((width, height), Image.Resampling.LANCZOS)
        
        # Save to cache with appropriate format
        if filename.lower().endswith('.jpg') or filename.lower().endswith('.jpeg'):
            format = 'JPEG'
            mimetype = 'image/jpeg'
            img.save(cache_path, format=format, quality=85, optimize=True)
        else:
            format = 'PNG'
            mimetype = 'image/png'
            img.save(cache_path, format=format, optimize=True)
        
        print(f"✅ Image cached: {cache_path} ({os.path.getsize(cache_path)} bytes)")
        
        # Send the cached file
        response = send_file(
            cache_path,
            mimetype=mimetype,
            as_attachment=False,
            download_name=f'thumb_{filename}',
            max_age=86400  # Cache for 24 hours
        )
        
        # Add CORS headers
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Cache-Control'] = 'public, max-age=86400'
        
        return response
        
    except Exception as e:
        print(f"❌ Error resizing image {filename}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
'''
'''
@templates_bp.route('/api/product-image/<path:filename>')
@limiter.limit("100 per minute")
def get_resized_product_image(filename):
    """Return a resized version of a product image with proper headers and security"""
    try:
        # ===== ENHANCED SECURITY: Multiple layers of path validation =====
        from werkzeug.utils import secure_filename
        import os
        import magic  # For MIME type validation (install: pip install python-magic-bin)
        
        # Layer 1: Basic path traversal prevention
        if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
            print(f"❌ Blocked path traversal attempt: {filename}")
            return jsonify({'error': 'Invalid filename'}), 400
        
        # Layer 2: Use secure_filename to get safe basename
        safe_filename = secure_filename(os.path.basename(filename))
        if safe_filename != filename:
            print(f"❌ Filename sanitization changed: {filename} -> {safe_filename}")
            return jsonify({'error': 'Invalid filename characters'}), 400
        
        # Layer 3: Validate file extension
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        ext = safe_filename.rsplit('.', 1)[1].lower() if '.' in safe_filename else ''
        if ext not in allowed_extensions:
            print(f"❌ Blocked invalid extension: {ext}")
            return jsonify({'error': 'Invalid file type'}), 400
        
        # Construct paths
        upload_folder = os.path.join(BASE_DIR, 'static', 'uploads', 'products')
        
        # Layer 4: Path resolution to prevent symlink attacks
        real_upload_folder = os.path.realpath(upload_folder)
        file_path = os.path.join(real_upload_folder, safe_filename)
        real_file_path = os.path.realpath(file_path)
        
        # Layer 5: Verify the resolved path is still within upload folder
        if not real_file_path.startswith(real_upload_folder):
            print(f"❌ Path escape attempt: {real_file_path}")
            return jsonify({'error': 'Access denied'}), 403
        
        # Check if file exists
        if not os.path.exists(real_file_path):
            print(f"❌ Image not found: {safe_filename}")
            return jsonify({'error': 'Image not found'}), 404
        
        # Layer 6: Validate file is actually an image (MIME type check)
        try:
            file_mime = magic.from_file(real_file_path, mime=True)
            if not file_mime.startswith('image/'):
                print(f"❌ Not an image file: {file_mime}")
                return jsonify({'error': 'Invalid image file'}), 400
        except Exception as e:
            print(f"⚠️ MIME check failed: {e}")
            # Fallback to PIL validation
        
        # Get requested size from query parameters
        width = request.args.get('w', 150, type=int)
        height = request.args.get('h', 150, type=int)
        
        # Layer 7: Limit dimensions to prevent DoS
        MAX_DIMENSION = 800
        width = min(max(width, 16), MAX_DIMENSION)  # Min 16px, max 800px
        height = min(max(height, 16), MAX_DIMENSION)
        
        print(f"🖼️ Serving image: {safe_filename} ({width}x{height})")
        
        # Check cache
        cache_folder = os.path.join(real_upload_folder, 'cache')
        os.makedirs(cache_folder, mode=0o755, exist_ok=True)  # Secure permissions
        
        # Layer 8: Sanitize cache filename
        cache_filename = f"{width}x{height}_{safe_filename}"
        cache_filename = secure_filename(cache_filename)
        cache_path = os.path.join(cache_folder, cache_filename)
        
        # Serve cached version if available
        if os.path.exists(cache_path) and os.path.getmtime(cache_path) > os.path.getmtime(real_file_path):
            print(f"📦 Serving cached version: {cache_filename}")
            
            # Layer 9: Validate cached file
            try:
                cache_mime = magic.from_file(cache_path, mime=True)
                if not cache_mime.startswith('image/'):
                    os.remove(cache_path)  # Delete corrupted cache
                    print(f"🗑️ Removed invalid cache: {cache_filename}")
                else:
                    return send_file(
                        cache_path,
                        mimetype=cache_mime,
                        as_attachment=False,
                        download_name=f'thumb_{safe_filename}',
                        max_age=86400
                    )
            except:
                pass  # Proceed to regenerate
        
        # Open and validate image with PIL
        try:
            img = Image.open(real_file_path)
            img.verify()  # Verify it's a valid image
            img = Image.open(real_file_path)  # Reopen after verify
        except Exception as e:
            print(f"❌ Error opening image: {e}")
            return jsonify({'error': 'Corrupted image file'}), 500
        
        # Layer 10: Limit image size to prevent memory DoS
        MAX_PIXELS = 4000 * 4000  # 16 megapixels
        if img.size[0] * img.size[1] > MAX_PIXELS:
            print(f"❌ Image too large: {img.size[0]}x{img.size[1]}")
            return jsonify({'error': 'Image too large'}), 400
        
        # CREAM COLOR for background
        CREAM_BG = (245, 237, 230)
        
        # Handle different image modes
        try:
            if img.mode == 'RGBA':
                # Create cream background
                background = Image.new('RGBA', img.size, CREAM_BG + (255,))
                background.paste(img, (0, 0), img)
                img = background.convert('RGB')
            elif img.mode in ('RGBA', 'LA', 'P'):  # Handle palette images
                img = img.convert('RGBA')
                background = Image.new('RGBA', img.size, CREAM_BG + (255,))
                background.paste(img, (0, 0), img)
                img = background.convert('RGB')
            else:
                img = img.convert('RGB')
        except Exception as e:
            print(f"❌ Error processing image: {e}")
            return jsonify({'error': 'Image processing failed'}), 500
        
        # Resize with high-quality algorithm
        img.thumbnail((width, height), Image.Resampling.LANCZOS)
        
        # Save to cache with secure permissions
        try:
            if ext in ('jpg', 'jpeg'):
                img.save(cache_path, format='JPEG', quality=85, optimize=True)
                mimetype = 'image/jpeg'
            else:
                img.save(cache_path, format='PNG', optimize=True)
                mimetype = 'image/png'
            
            # Set secure file permissions
            os.chmod(cache_path, 0o644)
            
        except Exception as e:
            print(f"❌ Error saving cache: {e}")
            return jsonify({'error': 'Failed to process image'}), 500
        
        print(f"✅ Image cached: {cache_path} ({os.path.getsize(cache_path)} bytes)")
        
        # Send response with security headers
        response = send_file(
            cache_path,
            mimetype=mimetype,
            as_attachment=False,
            download_name=f'thumb_{safe_filename}',
            max_age=86400
        )
        
        # Layer 11: Security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        # Cache control
        response.headers['Cache-Control'] = 'public, max-age=86400, immutable'
        
        # CORS - restrict to your domains in production
        if app.debug:
            response.headers['Access-Control-Allow-Origin'] = '*'
        else:
            # Replace with your actual domains
            response.headers['Access-Control-Allow-Origin'] = 'https://yourdomain.com'
        
        return response
        
    except Exception as e:
        print(f"❌ Error in get_resized_product_image: {e}")
        import traceback
        traceback.print_exc()
        # Don't expose internal errors to client
        return jsonify({'error': 'An error occurred processing the image'}), 500
'''
    

@templates_bp.route('/seller/archive')
@seller_required
def seller_archive():
    """Render the seller archive page"""
    return render_template('seller_archive.html')

'''
@templates_bp.route('/seller/products/<int:product_id>/images/<int:image_id>', methods=['DELETE'])
def delete_product_image(product_id, image_id):
    """Delete a specific product image"""
    if session.get('role') != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        # Get seller's store
        store = Store.query.filter_by(seller_id=session.get('user_id')).first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        image = ProductImage.query.filter_by(id=image_id, product_id=product_id).first()
        if not image:
            return jsonify({'error': 'Image not found'}), 404
        
        # Don't allow deleting the last image
        if len(product.images) <= 1:
            return jsonify({'error': 'Cannot delete the last image of a product'}), 400
        
        # Delete file from filesystem
        upload_path = os.path.join(BASE_DIR, 'static', 'uploads', 'products')
        file_path = os.path.join(upload_path, image.filename)
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # If this was the primary image, make the next image primary
        if image.is_primary and len(product.images) > 1:
            next_image = next((img for img in product.images if img.id != image_id), None)
            if next_image:
                next_image.is_primary = True
        
        db.session.delete(image)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Image deleted successfully',
            'product': product.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting image: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

'''


@templates_bp.route('/stores')
def stores():
    """Public store directory — all active partner stores."""
    try:
        from sqlalchemy import func

        current_user_id = session.get('user_id')
        is_customer = session.get('role') == 'customer' and current_user_id
        customer_address = _get_default_customer_address(current_user_id) if is_customer else None

        browse_all_arg = request.args.get('browse_all')
        if browse_all_arg is not None:
            session['storefront_browse_all'] = browse_all_arg == '1'
        browse_all_mode = bool(session.get('storefront_browse_all', False))

        active_stores = (
            Store.query
            .filter_by(status='active')
            .order_by(Store.created_at.desc())
            .all()
        )

        product_counts = dict(
            db.session.query(Product.store_id, func.count(Product.id))
            .filter(
                Product.is_available == True,
                Product.is_archived == False,
            )
            .group_by(Product.store_id)
            .all()
        )

        now = datetime.utcnow()
        store_ids = [store.id for store in active_stores]
        fulfillment_map = _store_fulfillment_stats(store_ids)
        rating_map = _store_rating_stats(store_ids)
        store_list = []
        for store in active_stores:
            store_data = store.to_dict()
            store_data['can_deliver_to_customer'] = True
            store_data['delivery_block_reason'] = None

            if is_customer:
                delivery = _store_delivery_match(store, customer_address)
                store_data['can_deliver_to_customer'] = bool(delivery.get('can_deliver'))
                store_data['delivery_block_reason'] = delivery.get('reason')

            total_orders, delivered_or_completed = fulfillment_map.get(store.id, (0, 0))
            _apply_store_performance(store_data, total_orders, delivered_or_completed)
            avg_rating, review_count = rating_map.get(store.id, (0.0, 0))
            _apply_store_card_rating(store_data, avg_rating, review_count)
            store_data['product_count'] = int(product_counts.get(store.id, 0))
            store_data['is_newly_approved'] = bool(
                store.approved_at and (now - store.approved_at).days < 7
            )
            store_data['created_at_sort'] = (
                store.created_at.isoformat() if store.created_at else ''
            )
            store_list.append(store_data)

        if is_customer and customer_address and not browse_all_mode:
            store_list = [s for s in store_list if s.get('can_deliver_to_customer')]

        return render_template(
            'stores.html',
            stores=store_list,
            now=datetime.now(),
            browse_all_mode=browse_all_mode,
            customer_has_default_address=bool(customer_address),
        )
    except Exception as e:
        current_app.logger.exception('stores directory: %s', e)
        try:
            db.session.rollback()
        except Exception:
            pass
        return render_template(
            'stores.html',
            stores=[],
            now=datetime.now(),
            browse_all_mode=False,
            customer_has_default_address=False,
        )


@templates_bp.route('/store/<int:store_id>')
def store_detail(store_id):
    """Public store detail page — shows store info + all its active products."""
    try:
        from datetime import timedelta

        store = Store.query.get_or_404(store_id)

        # Only show active stores to the public
        if store.status != 'active':
            flash('This store is not currently available.', 'warning')
            return redirect(url_for('templates.index'))

        # Build store dict
        store_data = store.to_dict()

        # ===== UPDATED: Use Cloudinary URL for logo if available =====
        # Attach logo URL from seller application - prefer Cloudinary URL
        if store.seller_application:
            # Use Cloudinary URL if available
            if store.seller_application.store_logo_url:
                store_data['logo_url'] = store.seller_application.store_logo_url
            # Fallback to local path
            elif store.seller_application.store_logo_path:
                store_data['logo_url'] = f'/static/uploads/seller_logos/{store.seller_application.store_logo_path}'
            else:
                store_data['logo_url'] = None
        else:
            store_data['logo_url'] = None

        # Get active, non-archived products for this store
        products = Product.query \
            .filter_by(
                store_id=store.id,
                is_available=True,
                is_archived=False
            ) \
            .order_by(Product.created_at.desc()) \
            .all()

        product_list = _product_list_for_storefront(products)

        # Delivery map data is intentionally scoped to this store.  A customer's
        # default-address coordinates are only exposed back to that same customer.
        delivery_method = (store.delivery_method or 'radius').strip().casefold()
        geometry_key = {
            'radius': 'radius_geojson',
            'zone': 'zone_geojson',
            'municipality': 'municipality_geojson',
        }.get(delivery_method, 'current_delivery_geojson')
        coverage_geometry = store_data.get(geometry_key) or store_data.get('current_delivery_geojson')
        if isinstance(coverage_geometry, str):
            try:
                coverage_geometry = json.loads(coverage_geometry)
            except (TypeError, ValueError):
                coverage_geometry = None

        is_customer = session.get('role') == 'customer' and session.get('user_id')
        default_address = _get_default_customer_address(session.get('user_id')) if is_customer else None
        delivery_match = _store_delivery_match(store, default_address) if default_address else {
            'can_deliver': False,
            'reason': 'Set your default address to check delivery coverage.',
        }
        customer_map_location = None
        if default_address and default_address.latitude is not None and default_address.longitude is not None:
            customer_map_location = {
                'latitude': default_address.latitude,
                'longitude': default_address.longitude,
                'label': default_address.address_label or 'Default address',
            }

        store_map_data = {
            'store': {
                'name': store.name,
                'address': store.formatted_address or store.address,
                'latitude': store.latitude,
                'longitude': store.longitude,
                'logo_url': store_data.get('logo_url'),
            },
            'customer': customer_map_location,
            'coverage': {
                'method': delivery_method,
                'radius_km': store.delivery_radius_km,
                'municipalities': store.selected_municipalities or [],
                'geometry': coverage_geometry,
            },
            'delivery': delivery_match,
            'is_customer': bool(is_customer),
        }

        # Real store ratings from post-order StoreRating (not legacy testimonials)
        store_avg_row = db.session.query(
            db.func.coalesce(db.func.avg(StoreRating.rating), 0),
            db.func.count(StoreRating.id),
        ).filter(StoreRating.store_id == store.id).first()
        avg_rating = round(float(store_avg_row[0]), 1) if store_avg_row else 0.0
        total_reviews = int(store_avg_row[1]) if store_avg_row else 0

        store_ratings = (
            StoreRating.query
            .filter_by(store_id=store.id)
            .order_by(StoreRating.created_at.desc())
            .limit(50)
            .all()
        )
        reviews = [r.to_dict() for r in store_ratings]

        # Keep legacy testimonials as fallback if no StoreRating rows exist yet
        if not reviews:
            testimonials = (
                Testimonial.query
                .filter_by(store_id=store.id)
                .order_by(Testimonial.created_at.desc())
                .limit(50)
                .all()
            )
            reviews = [t.to_dict() for t in testimonials]
            if reviews and total_reviews == 0:
                total_reviews = len(reviews)
                avg_rating = round(sum(t['rating'] for t in reviews) / len(reviews), 1)

        now = datetime.utcnow()

        return render_template(
            'store_detail.html',
            store=store_data,
            products=product_list,
            reviews=reviews,
            testimonials=reviews,
            avg_rating=avg_rating,
            total_reviews=total_reviews,
            store_map_data=store_map_data,
            now=now,
            timedelta=timedelta,
        )

    except Exception as e:
        print(f"Error loading store {store_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Store not found.', 'error')
        return redirect(url_for('templates.index'))


















@templates_bp.route('/api/store/<int:store_id>/time-slots')
def get_store_time_slots_web(store_id):
    """Get available delivery time slots for a store (web/session-based, no JWT required)"""
    from datetime import datetime as dt
    from app.utils.store_schedule import build_store_time_slots

    store = Store.query.get(store_id)
    if not store:
        return jsonify({'error': 'Store not found'}), 404

    date_str = request.args.get('date')
    target_date = None
    if date_str:
        try:
            target_date = dt.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    return jsonify(build_store_time_slots(store, target_date))


@templates_bp.route('/seller/store-settings')
@seller_required
def store_settings():
    try:
        _ensure_store_payment_settings_table()
        store = Store.query.filter_by(seller_id=session['user_id']).first()
        if not store:
            flash('Store not found.', 'error')
            return redirect(url_for('templates.seller_dashboard'))
        
        # Import the laguna_addresses functions
        from app.laguna_addresses import get_municipalities, get_barangays
        
        # Get list of municipalities for the dropdown
        municipalities = get_municipalities()
        
        # FIXED: Process GCash QR codes for template using Cloudinary URL
        gcash_qr_data = []
        if store.gcash_qr_images:
            sorted_qrs = sorted(store.gcash_qr_images, key=lambda x: x.sort_order)
            for qr in sorted_qrs:
                gcash_qr_data.append({
                    'id': qr.id,
                    'filename': qr.filename,
                    'url': qr.cloudinary_url,  # ✅ FIXED: Use Cloudinary URL, not local path
                    'public_id': qr.public_id,
                    'is_primary': qr.is_primary,
                    'sort_order': qr.sort_order
                })
        
        # DEBUG: Print store data
        print("\n" + "="*60)
        print("🔍 STORE SETTINGS PAGE LOADED")
        print(f"Store ID: {store.id}")
        print(f"Store Name: {store.name}")
        print(f"Municipality: {store.municipality}")
        print(f"Barangay: {store.barangay}")
        print(f"Delivery Method: {store.delivery_method}")
        print(f"Has zone_delivery_area: {store.zone_delivery_area is not None}")
        print(f"Has selected_municipalities: {store.selected_municipalities is not None}")
        print(f"Has municipality_delivery_area: {store.municipality_delivery_area is not None}")
        print(f"GCash QR count: {len(gcash_qr_data)}")
        if gcash_qr_data:
            print(f"First QR URL: {gcash_qr_data[0]['url']}")
        print("="*60 + "\n")
        
        payment_setting = StorePaymentSetting.query.filter_by(store_id=store.id).first()
        allow_cod = bool(payment_setting.allow_cod) if payment_setting else False

        return render_template('store_settings.html', 
                             store=store,
                             municipalities=municipalities,
                             get_barangays=get_barangays,
                             gcash_qr_data=gcash_qr_data,
                             allow_cod=allow_cod)
    
    except Exception as e:
        print(f"❌ Error in store_settings: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('Error loading page.', 'error')
        return redirect(url_for('templates.seller_dashboard'))


@templates_bp.route('/api/seller/store/settings', methods=['POST'])
@seller_required
def update_store_settings():
    """Update all store settings at once including GCash QR codes with Cloudinary"""
    print("\n" + "="*60)
    print("📥 RECEIVED UPDATE STORE SETTINGS REQUEST")
    
    import json
    
    try:
        _ensure_store_payment_settings_table()
        store = Store.query.filter_by(seller_id=session['user_id']).first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        # Handle form data
        if request.content_type and 'multipart/form-data' in request.content_type:
            data = request.form
            files = request.files
            print(f"📦 Processing multipart form data with {len(files)} files")
        else:
            data = request.get_json() or {}
            files = {}
            print(f"📦 Processing JSON data")
        
        print(f"📋 Form data keys: {list(data.keys())}")
        
        # ===== BASIC INFO =====
        # Handle both 'name' and 'store_name' for backwards compatibility
        if 'store_name' in data:
            store.name = data['store_name']
            print(f"✅ Updated store name to: {data['store_name']}")
        elif 'name' in data:
            store.name = data['name']
            print(f"✅ Updated store name to: {data['name']}")
        
        # ===== STORE LOGO HANDLING =====
        if 'store_logo_url' in data and data['store_logo_url']:
            # Get or create seller_application for this store
            seller_app = store.seller_application
            
            # If no direct relationship, try to find one by seller_id
            if not seller_app:
                seller_app = SellerApplication.query.filter_by(user_id=store.seller_id).first()
            
            # If still no seller_application, create one
            if not seller_app:
                seller_app = SellerApplication(
                    user_id=store.seller_id,
                    store_name=store.name,
                    status='approved'
                )
                db.session.add(seller_app)
                db.session.flush()  # Get the ID
                print(f"✅ Created new SellerApplication for seller {store.seller_id}")
            
            # Now save the logo
            seller_app.store_logo_url = data['store_logo_url']
            store.seller_application_id = seller_app.id
            print(f"✅ Updated store logo URL: {data['store_logo_url']}")
            print(f"✅ Linked store to seller_application ID: {seller_app.id}")
            
            if 'store_logo_public_id' in data and data['store_logo_public_id']:
                seller_app.store_logo_public_id = data['store_logo_public_id']
                print(f"✅ Stored logo public_id: {data['store_logo_public_id']}")

        # ===== STOREFRONT BANNER HANDLING =====
        # Empty values are meaningful here: they restore the shared floral default.
        if 'store_banner_url' in data:
            store.banner_url = data['store_banner_url'] or None
        if 'store_banner_public_id' in data:
            store.banner_public_id = data['store_banner_public_id'] or None
        
        # ===== ADDRESS FIELDS =====
        if 'municipality' in data:
            store.municipality = data['municipality']
        if 'barangay' in data:
            store.barangay = data['barangay']
        # Handle both 'street' and 'street_address' for backwards compatibility
        if 'street_address' in data:
            store.street = data['street_address']
            print(f"✅ Updated street to: {data['street_address']}")
        elif 'street' in data:
            store.street = data['street']
            print(f"✅ Updated street to: {data['street']}")
        
        # Update full address
        if 'address' in data:
            store.address = data['address']
        else:
            if store.municipality and store.barangay:
                if store.street:
                    store.address = f"{store.street}, Barangay {store.barangay}, {store.municipality}, Laguna"
                else:
                    store.address = f"Barangay {store.barangay}, {store.municipality}, Laguna"
        
        if 'contact_number' in data:
            store.contact_number = data['contact_number']
        if 'description' in data:
            store.description = data['description']
        if 'status' in data:
            requested_status = (data.get('status') or '').strip().lower()
            current_status = (store.status or '').strip().lower()
            # Sellers may hide/show the storefront. Admin pending/suspended stays locked.
            if current_status not in ('pending', 'suspended') and requested_status in ('active', 'inactive'):
                store.status = requested_status
        
        # ===== LOCATION FIELDS =====
        if 'latitude' in data and data['latitude']:
            try:
                store.latitude = float(data['latitude'])
            except:
                pass
        if 'longitude' in data and data['longitude']:
            try:
                store.longitude = float(data['longitude'])
            except:
                pass
        if 'formatted_address' in data:
            store.formatted_address = data['formatted_address']
        if 'place_id' in data:
            store.place_id = data['place_id']
        
        # Update PostGIS location
        if store.latitude and store.longitude:
            try:
                from geoalchemy2.shape import from_shape
                from shapely.geometry import Point
                store.location = from_shape(Point(store.longitude, store.latitude), srid=4326)
            except Exception as e:
                print(f"⚠️ Could not update PostGIS location: {e}")
        
        # ===== STORE SCHEDULE =====
        if 'store_schedule' in data:
            from app.utils.store_schedule import sanitize_store_schedule
            schedule_value = data['store_schedule']
            if isinstance(schedule_value, str):
                try:
                    schedule_value = json.loads(schedule_value)
                except Exception:
                    schedule_value = None
            if isinstance(schedule_value, dict):
                cleaned = sanitize_store_schedule(schedule_value)
                if cleaned is not None:
                    store.store_schedule = cleaned
                    print(f"✅ Updated store_schedule: {store.store_schedule}")
        
        # ===== DELIVERY SETTINGS =====
        old_method = store.delivery_method
        if 'delivery_method' in data:
            store.delivery_method = data['delivery_method']
            print(f"✅ Updated delivery_method from {old_method} to {store.delivery_method}")
        
        if 'delivery_radius_km' in data:
            try:
                store.delivery_radius_km = float(data['delivery_radius_km'])
            except:
                pass
        if 'max_delivery_distance' in data:
            try:
                store.max_delivery_distance = float(data['max_delivery_distance'])
            except:
                pass
        if 'base_delivery_fee' in data:
            try:
                store.base_delivery_fee = float(data['base_delivery_fee'])
            except:
                pass
        if 'delivery_rate_per_km' in data:
            try:
                store.delivery_rate_per_km = float(data['delivery_rate_per_km'])
            except:
                pass
        if 'free_delivery_minimum' in data:
            try:
                store.free_delivery_minimum = float(data['free_delivery_minimum'])
            except:
                pass
        if 'free_delivery_enabled' in data:
            enabled_raw = str(data.get('free_delivery_enabled', '')).strip().lower()
            store.free_delivery_enabled = enabled_raw in {'1', 'true', 'yes', 'on'}
        
        # ===== ZONE DELIVERY AREA (always save when provided) =====
        if 'zone_delivery_area' in data:
            zone_value = data['zone_delivery_area']
            if zone_value and zone_value != 'null' and zone_value != 'None':
                try:
                    from geoalchemy2.shape import from_shape
                    from shapely.geometry import shape
                    
                    zone_geojson = json.loads(zone_value)
                    polygon = shape(zone_geojson)
                    store.zone_delivery_area = from_shape(polygon, srid=4326)
                    print(f"✅ Saved zone_delivery_area to database")
                except Exception as e:
                    print(f"⚠️ Error saving zone_delivery_area: {e}")

        effective_method = (data.get('delivery_method') or store.delivery_method or 'radius').strip().casefold()

        # A custom delivery zone must cover the store itself.  Otherwise a
        # seller could define an isolated delivery island unrelated to its pin.
        if effective_method == 'zone':
            if store.latitude is None or store.longitude is None:
                db.session.rollback()
                return jsonify({
                    'success': False,
                    'error': 'Set the store location pin before saving a custom delivery zone.',
                }), 400
            if store.zone_delivery_area is None:
                db.session.rollback()
                return jsonify({
                    'success': False,
                    'error': 'Draw a custom delivery zone that includes the store location.',
                }), 400
            try:
                from geoalchemy2.shape import to_shape
                from shapely.geometry import Point

                zone_shape = to_shape(store.zone_delivery_area)
                store_point = Point(float(store.longitude), float(store.latitude))
                if zone_shape is None or zone_shape.is_empty or not zone_shape.covers(store_point):
                    db.session.rollback()
                    return jsonify({
                        'success': False,
                        'error': 'Custom delivery zone must include the store location pin.',
                    }), 400
            except Exception as e:
                print(f"⚠️ Custom zone/store location validation failed: {e}")
                db.session.rollback()
                return jsonify({
                    'success': False,
                    'error': 'Could not validate that the custom delivery zone includes the store location.',
                }), 400
        
        # ===== MUNICIPALITY SELECTION (always save when provided) =====
        if 'selected_municipalities' in data:
            selected_muni = data['selected_municipalities']
            
            # Parse and save selected municipalities
            if isinstance(selected_muni, str):
                if selected_muni and selected_muni.strip():
                    if selected_muni.strip().startswith('['):
                        try:
                            store.selected_municipalities = json.loads(selected_muni)
                        except:
                            store.selected_municipalities = []
                    elif ',' in selected_muni:
                        store.selected_municipalities = [m.strip() for m in selected_muni.split(',') if m.strip()]
                    else:
                        store.selected_municipalities = [selected_muni.strip()] if selected_muni.strip() else []
                else:
                    store.selected_municipalities = []
            elif isinstance(selected_muni, list):
                store.selected_municipalities = selected_muni
            else:
                store.selected_municipalities = []
            print(f"✅ Saved selected_municipalities: {store.selected_municipalities}")
        
        # ===== MUNICIPALITY DELIVERY AREA (when generated) =====
        def _coerce_to_multipolygon(geom):
            from shapely.geometry import Polygon, MultiPolygon, GeometryCollection
            if geom is None or geom.is_empty:
                return None
            if isinstance(geom, MultiPolygon):
                return geom
            if isinstance(geom, Polygon):
                return MultiPolygon([geom])
            if isinstance(geom, GeometryCollection):
                polys = []
                for g in geom.geoms:
                    if isinstance(g, Polygon):
                        polys.append(g)
                    elif isinstance(g, MultiPolygon):
                        polys.extend(list(g.geoms))
                return MultiPolygon(polys) if polys else None
            return None

        def _merge_selected_municipality_geojson(names, province='Laguna'):
            if not names:
                return None
            from sqlalchemy import text
            from app.extensions import db as _db
            from app.models import MunicipalityBoundary as _MB
            resolved, missing = _MB.resolve_by_names(names, province=province)
            if missing or not resolved:
                print(f"⚠️ Municipality merge name resolve missing={missing}")
                return None
            db_names = [item['boundary'].name for item in resolved]
            placeholders = ','.join([f":m{i}" for i in range(len(db_names))])
            params = {f'm{i}': n for i, n in enumerate(db_names)}
            params['province'] = f'%{province}%'
            query = text(f"""
                SELECT ST_AsGeoJSON(ST_Multi(ST_CollectionExtract(ST_Union(boundary), 3))) as geometry
                FROM municipality_boundaries
                WHERE name IN ({placeholders})
                AND province ILIKE :province
            """)
            row = _db.session.execute(query, params).fetchone()
            if not row or not row[0]:
                return None
            return json.loads(row[0])

        muni_geo_saved = False
        if 'municipality_delivery_area' in data:
            muni_value = data['municipality_delivery_area']
            if muni_value and muni_value != 'null' and muni_value != 'None':
                try:
                    from geoalchemy2.shape import from_shape
                    from shapely.geometry import shape

                    muni_geojson = json.loads(muni_value)
                    if isinstance(muni_geojson, dict) and muni_geojson.get('type') == 'Feature':
                        muni_geojson = muni_geojson.get('geometry')
                    polygon = _coerce_to_multipolygon(shape(muni_geojson))
                    if polygon is None:
                        raise ValueError('Empty municipality geometry')
                    store.municipality_delivery_area = from_shape(polygon, srid=4326)
                    muni_geo_saved = True
                    print(f"✅ Saved municipality_delivery_area to database")
                except Exception as e:
                    print(f"⚠️ Error saving municipality_delivery_area: {e}")

        # Auto-build WKB when municipality method is selected but geo was not posted
        if (
            effective_method == 'municipality'
            and store.selected_municipalities
            and not muni_geo_saved
        ):
            try:
                from geoalchemy2.shape import from_shape
                from shapely.geometry import shape
                merged = _merge_selected_municipality_geojson(store.selected_municipalities)
                if merged:
                    polygon = _coerce_to_multipolygon(shape(merged))
                    if polygon is not None:
                        store.municipality_delivery_area = from_shape(polygon, srid=4326)
                        print(f"✅ Auto-merged municipality_delivery_area from {store.selected_municipalities}")
            except Exception as e:
                print(f"⚠️ Auto-merge municipality_delivery_area failed: {e}")

        # Block non-adjacent municipality coverage from being saved
        if effective_method == 'municipality':
            selected_for_check = store.selected_municipalities or []
            if not selected_for_check:
                db.session.rollback()
                return jsonify({
                    'success': False,
                    'error': 'Select at least one municipality for delivery coverage.'
                }), 400
            store_municipality = _normalize_place_name(store.municipality)
            if not store_municipality:
                db.session.rollback()
                return jsonify({
                    'success': False,
                    'error': 'Set the municipality for the store location pin before using municipality coverage.',
                }), 400
            if not any(
                _normalize_place_name(municipality) == store_municipality
                for municipality in selected_for_check
            ):
                db.session.rollback()
                return jsonify({
                    'success': False,
                    'error': (
                        f'The store municipality ({store.municipality}) must be included '
                        'as the starting point for municipality delivery coverage.'
                    ),
                }), 400
            try:
                contig = _evaluate_municipality_contiguity(selected_for_check, province='Laguna')
                if not contig.get('contiguous'):
                    disconnected = contig.get('disconnected') or []
                    detail = f" Non-adjacent: {', '.join(disconnected)}." if disconnected else ''
                    db.session.rollback()
                    return jsonify({
                        'success': False,
                        'error': f'Selected municipalities must be adjacent (share borders).{detail}',
                        'disconnected': disconnected,
                    }), 400
            except Exception as e:
                print(f"⚠️ Municipality contiguity validation failed: {e}")
                db.session.rollback()
                return jsonify({
                    'success': False,
                    'error': 'Could not validate municipality adjacency. Please try again.'
                }), 400
        
        # ===== UPDATE ACTIVE DELIVERY AREA BASED ON CURRENT METHOD =====
        store.update_delivery_area_from_method()
        
        # ===== GCASH QR CODE HANDLING WITH CLOUDINARY =====
        print("\n📱 Processing GCash QR codes with Cloudinary...")

        # Get QR IDs to keep and delete
        qr_ids_to_keep = []
        if 'gcash_qr_ids_to_keep' in data:
            keep_str = data['gcash_qr_ids_to_keep']
            if keep_str:
                try:
                    qr_ids_to_keep = json.loads(keep_str)
                except:
                    qr_ids_to_keep = []

        qr_ids_to_delete = []
        if 'gcash_qr_ids_to_delete' in data:
            delete_str = data['gcash_qr_ids_to_delete']
            if delete_str:
                try:
                    qr_ids_to_delete = json.loads(delete_str)
                except:
                    qr_ids_to_delete = []

        primary_qr_id = data.get('primary_qr_id')
        primary_qr_public_id = data.get('primary_qr_public_id')

        # Import Cloudinary helper
        from app.utils.cloudinary_helper import delete_from_cloudinary

        # Delete marked QR codes from Cloudinary and database
        for qr_id in qr_ids_to_delete:
            qr = GCashQR.query.get(qr_id)
            if qr and qr.store_id == store.id:
                # Delete from Cloudinary if public_id exists
                if qr.public_id:
                    delete_from_cloudinary(qr.public_id)
                    print(f"   🗑️ Deleted QR from Cloudinary: {qr.public_id}")
                
                # Delete from database
                db.session.delete(qr)
                print(f"   ✅ Deleted QR record ID: {qr_id}")

        # Process new QR code uploads from Cloudinary
        current_qr_count = GCashQR.query.filter_by(store_id=store.id).count()
        next_sort_order = current_qr_count

        # Look for Cloudinary QR data in form data (sent from frontend after upload)
        qr_index = 0
        while f'gcash_qr_public_id_{qr_index}' in data:
            public_id = data.get(f'gcash_qr_public_id_{qr_index}')
            url = data.get(f'gcash_qr_url_{qr_index}')
            filename = data.get(f'gcash_qr_filename_{qr_index}')
            
            if public_id and url:
                is_primary = False
                
                new_qr = GCashQR(
                    store_id=store.id,
                    filename=filename or f"gcash_{public_id}.jpg",
                    public_id=public_id,
                    cloudinary_url=url,
                    is_primary=is_primary,
                    sort_order=next_sort_order
                )
                db.session.add(new_qr)
                next_sort_order += 1
                print(f"   ✅ Created new QR record from Cloudinary: {public_id}")
            
            qr_index += 1

        # Also check for file uploads (backward compatibility, but not recommended)
        for key in files:
            if key.startswith('gcash_qr_'):
                file = files[key]
                if file and file.filename:
                    print(f"   ⚠️ Direct file upload detected for {key}. Please use Cloudinary upload instead.")
                    # You could still process it, but better to use Cloudinary
                    # Consider showing a warning to the user

        # Update sort_order for kept QRs
        if qr_ids_to_keep:
            kept_qrs = GCashQR.query.filter(GCashQR.id.in_(qr_ids_to_keep)).all()
            for i, qr in enumerate(kept_qrs):
                qr.sort_order = i
                qr.is_primary = False

        # Persist explicit primary QR choice from UI.
        all_store_qrs = GCashQR.query.filter_by(store_id=store.id).all()
        for qr in all_store_qrs:
            qr.is_primary = False

        chosen_primary = None
        if primary_qr_id:
            try:
                chosen_primary = GCashQR.query.filter_by(id=int(primary_qr_id), store_id=store.id).first()
            except Exception:
                chosen_primary = None

        if not chosen_primary and primary_qr_public_id:
            chosen_primary = GCashQR.query.filter_by(store_id=store.id, public_id=primary_qr_public_id).first()

        if not chosen_primary and all_store_qrs:
            chosen_primary = sorted(all_store_qrs, key=lambda q: (q.sort_order or 0, q.id or 0))[0]

        if chosen_primary:
            chosen_primary.is_primary = True

        # Update GCash instructions
        if 'gcash_instructions' in data:
            store.gcash_instructions = data['gcash_instructions']

        # Store-level payment options
        if 'allow_cod' in data:
            allow_cod_raw = str(data.get('allow_cod', '')).strip().lower()
            allow_cod = allow_cod_raw in {'1', 'true', 'yes', 'on'}
            payment_setting = StorePaymentSetting.query.filter_by(store_id=store.id).first()
            if not payment_setting:
                payment_setting = StorePaymentSetting(store_id=store.id)
                db.session.add(payment_setting)
            payment_setting.allow_cod = allow_cod
        
        store.updated_at = datetime.utcnow()
        db.session.commit()
        
        print("✅ Database commit successful")
        print(f"📊 FINAL STORE DATA AFTER COMMIT:")
        print(f"   delivery_method: {store.delivery_method}")
        print(f"   has zone_delivery_area: {store.zone_delivery_area is not None}")
        print(f"   selected_municipalities: {store.selected_municipalities}")
        print(f"   has municipality_delivery_area: {store.municipality_delivery_area is not None}")
        
        return jsonify({
            'success': True,
            'message': 'Store settings updated successfully',
            'store': store.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ ERROR UPDATING STORE SETTINGS: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
    
@templates_bp.route('/api/seller/store/geocode', methods=['POST'])
@seller_required
def reverse_geocode():
    """Reverse geocode coordinates to get address using Mapbox"""
    print("\n" + "="*60)
    print("📍 REVERSE GEOCODE REQUEST")
    
    try:
        data = request.get_json()
        lat = data.get('latitude')
        lng = data.get('longitude')
        
        print(f"Coordinates: lat={lat}, lng={lng}")
        
        if not lat or not lng:
            print("❌ Missing coordinates")
            return jsonify({'error': 'Latitude and longitude required'}), 400
        
        import requests
        mapbox_token = os.getenv('MAPBOX_PUBLIC_TOKEN')
        
        print(f"Mapbox token exists: {mapbox_token is not None}")
        if mapbox_token:
            print(f"Token preview: {mapbox_token[:10]}...")
        else:
            print("❌ MAPBOX_PUBLIC_TOKEN not found in environment")
            return jsonify({'error': 'Mapbox token not configured'}), 500
        
        url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{lng},{lat}.json"
        params = {
            'access_token': mapbox_token,
            'types': 'address,poi,place,locality',
            'language': 'en',
            'limit': 1
        }
        
        print(f"Calling Mapbox API: {url}")
        
        response = requests.get(url, params=params, timeout=5)
        print(f"Mapbox response status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ Mapbox error: {response.text[:200]}")
            return jsonify({'error': f'Failed to geocode: {response.status_code}'}), 500
        
        data = response.json()
        print(f"Mapbox response keys: {list(data.keys())}")
        
        if data.get('features') and len(data['features']) > 0:
            feature = data['features'][0]
            print(f"✅ Found address: {feature['place_name']}")
            print("="*60 + "\n")
            return jsonify({
                'success': True,
                'address': feature['place_name'],
                'place_id': feature['id']
            })
        else:
            print("❌ No address found for these coordinates")
            print("="*60 + "\n")
            return jsonify({'error': 'No address found'}), 404
            
    except requests.exceptions.Timeout:
        print("❌ Mapbox API timeout")
        return jsonify({'error': 'Mapbox API timeout'}), 500
    except requests.exceptions.RequestException as e:
        print(f"❌ Mapbox request error: {e}")
        return jsonify({'error': f'Mapbox request failed: {str(e)}'}), 500
    except Exception as e:
        print(f"❌ Unexpected error in reverse_geocode: {str(e)}")
        import traceback
        traceback.print_exc()
        print("="*60 + "\n")
        return jsonify({'error': str(e)}), 500
'''
# ADD THIS DEBUG ENDPOINT
@templates_bp.route('/debug/mapbox-config')
def debug_mapbox_config():
    """Debug endpoint to check Mapbox configuration"""
    mapbox_token = os.getenv('MAPBOX_PUBLIC_TOKEN')
    return jsonify({
        'token_exists': mapbox_token is not None,
        'token_preview': mapbox_token[:15] + '...' if mapbox_token else None,
        'token_length': len(mapbox_token) if mapbox_token else 0,
        'env_keys': list(os.environ.keys())  # BE CAREFUL - this exposes all env vars!
    })
'''



@templates_bp.route('/api/laguna/municipalities', methods=['GET'])
def get_laguna_municipalities():
    """Get all municipalities in Laguna"""
    try:
        municipalities = get_municipalities()
        return jsonify({
            'success': True,
            'municipalities': municipalities
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@templates_bp.route('/api/laguna/barangays/<municipality>', methods=['GET'])
def get_municipality_barangays(municipality):
    """Get all barangays for a specific municipality"""
    try:
        barangays = get_barangays(municipality)
        coordinates = get_coordinates(municipality)
        
        return jsonify({
            'success': True,
            'municipality': municipality,
            'barangays': barangays,
            'coordinates': coordinates
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@templates_bp.route('/api/laguna/barangay-coordinates/<municipality>/<barangay>', methods=['GET'])
def get_barangay_coordinates(municipality, barangay):
    """Get approximate coordinates for a specific barangay within a municipality"""
    try:
        from app.laguna_addresses import LAGUNA_ADDRESSES
        
        if municipality not in LAGUNA_ADDRESSES:
            return jsonify({'error': 'Municipality not found'}), 404
        
        muni_data = LAGUNA_ADDRESSES[municipality]
        muni_coords = muni_data.get('coordinates', {})
        
        # For now, return municipality center coordinates as barangay coordinates
        # Users can fine-tune with the map
        return jsonify({
            'success': True,
            'municipality': municipality,
            'barangay': barangay,
            'coordinates': muni_coords  # Uses municipality center as starting point
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@templates_bp.route('/api/account/addresses', methods=['GET'])
def get_user_addresses():
    """Get all addresses for the logged-in user (supports JWT and sessions)"""
    user_id = get_authenticated_user_id()
    if not user_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        addresses = UserAddress.query.filter_by(user_id=user_id).order_by(
            UserAddress.is_default.desc(),
            UserAddress.created_at.desc()
        ).all()
        
        print(f"✅ Retrieved {len(addresses)} addresses for user {user_id}")
        
        return jsonify({
            'success': True,
            'addresses': [addr.to_dict() for addr in addresses]
        })
    except Exception as e:
        print(f"❌ Error fetching addresses: {str(e)}")
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/account/addresses', methods=['POST'])
def add_user_address():
    """Add a new address for the user (supports JWT and sessions)"""
    user_id = get_authenticated_user_id()
    if not user_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        data = request.get_json()
        
        # Validate required fields
        required = ['municipality', 'barangay', 'address_label', 'latitude', 'longitude']
        for field in required:
            if field not in data or data[field] is None:
                return jsonify({'error': f'{field} is required'}), 400
        
        # Format the complete address
        address_line = format_address(
            data['municipality'],
            data['barangay'],
            data.get('street'),
            data.get('building_details')
        )
        
        # If this is set as default, unset other defaults
        if data.get('is_default'):
            UserAddress.query.filter_by(
                user_id=user_id,
                is_default=True
            ).update({'is_default': False})
        
        # Create new address with EXACT coordinates and place_id from Mapbox
        address = UserAddress(
            user_id=user_id,
            municipality=data['municipality'],
            barangay=data['barangay'],
            street=data.get('street'),
            building_details=data.get('building_details'),
            address_line=address_line,
            latitude=float(data['latitude']),    # EXACT from map
            longitude=float(data['longitude']),  # EXACT from map
            place_id=data.get('place_id'),        # Mapbox place_id (optional)
            address_label=data['address_label'],
            is_default=data.get('is_default', False)
        )
        
        db.session.add(address)
        db.session.commit()
        
        print(f"✅ Address created for user {user_id}: {address_line}")
        
        return jsonify({
            'success': True,
            'message': 'Address added successfully',
            'address': address.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error adding address: {str(e)}")
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/account/addresses/<int:address_id>', methods=['PUT'])
def update_user_address(address_id):
    """Update an existing address (supports JWT and sessions)"""
    user_id = get_authenticated_user_id()
    if not user_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        address = UserAddress.query.filter_by(
            id=address_id,
            user_id=user_id
        ).first()
        
        if not address:
            return jsonify({'error': 'Address not found'}), 404
        
        data = request.get_json()
        
        # Update fields
        if 'municipality' in data:
            address.municipality = data['municipality']
        if 'barangay' in data:
            address.barangay = data['barangay']
        if 'street' in data:
            address.street = data['street']
        if 'building_details' in data:
            address.building_details = data['building_details']
        if 'address_label' in data:
            address.address_label = data['address_label']
        
        # Update EXACT coordinates from Mapbox (if provided)
        if 'latitude' in data and data['latitude'] is not None:
            address.latitude = float(data['latitude'])
        if 'longitude' in data and data['longitude'] is not None:
            address.longitude = float(data['longitude'])
        
        # Update place_id (if provided)
        if 'place_id' in data:
            address.place_id = data['place_id']
        
        # Reformat address line
        address.address_line = format_address(
            address.municipality,
            address.barangay,
            address.street,
            address.building_details
        )
        
        # Handle default status
        if data.get('is_default'):
            UserAddress.query.filter_by(
                user_id=user_id,
                is_default=True
            ).filter(UserAddress.id != address_id).update({'is_default': False})
            address.is_default = True
        elif 'is_default' in data:
            address.is_default = False
        
        address.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Address updated successfully',
            'address': address.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating address: {str(e)}")
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/account/addresses/<int:address_id>', methods=['DELETE'])
def delete_user_address(address_id):
    """Delete an address (supports JWT and sessions)"""
    user_id = get_authenticated_user_id()
    if not user_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        address = UserAddress.query.filter_by(
            id=address_id,
            user_id=user_id
        ).first()
        
        if not address:
            return jsonify({'error': 'Address not found'}), 404
        
        # If this was the default, make another address default
        if address.is_default:
            next_address = UserAddress.query.filter_by(
                user_id=user_id
            ).filter(UserAddress.id != address_id).first()
            
            if next_address:
                next_address.is_default = True
        
        db.session.delete(address)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Address deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting address: {str(e)}")
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/account/addresses/<int:address_id>/set-default', methods=['POST'])
def set_default_address(address_id):
    """Set an address as default (supports JWT and sessions)"""
    user_id = get_authenticated_user_id()
    if not user_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        address = UserAddress.query.filter_by(
            id=address_id,
            user_id=user_id
        ).first()
        
        if not address:
            return jsonify({'error': 'Address not found'}), 404
        
        # Unset all other defaults
        UserAddress.query.filter_by(
            user_id=user_id,
            is_default=True
        ).update({'is_default': False})
        
        # Set this one as default
        address.is_default = True
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Default address updated',
            'address': address.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500






# ===== MUNICIPALITY BOUNDARY ENDPOINTS =====
@templates_bp.route('/api/municipality-boundaries', methods=['GET'])
def get_municipality_boundaries():
    """Get all municipality boundaries as GeoJSON FeatureCollection"""
    try:
        # Check if the MunicipalityBoundary model exists
        from app.models import MunicipalityBoundary
        
        # Optional: filter by province
        province = request.args.get('province', 'Laguna')
        
        query = MunicipalityBoundary.query
        if province:
            query = query.filter(MunicipalityBoundary.province.ilike(f'%{province}%'))
        
        municipalities = query.order_by(MunicipalityBoundary.name).all()
        
        features = [m.to_geojson() for m in municipalities]
        
        return jsonify({
            'type': 'FeatureCollection',
            'features': features,
            'count': len(features)
        })
    except ImportError:
        return jsonify({'error': 'MunicipalityBoundary model not found'}), 500
    except Exception as e:
        print(f"Error getting boundaries: {e}")
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/municipality/province-boundary', methods=['GET'])
def get_province_merged_boundary():
    """Merge all municipality polygons in a province into one geometry (GeoJSON) for map overlays."""
    province = (request.args.get('province') or 'Laguna').strip()
    if not province:
        return jsonify({'success': False, 'error': 'province is required'}), 400
    try:
        from sqlalchemy import func as sa_func
        from geoalchemy2.functions import ST_AsGeoJSON, ST_Union

        merged_geojson = (
            db.session.query(ST_AsGeoJSON(ST_Union(MunicipalityBoundary.boundary)))
            .filter(MunicipalityBoundary.province.ilike(f'%{province}%'))
            .scalar()
        )
        if not merged_geojson:
            return jsonify({'success': False, 'error': 'No boundary rows for this province'}), 404

        geometry = json.loads(merged_geojson)
        return jsonify({
            'success': True,
            'province': province,
            'geometry': geometry,
        })
    except Exception as e:
        current_app.logger.exception('get_province_merged_boundary: %s', e)
        return jsonify({'success': False, 'error': str(e)}), 500


def _evaluate_municipality_contiguity(municipalities, province='Laguna'):
    """Return {contiguous, connected, disconnected, missing, error?} for UI municipality names."""
    names = [n for n in (municipalities or []) if n]
    if not names:
        return {
            'contiguous': True,
            'connected': [],
            'disconnected': [],
            'missing': [],
        }
    if len(names) == 1:
        return {
            'contiguous': True,
            'connected': names,
            'disconnected': [],
            'missing': [],
        }

    resolved, missing = MunicipalityBoundary.resolve_by_names(names, province=province)
    if missing:
        return {
            'contiguous': False,
            'connected': [],
            'disconnected': names,
            'missing': missing,
            'error': f'Some municipalities not found in database: {", ".join(missing)}',
        }

    ui_names = [item['requested'] for item in resolved]
    id_to_ui = {item['boundary'].id: item['requested'] for item in resolved}
    ids = list(id_to_ui.keys())

    placeholders = ','.join([f':id{i}' for i in range(len(ids))])
    params = {f'id{i}': i_val for i, i_val in enumerate(ids)}
    pair_sql = text(f"""
        SELECT a.id AS id_a, b.id AS id_b
        FROM municipality_boundaries a
        JOIN municipality_boundaries b ON a.id < b.id
        WHERE a.id IN ({placeholders})
          AND b.id IN ({placeholders})
          AND (
            ST_Touches(a.boundary, b.boundary)
            OR ST_Intersects(a.boundary, b.boundary)
          )
    """)
    edges = db.session.execute(pair_sql, params).fetchall()

    adj = {name: set() for name in ui_names}
    for row in edges:
        a = id_to_ui.get(row.id_a)
        b = id_to_ui.get(row.id_b)
        if a and b:
            adj[a].add(b)
            adj[b].add(a)

    def component_from(start):
        visited = set()
        queue = [start]
        visited.add(start)
        while queue:
            current = queue.pop(0)
            for neighbor in adj.get(current, ()):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                queue.append(neighbor)
        return visited

    remaining = set(ui_names)
    components = []
    while remaining:
        start = next(iter(remaining))
        comp = component_from(start)
        components.append(comp)
        remaining -= comp

    largest = max(components, key=len) if components else set()
    connected = [name for name in ui_names if name in largest]
    disconnected = [name for name in ui_names if name not in largest]
    return {
        'contiguous': len(disconnected) == 0,
        'connected': connected,
        'disconnected': disconnected,
        'missing': [],
    }


@templates_bp.route('/api/municipality/check-contiguity', methods=['POST'])
def check_municipality_contiguity():
    """Check if a list of municipalities are contiguous (single PostGIS adjacency query)."""
    try:
        data = request.get_json()
        municipalities = data.get('municipalities', [])
        province = data.get('province', 'Laguna')

        result = _evaluate_municipality_contiguity(municipalities, province=province)
        if result.get('missing'):
            return jsonify({
                'contiguous': False,
                'connected': result.get('connected') or [],
                'disconnected': result.get('disconnected') or municipalities,
                'error': result.get('error') or 'Some municipalities not found in database',
            }), 404

        is_contiguous = bool(result.get('contiguous'))
        return jsonify({
            'contiguous': is_contiguous,
            'selected_count': len(municipalities or []),
            'connected_count': len(result.get('connected') or []),
            'connected': result.get('connected') or [],
            'disconnected': result.get('disconnected') or [],
            'message': 'Municipalities are contiguous' if is_contiguous else 'Municipalities are not contiguous'
        })
        
    except ImportError:
        return jsonify({'error': 'MunicipalityBoundary model not found'}), 500
    except Exception as e:
        print(f"Error checking contiguity: {e}")
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/municipality/merge-boundaries', methods=['POST'])
def merge_municipality_boundaries():
    """Merge multiple municipality boundaries into one MultiPolygon"""
    try:
        from app.models import MunicipalityBoundary
        from sqlalchemy import text
        
        data = request.get_json()
        municipalities = data.get('municipalities', [])
        province = data.get('province', 'Laguna')
        
        if not municipalities:
            return jsonify({'error': 'No municipalities provided'}), 400

        resolved, missing = MunicipalityBoundary.resolve_by_names(municipalities, province=province)
        if missing:
            return jsonify({'error': f'Some municipalities not found: {", ".join(missing)}'}), 404
        if not resolved:
            return jsonify({'error': 'No municipalities provided'}), 400

        db_names = [item['boundary'].name for item in resolved]
        
        # Use PostGIS ST_Union to merge boundaries (force MultiPolygon for column type)
        placeholders = ','.join([f':n{i}' for i in range(len(db_names))])
        params = {f'n{i}': n for i, n in enumerate(db_names)}
        params['province'] = f'%{province}%'
        query = text(f"""
            SELECT ST_AsGeoJSON(
                ST_Multi(ST_CollectionExtract(ST_Union(boundary), 3))
            ) as geometry
            FROM municipality_boundaries
            WHERE name IN ({placeholders})
            AND province ILIKE :province
        """)
        
        from app.extensions import db
        result = db.session.execute(query, params).fetchone()
        
        if not result or not result[0]:
            return jsonify({'error': 'Could not merge boundaries'}), 404
        
        import json
        geometry = json.loads(result[0])
        
        return jsonify({
            'success': True,
            'type': 'Feature',
            'geometry': geometry,
            'municipalities': [item['requested'] for item in resolved],
            'boundary_names': db_names
        })
        
    except ImportError:
        return jsonify({'error': 'MunicipalityBoundary model not found'}), 500
    except Exception as e:
        print(f"Error merging boundaries: {e}")
        return jsonify({'error': str(e)}), 500

























# ===== PRODUCT VARIANT ROUTES =====
@templates_bp.route('/api/seller/products/<int:product_id>/variants', methods=['GET'])
@seller_required
def get_product_variants(product_id):
    """Get all variants for a product"""
    try:
        store = Store.query.filter_by(seller_id=session['user_id']).first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        variants = [v.to_dict() for v in product.variants]
        
        return jsonify({
            'success': True,
            'variants': variants
        })
        
    except Exception as e:
        print(f"Error getting variants: {str(e)}")
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/seller/variants/<int:variant_id>', methods=['GET'])
@seller_required
def get_variant(variant_id):
    """Get a single variant by ID"""
    try:
        store = Store.query.filter_by(seller_id=session['user_id']).first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        variant = ProductVariant.query.get(variant_id)
        if not variant:
            return jsonify({'error': 'Variant not found'}), 404
        
        # Verify product belongs to seller's store
        if variant.product.store_id != store.id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        return jsonify({
            'success': True,
            'variant': variant.to_dict()
        })
        
    except Exception as e:
        print(f"Error getting variant: {str(e)}")
        return jsonify({'error': str(e)}), 500

@templates_bp.route('/api/seller/variants/create', methods=['POST'])
@seller_required
def create_variant():
    """Create a new product variant"""
    print("\n" + "="*60)
    print("📥 CREATE VARIANT REQUEST RECEIVED")
    
    try:
        store = Store.query.filter_by(seller_id=session['user_id']).first()
        if not store:
            print("❌ Store not found")
            return jsonify({'error': 'Store not found'}), 404
        
        # Debug: Print all form data
        print(f"📋 Form data keys: {list(request.form.keys())}")
        print(f"📋 Form data values:")
        for key in request.form.keys():
            print(f"   {key}: {request.form.get(key)}")
        
        print(f"📎 Files: {list(request.files.keys())}")
        
        product_id = request.form.get('product_id')
        if not product_id:
            print("❌ Product ID is missing")
            return jsonify({'error': 'Product ID is required'}), 400
        
        try:
            product_id = int(product_id)
        except ValueError:
            print(f"❌ Invalid product_id format: {product_id}")
            return jsonify({'error': 'Invalid product ID format'}), 400
        
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            print(f"❌ Product {product_id} not found in store {store.id}")
            return jsonify({'error': 'Product not found'}), 404
        
        name = request.form.get('name')
        price = request.form.get('price')
        stock_quantity = request.form.get('stock_quantity')
        
        print(f"📝 Variant data - Name: {name}, Price: {price}, Stock: {stock_quantity}")
        
        if not name:
            print("❌ Name is missing")
            return jsonify({'error': 'Variant name is required'}), 400
        if not price:
            print("❌ Price is missing")
            return jsonify({'error': 'Price is required'}), 400
        if not stock_quantity:
            print("❌ Stock quantity is missing")
            return jsonify({'error': 'Stock quantity is required'}), 400
        
        try:
            price_float = float(price)
            if price_float < 0:
                print(f"❌ Price cannot be negative: {price_float}")
                return jsonify({'error': 'Price cannot be negative'}), 400
        except ValueError as e:
            print(f"❌ Invalid price format: {price} - {e}")
            return jsonify({'error': 'Invalid price format'}), 400
        
        try:
            stock_int = int(stock_quantity)
            if stock_int < 0:
                print(f"❌ Stock cannot be negative: {stock_int}")
                return jsonify({'error': 'Stock quantity cannot be negative'}), 400
        except ValueError as e:
            print(f"❌ Invalid stock format: {stock_quantity} - {e}")
            return jsonify({'error': 'Invalid stock quantity format'}), 400
        
        # Parse attributes JSON if provided
        attributes = None
        attributes_str = request.form.get('attributes')
        if attributes_str:
            print(f"📋 Attributes string: {attributes_str}")
            try:
                attributes = json.loads(attributes_str)
                print(f"✅ Parsed attributes: {attributes}")
            except json.JSONDecodeError as e:
                print(f"❌ Invalid attributes JSON: {e}")
                return jsonify({'error': 'Invalid attributes JSON'}), 400
        
        # Handle variant image upload
        image_filename = None
        if 'image' in request.files:
            file = request.files['image']
            print(f"📸 Image file received: {file.filename if file.filename else 'None'}")
            
            if file and file.filename and allowed_file(file.filename):
                # Create variant images directory if it doesn't exist
                variant_upload_path = os.path.join(BASE_DIR, 'static', 'uploads', 'product_variants')
                os.makedirs(variant_upload_path, exist_ok=True)
                
                # Generate filename
                ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
                timestamp = str(int(time.time()))[-6:]
                random_str = uuid.uuid4().hex[:8]
                image_filename = f"v{product_id}_{timestamp}_{random_str}.{ext}"
                
                filepath = os.path.join(variant_upload_path, image_filename)
                file.save(filepath)
                print(f"✅ Saved variant image: {image_filename}")
            else:
                print(f"⚠️ Invalid file or not allowed: {file.filename if file.filename else 'No file'}")
        
        # Get max sort order
        max_sort = db.session.query(db.func.max(ProductVariant.sort_order)).filter_by(product_id=product.id).scalar() or 0
        print(f"📊 Max sort order: {max_sort}, new sort order: {max_sort + 1}")
        
        is_available = request.form.get('is_available', 'true').lower()
        print(f"🔘 is_available: {is_available}")
        
        variant = ProductVariant(
            product_id=product.id,
            name=name.strip(),
            price=price_float,
            stock_quantity=stock_int,
            sku=request.form.get('sku') or None,
            image_filename=image_filename,
            attributes=attributes,
            sort_order=max_sort + 1,
            is_available=is_available == 'true'
        )
        
        db.session.add(variant)
        db.session.commit()
        
        print(f"✅ Variant created successfully with ID: {variant.id}")
        print("="*60 + "\n")
        
        return jsonify({
            'success': True,
            'message': 'Variant created successfully',
            'variant': variant.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error creating variant: {str(e)}")
        import traceback
        traceback.print_exc()
        print("="*60 + "\n")
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/seller/variants/<int:variant_id>', methods=['PUT'])
@seller_required
def update_variant(variant_id):
    """Update a product variant"""
    try:
        store = Store.query.filter_by(seller_id=session['user_id']).first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        variant = ProductVariant.query.get(variant_id)
        if not variant:
            return jsonify({'error': 'Variant not found'}), 404
        
        # Verify product belongs to seller's store
        if variant.product.store_id != store.id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Update fields
        if request.form.get('name'):
            variant.name = request.form.get('name').strip()
        
        if request.form.get('price'):
            try:
                variant.price = float(request.form.get('price'))
            except ValueError:
                return jsonify({'error': 'Invalid price format'}), 400
        
        if request.form.get('stock_quantity'):
            try:
                variant.stock_quantity = int(request.form.get('stock_quantity'))
            except ValueError:
                return jsonify({'error': 'Invalid stock quantity format'}), 400
        
        if request.form.get('sku') is not None:
            variant.sku = request.form.get('sku') or None
        
        if request.form.get('attributes'):
            try:
                variant.attributes = json.loads(request.form.get('attributes'))
            except:
                return jsonify({'error': 'Invalid attributes JSON'}), 400
        elif 'attributes' in request.form:
            variant.attributes = None
        
        if request.form.get('is_available') is not None:
            variant.is_available = request.form.get('is_available').lower() == 'true'
        
        # Handle variant image upload
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename):
                # Delete old image if exists
                if variant.image_filename:
                    old_path = os.path.join(BASE_DIR, 'static', 'uploads', 'product_variants', variant.image_filename)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                
                # Save new image
                variant_upload_path = os.path.join(BASE_DIR, 'static', 'uploads', 'product_variants')
                os.makedirs(variant_upload_path, exist_ok=True)
                
                ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
                timestamp = str(int(time.time()))[-6:]
                random_str = uuid.uuid4().hex[:8]
                image_filename = f"v{variant.product_id}_{timestamp}_{random_str}.{ext}"
                
                filepath = os.path.join(variant_upload_path, image_filename)
                file.save(filepath)
                variant.image_filename = image_filename
                print(f"📸 Updated variant image: {image_filename}")
        
        variant.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Variant updated successfully',
            'variant': variant.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating variant: {str(e)}")
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/seller/variants/<int:variant_id>', methods=['DELETE'])
@seller_required
def delete_variant(variant_id):
    """Delete a product variant"""
    try:
        store = Store.query.filter_by(seller_id=session['user_id']).first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        variant = ProductVariant.query.get(variant_id)
        if not variant:
            return jsonify({'error': 'Variant not found'}), 404
        
        # Verify product belongs to seller's store
        if variant.product.store_id != store.id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Check if variant is in any carts or orders
        cart_count = CartItem.query.filter_by(variant_id=variant_id).count()
        order_count = OrderItem.query.filter_by(variant_id=variant_id).count()
        pos_count = POSOrderItem.query.filter_by(variant_id=variant_id).count()
        
        if cart_count > 0 or order_count > 0 or pos_count > 0:
            return jsonify({
                'error': f'Cannot delete. Variant is in {cart_count} carts and {order_count + pos_count} orders.'
            }), 400
        
        # Delete image file if exists
        if variant.image_filename:
            image_path = os.path.join(BASE_DIR, 'static', 'uploads', 'product_variants', variant.image_filename)
            if os.path.exists(image_path):
                os.remove(image_path)
        
        db.session.delete(variant)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Variant deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting variant: {str(e)}")
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/seller/variants/reorder', methods=['POST'])
@seller_required
def reorder_variants():
    """Reorder variants for a product"""
    try:
        store = Store.query.filter_by(seller_id=session['user_id']).first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        data = request.get_json()
        product_id = data.get('product_id')
        variant_order = data.get('variant_order', [])  # List of variant IDs in desired order
        
        if not product_id or not variant_order:
            return jsonify({'error': 'Product ID and variant order required'}), 400
        
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        for index, variant_id in enumerate(variant_order):
            variant = ProductVariant.query.get(variant_id)
            if variant and variant.product_id == product.id:
                variant.sort_order = index
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Variants reordered successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error reordering variants: {str(e)}")
        return jsonify({'error': str(e)}), 500
    



@templates_bp.route('/seller/products/add')
@seller_required
def add_product_page():
    """Render the add/edit product page"""
    product_id = request.args.get('edit')
    is_edit = bool(product_id)
    product = None
    
    # ===== ADD THIS: Get all main categories =====
    from app.models import Category
    main_categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()
    # =============================================
    
    if is_edit:
        # Convert product_id to integer
        try:
            product_id = int(product_id)
        except (TypeError, ValueError):
            flash('Invalid product ID', 'error')
            return redirect(url_for('templates.seller_products'))
        
        store = _get_seller_store()
        if not store:
            flash('Store not found', 'error')
            return redirect(url_for('templates.seller_products'))
        
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            flash('Product not found', 'error')
            return redirect(url_for('templates.seller_products'))
    
    return render_template('add_product.html', 
                         is_edit=is_edit, 
                         product=product,
                         main_categories=main_categories)  # ← Pass to template








@templates_bp.route('/api/store/<int:store_id>/gcash-qrs', methods=['GET'])
def get_store_gcash_qrs(store_id):
    """Get GCash QR codes for a store (for checkout page)"""
    try:
        store = Store.query.get_or_404(store_id)
        
        # Build QR code URLs
        qr_codes = []
        if store.gcash_qr_codes:
            qr_codes_list = store.gcash_qr_codes
            if isinstance(qr_codes_list, str):
                try:
                    qr_codes_list = json.loads(qr_codes_list)
                except:
                    qr_codes_list = []
            
            for i, filename in enumerate(qr_codes_list):
                if filename:
                    qr_codes.append({
                        'url': f'/static/uploads/gcash_qr/{filename}',
                        'is_primary': (i == 0)
                    })
        
        _ensure_store_payment_settings_table()
        payment_setting = StorePaymentSetting.query.filter_by(store_id=store.id).first()

        return jsonify({
            'success': True,
            'qr_codes': qr_codes,
            'instructions': store.gcash_instructions,
            'allow_cod': bool(payment_setting.allow_cod) if payment_setting else False,
        })
        
    except Exception as e:
        print(f"Error getting GCash QR codes: {str(e)}")
        return jsonify({'error': str(e)}), 500
    



@templates_bp.route('/api/seller/store/gcash-qr/<path:filename>', methods=['DELETE'])
@seller_required
def delete_gcash_qr(filename):
    """Delete a specific GCash QR code"""
    try:
        store = Store.query.filter_by(seller_id=session['user_id']).first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        # Security: Prevent directory traversal
        if '..' in filename or filename.startswith('/'):
            return jsonify({'error': 'Invalid filename'}), 400
        
        # Check if QR code exists in store's list
        qr_codes = store.gcash_qr_codes or []
        if isinstance(qr_codes, str):
            try:
                qr_codes = json.loads(qr_codes)
            except:
                qr_codes = []
        
        if filename not in qr_codes:
            return jsonify({'error': 'QR code not found'}), 404
        
        # Delete file
        gcash_upload_path = os.path.join(BASE_DIR, 'static', 'uploads', 'gcash_qr')
        file_path = os.path.join(gcash_upload_path, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"🗑️ Deleted QR code file: {filename}")
        
        # Remove from list
        qr_codes.remove(filename)
        store.gcash_qr_codes = qr_codes
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'QR code deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting QR code: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ─── STORE LOGO MANAGEMENT ENDPOINTS ───

@templates_bp.route('/api/upload-cloudinary', methods=['POST'])
@seller_required
def upload_store_logo():
    """Upload store logo to Cloudinary"""
    try:
        # Check if file exists
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        if not file or not file.filename:
            return jsonify({'success': False, 'error': 'Empty file'}), 400
        
        # File type validation - allow all image file types
        if '.' not in file.filename:
            return jsonify({
                'success': False, 
                'error': 'File must have an extension'
            }), 400
        
        # Validate file size (max 5MB for logos)
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        max_size = 5 * 1024 * 1024  # 5MB
        
        if file_size > max_size:
            return jsonify({
                'success': False, 
                'error': 'File too large. Maximum size is 5MB.'
            }), 400
        
        # Import Cloudinary helper
        from app.utils.cloudinary_helper import upload_to_cloudinary, should_use_cloudinary
        
        # Check if Cloudinary is configured
        if not should_use_cloudinary():
            return jsonify({
                'success': False, 
                'error': 'Cloudinary is not configured.'
            }), 500
        
        upload_type = request.form.get('type', 'store_logo')
        upload_targets = {
            'store_logo': ('e-flowers/store_logos', None),
            'store_banner': (
                'e-flowers/store_banners',
                [{'width': 1600, 'height': 500, 'crop': 'fill', 'gravity': 'auto', 'fetch_format': 'auto', 'quality': 'auto'}],
            ),
        }
        if upload_type not in upload_targets:
            return jsonify({'success': False, 'error': 'Unsupported upload type.'}), 400

        folder, transformation = upload_targets[upload_type]
        result = upload_to_cloudinary(file, folder, transformation=transformation)
        
        if result['success']:
            return jsonify({
                'success': True,
                'public_id': result['public_id'],
                'url': result['url']
            })
        else:
            return jsonify({
                'success': False, 
                'error': result.get('error', 'Upload failed')
            }), 500
            
    except Exception as e:
        print(f"Error uploading logo: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'Server error: {str(e)}'
        }), 500


@templates_bp.route('/api/delete-cloudinary', methods=['POST'])
@seller_required
def delete_cloudinary_file():
    """Delete a file from Cloudinary"""
    try:
        data = request.get_json()
        public_id = data.get('public_id')
        
        if not public_id:
            return jsonify({'success': False, 'error': 'No public_id provided'}), 400
        
        # Import Cloudinary helper
        from app.utils.cloudinary_helper import delete_from_cloudinary
        
        # delete_from_cloudinary returns a boolean
        success = delete_from_cloudinary(public_id)
        
        if success:
            print(f"✅ Successfully deleted from Cloudinary: {public_id}")
            return jsonify({'success': True})
        else:
            # Don't fail if deletion fails, just log it
            print(f"⚠️ Warning: Could not delete {public_id} from Cloudinary")
            return jsonify({'success': True})  # Still return success to frontend
            
    except Exception as e:
        print(f"❌ Error deleting file: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'Server error: {str(e)}'
        }), 500
    


@templates_bp.route('/seller/products/images-count', methods=['POST'])
@seller_required
def get_products_image_count():
    """Get total Cloudinary image count for selected products"""
    try:
        store = Store.query.filter_by(seller_id=session.get('user_id')).first()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        data = request.get_json()
        product_ids = data.get('product_ids', [])
        
        if not product_ids:
            return jsonify({'total_images': 0})
        
        total_images = 0
        
        for product_id in product_ids:
            product = Product.query.filter_by(id=product_id, store_id=store.id).first()
            if product:
                # Count product images
                total_images += len(product.images)
                
                # Count variant images
                for variant in product.variants:
                    if variant.image_public_id:
                        total_images += 1
        
        return jsonify({'total_images': total_images})
        
    except Exception as e:
        print(f"Error counting images: {e}")
        return jsonify({'error': str(e)}), 500
    
@templates_bp.route('/api/v1/cloudinary/upload', methods=['POST', 'OPTIONS'])
def cloudinary_upload():
    """Upload an image directly to Cloudinary and return the result
    Supports both sellers and customers (customers can upload avatars, sellers can upload products)
    """
    # Handle preflight OPTIONS request for CORS
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, X-CSRFToken, X-Requested-With')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response
    
    try:
        # Log the request for debugging
        print("\n" + "="*60)
        print("📤 CLOUDINARY UPLOAD REQUEST RECEIVED")
        print(f"Session user_id: {session.get('user_id')}")
        print(f"Session role: {session.get('role')}")
        print(f"Content Type: {request.content_type}")
        print(f"Files keys: {list(request.files.keys())}")
        print(f"Form keys: {list(request.form.keys())}")
        
        # Check if user is authenticated (any role can upload)
        if 'user_id' not in session:
            print("❌ User not authenticated")
            return jsonify({
                'success': False, 
                'error': 'Not authenticated. Please log in first.'
            }), 401
        
        # Get the user to verify they exist
        user = User.query.get(session['user_id'])
        if not user:
            print(f"❌ User {session['user_id']} not found in database")
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        # Check if file exists
        if 'file' not in request.files:
            print("❌ No file in request")
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        if not file or not file.filename:
            print("❌ Empty file")
            return jsonify({'success': False, 'error': 'Empty file'}), 400
        
        folder = request.form.get('folder', 'e-flowers/temp')
        print(f"📁 Folder: {folder}")
        print(f"📄 Filename: {file.filename}")
        print(f"📄 File size: {file.tell()} bytes")
        
        # File type validation - allow all image file types
        if '.' not in file.filename:
            print(f"❌ File has no extension: {file.filename}")
            return jsonify({
                'success': False, 
                'error': 'File must have an extension'
            }), 400
        
        # Validate file size (max 10MB)
        file.seek(0, 2)  # Seek to end
        file_size = file.tell()
        file.seek(0)  # Reset to beginning
        max_size = 10 * 1024 * 1024  # 10MB
        
        if file_size > max_size:
            print(f"❌ File too large: {file_size} bytes")
            return jsonify({
                'success': False, 
                'error': f'File too large. Maximum size is 10MB.'
            }), 400
        
        # Import Cloudinary helper
        from app.utils.cloudinary_helper import upload_to_cloudinary, should_use_cloudinary
        
        # Check if Cloudinary is configured
        if not should_use_cloudinary():
            print("❌ Cloudinary not configured")
            return jsonify({
                'success': False, 
                'error': 'Cloudinary is not configured. Please contact support.'
            }), 500
        
        # Upload to Cloudinary
        print("⏫ Uploading to Cloudinary...")
        result = upload_to_cloudinary(file, folder)
        
        if result['success']:
            print(f"✅ Upload successful: {result['public_id']}")
            print(f"🔗 URL: {result['url']}")
            print(f"📊 Format: {result.get('format')}, Size: {result.get('width')}x{result.get('height')}")
            
            response = jsonify({
                'success': True,
                'public_id': result['public_id'],
                'url': result['url'],
                'format': result.get('format'),
                'width': result.get('width'),
                'height': result.get('height'),
                'bytes': result.get('bytes')
            })
            
            # Add CORS headers for development
            response.headers.add('Access-Control-Allow-Origin', '*')
            return response
        else:
            print(f"❌ Upload failed: {result.get('error', 'Unknown error')}")
            return jsonify({
                'success': False, 
                'error': result.get('error', 'Upload failed')
            }), 500
            
    except Exception as e:
        print(f"❌ Cloudinary upload error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False, 
            'error': f'Server error: {str(e)}'
        }), 500


















'''

@templates_bp.route('/api/seller/pos/next-order-id', methods=['GET'])
@seller_required
def get_next_pos_order_id():
    """Get the next available POS order ID"""
    store = _get_seller_store()
    if not store:
        return jsonify({'error': 'No active store.'}), 403
    
    # Get the latest order
    latest_order = POSOrder.query.filter_by(store_id=store.id).order_by(POSOrder.id.desc()).first()
    
    if latest_order:
        next_id = latest_order.id + 1
    else:
        next_id = 1  # Start from 1 if no orders exist
    
    return jsonify({'next_id': next_id})
'''



'''
@templates_bp.route('/seller/pos/orders')
@seller_required
def seller_pos_orders():
    """Render the POS orders history page"""
    store = _get_seller_store()
    if not store:
        return redirect(url_for('templates.dashboard'))
    
    return render_template('seller_pos_orders.html', store=store)
'''
@templates_bp.route('/api/seller/pos/orders/<int:order_id>', methods=['GET'])
@seller_required
def pos_order_detail_api(order_id):
    store = _get_seller_store()
    if not store:
        return jsonify({'error': 'No active store found'}), 403
    
    try:
        _ensure_pos_order_item_line_columns()
        order = (
            POSOrder.query.options(
                joinedload(POSOrder.items).joinedload(POSOrderItem.product).joinedload(Product.images),
                joinedload(POSOrder.items).joinedload(POSOrderItem.variant),
                joinedload(POSOrder.items).joinedload(POSOrderItem.addon_option),
            )
            .filter_by(id=order_id, store_id=store.id)
            .first()
        )
        if not order:
            return jsonify({'error': 'Order not found'}), 404
        
        items = []
        subtotal = 0
        for item in order.items:
            if item.line_name:
                product_name = item.line_name
            else:
                product_name = 'Unknown Product'
                if item.product:
                    product_name = item.product.name
                if item.variant_id and item.variant:
                    product_name = f"{product_name} - {item.variant.name}"
                # Legacy add-on-only rows (no line_name): prefer linked option name
                if item.addon_option_id and item.addon_option:
                    product_name = item.addon_option.name

            item_subtotal = float(item.price * item.quantity) if item.price is not None else 0.0
            unit_price = float(item.price) if item.price is not None else 0.0
            # Legacy add-on-only rows were sometimes saved with price=0; recover from option.
            if unit_price <= 0 and item.addon_option_id and item.addon_option:
                unit_price = float(item.addon_option.price or 0)
                item_subtotal = unit_price * float(item.quantity or 0)
            subtotal += item_subtotal
            items.append({
                'id': item.id,
                'product_id': item.product_id,
                'variant_id': item.variant_id,
                'product_name': product_name,
                'product_image_url': item.product_image,
                'is_addon': bool(item.addon_option_id),
                'quantity': item.quantity,
                'unit_price': unit_price,
                'subtotal': item_subtotal
            })

        discount_val = float(order.discount or 0)
        subtotal_val = float(subtotal)
        computed_total = max(0.0, subtotal_val - discount_val)
        # Do not use `if order.total_amount` — Decimal('0') is falsy but is a valid total.
        if order.total_amount is not None:
            total_val = float(order.total_amount)
        else:
            total_val = computed_total

        # created_at is stored as UTC-naive (datetime.utcnow); emit true PHT ISO.
        created_at_iso = None
        created_at_date = None
        if order.created_at:
            created_at_iso  = _to_pht_iso(order.created_at)
            created_at_date = _fmt_pht(order.created_at, '%Y-%m-%d')

        return jsonify({
            'id': order.id,
            'created_at': created_at_iso,
            'created_at_date': created_at_date,
            'customer_name': order.customer_name or 'Walk-in',
            'customer_contact': order.customer_contact,
            'payment_method': order.payment_method or 'cash',
            'amount_given': float(order.amount_given) if order.amount_given is not None else 0,
            'change_amount': float(order.change_amount) if order.change_amount is not None else 0,
            'total_amount': total_val,
            'subtotal': subtotal_val,
            'discount': discount_val,
            'items': items,
            'item_count': len(items)
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@templates_bp.route('/api/seller/pos/orders', methods=['GET'])
@seller_required
def pos_order_history_api():
    """API endpoint to get POS orders data (returns JSON)"""
    store = _get_seller_store()
    if not store:
        return jsonify({'error': 'No active store.'}), 403

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    date_filter = request.args.get('date', 'this_week')
    payment_filter = request.args.get('payment', 'all')
    search_query = request.args.get('search', '')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = POSOrder.query.filter_by(store_id=store.id)

    # ── Date filtering ────────────────────────────────────────────────────────
    # created_at is UTC-naive (datetime.utcnow). Convert PH calendar-day bounds
    # to UTC-naive before comparing so "today" / week / month match Manila time.
    today_ph = datetime.now(PHT).date()

    if date_filter == 'today':
        start, end = _ph_day_bounds_as_utc_naive(today_ph)
        query = query.filter(POSOrder.created_at >= start, POSOrder.created_at <= end)

    elif date_filter == 'yesterday':
        yesterday = today_ph - timedelta(days=1)
        start, end = _ph_day_bounds_as_utc_naive(yesterday)
        query = query.filter(POSOrder.created_at >= start, POSOrder.created_at <= end)

    elif date_filter == 'this_week':
        start_of_week = today_ph - timedelta(days=today_ph.weekday())  # Monday
        start, _ = _ph_day_bounds_as_utc_naive(start_of_week)
        query = query.filter(POSOrder.created_at >= start)

    elif date_filter == 'this_month':
        start_of_month = today_ph.replace(day=1)
        start, _ = _ph_day_bounds_as_utc_naive(start_of_month)
        query = query.filter(POSOrder.created_at >= start)

    elif date_filter == 'custom' and start_date and end_date:
        try:
            start_day = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_day = datetime.strptime(end_date, '%Y-%m-%d').date()
            start, _ = _ph_day_bounds_as_utc_naive(start_day)
            _, end = _ph_day_bounds_as_utc_naive(end_day)
            query = query.filter(POSOrder.created_at >= start, POSOrder.created_at <= end)
        except ValueError:
            pass

    # ── Payment filter ────────────────────────────────────────────────────────
    if payment_filter != 'all':
        query = query.filter_by(payment_method=payment_filter)

    # ── Search filter ─────────────────────────────────────────────────────────
    if search_query:
        query = query.filter(
            db.or_(
                POSOrder.customer_name.ilike(f'%{search_query}%'),
                POSOrder.customer_contact.ilike(f'%{search_query}%'),
                db.cast(POSOrder.id, db.String).ilike(f'%{search_query}%')
            )
        )

    # ── Paginate ──────────────────────────────────────────────────────────────
    pagination = query.order_by(POSOrder.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # ── Serialize ─────────────────────────────────────────────────────────────
    # created_at is UTC-naive; convert to Asia/Manila before emitting ISO.
    orders = []
    for o in pagination.items:
        subtotal   = sum(float(item.price * item.quantity) for item in o.items)
        item_count = sum(item.quantity for item in o.items)
        discount_f = float(o.discount or 0)
        subtotal_f = float(subtotal)
        computed_total = max(0.0, subtotal_f - discount_f)
        if o.total_amount is not None:
            total_f = float(o.total_amount)
        else:
            total_f = computed_total

        if o.created_at:
            created_at_iso  = _to_pht_iso(o.created_at)
            created_at_date = _fmt_pht(o.created_at, '%Y-%m-%d')
        else:
            created_at_iso  = None
            created_at_date = None

        orders.append({
            'id':             o.id,
            'created_at':     created_at_iso,
            'created_at_date': created_at_date,
            'customer_name':  o.customer_name or 'Walk-in',
            'customer_contact': o.customer_contact,
            'item_count':     item_count,
            'subtotal':       subtotal_f,
            'discount':       discount_f,
            'total_amount':   total_f,
            'amount_given':   float(o.amount_given) if o.amount_given is not None else 0,
            'change_amount':  float(o.change_amount) if o.change_amount is not None else 0,
            'payment_method': o.payment_method or 'cash'
        })

    return jsonify({
        'orders':       orders,
        'total':        pagination.total,
        'pages':        pagination.pages,
        'current_page': pagination.page,
        'has_next':     pagination.has_next,
        'has_prev':     pagination.has_prev,
    })


@templates_bp.route('/seller/pos/orders')
@seller_required
def seller_pos_orders():
    """Render the POS orders history page - JS loads data via API"""
    store = _get_seller_store()
    if not store:
        flash('Please set up your store first.', 'warning')
        return redirect(url_for('templates.dashboard'))
    
    return render_template('seller_pos_orders.html', store=store)



























@templates_bp.route('/store/<int:store_id>/category/<int:category_id>')
def store_category(store_id, category_id):
    """View products in a store-specific subcategory"""
    from app.models import Store, StoreCategory, Product
    
    store = Store.query.get_or_404(store_id)
    category = StoreCategory.query.get_or_404(category_id)
    
    # Verify category belongs to store
    if category.store_id != store_id:
        os.abort(404)
    
    products = Product.query.filter_by(
        store_id=store_id,
        store_category_id=category_id,
        is_archived=False,
        is_available=True
    ).all()
    
    return render_template('store_category.html',
                         store=store,
                         category=category,
                         products=products)


@templates_bp.route('/api/store/categories', methods=['GET'])
@seller_required
def get_store_categories():
    """Get store-specific subcategories for a main category"""
    main_category_id = request.args.get('main_category_id')
    store = _get_seller_store()
    
    if not store:
        return jsonify({'success': False, 'error': 'Store not found'}), 404
    
    if not main_category_id:
        return jsonify({'success': False, 'error': 'Main category ID required'}), 400
    
    from app.models import StoreCategory
    
    categories = StoreCategory.query.filter_by(
        store_id=store.id,
        main_category_id=main_category_id,
        is_active=True
    ).order_by(StoreCategory.sort_order).all()
    
    return jsonify({
        'success': True,
        'categories': [cat.to_dict() for cat in categories]
    })


@templates_bp.route('/api/store/categories/create', methods=['POST'])
@seller_required
def create_store_category():
    """Create a new store-specific subcategory"""
    data = request.get_json()
    store = _get_seller_store()
    
    if not store:
        return jsonify({'success': False, 'error': 'Store not found'}), 404
    
    main_category_id = data.get('main_category_id')
    name = data.get('name', '').strip()
    description = data.get('description', '').strip()
    
    if not main_category_id:
        return jsonify({'success': False, 'error': 'Main category ID required'}), 400
    
    if not name:
        return jsonify({'success': False, 'error': 'Subcategory name required'}), 400
    
    from app.models import StoreCategory, Category
    
    # Verify main category exists
    main_category = Category.query.get(main_category_id)
    if not main_category:
        return jsonify({'success': False, 'error': 'Main category not found'}), 404
    
    # Check if subcategory already exists for this store
    existing = StoreCategory.query.filter_by(
        store_id=store.id,
        name=name
    ).first()
    
    if existing:
        return jsonify({'success': False, 'error': 'Subcategory already exists'}), 400
    
    # Create slug
    import re
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    slug = f"{slug}-{store.id}"
    
    subcategory = StoreCategory(
        store_id=store.id,
        main_category_id=main_category_id,
        name=name,
        slug=slug,
        description=description
    )
    
    db.session.add(subcategory)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'category': subcategory.to_dict()
    })
