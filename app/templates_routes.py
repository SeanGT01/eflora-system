# app/templates_routes.py - FIXED VERSION
from datetime import datetime, timedelta
from collections import defaultdict
from flask import Blueprint, app, flash, json, make_response, render_template, jsonify, request, session, redirect, url_for, current_app, send_from_directory
from app.archive_routes import get_seller_store
from app.models import MunicipalityBoundary, OrderItem, ProductVariant, User, Store, Rider, Product, Order, SellerApplication, Cart, CartItem, ProductImage, POSOrder, POSOrderItem, Testimonial, HomePageTestimonial, SupportFAQ, SavedReport, ProductRating, StoreRating, MunicipalityBoundary, GCashQR, StockReduction, RiderOTP, RiderLocation, Notification, Category, CustomerOTP, SellerSignupOTP, AccountBan, StorePaymentSetting, Conversation, PasswordResetOTP, ProductAddonGroup, ProductAddonOption, CartItemAddon, OrderItemAddon, WishlistItem, AdminPaymentSetting, SellerSubscriptionPayment
from app.extensions import db
import os
from werkzeug.utils import secure_filename
from functools import wraps
from decimal import Decimal
from sqlalchemy import or_, inspect, text, func
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
from app.utils.seller_notifications import notify_low_stock_if_crossed, clear_resolved_stock_notifications
# app/templates_routes.py - Add these imports at the top
from flask_wtf.csrf import generate_csrf
from sqlalchemy.orm import joinedload, selectinload
import hashlib

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
                raw_cp = opt_data.get('cost_price')
                if raw_cp not in (None, ''):
                    cost_price = Decimal(str(round(float(raw_cp), 2)))
                else:
                    cost_price = Decimal(str(round(float(price) * 0.60, 2)))
            except Exception:
                cost_price = Decimal(str(round(float(price) * 0.60, 2)))
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
                if opt_data.get('cost_price') not in (None, ''):
                    opt.cost_price = cost_price
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
                    cost_price=cost_price,
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

                if max(0, stock) > 0:
                    from app.models import StockReduction
                    seller_uid = session.get('user_id') or (product.store.seller_id if getattr(product, 'store', None) else 1)
                    db.session.add(StockReduction(
                        product_id=product.id,
                        addon_option_id=opt.id,
                        reduction_amount=max(0, stock),
                        reason='restock',
                        reason_notes=f"Initial inventory for add-on: {opt.name}",
                        reduced_by=seller_uid,
                        unit_cost=float(cost_price),
                        total_cost=round(float(cost_price) * max(0, stock), 2)
                    ))

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


_STORE_PAYMENT_SETTINGS_ENSURED = False


def _ensure_store_payment_settings_table():
    """Create store_payment_settings from ORM if migration wasn't run yet."""
    global _STORE_PAYMENT_SETTINGS_ENSURED
    if _STORE_PAYMENT_SETTINGS_ENSURED:
        return True
    from sqlalchemy import inspect, text

    try:
        insp = inspect(db.engine)
        if not insp.has_table('store_payment_settings'):
            StorePaymentSetting.__table__.create(db.engine, checkfirst=True)
            _STORE_PAYMENT_SETTINGS_ENSURED = True
            return True
        cols = {c['name'] for c in insp.get_columns('store_payment_settings')}
        if 'allow_gcash' not in cols:
            db.session.execute(text(
                'ALTER TABLE store_payment_settings '
                'ADD COLUMN allow_gcash BOOLEAN NOT NULL DEFAULT TRUE'
            ))
            db.session.commit()
        _STORE_PAYMENT_SETTINGS_ENSURED = True
        return True
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
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


def _point_geom_lat_lng(geom):
    """WKT POINT is stored as (lng lat); Shapely x=lng, y=lat."""
    if geom is None:
        return None, None
    try:
        from geoalchemy2.shape import to_shape
        point = to_shape(geom)
        return float(point.y), float(point.x)
    except Exception:
        return None, None


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

        custom_ticket = order.custom_ticket if order.order_type == 'custom_chat' else None
        raw_name = custom_ticket.title if custom_ticket else (item.product_name or (item.product.name if item.product else 'Product'))
        resolved_name = raw_name
        if resolved_name:
            if resolved_name.startswith('[Deleted Snapshot]'):
                resolved_name = resolved_name[len('[Deleted Snapshot]'):].strip(' -') or 'Product'
            elif resolved_name.startswith('[Deleted'):
                resolved_name = resolved_name.split(']', 1)[-1].strip(' -') or 'Product'
        items_payload.append({
            'id': item.id,
            'product_id': item.product_id,
            'variant_id': item.variant_id,
            'product_name': resolved_name,
            'name': resolved_name,
            'variant_name': item.variant_name or (item.variant.name if item.variant else None),
            'quantity': quantity,
            'price': unit_price,
            'total': float(quantity * unit_price) + addons_sum,
            'product_image_url': item.product_image,
            'image_url': item.product_image,
            'is_custom_order': bool(order.order_type == 'custom_chat'),
            'is_rated': item.id in rated_item_ids,
            'rating': item_rating,
            'addons': addons_list,
            'addons_total': addons_sum,
        })

    rateable_items = [
        item for item in (order.items or [])
        if not (item.product and (item.product.name or '').startswith('[Deleted'))
    ]
    n_rateable = len(rateable_items)
    rateable_ids = {item.id for item in rateable_items}
    products_all_rated = rateable_ids.issubset(rated_item_ids) if n_rateable else True
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
        'order_type': order.order_type,
        'fulfillment_type': (
            getattr(order, 'fulfillment_type', None)
            or ('pickup' if (getattr(order, 'payment_method', '') or '').lower() == 'cop'
                or (getattr(order, 'delivery_address', '') or '').lower().startswith('store pickup')
                else 'delivery')
        ),
        'custom_ticket_id': order.custom_ticket_id,
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
    """Add line_name / line_image_url / addon_option_id and custom order columns for accurate POS display."""
    required = {
        'line_name': "ALTER TABLE pos_order_items ADD COLUMN line_name VARCHAR(255)",
        'line_image_url': "ALTER TABLE pos_order_items ADD COLUMN line_image_url VARCHAR(500)",
        'addon_option_id': (
            "ALTER TABLE pos_order_items ADD COLUMN addon_option_id INTEGER "
            "REFERENCES product_addon_options(id) ON DELETE SET NULL"
        ),
        'is_custom': "ALTER TABLE pos_order_items ADD COLUMN is_custom BOOLEAN NOT NULL DEFAULT FALSE",
        'custom_title': "ALTER TABLE pos_order_items ADD COLUMN custom_title VARCHAR(255)",
        'custom_inclusions': "ALTER TABLE pos_order_items ADD COLUMN custom_inclusions TEXT",
        'custom_category': "ALTER TABLE pos_order_items ADD COLUMN custom_category VARCHAR(50)",
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


def _ensure_order_item_snapshot_columns():
    """Add product_name, product_image_url, and variant_name to order_items for frozen history."""
    try:
        existing = inspect(db.engine).get_table_names()
        if 'order_items' not in existing:
            return False
        cols = {c['name'] for c in inspect(db.engine).get_columns('order_items')}
        stmts = []
        if 'product_name' not in cols:
            stmts.append("ALTER TABLE order_items ADD COLUMN product_name VARCHAR(255)")
        if 'product_image_url' not in cols:
            stmts.append("ALTER TABLE order_items ADD COLUMN product_image_url VARCHAR(500)")
        if 'variant_name' not in cols:
            stmts.append("ALTER TABLE order_items ADD COLUMN variant_name VARCHAR(255)")
        for stmt in stmts:
            try:
                db.session.execute(text(stmt))
                db.session.commit()
            except Exception:
                db.session.rollback()

        # Safe ANSI-SQL backfill for existing order_items from active products/variants
        try:
            db.session.execute(text("""
                UPDATE order_items
                SET product_name = (
                    SELECT name FROM products WHERE products.id = order_items.product_id
                )
                WHERE product_name IS NULL AND product_id IS NOT NULL
            """))
            db.session.commit()
        except Exception:
            db.session.rollback()

        try:
            db.session.execute(text("""
                UPDATE order_items
                SET variant_name = (
                    SELECT name FROM product_variants WHERE product_variants.id = order_items.variant_id
                )
                WHERE variant_name IS NULL AND variant_id IS NOT NULL
            """))
            db.session.commit()
        except Exception:
            db.session.rollback()
        return True
    except Exception as exc:
        db.session.rollback()
        current_app.logger.warning('Failed ensuring order_items snapshot columns: %s', exc)
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

    from app.utils.cloudinary_helper import optimize_cloudinary_url

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
                'slug': product.store_category.slug,
                'filter_key': _subcategory_filter_key(product.store_category.name, product.store_category.slug)
            }
        # Optimize listing card image for high-performance responsive thumbnail loading
        if product_dict.get('image_url'):
            product_dict['image_url'] = optimize_cloudinary_url(
                product_dict['image_url'],
                width=380,
                crop='limit',
                quality='auto',
                format='auto'
            )
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


FEATURED_HOME_CATEGORY_ROWS = (
    ('bouquets', 'Bouquets'),
    ('potted-plants', 'Potted Plants'),
    ('fresh-flowers', 'Fresh Flowers'),
    ('succulents', 'Succulents'),
    ('others', 'Others'),
)
FEATURED_PRODUCTS_PER_CATEGORY = 10


def _apply_storefront_delivery_flags(product_list, orm_products, is_customer, customer_address):
    """Attach can_deliver_to_customer on serialized storefront product dicts."""
    delivery_map = {}
    if is_customer and customer_address:
        for product in orm_products:
            delivery_map[product.id] = _store_delivery_match(product.store, customer_address)

    for pd in product_list:
        if is_customer and customer_address:
            delivery = delivery_map.get(
                pd.get('id'),
                {'can_deliver': True, 'reason': None},
            )
            pd['can_deliver_to_customer'] = bool(delivery.get('can_deliver'))
            pd['delivery_block_reason'] = delivery.get('reason')
        else:
            pd['can_deliver_to_customer'] = True
            pd['delivery_block_reason'] = None
    return product_list


def _build_featured_product_rows(is_customer, customer_address, location_filter_on):
    """Landing-page featured rows grouped by main category."""
    from app.models import Category

    slugs = [slug for slug, _ in FEATURED_HOME_CATEGORY_ROWS]
    categories = Category.query.filter(
        Category.slug.in_(slugs),
        Category.is_active.is_(True),
    ).all()
    category_by_slug = {cat.slug: cat for cat in categories}

    rows = []
    for slug, display_name in FEATURED_HOME_CATEGORY_ROWS:
        category = category_by_slug.get(slug)
        orm_products = []
        if category:
            fetch_limit = FEATURED_PRODUCTS_PER_CATEGORY * 4 if (location_filter_on and customer_address) else FEATURED_PRODUCTS_PER_CATEGORY
            orm_products = (
                _public_storefront_product_base_query(require_sellable=True)
                .filter(Product.main_category_id == category.id)
                .order_by(Product.created_at.desc())
                .limit(fetch_limit)
                .all()
            )
            if location_filter_on and customer_address:
                orm_products = [
                    product for product in orm_products
                    if _store_delivery_match(product.store, customer_address).get('can_deliver')
                ][:FEATURED_PRODUCTS_PER_CATEGORY]

        product_list = _product_list_for_storefront(orm_products)
        _apply_storefront_delivery_flags(
            product_list,
            orm_products,
            is_customer,
            customer_address,
        )
        rows.append({
            'name': display_name,
            'slug': slug,
            'products': product_list,
        })
    return rows


def _flatten_featured_product_rows(featured_product_rows):
    """Single list for quick-add JSON (deduped by product id, preserve row order)."""
    seen = set()
    flat = []
    for row in featured_product_rows or []:
        for product in row.get('products') or []:
            product_id = product.get('id')
            if product_id is None or product_id in seen:
                continue
            seen.add(product_id)
            flat.append(product)
    return flat


def _subcategory_filter_key(name, slug=None):
    # Prioritize clean name so identical subcategories across different stores merge!
    # (e.g., 'Valentines', "Valentine's", and 'valentines' from Store 1 and Store 2 both become 'valentines')
    raw = (name or '').strip().lower()
    raw = raw.replace("'", "").replace("’", "").replace('"', '')
    if not raw and slug:
        raw = re.sub(r'-\d+$', '', slug.strip().lower())
        raw = raw.replace("'", "").replace("’", "").replace('"', '')
    key = re.sub(r'[^a-z0-9]+', '-', raw).strip('-')
    return key


def _subcategory_filters_for_products(product_list):
    """Unique store-subcategory chips for a main-category listing (grouped by normalized name)."""
    grouped = {}
    order = []
    for product in product_list or []:
        store_category = product.get('store_category') or {}
        name = (
            (store_category.get('name') if isinstance(store_category, dict) else None)
            or product.get('store_category_name')
            or ''
        ).strip()
        slug = (
            (store_category.get('slug') if isinstance(store_category, dict) else None)
            or product.get('store_category_slug')
            or ''
        ).strip()
        key = _subcategory_filter_key(name, slug)
        if not key:
            continue
        if key not in grouped:
            # Choose the most nicely capitalized name (prefer Title Case / Capitalized)
            display_name = name.title() if (name.islower() or name.isupper()) else (name or slug.title())
            grouped[key] = {'key': key, 'name': display_name, 'count': 0}
            order.append(key)
        grouped[key]['count'] += 1
        product['subcategory_filter_key'] = key
    order.sort(key=lambda k: grouped[k]['name'].lower())
    return [grouped[k] for k in order]


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


def _build_store_map_data(store, store_data=None):
    """Build standardized map & coverage data payload for storefront delivery map modals."""
    if not store:
        return None
    if store_data is None:
        store_data = store.to_dict()

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

    logo_url = store_data.get('logo_url')
    if not logo_url and getattr(store, 'seller_application', None):
        if store.seller_application.store_logo_url:
            logo_url = store.seller_application.store_logo_url
        elif store.seller_application.store_logo_path:
            logo_url = f'/static/uploads/seller_logos/{store.seller_application.store_logo_path}'

    return {
        'store': {
            'name': store.name,
            'address': store.formatted_address or store.address,
            'latitude': store.latitude,
            'longitude': store.longitude,
            'logo_url': logo_url,
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


@templates_bp.route('/googlea5dba4f15d616309.html')
def google_site_verification():
    """Google Search Console HTML-file ownership check (keep after verify)."""
    return (
        'google-site-verification: googlea5dba4f15d616309.html\n',
        200,
        {'Content-Type': 'text/html; charset=UTF-8'},
    )


@templates_bp.route('/favicon.ico')
@limiter.exempt
def favicon():
    return send_from_directory(
        os.path.join(current_app.root_path, 'static'),
        'favicon.ico',
        mimetype='image/x-icon'
    )


@templates_bp.route('/robots.txt')
@limiter.exempt
def robots_txt():
    from app.seo import site_base_url
    body = (
        'User-agent: *\n'
        'Allow: /\n'
        'Allow: /favicon.ico\n'
        'Allow: /static/\n'
        'Disallow: /api/\n'
        'Disallow: /my-account\n'
        'Disallow: /dashboard\n'
        'Disallow: /orders\n'
        'Disallow: /cart\n'
        'Disallow: /checkout\n'
        'Disallow: /wishlist\n'
        'Disallow: /settings\n'
        'Disallow: /admin/\n'
        'Disallow: /seller/\n'
        'Allow: /seller/signup\n'
        'Disallow: /login\n'
        'Disallow: /register\n'
        'Disallow: /logout\n'
        'Disallow: /home\n'
        f'Sitemap: {site_base_url()}/sitemap.xml\n'
    )
    return body, 200, {'Content-Type': 'text/plain; charset=UTF-8'}


@templates_bp.route('/sitemap.xml')
@limiter.exempt
def sitemap_xml():
    from xml.sax.saxutils import escape
    from app.seo import canonical_url
    from app.models import Category

    urls = [
        ('/', '1.0', 'daily'),
        ('/browse', '0.9', 'daily'),
        ('/stores', '0.8', 'daily'),
        ('/contact', '0.4', 'monthly'),
        ('/faq', '0.4', 'monthly'),
        ('/shipping', '0.3', 'monthly'),
        ('/returns', '0.3', 'monthly'),
    ]
    try:
        for cat in Category.query.filter_by(is_active=True).order_by(Category.sort_order).all():
            if cat.slug:
                urls.append((f'/category/{cat.slug}', '0.7', 'weekly'))
        for store in Store.query.filter_by(status='active').order_by(Store.id).all():
            urls.append((f'/store/{store.id}', '0.6', 'weekly'))
        products = (
            _public_storefront_product_base_query(require_sellable=True)
            .order_by(Product.updated_at.desc())
            .limit(2000)
            .all()
        )
        for product in products:
            urls.append((f'/product/{product.id}', '0.8', 'weekly'))
    except Exception:
        current_app.logger.exception('sitemap.xml catalog query failed')

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for path, priority, changefreq in urls:
        loc = escape(canonical_url(path))
        parts.append(
            '<url>'
            f'<loc>{loc}</loc>'
            f'<changefreq>{changefreq}</changefreq>'
            f'<priority>{priority}</priority>'
            '</url>'
        )
    parts.append('</urlset>')
    return ''.join(parts), 200, {'Content-Type': 'application/xml; charset=UTF-8'}


@templates_bp.route('/')
@limiter.exempt
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

        featured_product_rows = _build_featured_product_rows(
            is_customer,
            customer_address,
            location_filter_on,
        )
        products = _flatten_featured_product_rows(featured_product_rows)

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
            featured_product_rows=featured_product_rows,
            products=products,
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
                             featured_product_rows=[],
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
        row.is_approved = False
        mode = 'updated'
        status_code = 200
    else:
        row = HomePageTestimonial(
            customer_name=name,
            rating=rating,
            comment=comment,
            is_approved=False,
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
        if session.get('role') not in ('seller', 'store_admin'):
            return redirect(url_for('templates.dashboard'))
        # Admin-suspended storefronts cannot use seller tools.
        # Seller-chosen "inactive" still allows portal access (store is just hidden).
        if request.endpoint != 'templates.seller_store_suspended':
            if (
                _seller_portal_suspended_store(session['user_id'])
                and not _seller_portal_manageable_store(session['user_id'])
            ):
                return redirect(url_for('templates.seller_store_suspended'))
        from app.utils.store_admin_perms import deny_if_forbidden
        denied = deny_if_forbidden()
        if denied:
            return denied
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


def _product_listing_thumb(product, variant=None, size=80):
    """Cloudinary (or stored) square thumbnail for seller dashboard lists."""
    if variant is not None:
        url = variant.get_transformed_url(width=size, height=size) or variant.image_url
        if url:
            return url
    if not product:
        return None
    images = list(getattr(product, 'images', None) or [])
    if not images:
        return None
    primary = next((img for img in images if img.is_primary), images[0])
    return (
        primary.get_transformed_url(width=size, height=size)
        or primary.image_url
        or getattr(primary, 'cloudinary_url', None)
    )


def _attach_listing_thumbs(items, size=80):
    """Attach image_url onto product-row dicts that include id / variant_id."""
    prod_ids = [item.get('id') for item in items if item.get('id')]
    if not prod_ids:
        for item in items:
            item.setdefault('image_url', None)
        return items
    products_by_id = {
        p.id: p
        for p in Product.query.options(selectinload(Product.images)).filter(
            Product.id.in_(prod_ids)
        ).all()
    }
    var_ids = [item.get('variant_id') for item in items if item.get('variant_id')]
    variants_by_id = {}
    if var_ids:
        variants_by_id = {
            v.id: v
            for v in ProductVariant.query.filter(ProductVariant.id.in_(var_ids)).all()
        }
    for item in items:
        product = products_by_id.get(item.get('id'))
        variant = variants_by_id.get(item.get('variant_id'))
        item['image_url'] = _product_listing_thumb(product, variant, size=size)
    return items



def _seller_sidebar_badge_counts(store):
    """Sidebar badges: active online orders + unseen POS orders."""
    if not store:
        return 0, 0
    orders = Order.query.filter(
        Order.store_id == store.id,
        or_(
            Order.payment_status == 'pending_verification',
            Order.status.in_(['pending', 'accepted', 'preparing']),
        ),
    ).count()
    pos = POSOrder.query.filter(
        POSOrder.store_id == store.id,
        POSOrder.is_seen_by_seller.is_(False),
    ).count()
    return int(orders or 0), int(pos or 0)


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
            if session.get('role') in ('seller', 'store_admin'):
                portal_store = _seller_portal_manageable_store(session['user_id'])
                if portal_store:
                    seller_orders_badge_count, pos_orders_badge_count = (
                        _seller_sidebar_badge_counts(portal_store)
                    )

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
    from app.utils.store_admin_perms import current_store_admin_permissions, default_permissions
    from app.utils.feature_controls import phone_registration_enabled
    store_admin_perms = (
        current_store_admin_permissions()
        if session.get('role') == 'store_admin'
        else default_permissions()
    )
    return dict(
        user=user,
        seller_orders_badge_count=seller_orders_badge_count,
        pos_orders_badge_count=pos_orders_badge_count,
        chat_unread_count=chat_unread_count,
        store_admin_perms=store_admin_perms,
        current_year=datetime.utcnow().year,
        phone_registration_enabled=phone_registration_enabled(),
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

        if len(store_name) > 50:
            return jsonify({'error': 'Store name must be 50 characters or less.'}), 400
        if len(store_description) > 300:
            return jsonify({'error': 'Store description must be 300 characters or less.'}), 400

        # Get Cloudinary data from form (uploaded by frontend)
        store_logo_public_id = request.form.get('store_logo_public_id')
        store_logo_url = request.form.get('store_logo_url')
        government_id_public_id = request.form.get('government_id_public_id')
        government_id_url = request.form.get('government_id_url')
        payment_receipt_public_id = request.form.get('payment_receipt_public_id')
        payment_receipt_url = request.form.get('payment_receipt_url')

        # Check if admin QR code is configured
        setting = AdminPaymentSetting.query.first()
        if not setting or not setting.is_configured:
            return jsonify({'error': 'Seller registration is temporarily unavailable at this time because payment verification setup is being updated by the administrator.'}), 400

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
            if payment_receipt_public_id:
                delete_from_cloudinary(payment_receipt_public_id)
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
                if not payment_receipt_public_id or not payment_receipt_url:
                    return jsonify({'error': 'Payment receipt upload failed. Please try again.'}), 400

                latest_rejected.store_name = store_name
                latest_rejected.store_description = store_description
                latest_rejected.store_logo_public_id = store_logo_public_id
                latest_rejected.store_logo_url = store_logo_url
                latest_rejected.government_id_public_id = government_id_public_id
                latest_rejected.government_id_url = government_id_url
                latest_rejected.payment_receipt_public_id = payment_receipt_public_id
                latest_rejected.payment_receipt_url = payment_receipt_url
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

                if _is_rejected('payment_receipt'):
                    if not payment_receipt_public_id or not payment_receipt_url:
                        return jsonify({'error': 'Please upload a new payment receipt.'}), 400
                    latest_rejected.payment_receipt_public_id = payment_receipt_public_id
                    latest_rejected.payment_receipt_url = payment_receipt_url
                    updated_fields.append('payment_receipt')

                    # Keep initial SellerSubscriptionPayment in sync
                    reg_payment = SellerSubscriptionPayment.query.filter_by(
                        application_id=latest_rejected.id,
                        payment_type='registration'
                    ).first()
                    if reg_payment:
                        reg_payment.receipt_url = payment_receipt_url
                        reg_payment.receipt_public_id = payment_receipt_public_id
                        reg_payment.status = 'pending'
                        reg_payment.submitted_at = datetime.utcnow()
                    else:
                        reg_payment = SellerSubscriptionPayment(
                            seller_id=session['user_id'],
                            application_id=latest_rejected.id,
                            payment_type='registration',
                            amount=setting.monthly_fee if setting else 300.0,
                            receipt_url=payment_receipt_url,
                            receipt_public_id=payment_receipt_public_id,
                            status='pending',
                        )
                        db.session.add(reg_payment)

            if not updated_fields:
                return jsonify({'error': 'No rejected fields were updated.'}), 400

            latest_rejected.status = 'resubmitted'
            latest_rejected.admin_notes = None
            latest_rejected.rejection_details = None
            latest_rejected.reviewed_at = None
            latest_rejected.reviewed_by = None
            latest_rejected.submitted_at = datetime.utcnow()
            from app.utils.admin_notifications import notify_admins
            notify_admins(
                title='Seller application resubmitted',
                message=f'"{latest_rejected.store_name}" was resubmitted and needs review.',
                type='seller_app_resubmitted',
                reference_id=latest_rejected.id,
            )
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
        if not payment_receipt_public_id or not payment_receipt_url:
            return jsonify({'error': 'GCash payment receipt is required. Please accept the terms to view the QR code and upload your receipt.'}), 400

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
            payment_receipt_public_id=payment_receipt_public_id,
            payment_receipt_url=payment_receipt_url,
            status='pending'
        )
        
        db.session.add(application)
        db.session.flush()

        # Create initial registration payment record visible on admin payments page
        initial_sub_payment = SellerSubscriptionPayment(
            seller_id=session['user_id'],
            application_id=application.id,
            payment_type='registration',
            amount=setting.monthly_fee if setting else 300.0,
            receipt_url=payment_receipt_url,
            receipt_public_id=payment_receipt_public_id,
            status='pending'
        )
        db.session.add(initial_sub_payment)

        from app.utils.admin_notifications import notify_admins
        notify_admins(
            title='New seller application',
            message=f'"{application.store_name}" submitted by {user.full_name or user.email} needs review.',
            type='seller_app_pending',
            reference_id=application.id,
        )
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
            from app.models import AdminPaymentSetting
            admin_setting = AdminPaymentSetting.query.first()
            return render_template('account_parts/profile_content.html', 
                                 user=user.to_dict() if user else None,
                                 admin_payment_setting=admin_setting,
                                 admin_qr_available=bool(admin_setting and admin_setting.is_configured))
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
            from app.utils.validators import compose_full_name
            full_name, name_err = compose_full_name(first_name, last_name)
            if name_err:
                return jsonify({'success': False, 'error': name_err}), 400
            user.full_name = full_name
        
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


@templates_bp.route('/api/account/profile/phone/send-otp', methods=['POST'])
def account_phone_send_otp():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    from app.utils.phone_bind import send_phone_bind_otp
    user = User.query.get(session['user_id'])
    data = request.get_json(silent=True) or {}
    return send_phone_bind_otp(user, data.get('phone'))


@templates_bp.route('/api/account/profile/phone/verify', methods=['POST'])
def account_phone_verify():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    from app.utils.phone_bind import verify_phone_bind_otp
    user = User.query.get(session['user_id'])
    data = request.get_json(silent=True) or {}
    return verify_phone_bind_otp(user, data.get('otp_code') or data.get('otp'))


@templates_bp.route('/api/seller/email/send-otp', methods=['POST'])
@templates_bp.route('/api/account/profile/email/send-otp', methods=['POST'])
def seller_email_send_otp():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    from app.utils.email_bind import send_email_bind_otp
    user = User.query.get(session['user_id'])
    store = _seller_portal_manageable_store(user.id) if user else None
    data = request.get_json(silent=True) or {}
    return send_email_bind_otp(user, data.get('email'), store=store)


@templates_bp.route('/api/seller/email/verify-otp', methods=['POST'])
@templates_bp.route('/api/account/profile/email/verify', methods=['POST'])
def seller_email_verify_otp():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    from app.utils.email_bind import verify_email_bind_otp
    user = User.query.get(session['user_id'])
    data = request.get_json(silent=True) or {}
    return verify_email_bind_otp(user, data.get('email'), data.get('otp_code') or data.get('otp'))


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

        if current_password == new_password:
            return jsonify({'error': 'New password must be different from current password'}), 400
        
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


@templates_bp.route('/api/account/delete', methods=['POST'])
def api_account_delete():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    from app.utils.account_deletion import delete_customer_account
    try:
        user = User.query.get(session['user_id'])
        data = request.get_json(silent=True) or {}
        password = data.get('password') or data.get('current_password') or request.form.get('password')
        confirmation = data.get('confirmation') or request.form.get('confirmation')
        resp, status = delete_customer_account(user, password, confirmation)
        if status == 200:
            session.clear()
        return resp, status
    except Exception as e:
        db.session.rollback()
        print(f'Account delete error: {e}')
        return jsonify({'success': False, 'error': 'Could not delete the account. Please try again.'}), 500


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
    from app.models import AdminPaymentSetting
    admin_setting = AdminPaymentSetting.query.first()

    return render_template('my_account.html', 
                         user=user_data, 
                         active_page=page,
                         initial_page=page,
                         admin_payment_setting=admin_setting,
                         admin_qr_available=bool(admin_setting and admin_setting.is_configured),
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
        if role == 'store_admin':
            from app.utils.store_admin_perms import store_admin_home_redirect
            return store_admin_home_redirect()
        if role == 'rider':
            # Riders sign in via the mobile app. There is no web rider dashboard.
            session.pop('user_id', None)
            session.pop('user_name', None)
            session.pop('role', None)
            session.pop('email', None)
        else:
            return redirect(url_for('templates.index'))

    if request.method == 'POST':
        raw_id = (request.form.get('identifier') or request.form.get('email') or '').strip()
        password = request.form.get('password')
        invalid_login = lambda: render_template(
            'login.html',
            error='Invalid email/phone or password',
            form_data={'identifier': raw_id or ''},
            login_next=request.form.get('next') or request.args.get('next'),
        )

        # Find user by email or PH mobile
        user = _find_user_by_login_identifier_web(raw_id)

        password_ok = False
        try:
            password_ok = bool(
                user and password and user.password_hash and user.check_password(password)
            )
        except Exception:
            password_ok = False

        # Riders are app-only; do not create a web session or hit a missing dashboard route.
        if password_ok and (user.role or '').lower() == 'rider':
            return invalid_login()

        # Check if user exists and password is correct
        if password_ok:
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
            elif user.role == 'store_admin':
                store = _seller_portal_manageable_store(user.id)
                if not store:
                    session.clear()
                    return render_template(
                        'login.html',
                        error='This store admin account is inactive. Ask the store owner to reactivate it.',
                        form_data={'identifier': raw_id or ''},
                    )
                from app.utils.store_admin_perms import store_admin_home_redirect
                return store_admin_home_redirect()
            else:
                return redirect(url_for('templates.index'))
        else:
            return invalid_login()

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
            agree_terms = (request.form.get('agree_terms') or '').strip().lower()

            # ── Validation ────────────────────────────────────────────────
            if agree_terms not in ('on', '1', 'true', 'yes'):
                return render_template('register.html',
                                       error='Please agree to the Terms & Conditions to continue.',
                                       form_data=request.form)

            if not all([full_name, identifier, password, confirm_password]):
                return render_template('register.html',
                                       error='All fields are required',
                                       form_data=request.form)

            from app.utils.validators import normalize_full_name
            full_name, name_err = normalize_full_name(full_name)
            if name_err:
                return render_template('register.html',
                                       error=name_err,
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

            from app.utils.feature_controls import phone_registration_enabled
            allow_phone_reg = phone_registration_enabled()

            email = None
            phone = None
            channel = 'email'
            if '@' in identifier:
                from app.utils.validators import validate_email_format
                clean_email, email_err = validate_email_format(identifier)
                if email_err:
                    return render_template(
                        'register.html',
                        error=email_err,
                        form_data=request.form,
                    )
                email = clean_email
                channel = 'email'
            elif is_valid_ph_mobile(identifier):
                if not allow_phone_reg:
                    return render_template(
                        'register.html',
                        error='Phone number registration is currently disabled. Please register using an email address.',
                        form_data=request.form,
                    )
                phone = normalize_ph_mobile(identifier)
                email = phone_to_account_email(phone)
                channel = 'sms'
            else:
                return render_template(
                    'register.html',
                    error='Enter a valid email address.' if not allow_phone_reg else 'Enter a valid email address or Philippine mobile number (e.g. 09171234567).',
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
    """Store the user can manage: owner (seller_id) or invited store_admin."""
    if not user_id:
        return None
    owned = (
        Store.query.filter(
            Store.seller_id == user_id,
            Store.status.in_(('active', 'inactive')),
        )
        .order_by(Store.updated_at.desc().nullslast(), Store.id.desc())
        .first()
    )
    if owned:
        return owned
    from app.models import StoreAdmin
    staff = (
        StoreAdmin.query.filter_by(user_id=user_id, is_active=True, is_archived=False)
        .order_by(StoreAdmin.id.desc())
        .first()
    )
    if not staff:
        return None
    return (
        Store.query.filter(
            Store.id == staff.store_id,
            Store.status.in_(('active', 'inactive')),
        )
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
    latest = _seller_portal_latest_application(user_id)
    if latest and latest.status == 'rejected':
        return redirect(url_for('templates.seller_signup_status'))
    if latest and latest.status in ('pending', 'resubmitted'):
        return redirect(url_for('templates.seller_signup_status'))
    if _seller_portal_manageable_store(user_id):
        return redirect(url_for('templates.seller_products'))
    suspended = _seller_portal_suspended_store(user_id)
    if suspended:
        return redirect(url_for('templates.seller_store_suspended'))
    return redirect(url_for('templates.seller_signup_complete'))


def _seller_portal_latest_application(user_id):
    return (
        SellerApplication.query.filter_by(user_id=user_id)
        .order_by(SellerApplication.submitted_at.desc())
        .first()
    )


def _finalize_seller_signup_from_otp(record, email):
    """Create seller user after OTP verification; log in and clear OTP row."""
    def _clear_pending_seller_session():
        session.pop('pending_seller_reg_email', None)
        session.pop('pending_seller_reg_channel', None)
        session.pop('pending_seller_reg_dest', None)
        session.pop('pending_seller_reg_login_id', None)

    if User.query.filter_by(email=email).first():
        db.session.delete(record)
        db.session.commit()
        _clear_pending_seller_session()
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

    _clear_pending_seller_session()
    session.permanent = True
    session['user_id'] = user.id
    session['user_name'] = user.full_name
    session['role'] = user.role
    session['email'] = user.email

    return redirect(url_for('templates.seller_signup_complete'))


@templates_bp.route('/seller/signup', methods=['GET'])
def seller_signup_landing():
    """Lazada-style seller portal entry: account step (Gmail OTP first)."""
    from app.models import AdminPaymentSetting
    admin_setting = AdminPaymentSetting.query.first()
    admin_qr_available = bool(admin_setting and admin_setting.is_configured)

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
            return render_template(
                'seller_signup_landing.html',
                admin_payment_setting=admin_setting,
                admin_qr_available=admin_qr_available
            )

    print("Decision: guest/unknown -> render seller_signup_landing.html")
    print("=" * 60 + "\n")
    return render_template(
        'seller_signup_landing.html',
        admin_payment_setting=admin_setting,
        admin_qr_available=admin_qr_available
    )


@templates_bp.route('/seller/signup/start', methods=['POST'])
def seller_signup_start():
    """Validate account fields (email OR phone), send OTP, redirect to verify."""
    from app.models import AdminPaymentSetting
    admin_setting = AdminPaymentSetting.query.first()
    admin_qr_available = bool(admin_setting and admin_setting.is_configured)

    if not admin_qr_available:
        return render_template(
            'seller_signup_landing.html',
            error='Seller application is temporarily unavailable.',
            admin_payment_setting=admin_setting,
            admin_qr_available=False,
            form_data=request.form,
        )

    if session.get('user_id'):
        return render_template(
            'seller_signup_landing.html',
            error='You are already signed in. Sign out first to create a new seller account.',
            admin_payment_setting=admin_setting,
            admin_qr_available=admin_qr_available,
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
        from app.utils.phone_utils import (
            display_login_id,
            is_synthetic_account_email,
            is_valid_ph_mobile,
            mask_email,
            mask_phone,
            normalize_ph_mobile,
            phone_to_account_email,
        )

        full_name = (request.form.get('full_name') or '').strip()
        identifier = (request.form.get('identifier') or request.form.get('email') or '').strip()
        password = request.form.get('password') or ''
        confirm_password = request.form.get('confirm_password') or ''

        if not all([full_name, identifier, password, confirm_password]):
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

        # Same identifier rules as customer registration: email OR PH mobile.
        from app.utils.feature_controls import phone_registration_enabled
        allow_phone_reg = phone_registration_enabled()

        email = None
        phone = None
        channel = 'email'
        if '@' in identifier:
            email = identifier.lower()
            if is_synthetic_account_email(email) or '@' not in email or '.' not in email.split('@')[-1]:
                return render_template(
                    'seller_signup_landing.html',
                    error='Enter a valid email address.' if not allow_phone_reg else 'Enter a valid email address or Philippine mobile number.',
                    form_data=request.form,
                )
            channel = 'email'
        elif is_valid_ph_mobile(identifier):
            if not allow_phone_reg:
                return render_template(
                    'seller_signup_landing.html',
                    error='Phone number registration is currently disabled. Please register using an email address.',
                    form_data=request.form,
                )
            phone = normalize_ph_mobile(identifier)
            email = phone_to_account_email(phone)
            channel = 'sms'
        else:
            return render_template(
                'seller_signup_landing.html',
                error='Enter a valid email address.' if not allow_phone_reg else 'Enter a valid email address or Philippine mobile number (e.g. 09171234567).',
                form_data=request.form,
            )

        if phone and _phone_taken_web(phone, exclude_email=email):
            return render_template(
                'seller_signup_landing.html',
                error='This phone number is already registered to another account.',
                form_data=request.form,
            )

        existing = User.query.filter_by(email=email).first()
        if existing:
            kind = 'phone number' if channel == 'sms' else 'email'
            if existing.role == 'customer':
                existing_msg = (
                    f'This {kind} is already registered as a customer account. '
                    'Please sign in to continue your seller application, or use a different email/phone.'
                )
            else:
                existing_msg = (
                    f'This {kind} is already registered as a {existing.role} account. '
                    'Please sign in, or use a different email/phone.'
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
                session['pending_seller_reg_dest'] = (
                    mask_phone(phone) if channel == 'sms' else mask_email(email)
                )
                session['pending_seller_reg_login_id'] = display_login_id(email=email, phone=phone)
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
        session['pending_seller_reg_login_id'] = display_login_id(email=email, phone=phone)
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

    latest = _seller_portal_latest_application(user.id)
    if latest and latest.status in ('pending', 'resubmitted'):
        return redirect(url_for('templates.seller_signup_status'))

    # Revisions requested: always show the edit form, even if an inactive
    # store still exists from a previous approval (seller-portal accounts).
    if not (latest and latest.status == 'rejected'):
        if user.role == 'seller' and _seller_portal_manageable_store(user.id):
            return redirect(url_for('templates.seller_products'))

        if user.role == 'seller' and _seller_portal_suspended_store(user.id):
            return redirect(url_for('templates.seller_store_suspended'))

    from app.utils.phone_utils import display_login_id
    from app.models import AdminPaymentSetting
    admin_setting = AdminPaymentSetting.query.first()
    admin_qr_available = bool(admin_setting and admin_setting.is_configured)

    return render_template(
        'seller_signup_complete.html',
        user=user,
        application=latest,
        login_id=display_login_id(email=user.email, phone=user.phone),
        admin_payment_setting=admin_setting,
        admin_qr_available=admin_qr_available,
    )


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
    submitted_at_display = ''
    reviewed_at_display = ''
    if latest and latest.submitted_at:
        submitted_at_display = _fmt_pht(latest.submitted_at, '%b %d, %Y at %I:%M %p')
    if latest and latest.reviewed_at:
        reviewed_at_display = _fmt_pht(latest.reviewed_at, '%b %d, %Y at %I:%M %p')

    return render_template(
        'seller_signup_status.html',
        user=user,
        application=latest,
        submitted_at_display=submitted_at_display,
        reviewed_at_display=reviewed_at_display,
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
            joinedload(Order.items).joinedload(OrderItem.variant),
            joinedload(Order.items).joinedload(OrderItem.addons).joinedload(OrderItemAddon.addon_option),
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
            joinedload(Order.assigned_rider).joinedload(Rider.user),
            joinedload(Order.items).joinedload(OrderItem.product).joinedload(Product.images),
            joinedload(Order.items).joinedload(OrderItem.variant),
            joinedload(Order.items).joinedload(OrderItem.addons).joinedload(OrderItemAddon.addon_option),
        )
        .filter_by(id=order_id, customer_id=user_id)
        .first()
    )

    if not order:
        return jsonify({'error': 'Order not found'}), 404

    order_dict = _serialize_customer_order(order)
    order_dict['date'] = order_dict['created_at']
    resp = jsonify(order_dict)
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@templates_bp.route('/api/account/orders/<int:order_id>/tracking', methods=['GET'])
def account_order_tracking(order_id):
    """Latest rider GPS + pickup/drop-off for live customer map (session auth)."""
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        user_id = int(session['user_id'])
        order = (
            Order.query
            .filter_by(id=order_id, customer_id=user_id)
            .options(
                joinedload(Order.store),
                joinedload(Order.assigned_rider).joinedload(Rider.user),
            )
            .first()
        )
        if not order:
            return jsonify({'error': 'Order not found'}), 404

        live = order.status == 'on_delivery' and order.rider_id is not None
        rider_lat = rider_lng = None
        updated_at = None
        if live:
            loc = (
                RiderLocation.query
                .filter_by(rider_id=order.rider_id, order_id=order.id)
                .order_by(RiderLocation.timestamp.desc())
                .first()
            )
            if loc is None:
                loc = (
                    RiderLocation.query
                    .filter_by(rider_id=order.rider_id)
                    .order_by(RiderLocation.timestamp.desc())
                    .first()
                )
            if loc is not None:
                rider_lat, rider_lng = _point_geom_lat_lng(loc.location)
                updated_at = loc.timestamp.isoformat() if loc.timestamp else None

        store = order.store
        return jsonify({
            'live': live,
            'status': order.status,
            'rider_name': (
                order.assigned_rider.user.full_name
                if order.assigned_rider and order.assigned_rider.user
                else None
            ),
            'rider_latitude': rider_lat,
            'rider_longitude': rider_lng,
            'rider_updated_at': updated_at,
            'customer_latitude': order.customer_latitude,
            'customer_longitude': order.customer_longitude,
            'store_latitude': float(store.latitude) if store and store.latitude is not None else None,
            'store_longitude': float(store.longitude) if store and store.longitude is not None else None,
        })
    except Exception as e:
        current_app.logger.exception('account_order_tracking: %s', e)
        return jsonify({'error': str(e)}), 500


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
        order.payment_status = 'cancelled'
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
        try:
            from app.utils.push import queue_order_status_push
            queue_order_status_push(order, 'cancelled', 'pending')
        except Exception:
            pass
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

    from app.utils.push import is_order_pickup
    is_pickup = is_order_pickup(order)
    order.set_status('completed')
    from app.utils.seller_notifications import notify_store_seller
    action_text = 'pickup' if is_pickup else 'delivery'
    notify_store_seller(
        store_id=order.store_id,
        title='Order completed',
        message=f'Customer confirmed {action_text} for Order #{order.id}.',
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
        products = (
            _public_storefront_product_base_query(require_sellable=True)
            .filter(Product.main_category_id == category.id)
            .order_by(Product.created_at.desc())
            .all()
        )

        product_list = _product_list_for_storefront(products)
        subcategories = _subcategory_filters_for_products(product_list)
        requested_sub = _subcategory_filter_key(request.args.get('sub') or '')
        matched_sub = next((item['key'] for item in subcategories if item['key'] == requested_sub), None)
        if not matched_sub and requested_sub:
            matched_sub = next(
                (item['key'] for item in subcategories 
                 if _subcategory_filter_key(item['name']) == requested_sub or item['key'].startswith(requested_sub + '-')),
                None
            )
        initial_subcategory = matched_sub or 'all'

        return render_template('category.html',
                             category=category,
                             products=product_list,
                             subcategories=subcategories,
                             initial_subcategory=initial_subcategory,
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


_DEFAULT_PUBLIC_FAQS = (
    {
        'question': 'What is E-FLORA?',
        'answer': 'E-FLORA is a marketplace that connects you with local flower and plant shops — so you can browse arrangements, order online, and get fresh blooms delivered from nearby partners.',
    },
    {
        'question': 'Where do you deliver?',
        'answer': 'Delivery depends on each partner shop’s coverage area, typically across cities and barangays in Laguna. Set your address in your account to see which shops can deliver to you.',
    },
    {
        'question': 'How do I track my order?',
        'answer': 'Open My Orders after checkout. You’ll see status updates as the shop prepares and delivers your order. You can also message the shop from chat when needed.',
    },
    {
        'question': 'Can I cancel an order?',
        'answer': 'Yes, while the shop hasn’t started preparing. Once an order is accepted and in preparation, cancel options may close — contact the shop or support right away if plans change.',
    },
    {
        'question': 'What if my flowers arrive damaged?',
        'answer': 'Message the shop or E-FLORA support within 24 hours with your order number and photos. Eligible issues may be resolved with a replacement or refund. See our Returns page for details.',
    },
    {
        'question': 'How do I become a seller?',
        'answer': 'Use Become a Seller from the footer or account menu, complete the signup steps, and wait for admin approval. Once approved, you can list products and fulfill orders from your seller dashboard.',
    },
    {
        'question': 'Do I need an account to order?',
        'answer': 'Yes — a free customer account lets you save addresses, track orders, chat with shops, and keep your wishlist.',
    },
)


@templates_bp.route('/faq')
def faq():
    """FAQ page — prefers admin-managed SupportFAQ rows, with sensible fallbacks."""
    faqs = []
    try:
        _ensure_support_faqs_table()
        rows = (
            SupportFAQ.query
            .filter_by(is_active=True)
            .order_by(SupportFAQ.updated_at.desc(), SupportFAQ.id.desc())
            .limit(50)
            .all()
        )
        faqs = [{'question': r.question, 'answer': r.answer} for r in rows]
    except Exception as ex:
        current_app.logger.warning('faq page: could not load SupportFAQ (%s)', ex)
        try:
            db.session.rollback()
        except Exception:
            pass

    if not faqs:
        faqs = list(_DEFAULT_PUBLIC_FAQS)

    return render_template('faq.html', faqs=faqs)


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
        {'id': 'others', 'name': 'Others', 'icon': 'more-2-line', 'count': 0},
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
    params = {k: v for k, v in request.args.items() if k != 'browse_all'}
    dest = url_for('templates.browse_products', **params)
    return redirect(dest, code=301)


@templates_bp.route('/product/<int:product_id>')
def product_detail(product_id):
    """Legacy redirect to /products/<product_id>"""
    return redirect(url_for('templates.product_details', product_id=product_id))

    
@templates_bp.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('templates.login'))
    if session.get('role') in ('seller', 'store_admin'):
        return redirect(url_for('templates.seller_dashboard'))

    if session.get('role') == 'admin':
        return _render_admin_dashboard()

    return render_template('dashboard.html', is_admin=False)


def _render_admin_dashboard():
    """Render the admin dashboard with platform-wide aggregates."""
    from sqlalchemy import func
    from app.utils.report_service import (
        period_range,
        _platform_new_customer_count,
        _pht_date,
        _iter_pht_days,
        COMPLETED_ORDER_STATUSES,
        _not_cancelled_order_filter,
        _delivery_completion_rate,
        _compute_period_cogs,
    )

    period = (request.args.get('period') or 'month').lower().strip()
    custom_from = request.args.get('from')
    custom_to = request.args.get('to')
    range_start, range_end, period_label = period_range(period, custom_from, custom_to)
    prev_start = range_start - (range_end - range_start)
    prev_end = range_start

    # Revenue KPI: online = delivered/completed, POS = all
    online_revenue = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(
        Order.status.in_(COMPLETED_ORDER_STATUSES),
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
        Order.status.in_(COMPLETED_ORDER_STATUSES),
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

    # ── Platform COGS & Profit ──
    online_cogs_this, pos_cogs_this, cogs_this_month = _compute_period_cogs(range_start, range_end, store_id=None)
    online_cogs_prev, pos_cogs_prev, cogs_prev_month = _compute_period_cogs(prev_start, prev_end, store_id=None)
    profit_this_month = float(revenue_this_month) - float(cogs_this_month)
    profit_prev_month = float(revenue_prev_month) - float(cogs_prev_month)

    profit_change = 0
    if profit_prev_month > 0:
        profit_change = round(((profit_this_month - profit_prev_month) / profit_prev_month) * 100, 1)
    elif profit_prev_month < 0 and profit_this_month > profit_prev_month:
        profit_change = 100.0

    cogs_change = 0
    if cogs_prev_month > 0:
        cogs_change = round(((cogs_this_month - cogs_prev_month) / cogs_prev_month) * 100, 1)

    margin_pct_this = round((profit_this_month / revenue_this_month * 100), 1) if revenue_this_month > 0 else 0.0
    margin_pct_prev = round((profit_prev_month / revenue_prev_month * 100), 1) if revenue_prev_month > 0 else 0.0
    margin_change = round(margin_pct_this - margin_pct_prev, 1)

    # Orders KPI: online except cancelled + all POS
    online_orders_this = Order.query.filter(
        _not_cancelled_order_filter(),
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).count()
    pos_orders_this = POSOrder.query.filter(
        POSOrder.created_at >= range_start,
        POSOrder.created_at < range_end,
    ).count()
    orders_this_month = online_orders_this + pos_orders_this

    online_orders_prev = Order.query.filter(
        _not_cancelled_order_filter(),
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

    # Customers KPI: first-time buyers (matches analytics New Customers)
    customers_this_month = _platform_new_customer_count(range_start, range_end)
    customers_prev_month = _platform_new_customer_count(prev_start, prev_end)
    customers_change = 0
    if customers_prev_month > 0:
        customers_change = round(((customers_this_month - customers_prev_month) / customers_prev_month) * 100, 1)

    # Delivery completion: delivered / all non-cancelled online orders
    delivery_rate = _delivery_completion_rate(range_start, range_end)

    # Top products: completed online + POS, merged by product/variant
    online_top = db.session.query(
        Product.id,
        Product.name,
        ProductVariant.id.label('variant_id'),
        ProductVariant.name.label('variant_name'),
        Store.name.label('store_name'),
        Category.name.label('category_name'),
        func.coalesce(func.sum(OrderItem.quantity), 0).label('total_sold'),
        func.coalesce(func.sum(OrderItem.quantity * OrderItem.price), 0).label('total_sales'),
        func.coalesce(func.sum(OrderItem.quantity * func.coalesce(OrderItem.cost_price, OrderItem.price * 0.60)), 0).label('total_cogs'),
    ).join(OrderItem, OrderItem.product_id == Product.id) \
     .join(Order, Order.id == OrderItem.order_id) \
     .outerjoin(ProductVariant, ProductVariant.id == OrderItem.variant_id) \
     .outerjoin(Store, Store.id == Product.store_id) \
     .outerjoin(Category, Category.id == Product.main_category_id) \
     .filter(
        Order.status.in_(COMPLETED_ORDER_STATUSES),
        Order.created_at >= range_start,
        Order.created_at < range_end,
     ) \
     .group_by(Product.id, Product.name, ProductVariant.id, ProductVariant.name, Store.name, Category.name).all()

    pos_top = db.session.query(
        Product.id,
        Product.name,
        ProductVariant.id.label('variant_id'),
        ProductVariant.name.label('variant_name'),
        Store.name.label('store_name'),
        Category.name.label('category_name'),
        func.coalesce(func.sum(POSOrderItem.quantity), 0).label('total_sold'),
        func.coalesce(func.sum(POSOrderItem.quantity * POSOrderItem.price), 0).label('total_sales'),
        func.coalesce(func.sum(POSOrderItem.quantity * func.coalesce(POSOrderItem.cost_price, POSOrderItem.price * 0.60)), 0).label('total_cogs'),
    ).join(POSOrderItem, POSOrderItem.product_id == Product.id) \
     .join(POSOrder, POSOrder.id == POSOrderItem.pos_order_id) \
     .outerjoin(ProductVariant, ProductVariant.id == POSOrderItem.variant_id) \
     .outerjoin(Store, Store.id == Product.store_id) \
     .outerjoin(Category, Category.id == Product.main_category_id) \
     .filter(
        POSOrder.created_at >= range_start,
        POSOrder.created_at < range_end,
     ) \
     .group_by(Product.id, Product.name, ProductVariant.id, ProductVariant.name, Store.name, Category.name).all()

    merged_top = {}
    for r in list(online_top) + list(pos_top):
        key = (int(r.id), int(r.variant_id) if r.variant_id else None)
        entry = merged_top.setdefault(key, {
            'id': r.id,
            'variant_id': int(r.variant_id) if r.variant_id else None,
            'name': f"{r.name} — {r.variant_name}" if r.variant_name else r.name,
            'store_name': r.store_name or '—',
            'category': r.category_name or 'General',
            'total_sold': 0,
            'total_sales': 0.0,
            'total_cogs': 0.0,
            'total_profit': 0.0,
            'margin_pct': 0.0,
        })
        entry['total_sold'] += int(r.total_sold or 0)
        entry['total_sales'] += float(r.total_sales or 0.0)
        entry['total_cogs'] += float(r.total_cogs or 0.0)

    for item in merged_top.values():
        s = float(item['total_sales'] or 0.0)
        c = float(item['total_cogs'] or 0.0)
        p = s - c
        item['total_profit'] = p
        item['margin_pct'] = round((p / s * 100), 1) if s > 0 else 0.0

    _attach_listing_thumbs(list(merged_top.values()))
    top_products_by_qty = sorted(merged_top.values(), key=lambda x: (x['total_sold'], x['total_sales']), reverse=True)[:5]
    top_products_by_sales = sorted(merged_top.values(), key=lambda x: (x['total_sales'], x['total_sold']), reverse=True)[:5]
    top_products_by_profit = sorted(merged_top.values(), key=lambda x: (x['total_profit'], x['total_sales']), reverse=True)[:5]
    top_products = top_products_by_qty

    # Recent orders: completed online + POS, sorted by real timestamp
    online_recent_q = (Order.query
                       .filter(
                           Order.status.in_(COMPLETED_ORDER_STATUSES),
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
            '_sort_at': o.created_at or datetime.min,
            'total': float(o.total_amount or 0),
            'status': o.status or 'pending',
            'type': 'online',
            'fulfillment_type': getattr(o, 'fulfillment_type', 'delivery') or 'delivery',
        })
    for p in pos_recent_q:
        recent_orders_list.append({
            'id': p.id,
            'order_no': f"#{p.order_number}" if p.order_number else f"#POS-{p.id:04d}",
            'customer_name': p.customer_name or 'Walk-in',
            'customer_initial': ((p.customer_name or 'W')[0]).upper(),
            'store_name': p.store.name if getattr(p, 'store', None) else '—',
            'date': _fmt_pht(p.created_at) if p.created_at else '',
            '_sort_at': p.created_at or datetime.min,
            'total': float(p.total_amount or 0),
            'status': 'completed',
            'type': 'pos',
        })
    recent_orders_list.sort(key=lambda x: x['_sort_at'], reverse=True)
    recent_orders_list = recent_orders_list[:8]
    for row in recent_orders_list:
        row.pop('_sort_at', None)

    # Chart data: Philippine calendar days within selected period
    def _admin_build_chart(ds_start, ds_end):
        online_rows = db.session.query(Order.created_at, Order.total_amount).filter(
            Order.status.in_(COMPLETED_ORDER_STATUSES),
            Order.created_at >= ds_start,
            Order.created_at < ds_end,
        ).all()
        pos_rows = db.session.query(POSOrder.created_at, POSOrder.total_amount).filter(
            POSOrder.created_at >= ds_start,
            POSOrder.created_at < ds_end,
        ).all()

        oi_cogs_rows = db.session.query(
            Order.created_at,
            func.coalesce(OrderItem.quantity * func.coalesce(OrderItem.cost_price, OrderItem.price * 0.60), 0)
        ).join(Order, Order.id == OrderItem.order_id).filter(
            Order.status.in_(COMPLETED_ORDER_STATUSES),
            Order.created_at >= ds_start,
            Order.created_at < ds_end,
        ).all()

        oia_cogs_rows = db.session.query(
            Order.created_at,
            func.coalesce(OrderItemAddon.quantity * func.coalesce(OrderItemAddon.cost_price, OrderItemAddon.price * 0.60), 0)
        ).join(OrderItem, OrderItem.id == OrderItemAddon.order_item_id) \
         .join(Order, Order.id == OrderItem.order_id).filter(
            Order.status.in_(COMPLETED_ORDER_STATUSES),
            Order.created_at >= ds_start,
            Order.created_at < ds_end,
        ).all()

        pos_cogs_rows = db.session.query(
            POSOrder.created_at,
            func.coalesce(POSOrderItem.quantity * func.coalesce(POSOrderItem.cost_price, POSOrderItem.price * 0.60), 0)
        ).join(POSOrder, POSOrder.id == POSOrderItem.pos_order_id).filter(
            POSOrder.created_at >= ds_start,
            POSOrder.created_at < ds_end,
        ).all()

        o_map = defaultdict(lambda: [0.0, 0])
        p_map = defaultdict(lambda: [0.0, 0])
        c_map = defaultdict(float)

        for ts, amt in online_rows:
            d = _pht_date(ts)
            if d:
                o_map[d][0] += float(amt or 0)
                o_map[d][1] += 1
        for ts, amt in pos_rows:
            d = _pht_date(ts)
            if d:
                p_map[d][0] += float(amt or 0)
                p_map[d][1] += 1
        for ts, c_amt in oi_cogs_rows:
            d = _pht_date(ts)
            if d:
                c_map[d] += float(c_amt or 0)
        for ts, c_amt in oia_cogs_rows:
            d = _pht_date(ts)
            if d:
                c_map[d] += float(c_amt or 0)
        for ts, c_amt in pos_cogs_rows:
            d = _pht_date(ts)
            if d:
                c_map[d] += float(c_amt or 0)

        labels, rev, o_rev, p_rev, cnt, o_cnt, p_cnt = [], [], [], [], [], [], []
        cogs_series, profit_series = [], []
        for day_val in _iter_pht_days(ds_start, ds_end):
            labels.append(day_val.strftime('%b %d'))
            or_v, oc = o_map.get(day_val, [0.0, 0])
            pr_v, pc = p_map.get(day_val, [0.0, 0])
            day_rev = or_v + pr_v
            day_cogs = c_map.get(day_val, 0.0)
            day_profit = day_rev - day_cogs

            o_rev.append(or_v)
            p_rev.append(pr_v)
            rev.append(day_rev)
            o_cnt.append(oc)
            p_cnt.append(pc)
            cnt.append(oc + pc)
            cogs_series.append(round(day_cogs, 2))
            profit_series.append(round(day_profit, 2))
        return {
            'labels': labels,
            'revenue': rev,
            'online_revenue': o_rev,
            'pos_revenue': p_rev,
            'orders': cnt,
            'online_orders': o_cnt,
            'pos_orders': p_cnt,
            'cogs': cogs_series,
            'profit': profit_series,
        }

    chart_data = _admin_build_chart(range_start, range_end)

    total_stores = db.session.query(func.count(Store.id)).scalar() or 0
    active_stores = db.session.query(func.count(Store.id)).filter(Store.status == 'active').scalar() or 0
    pending_stores = db.session.query(func.count(Store.id)).filter(Store.status == 'pending').scalar() or 0

    total_users = db.session.query(func.count(User.id)).scalar() or 0
    total_riders = db.session.query(func.count(Rider.id)).scalar() or 0
    active_riders = db.session.query(func.count(Rider.id)).filter(Rider.is_active.is_(True)).scalar() or 0
    pending_orders = Order.query.filter(
        Order.status.in_(['pending', 'preparing', 'accepted', 'done_preparing']),
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).count()

    avg_rating_row = db.session.query(
        func.coalesce(func.avg(ProductRating.rating), 0),
        func.count(ProductRating.id),
    ).first()
    avg_rating = round(float(avg_rating_row[0]), 1) if avg_rating_row else 0
    total_reviews = int(avg_rating_row[1]) if avg_rating_row else 0

    low_stock_products = Product.query.options(
        selectinload(Product.images),
        joinedload(Product.store),
    ).filter(
        Product.is_archived == False,
        Product.stock_quantity <= 5,
        Product.stock_quantity > 0,
    ).order_by(Product.stock_quantity.asc(), Product.name.asc()).limit(5).all()

    out_of_stock = Product.query.filter(
        Product.is_archived == False,
        Product.stock_quantity == 0,
    ).count()
    out_of_stock_products = Product.query.options(
        selectinload(Product.images),
        joinedload(Product.store),
    ).filter(
        Product.is_archived == False,
        Product.stock_quantity == 0,
    ).order_by(Product.name.asc()).limit(5).all()

    customer_users = db.session.query(func.count(User.id)).filter(User.role == 'customer').scalar() or 0
    seller_users = db.session.query(func.count(User.id)).filter(User.role == 'seller').scalar() or 0
    total_catalog_products = db.session.query(func.count(Product.id)).filter(
        Product.is_archived == False
    ).scalar() or 0
    low_stock_count = db.session.query(func.count(Product.id)).filter(
        Product.is_archived == False,
        Product.stock_quantity <= 5,
        Product.stock_quantity > 0,
    ).scalar() or 0
    pending_applications = db.session.query(func.count(SellerApplication.id)).filter(
        SellerApplication.status == 'pending'
    ).scalar() or 0

    return render_template(
        'dashboard.html',
        is_admin=True,
        period=period,
        period_label=period_label,
        custom_from=custom_from,
        custom_to=custom_to,
        revenue_this_month=float(revenue_this_month),
        revenue_change=revenue_change,
        cogs_this_month=float(cogs_this_month),
        cogs_change=cogs_change,
        profit_this_month=float(profit_this_month),
        profit_change=profit_change,
        margin_pct_this=float(margin_pct_this),
        margin_change=margin_change,
        orders_this_month=orders_this_month,
        orders_change=orders_change,
        customers_this_month=customers_this_month,
        customers_change=customers_change,
        delivery_rate=delivery_rate,
        top_products=top_products,
        top_products_by_qty=top_products_by_qty,
        top_products_by_sales=top_products_by_sales,
        top_products_by_profit=top_products_by_profit,
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
        low_stock_products=[p.to_dict() for p in low_stock_products],
        out_of_stock=out_of_stock,
        out_of_stock_products=[p.to_dict() for p in out_of_stock_products],
        customer_users=customer_users,
        seller_users=seller_users,
        total_catalog_products=total_catalog_products,
        low_stock_count=low_stock_count,
        pending_applications=pending_applications,
    )


@templates_bp.route('/seller/dashboard')
def seller_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('templates.login'))
    if session.get('role') not in ('seller', 'store_admin'):
        return redirect(url_for('templates.dashboard'))

    from sqlalchemy import func, extract
    from datetime import timedelta
    from app.utils.report_service import (
        period_range,
        COMPLETED_ORDER_STATUSES,
        _not_cancelled_order_filter,
        _delivery_completion_rate,
        _pht_date,
        _iter_pht_days,
        _new_customer_count,
        _customer_metrics,
        _to_pht,
        _peak_hours,
        _compute_period_cogs,
    )

    user_id = session['user_id']
    if session.get('role') == 'seller':
        latest_app = _seller_portal_latest_application(user_id)
        if latest_app and latest_app.status == 'rejected':
            return redirect(url_for('templates.seller_signup_complete'))
        if latest_app and latest_app.status in ('pending', 'resubmitted'):
            return redirect(url_for('templates.seller_signup_status'))

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



    # ── KPI: Revenue this month (delivered orders) ──
    online_revenue_this = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(
        Order.store_id == store.id,
        Order.status.in_(COMPLETED_ORDER_STATUSES),
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
        Order.status.in_(COMPLETED_ORDER_STATUSES),
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

    # ── KPI: COGS & Profit ──
    online_cogs_this, pos_cogs_this, cogs_this_month = _compute_period_cogs(range_start, range_end, store_id=store.id)
    online_cogs_prev, pos_cogs_prev, cogs_prev_month = _compute_period_cogs(prev_start, prev_end, store_id=store.id)
    profit_this_month = float(revenue_this_month) - float(cogs_this_month)
    profit_prev_month = float(revenue_prev_month) - float(cogs_prev_month)

    profit_change = 0
    if profit_prev_month > 0:
        profit_change = round(((profit_this_month - profit_prev_month) / profit_prev_month) * 100, 1)
    elif profit_prev_month < 0 and profit_this_month > profit_prev_month:
        profit_change = 100.0

    cogs_change = 0
    if cogs_prev_month > 0:
        cogs_change = round(((cogs_this_month - cogs_prev_month) / cogs_prev_month) * 100, 1)

    margin_pct_this = round((profit_this_month / revenue_this_month * 100), 1) if revenue_this_month > 0 else 0.0
    margin_pct_prev = round((profit_prev_month / revenue_prev_month * 100), 1) if revenue_prev_month > 0 else 0.0
    margin_change = round(margin_pct_this - margin_pct_prev, 1)

    # ── KPI: Total orders (online except cancelled + all POS) ──
    orders_this_month = Order.query.filter(
        Order.store_id == store.id,
        _not_cancelled_order_filter(),
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
        _not_cancelled_order_filter(),
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

    # ── KPI: Unique customers with completed orders in period (Online + POS) ──
    curr_cust_metrics = _customer_metrics(store.id, range_start, range_end)
    customers_this_month = curr_cust_metrics['total_unique']

    prev_cust_metrics = _customer_metrics(store.id, prev_start, prev_end)
    customers_prev_month = prev_cust_metrics['total_unique']

    customers_change = 0
    if customers_prev_month > 0:
        customers_change = round(((customers_this_month - customers_prev_month) / customers_prev_month) * 100, 1)

    # ── KPI: Delivered share of non-cancelled online orders ──
    delivery_rate = _delivery_completion_rate(range_start, range_end, store_id=store.id)

    # ── Top products (online + POS, variant-level) ──
    online_top = db.session.query(
        Product.id,
        Product.name,
        ProductVariant.id.label('variant_id'),
        ProductVariant.name.label('variant_name'),
        Category.name.label('category_name'),
        func.coalesce(func.sum(OrderItem.quantity), 0).label('total_sold'),
        func.coalesce(func.sum(OrderItem.quantity * OrderItem.price), 0).label('total_sales'),
        func.coalesce(func.sum(OrderItem.quantity * func.coalesce(OrderItem.cost_price, OrderItem.price * 0.60)), 0).label('total_cogs'),
    ).join(OrderItem, OrderItem.product_id == Product.id) \
     .join(Order, Order.id == OrderItem.order_id) \
     .outerjoin(ProductVariant, ProductVariant.id == OrderItem.variant_id) \
     .outerjoin(Category, Category.id == Product.main_category_id) \
     .filter(
        Product.store_id == store.id,
        Order.status.in_(COMPLETED_ORDER_STATUSES),
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
        func.coalesce(func.sum(POSOrderItem.quantity * POSOrderItem.price), 0).label('total_sales'),
        func.coalesce(func.sum(POSOrderItem.quantity * func.coalesce(POSOrderItem.cost_price, POSOrderItem.price * 0.60)), 0).label('total_cogs'),
    ).join(POSOrderItem, POSOrderItem.product_id == Product.id) \
     .join(POSOrder, POSOrder.id == POSOrderItem.pos_order_id) \
     .outerjoin(ProductVariant, ProductVariant.id == POSOrderItem.variant_id) \
     .outerjoin(Category, Category.id == Product.main_category_id) \
     .filter(
        Product.store_id == store.id,
        POSOrder.created_at >= range_start,
        POSOrder.created_at < range_end,
    ).group_by(Product.id, Product.name, ProductVariant.id, ProductVariant.name, Category.name).all()

    tp_map = defaultdict(lambda: {
        'total_sold': 0,
        'total_sales': 0.0,
        'total_cogs': 0.0,
        'total_profit': 0.0,
        'margin_pct': 0.0,
        'category': 'General',
        'variant_name': None,
        'id': None,
        'variant_id': None,
    })
    for r in online_top:
        key = (r.id, r.variant_id)
        tp_map[key]['id'] = r.id
        tp_map[key]['variant_id'] = r.variant_id
        tp_map[key]['name'] = r.name
        tp_map[key]['variant_name'] = r.variant_name
        tp_map[key]['category'] = r.category_name or 'General'
        tp_map[key]['total_sold'] += int(r.total_sold or 0)
        tp_map[key]['total_sales'] += float(r.total_sales or 0.0)
        tp_map[key]['total_cogs'] += float(r.total_cogs or 0.0)
    for r in pos_top:
        key = (r.id, r.variant_id)
        tp_map[key]['id'] = r.id
        tp_map[key]['variant_id'] = r.variant_id
        tp_map[key]['name'] = r.name
        tp_map[key]['variant_name'] = r.variant_name
        tp_map[key]['category'] = r.category_name or 'General'
        tp_map[key]['total_sold'] += int(r.total_sold or 0)
        tp_map[key]['total_sales'] += float(r.total_sales or 0.0)
        tp_map[key]['total_cogs'] += float(r.total_cogs or 0.0)

    for tp in tp_map.values():
        if tp.get('variant_name'):
            tp['name'] = f"{tp['name']} — {tp['variant_name']}"
        s = float(tp['total_sales'] or 0.0)
        c = float(tp['total_cogs'] or 0.0)
        p = s - c
        tp['total_profit'] = p
        tp['margin_pct'] = round((p / s * 100), 1) if s > 0 else 0.0

    _attach_listing_thumbs(list(tp_map.values()))
    top_products_by_qty = sorted(tp_map.values(), key=lambda x: (x['total_sold'], x['total_sales']), reverse=True)[:5]
    top_products_by_sales = sorted(tp_map.values(), key=lambda x: (x['total_sales'], x['total_sold']), reverse=True)[:5]
    top_products_by_profit = sorted(tp_map.values(), key=lambda x: (x['total_profit'], x['total_sales']), reverse=True)[:5]
    top_products = top_products_by_qty

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
            '_sort_at': o.created_at or datetime.min,
            'total': float(o.total_amount or 0),
            'status': o.status,
            'type': 'online',
            'fulfillment_type': getattr(o, 'fulfillment_type', 'delivery') or 'delivery',
        })
    for p in pos_recent:
        recent_orders_list.append({
            'id': p.id,
            'customer_name': p.customer_name or 'Walk-in',
            'customer_initial': ((p.customer_name or 'W')[0]).upper(),
            'date': _fmt_pht(p.created_at) if p.created_at else '',
            '_sort_at': p.created_at or datetime.min,
            'total': float(p.total_amount or 0),
            'status': 'completed',
            'type': 'pos',
        })
    recent_orders_list.sort(key=lambda x: x['_sort_at'], reverse=True)
    recent_orders_list = recent_orders_list[:10]
    for row in recent_orders_list:
        row.pop('_sort_at', None)

    # ── Revenue chart data (Philippine calendar days) ──
    def _build_chart_dataset(store_id, ds_start, ds_end):
        online_rows = db.session.query(Order.created_at, Order.total_amount).filter(
            Order.store_id == store_id,
            Order.status.in_(COMPLETED_ORDER_STATUSES),
            Order.created_at >= ds_start,
            Order.created_at < ds_end,
        ).all()
        pos_rows = db.session.query(POSOrder.created_at, POSOrder.total_amount).filter(
            POSOrder.store_id == store_id,
            POSOrder.created_at >= ds_start,
            POSOrder.created_at < ds_end,
        ).all()

        oi_cogs_rows = db.session.query(
            Order.created_at,
            func.coalesce(OrderItem.quantity * func.coalesce(OrderItem.cost_price, OrderItem.price * 0.60), 0)
        ).join(Order, Order.id == OrderItem.order_id).filter(
            Order.store_id == store_id,
            Order.status.in_(COMPLETED_ORDER_STATUSES),
            Order.created_at >= ds_start,
            Order.created_at < ds_end,
        ).all()

        oia_cogs_rows = db.session.query(
            Order.created_at,
            func.coalesce(OrderItemAddon.quantity * func.coalesce(OrderItemAddon.cost_price, OrderItemAddon.price * 0.60), 0)
        ).join(OrderItem, OrderItem.id == OrderItemAddon.order_item_id) \
         .join(Order, Order.id == OrderItem.order_id).filter(
            Order.store_id == store_id,
            Order.status.in_(COMPLETED_ORDER_STATUSES),
            Order.created_at >= ds_start,
            Order.created_at < ds_end,
        ).all()

        pos_cogs_rows = db.session.query(
            POSOrder.created_at,
            func.coalesce(POSOrderItem.quantity * func.coalesce(POSOrderItem.cost_price, POSOrderItem.price * 0.60), 0)
        ).join(POSOrder, POSOrder.id == POSOrderItem.pos_order_id).filter(
            POSOrder.store_id == store_id,
            POSOrder.created_at >= ds_start,
            POSOrder.created_at < ds_end,
        ).all()

        o_map = defaultdict(lambda: [0.0, 0])
        p_map = defaultdict(lambda: [0.0, 0])
        c_map = defaultdict(float)

        for ts, amt in online_rows:
            d = _pht_date(ts)
            if d:
                o_map[d][0] += float(amt or 0)
                o_map[d][1] += 1
        for ts, amt in pos_rows:
            d = _pht_date(ts)
            if d:
                p_map[d][0] += float(amt or 0)
                p_map[d][1] += 1
        for ts, c_amt in oi_cogs_rows:
            d = _pht_date(ts)
            if d:
                c_map[d] += float(c_amt or 0)
        for ts, c_amt in oia_cogs_rows:
            d = _pht_date(ts)
            if d:
                c_map[d] += float(c_amt or 0)
        for ts, c_amt in pos_cogs_rows:
            d = _pht_date(ts)
            if d:
                c_map[d] += float(c_amt or 0)

        labels, rev, o_rev, p_rev, cnt, o_cnt, p_cnt = [], [], [], [], [], [], []
        cogs_series, profit_series = [], []
        for d in _iter_pht_days(ds_start, ds_end):
            labels.append(d.strftime('%b %d'))
            or_v, oc = o_map.get(d, [0.0, 0])
            pr_v, pc = p_map.get(d, [0.0, 0])
            day_rev = or_v + pr_v
            day_cogs = c_map.get(d, 0.0)
            day_profit = day_rev - day_cogs

            o_rev.append(or_v); p_rev.append(pr_v); rev.append(day_rev)
            o_cnt.append(oc); p_cnt.append(pc); cnt.append(oc + pc)
            cogs_series.append(round(day_cogs, 2))
            profit_series.append(round(day_profit, 2))
        return {
            'labels': labels, 'revenue': rev,
            'online_revenue': o_rev, 'pos_revenue': p_rev,
            'orders': cnt, 'online_orders': o_cnt, 'pos_orders': p_cnt,
            'cogs': cogs_series, 'profit': profit_series,
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
    low_stock_products = Product.query.options(selectinload(Product.images)).filter(
        Product.store_id == store.id,
        Product.is_archived == False,
        Product.stock_quantity <= 5,
        Product.stock_quantity > 0
    ).order_by(Product.stock_quantity.asc(), Product.name.asc()).all()

    out_of_stock_products = Product.query.options(selectinload(Product.images)).filter(
        Product.store_id == store.id,
        Product.is_archived == False,
        Product.stock_quantity == 0
    ).order_by(Product.name.asc()).all()
    out_of_stock = len(out_of_stock_products)

    # Active riders
    active_riders = Rider.query.filter_by(store_id=store.id, is_active=True).count()
    total_riders = Rider.query.filter_by(store_id=store.id).count()

    # Pending orders count
    pending_orders = Order.query.filter(
        Order.store_id == store.id,
        Order.status.in_(['pending', 'preparing', 'accepted', 'done_preparing']),
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).count()

    # POS revenue today (Philippine calendar day)
    today_start, today_end, _ = period_range('today')
    pos_revenue_today = db.session.query(
        func.coalesce(func.sum(POSOrder.total_amount), 0)
    ).filter(
        POSOrder.store_id == store.id,
        POSOrder.created_at >= today_start,
        POSOrder.created_at < today_end,
    ).scalar() or 0

    pos_orders_today = POSOrder.query.filter(
        POSOrder.store_id == store.id,
        POSOrder.created_at >= today_start,
        POSOrder.created_at < today_end,
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

    pos_count_in_period = POSOrder.query.filter(
        POSOrder.store_id == store.id,
        POSOrder.created_at >= range_start,
        POSOrder.created_at < range_end,
    ).count()
    if pos_count_in_period > 0:
        order_status_dist['completed'] = order_status_dist.get('completed', 0) + pos_count_in_period

    # ── Analytics: Revenue by payment method (online completed + POS) ──
    payment_method_query = db.session.query(
        func.lower(Order.payment_method),
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(
        Order.store_id == store.id,
        Order.status.in_(COMPLETED_ORDER_STATUSES),
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).group_by(func.lower(Order.payment_method)).all()
    revenue_by_payment = {str(row[0] or 'unknown').lower(): float(row[1]) for row in payment_method_query}

    pos_payment_query = db.session.query(
        func.lower(POSOrder.payment_method),
        func.coalesce(func.sum(POSOrder.total_amount), 0)
    ).filter(
        POSOrder.store_id == store.id,
        POSOrder.created_at >= range_start,
        POSOrder.created_at < range_end,
    ).group_by(func.lower(POSOrder.payment_method)).all()
    for method, amount in pos_payment_query:
        key = (method or 'cash').strip().lower()
        # Tag POS methods so they don't silently collide with online labels.
        label = f"pos_{key}"
        revenue_by_payment[label] = revenue_by_payment.get(label, 0.0) + float(amount or 0)

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
        Order.status.in_(COMPLETED_ORDER_STATUSES),
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
        POSOrderItem.product_id.isnot(None),
        (POSOrderItem.is_custom.is_(False)) | (POSOrderItem.is_custom.is_(None)),
    ).group_by(Category.name).all()

    pos_custom_category_sales_query = db.session.query(
        POSOrderItem.custom_category,
        func.coalesce(func.sum(POSOrderItem.quantity), 0).label('qty'),
        func.coalesce(func.sum(POSOrderItem.price * POSOrderItem.quantity), 0).label('rev')
    ).join(POSOrder, POSOrder.id == POSOrderItem.pos_order_id) \
     .filter(
        POSOrder.store_id == store.id,
        POSOrder.created_at >= range_start,
        POSOrder.created_at < range_end,
        (POSOrderItem.is_custom.is_(True)) | (POSOrderItem.product_id.is_(None)),
    ).group_by(POSOrderItem.custom_category).all()

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

    cat_lookup = {}
    try:
        for c in Category.query.all():
            if c.slug:
                cat_lookup[c.slug.strip().lower()] = c.name
            if c.name:
                cat_lookup[c.name.strip().lower()] = c.name
    except Exception:
        pass

    for raw_cat, qty, rev in pos_custom_category_sales_query:
        cat_key = (raw_cat or '').strip().lower()
        key = cat_lookup.get(cat_key) or (cat_key.replace('-', ' ').title() if cat_key else 'Custom Arrangements')
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

    # ── Analytics: POS vs Online revenue (reuse PHT chart series) ──
    pos_vs_online = {
        'labels': chart_data.get('labels', []),
        'online': chart_data.get('online_revenue', []),
        'pos': chart_data.get('pos_revenue', []),
    }

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

    # ── Analytics: Peak hours in PHT (online + POS, equal 2-hour windows) ──
    peak_hours = _peak_hours(store.id, range_start, range_end)
    hourly_distribution = {row['label']: row['count'] for row in peak_hours}

    # ── Analytics: AOV trend by PHT day (completed online + POS) ──
    aov_by_day = defaultdict(lambda: [0.0, 0])  # rev, count
    for ts, amt in db.session.query(Order.created_at, Order.total_amount).filter(
        Order.store_id == store.id,
        Order.status.in_(COMPLETED_ORDER_STATUSES),
        Order.created_at >= range_start,
        Order.created_at < range_end,
    ).all():
        d = _pht_date(ts)
        if d:
            aov_by_day[d][0] += float(amt or 0)
            aov_by_day[d][1] += 1
    for ts, amt in db.session.query(POSOrder.created_at, POSOrder.total_amount).filter(
        POSOrder.store_id == store.id,
        POSOrder.created_at >= range_start,
        POSOrder.created_at < range_end,
    ).all():
        d = _pht_date(ts)
        if d:
            aov_by_day[d][0] += float(amt or 0)
            aov_by_day[d][1] += 1

    aov_trend = {'labels': [], 'values': [], 'counts': []}
    for d in _iter_pht_days(range_start, range_end):
        rev, cnt = aov_by_day.get(d, [0.0, 0])
        if cnt <= 0:
            continue
        aov_trend['labels'].append(d.strftime('%b %d'))
        aov_trend['values'].append(round(rev / cnt, 2))
        aov_trend['counts'].append(cnt)

    # ── Analytics: Customer retention (repeat vs one-time vs first-time, ONLINE + POS) ──
    total_unique_customers = curr_cust_metrics['total_unique']
    repeat_customers = curr_cust_metrics['repeat']
    new_customers = curr_cust_metrics['new_customers']
    repeat_customers_list = curr_cust_metrics.get('repeat_list', [])
    repeat_customers_is_all_time = False
    if not repeat_customers_list and curr_cust_metrics.get('all_time_repeat_list'):
        repeat_customers_list = curr_cust_metrics.get('all_time_repeat_list', [])
        repeat_customers_is_all_time = True

    from app.utils.store_schedule import format_store_hours_parts
    from app.utils.phone_utils import is_synthetic_account_email
    store_hours_parts = format_store_hours_parts(store.store_schedule)
    seller_user = store.seller if store else None
    raw_seller_email = (seller_user.email or '').strip() if seller_user else ''
    seller_has_synthetic_email = is_synthetic_account_email(raw_seller_email)
    seller_phone = (seller_user.phone or '').strip() if seller_user else ''
    seller_email = '' if seller_has_synthetic_email else raw_seller_email

    return render_template('seller_dashboard.html',
        store=store,
        store_hours_parts=store_hours_parts,
        seller_has_synthetic_email=seller_has_synthetic_email,
        seller_phone=seller_phone,
        seller_email=seller_email,
        period=period,
        period_label=period_label,
        custom_from=custom_from,
        custom_to=custom_to,
        revenue_this_month=float(revenue_this_month),
        revenue_change=revenue_change,
        cogs_this_month=float(cogs_this_month),
        cogs_change=cogs_change,
        profit_this_month=float(profit_this_month),
        profit_change=profit_change,
        margin_pct_this=float(margin_pct_this),
        margin_change=margin_change,
        orders_this_month=orders_this_month,
        orders_change=orders_change,
        customers_this_month=customers_this_month,
        customers_change=customers_change,
        delivery_rate=delivery_rate,
        top_products=top_products,
        top_products_by_qty=top_products_by_qty,
        top_products_by_sales=top_products_by_sales,
        top_products_by_profit=top_products_by_profit,
        recent_orders=recent_orders_list,
        chart_data=chart_data,
        avg_rating=avg_rating,
        total_reviews=total_reviews,
        store_avg_rating=store_avg_rating,
        store_total_reviews=store_total_reviews,
        total_products=total_products,
        low_stock_products=[p.to_dict() for p in low_stock_products],
        out_of_stock=out_of_stock,
        out_of_stock_products=[p.to_dict() for p in out_of_stock_products],
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
        peak_hours=peak_hours,
        aov_trend=aov_trend,
        new_customers=new_customers,
        repeat_customers=repeat_customers,
        total_unique_customers=total_unique_customers,
        repeat_customers_list=repeat_customers_list,
        repeat_customers_is_all_time=repeat_customers_is_all_time,
    )

@templates_bp.route('/admin/system-checker')
def admin_system_checker():
    if session.get('role') != 'admin':
        return redirect(url_for('templates.dashboard'))
    return render_template('admin_system_checker.html')

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
    from app.utils.phone_utils import display_login_id
    for ban in bans:
        item = ban.to_dict()
        item['user_name'] = ban.user.full_name if ban.user else 'Unknown user'
        item['user_email'] = (
            display_login_id(email=ban.user.email, phone=ban.user.phone)
            if ban.user else None
        )
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
        # Add user details (login_id hides synthetic @sms.eflora.internal emails)
        user = User.query.get(app.user_id)
        if user:
            user_data = user.to_dict()
            app_dict['full_name'] = user_data.get('full_name') or user.full_name
            app_dict['email'] = user_data.get('login_id') or user_data.get('email')
            app_dict['login_id'] = app_dict['email']
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

        target_store = None
        if existing_store:
            # Reactivate the existing store — keeps all products intact
            existing_store.status = 'active'
            existing_store.name = application.store_name
            existing_store.description = application.store_description
            existing_store.seller_application_id = application.id
            target_store = existing_store
            print(f"♻️ Reactivated existing store ID {existing_store.id} for user {user.id}")
        else:
            # First-time approval — create a new store
            store = Store(
                seller_id=user.id,
                name=application.store_name,
                description=application.store_description,
                address='',
                status='active',
                seller_application_id=application.id
            )
            db.session.add(store)
            db.session.flush()
            target_store = store
            print(f"🆕 Created new store for user {user.id}")

        # Update store subscription
        valid_until = datetime.utcnow() + timedelta(days=30)
        target_store.subscription_status = 'active'
        target_store.subscription_valid_until = valid_until

        # Update linked initial registration payment
        from app.models import SellerSubscriptionPayment
        sub_payment = SellerSubscriptionPayment.query.filter_by(
            application_id=application.id
        ).order_by(SellerSubscriptionPayment.submitted_at.desc()).first()

        payment_amount = 300.0
        if sub_payment:
            sub_payment.status = 'approved'
            sub_payment.store_id = target_store.id
            sub_payment.reviewed_at = datetime.utcnow()
            sub_payment.reviewed_by = session['user_id']
            sub_payment.billing_period_start = datetime.utcnow().date()
            sub_payment.billing_period_end = valid_until.date()
            payment_amount = sub_payment.amount
        elif application.payment_receipt_url:
            from app.models import AdminPaymentSetting
            setting = AdminPaymentSetting.query.first()
            sub_payment = SellerSubscriptionPayment(
                seller_id=user.id,
                store_id=target_store.id,
                application_id=application.id,
                payment_type='registration',
                amount=setting.monthly_fee if setting else 300.0,
                receipt_url=application.payment_receipt_url,
                receipt_public_id=application.payment_receipt_public_id,
                status='approved',
                submitted_at=application.submitted_at or datetime.utcnow(),
                reviewed_at=datetime.utcnow(),
                reviewed_by=session['user_id'],
                billing_period_start=datetime.utcnow().date(),
                billing_period_end=valid_until.date()
            )
            db.session.add(sub_payment)
            payment_amount = sub_payment.amount

        # Send payment approved email via Gmail OAuth background thread
        from app.utils.email_helper import send_seller_payment_approved_email
        recipient_name = user.full_name or application.applicant_full_name or application.store_name
        send_seller_payment_approved_email(
            recipient_email=user.email or application.applicant_email,
            recipient_name=recipient_name,
            store_name=application.store_name,
            amount=payment_amount,
            billing_end=valid_until,
            payment_type='registration'
        )

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

        # Update linked initial registration payment
        from app.models import SellerSubscriptionPayment
        sub_payment = SellerSubscriptionPayment.query.filter_by(
            application_id=application.id
        ).order_by(SellerSubscriptionPayment.submitted_at.desc()).first()
        if sub_payment:
            sub_payment.status = 'rejected'
            sub_payment.reviewed_at = datetime.utcnow()
            sub_payment.reviewed_by = session['user_id']
            sub_payment.admin_notes = application.admin_notes

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

@templates_bp.route('/admin/payments')
def admin_payments():
    """Admin payments page for managing QR code, monthly fee, and approving payments."""
    if session.get('role') != 'admin':
        return redirect(url_for('templates.dashboard'))

    from app.models import AdminPaymentSetting, SellerSubscriptionPayment
    setting = AdminPaymentSetting.query.first()
    if not setting:
        setting = AdminPaymentSetting(monthly_fee=300.0)
        db.session.add(setting)
        db.session.commit()

    total_pending = SellerSubscriptionPayment.query.filter_by(status='pending').count()
    total_approved = SellerSubscriptionPayment.query.filter_by(status='approved').count()
    total_rejected = SellerSubscriptionPayment.query.filter_by(status='rejected').count()

    return render_template(
        'admin_payments.html',
        setting=setting,
        total_pending=total_pending,
        total_approved=total_approved,
        total_rejected=total_rejected
    )


@templates_bp.route('/api/admin/payment-settings', methods=['POST'])
def update_admin_payment_settings():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json() or {}
        from app.models import AdminPaymentSetting
        setting = AdminPaymentSetting.query.first()
        if not setting:
            setting = AdminPaymentSetting()
            db.session.add(setting)

        if 'monthly_fee' in data:
            try:
                raw_fee = float(data['monthly_fee'])
                if raw_fee < 0:
                    return jsonify({'error': 'Monthly platform fee cannot be negative'}), 400
                setting.monthly_fee = round(raw_fee, 2)
            except (ValueError, TypeError):
                return jsonify({'error': 'Invalid monthly fee amount'}), 400

        if 'qr_image_url' in data:
            setting.qr_image_url = data['qr_image_url'].strip() or None
        if 'qr_image_public_id' in data:
            setting.qr_image_public_id = data['qr_image_public_id'].strip() or None

        if 'account_name' in data:
            acc_name = (data.get('account_name') or '').strip()
            if len(acc_name) > 50:
                return jsonify({'error': 'GCash Account Name cannot exceed 50 characters'}), 400
            setting.account_name = acc_name or None

        if 'account_number' in data:
            acc_num = (data.get('account_number') or '').strip()
            if acc_num:
                clean_phone = re.sub(r'\D', '', acc_num)
                if not re.fullmatch(r'09\d{9}', clean_phone):
                    return jsonify({'error': 'GCash mobile number must be a valid 11-digit Philippine mobile number starting with 09 (e.g. 09171234567)'}), 400
                setting.account_number = clean_phone
            else:
                setting.account_number = None

        if 'instructions' in data:
            inst = (data.get('instructions') or '').strip()
            if len(inst) > 300:
                return jsonify({'error': 'Short instructions cannot exceed 300 characters'}), 400
            setting.instructions = inst or None

        setting.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Payment settings updated successfully',
            'setting': setting.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/admin/subscription-payments', methods=['GET'])
def get_subscription_payments():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401

    status_filter = request.args.get('status', 'all').lower()
    from app.models import SellerSubscriptionPayment
    query = SellerSubscriptionPayment.query

    if status_filter in ('pending', 'approved', 'rejected'):
        query = query.filter_by(status=status_filter)

    payments = query.order_by(SellerSubscriptionPayment.submitted_at.desc()).all()
    return jsonify({
        'success': True,
        'payments': [p.to_dict() for p in payments]
    })


@templates_bp.route('/api/admin/subscription-payments/<int:payment_id>/approve', methods=['POST'])
def approve_subscription_payment(payment_id):
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        from app.models import SellerSubscriptionPayment, Store, Notification
        from app.utils.email_helper import send_seller_payment_approved_email

        payment = SellerSubscriptionPayment.query.get_or_404(payment_id)
        if payment.status == 'approved':
            return jsonify({'error': 'Payment is already approved'}), 400

        # Determine target store
        store = None
        if payment.store_id:
            store = Store.query.get(payment.store_id)
        elif payment.application_id:
            store = Store.query.filter_by(seller_application_id=payment.application_id).first()
        if not store and payment.seller_id:
            store = Store.query.filter_by(seller_id=payment.seller_id).first()

        now = datetime.utcnow()
        months = getattr(payment, 'months_covered', None) or 1
        days_to_add = months * 30

        # Calculate new valid_until date
        if store:
            if store.subscription_valid_until and store.subscription_valid_until > now:
                new_valid_until = store.subscription_valid_until + timedelta(days=days_to_add)
            else:
                new_valid_until = now + timedelta(days=days_to_add)
            store.subscription_status = 'active'
            store.subscription_valid_until = new_valid_until
            payment.store_id = store.id
            billing_start = now.date()
            billing_end = new_valid_until.date()
        else:
            new_valid_until = now + timedelta(days=days_to_add)
            billing_start = now.date()
            billing_end = new_valid_until.date()

        payment.status = 'approved'
        payment.reviewed_at = now
        payment.reviewed_by = session['user_id']
        payment.billing_period_start = billing_start
        payment.billing_period_end = billing_end

        # Send in-app notification
        duration_desc = f"{months} Month{'s' if months > 1 else ''}"
        store_name = store.name if store else (payment.application.store_name if payment.application else 'Your Store')
        notif = Notification(
            user_id=payment.seller_id,
            title='Subscription Payment Approved',
            message=f'Your subscription payment of ₱{payment.amount:,.2f} ({duration_desc}) for "{store_name}" has been approved. Subscription is valid until {billing_end.strftime("%b %d, %Y")}.',
            type='payment_approved',
            reference_id=payment.id
        )
        db.session.add(notif)

        db.session.commit()

        # Send email using Gmail OAuth in background
        seller_user = User.query.get(payment.seller_id)
        if seller_user:
            send_seller_payment_approved_email(
                recipient_email=seller_user.email,
                recipient_name=seller_user.full_name or store_name,
                store_name=store_name,
                amount=payment.amount,
                billing_end=new_valid_until,
                payment_type=payment.payment_type
            )

        return jsonify({
            'success': True,
            'message': 'Payment approved and subscription extended successfully',
            'payment': payment.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/api/admin/subscription-payments/<int:payment_id>/reject', methods=['POST'])
def reject_subscription_payment(payment_id):
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        from app.models import SellerSubscriptionPayment, Notification
        data = request.get_json() or {}
        admin_notes = (data.get('admin_notes') or '').strip()

        payment = SellerSubscriptionPayment.query.get_or_404(payment_id)
        payment.status = 'rejected'
        payment.admin_notes = admin_notes
        payment.reviewed_at = datetime.utcnow()
        payment.reviewed_by = session['user_id']

        # Notify seller
        notif = Notification(
            user_id=payment.seller_id,
            title='Subscription Payment Rejected',
            message=f'Your subscription payment was rejected. Reason: {admin_notes or "Invalid receipt or amount."} Please resubmit your payment.',
            type='payment_rejected',
            reference_id=payment.id
        )
        db.session.add(notif)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Payment marked as rejected',
            'payment': payment.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


def _calculate_seller_subscription_billing_meta(store, setting):
    now = datetime.utcnow()
    valid_until = store.subscription_valid_until if store else None
    is_active = bool(valid_until and valid_until > now and store.subscription_status == 'active')
    days_left = (valid_until - now).days if is_active else 0

    # Renewal & advance rules:
    # - In renewal window if expired/inactive OR days_left <= 7.
    # - Max advance limit is 2 months (60-65 days).
    # - If days_left <= 7: seller can pay for 1 or 2 months.
    # - If 7 < days_left <= 35: seller can advance pay for 1 additional month (total coverage <= 65 days).
    # - If days_left > 35: seller is already covered for over a month in advance, so 0 advance payments allowed.
    if not is_active or days_left <= 7:
        max_advance_months_allowed = 2
        is_renewal_due = True
    elif days_left <= 35:
        max_advance_months_allowed = 1
        is_renewal_due = False
    else:
        max_advance_months_allowed = 0
        is_renewal_due = False

    can_renew = max_advance_months_allowed > 0

    # Next bill issue date: 7 days before valid_until, or today if expired
    if valid_until and is_active:
        next_bill_date = valid_until - timedelta(days=7)
    else:
        next_bill_date = now

    base_fee = float(setting.monthly_fee) if setting and setting.monthly_fee else 300.0
    start_date = valid_until if (valid_until and valid_until > now) else now

    quotations = {
        '1': {
            'months': 1,
            'amount': base_fee,
            'formatted_amount': f"₱{base_fee:,.2f}",
            'label': "1 Month (30 Days)",
            'coverage_start': start_date.strftime('%b %d, %Y'),
            'coverage_end': (start_date + timedelta(days=30)).strftime('%b %d, %Y'),
            'coverage_end_iso': (start_date + timedelta(days=30)).isoformat(),
        },
        '2': {
            'months': 2,
            'amount': round(base_fee * 2, 2),
            'formatted_amount': f"₱{base_fee * 2:,.2f}",
            'label': "2 Months Advance (60 Days)",
            'coverage_start': start_date.strftime('%b %d, %Y'),
            'coverage_end': (start_date + timedelta(days=60)).strftime('%b %d, %Y'),
            'coverage_end_iso': (start_date + timedelta(days=60)).isoformat(),
        }
    }

    return {
        'is_active': is_active,
        'days_left': days_left,
        'is_renewal_due': is_renewal_due,
        'max_advance_months_allowed': max_advance_months_allowed,
        'can_renew': can_renew,
        'next_bill_date': next_bill_date,
        'valid_until': valid_until,
        'quotations': quotations,
        'base_fee': base_fee,
    }


@templates_bp.route('/seller/payments')
def seller_payments():
    """Monthly subscription payments page for sellers."""
    if not session.get('user_id'):
        return redirect(url_for('templates.login', next=url_for('templates.seller_payments')))

    user = User.query.get(session['user_id'])
    if not user or user.role != 'seller':
        return redirect(url_for('templates.dashboard'))

    store = _seller_portal_manageable_store(user.id)
    if not store:
        # Check if they have an active or inactive store
        store = Store.query.filter_by(seller_id=user.id).first()
    if not store:
        return redirect(url_for('templates.seller_signup_complete'))

    from app.models import AdminPaymentSetting, SellerSubscriptionPayment
    setting = AdminPaymentSetting.query.first()
    if not setting:
        setting = AdminPaymentSetting(monthly_fee=300.0)

    # Payments for this seller / store
    payments = (
        SellerSubscriptionPayment.query
        .filter((SellerSubscriptionPayment.seller_id == user.id) | (SellerSubscriptionPayment.store_id == store.id))
        .order_by(SellerSubscriptionPayment.submitted_at.desc())
        .all()
    )

    billing_meta = _calculate_seller_subscription_billing_meta(store, setting)
    has_pending = any(p.status == 'pending' for p in payments)
    pending_payment = next((p for p in payments if p.status == 'pending'), None)

    return render_template(
        'seller_payments.html',
        user=user,
        store=store,
        setting=setting,
        payments=payments,
        is_active=billing_meta['is_active'],
        days_left=billing_meta['days_left'],
        is_renewal_due=billing_meta['is_renewal_due'],
        max_advance_months_allowed=billing_meta['max_advance_months_allowed'],
        can_renew=billing_meta['can_renew'],
        next_bill_date=billing_meta['next_bill_date'],
        quotations=billing_meta['quotations'],
        base_fee=billing_meta['base_fee'],
        has_pending=has_pending,
        pending_payment=pending_payment,
        valid_until=store.subscription_valid_until
    )


@templates_bp.route('/api/seller/subscription-payments', methods=['GET'])
def get_seller_subscription_payments():
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401

    user = User.query.get(session['user_id'])
    if not user or user.role != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401

    store = Store.query.filter_by(seller_id=user.id).first()
    from app.models import SellerSubscriptionPayment, AdminPaymentSetting
    setting = AdminPaymentSetting.query.first()

    payments = []
    if store:
        payments = (
            SellerSubscriptionPayment.query
            .filter((SellerSubscriptionPayment.seller_id == user.id) | (SellerSubscriptionPayment.store_id == store.id))
            .order_by(SellerSubscriptionPayment.submitted_at.desc())
            .all()
        )

    billing_meta = _calculate_seller_subscription_billing_meta(store, setting) if (store and setting) else {}

    return jsonify({
        'success': True,
        'store': {
            'id': store.id if store else None,
            'name': store.name if store else None,
            'subscription_status': store.subscription_status if store else 'inactive',
            'subscription_valid_until': store.subscription_valid_until.isoformat() if store and store.subscription_valid_until else None,
        },
        'billing': {
            'is_active': billing_meta.get('is_active', False),
            'days_left': billing_meta.get('days_left', 0),
            'is_renewal_due': billing_meta.get('is_renewal_due', False),
            'max_advance_months_allowed': billing_meta.get('max_advance_months_allowed', 0),
            'can_renew': billing_meta.get('can_renew', False),
            'next_bill_date': billing_meta.get('next_bill_date').isoformat() if billing_meta.get('next_bill_date') else None,
            'quotations': billing_meta.get('quotations', {}),
            'base_fee': billing_meta.get('base_fee', 300.0),
            'has_pending': any(p.status == 'pending' for p in payments)
        },
        'setting': setting.to_dict() if setting else None,
        'payments': [p.to_dict() for p in payments]
    })


@templates_bp.route('/api/seller/subscription-payments', methods=['POST'])
def submit_seller_subscription_payment():
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401

    user = User.query.get(session['user_id'])
    if not user or user.role != 'seller':
        return jsonify({'error': 'Unauthorized'}), 401

    store = Store.query.filter_by(seller_id=user.id).first()
    if not store:
        return jsonify({'error': 'Store not found'}), 404

    data = request.get_json() or {}
    receipt_url = (data.get('receipt_url') or '').strip()
    receipt_public_id = (data.get('receipt_public_id') or '').strip()

    if not receipt_url:
        return jsonify({'error': 'Payment receipt image is required'}), 400

    from app.models import AdminPaymentSetting, SellerSubscriptionPayment
    setting = AdminPaymentSetting.query.first()
    if not setting or not setting.is_configured:
        return jsonify({'error': 'Payment receiving is currently not configured by the admin'}), 400

    try:
        months_covered = int(data.get('months_covered') or 1)
    except (ValueError, TypeError):
        months_covered = 1

    if months_covered not in (1, 2):
        return jsonify({'error': 'You can only choose 1 month or 2 months advance.'}), 400

    meta = _calculate_seller_subscription_billing_meta(store, setting)
    if not meta['can_renew'] or months_covered > meta['max_advance_months_allowed']:
        return jsonify({
            'error': f'Your subscription is currently active with {meta["days_left"]} days remaining. You can advance-pay for at most {meta["max_advance_months_allowed"]} month(s).'
        }), 400

    expected_amount = round(setting.monthly_fee * months_covered, 2)

    # Check for existing pending payment
    pending = SellerSubscriptionPayment.query.filter_by(
        seller_id=user.id,
        store_id=store.id,
        status='pending'
    ).first()
    if pending:
        # Update existing pending payment
        pending.receipt_url = receipt_url
        pending.receipt_public_id = receipt_public_id
        pending.months_covered = months_covered
        pending.amount = expected_amount
        pending.submitted_at = datetime.utcnow()
        pending.admin_notes = None
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Your pending subscription payment was updated with the new receipt ({months_covered} month(s) - ₱{expected_amount:,.2f}).',
            'payment': pending.to_dict()
        })

    payment = SellerSubscriptionPayment(
        seller_id=user.id,
        store_id=store.id,
        payment_type='monthly',
        months_covered=months_covered,
        amount=expected_amount,
        receipt_url=receipt_url,
        receipt_public_id=receipt_public_id,
        status='pending',
        submitted_at=datetime.utcnow()
    )
    db.session.add(payment)
    db.session.flush()

    from app.utils.admin_notifications import notify_admins
    duration_label = "1 month" if months_covered == 1 else "2 months advance"
    notify_admins(
        title='New subscription payment submission',
        message=f'Store "{store.name}" submitted a subscription payment receipt (₱{expected_amount:,.2f} for {duration_label}) for review.',
        type='subscription_payment_pending',
        reference_id=payment.id
    )
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Subscription payment ({duration_label} - ₱{expected_amount:,.2f}) submitted successfully for admin review.',
        'payment': payment.to_dict()
    }), 201


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
        online_revenue = db.session.query(
            func.coalesce(func.sum(Order.total_amount), 0)
        ).filter(
            Order.store_id == s.id,
            Order.status == 'delivered'
        ).scalar() or 0
        online_revenue = float(online_revenue)

        pos_revenue = db.session.query(
            func.coalesce(func.sum(POSOrder.total_amount), 0)
        ).filter(
            POSOrder.store_id == s.id
        ).scalar() or 0
        pos_revenue = float(pos_revenue)

        revenue = online_revenue + pos_revenue

        online_order_count = db.session.query(func.count(Order.id)).filter(
            Order.store_id == s.id
        ).scalar() or 0

        pos_order_count = db.session.query(func.count(POSOrder.id)).filter(
            POSOrder.store_id == s.id
        ).scalar() or 0

        order_count = int(online_order_count + pos_order_count)

        product_count = db.session.query(func.count(Product.id)).filter(
            Product.store_id == s.id,
            Product.is_archived.is_(False)
        ).scalar() or 0

        owner_name = s.seller.full_name if s.seller else 'Unassigned'
        owner_email = s.seller.email if s.seller else ''
        raw_status = (s.status or 'pending').lower()
        # Normalize legacy "inactive" to suspended for the admin UI.
        status_key = 'suspended' if raw_status == 'inactive' else raw_status

        loc = (s.public_location_label or s.formatted_address or s.address or '').strip()
        rows.append({
            'id': s.id,
            'name': s.name,
            'description': s.description or '',
            'logo_url': s.logo_url,
            'banner_url': s.banner_url,
            'status': status_key,
            'owner_name': owner_name,
            'owner_email': owner_email,
            'location': loc,
            'delivery_radius_km': float(s.delivery_radius_km or 0),
            'delivery_method': s.delivery_method or 'radius',
            'selected_municipalities': s.selected_municipalities or [],
            'allow_pickup': bool(s.allow_pickup),
            'product_count': int(product_count),
            'order_count': int(order_count),
            'online_order_count': int(online_order_count),
            'pos_order_count': int(pos_order_count),
            'revenue': revenue,
            'online_revenue': online_revenue,
            'pos_revenue': pos_revenue,
            'revenue_display': f"₱{revenue:,.2f}",
            'created_at': _fmt_pht(s.created_at, '%b %d, %Y') if s.created_at else '—',
            'created_at_sort': s.created_at.isoformat() if s.created_at else '',
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


@templates_bp.route('/admin/controls')
def admin_controls():
    if session.get('role') != 'admin':
        return redirect(url_for('templates.dashboard'))
    return render_template('admin_controls.html')


@templates_bp.route('/admin/account')
def admin_account():
    if session.get('role') != 'admin':
        return redirect(url_for('templates.dashboard'))
    return redirect(url_for('templates.dashboard', account='1'))


@templates_bp.route('/api/admin/feature-controls', methods=['GET', 'PUT'])
def api_admin_feature_controls():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    from app.utils.feature_controls import get_feature_controls, set_feature_controls
    if request.method == 'GET':
        return jsonify({'success': True, 'flags': get_feature_controls()}), 200
    data = request.get_json(silent=True) or {}
    flags = set_feature_controls(data)
    return jsonify({'success': True, 'flags': flags}), 200


@templates_bp.route('/api/public/feature-flags', methods=['GET'])
def api_public_feature_flags():
    from app.utils.feature_controls import public_flags
    return jsonify(public_flags()), 200


# ═════════════════════════════════════════════════════════════════════════════
# ADMIN STORES API
# ═════════════════════════════════════════════════════════════════════════════

STORE_DESCRIPTION_MAX_LENGTH = 300


def _validated_store_description(raw):
    """Normalize and validate seller store description length."""
    description = (raw or '').strip()
    if len(description) > STORE_DESCRIPTION_MAX_LENGTH:
        return None, (
            f'Store description must be {STORE_DESCRIPTION_MAX_LENGTH} characters or less.'
        )
    return description or None, None


def _store_summary_dict(store: 'Store') -> dict:
    """Serialize a Store row plus computed counters for the admin UI."""
    from sqlalchemy import func as sa_func

    online_revenue = db.session.query(
        sa_func.coalesce(sa_func.sum(Order.total_amount), 0)
    ).filter(
        Order.store_id == store.id,
        Order.status == 'delivered'
    ).scalar() or 0
    online_revenue = float(online_revenue)

    pos_revenue = db.session.query(
        sa_func.coalesce(sa_func.sum(POSOrder.total_amount), 0)
    ).filter(
        POSOrder.store_id == store.id
    ).scalar() or 0
    pos_revenue = float(pos_revenue)

    total_revenue = online_revenue + pos_revenue

    online_order_count = db.session.query(sa_func.count(Order.id)).filter(
        Order.store_id == store.id
    ).scalar() or 0

    pos_order_count = db.session.query(sa_func.count(POSOrder.id)).filter(
        POSOrder.store_id == store.id
    ).scalar() or 0

    total_order_count = int(online_order_count + pos_order_count)

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
        'banner_url': store.banner_url,
        'location': (store.public_location_label or store.formatted_address or store.address or '').strip(),
        'delivery_radius_km': float(store.delivery_radius_km or 0),
        'delivery_method': store.delivery_method or 'radius',
        'selected_municipalities': store.selected_municipalities or [],
        'allow_pickup': bool(store.allow_pickup),
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
            'order_count': total_order_count,
            'online_order_count': int(online_order_count),
            'pos_order_count': int(pos_order_count),
            'revenue': total_revenue,
            'online_revenue': online_revenue,
            'pos_revenue': pos_revenue,
            'revenue_display': f"₱{total_revenue:,.2f}",
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
        if len(name) > 50:
            return jsonify({'error': 'Store name must be 50 characters or less'}), 400
        store.name = name
    if 'description' in data:
        description, desc_error = _validated_store_description(data.get('description'))
        if desc_error:
            return jsonify({'error': desc_error}), 400
        store.description = description
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
    if session.get('role') not in ('seller', 'store_admin'):
        return redirect(url_for('templates.dashboard'))
    user_id = session.get('user_id')
    if session.get('role') == 'seller':
        latest_app = _seller_portal_latest_application(user_id)
        if latest_app and latest_app.status == 'rejected':
            return redirect(url_for('templates.seller_signup_complete'))
        if latest_app and latest_app.status in ('pending', 'resubmitted'):
            return redirect(url_for('templates.seller_signup_status'))
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
    ).options(
        selectinload(Product.addon_groups).selectinload(ProductAddonGroup.options),
        selectinload(Product.variants),
        selectinload(Product.images),
    ).order_by(Product.created_at.desc()).all()
    
    # FIX: Convert products to dict for template
    product_list = [product.to_dict() for product in products]
    for item in product_list:
        item['store_name'] = store.name

    from sqlalchemy import func
    from app.utils.report_service import COMPLETED_ORDER_STATUSES

    online_sold = dict(
        db.session.query(
            OrderItem.product_id,
            func.coalesce(func.sum(OrderItem.quantity), 0),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            Order.store_id == store.id,
            Order.status.in_(COMPLETED_ORDER_STATUSES),
            OrderItem.product_id.isnot(None),
        )
        .group_by(OrderItem.product_id)
        .all()
    )
    pos_sold = dict(
        db.session.query(
            POSOrderItem.product_id,
            func.coalesce(func.sum(POSOrderItem.quantity), 0),
        )
        .join(POSOrder, POSOrder.id == POSOrderItem.pos_order_id)
        .filter(
            POSOrder.store_id == store.id,
            POSOrderItem.product_id.isnot(None),
        )
        .group_by(POSOrderItem.product_id)
        .all()
    )
    for item in product_list:
        pid = item.get('id')
        item['total_sold'] = int(online_sold.get(pid, 0) or 0) + int(pos_sold.get(pid, 0) or 0)
    
    return render_template('products.html', products=product_list, categories=categories)


@templates_bp.route('/seller/inventory')
def seller_inventory():
    if session.get('role') not in ('seller', 'store_admin'):
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
    ).order_by(Product.created_at.desc().nullslast(), Product.id.desc()).all()

    product_list = [product.to_dict(include_inactive_addons=True) for product in products]
    categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order.asc(), Category.name.asc()).all()

    inv_total = 0
    inv_in = 0
    inv_low = 0
    inv_oos = 0
    inv_products_count = len(product_list)
    inv_variants_count = 0
    inv_addons_count = 0

    for p in product_list:
        inv_total += 1
        p_qty = p.get('stock_quantity') or 0
        if p_qty > 10:
            inv_in += 1
        elif p_qty > 0:
            inv_low += 1
        else:
            inv_oos += 1

        for v in (p.get('variants') or []):
            inv_variants_count += 1
            inv_total += 1
            v_qty = v.get('stock_quantity') or 0
            if v_qty > 10:
                inv_in += 1
            elif v_qty > 0:
                inv_low += 1
            else:
                inv_oos += 1

        for g in (p.get('addon_groups') or []):
            for opt in (g.get('options') or []):
                inv_addons_count += 1
                inv_total += 1
                opt_qty = opt.get('stock_quantity') or 0
                if opt_qty > 10:
                    inv_in += 1
                elif opt_qty > 0:
                    inv_low += 1
                else:
                    inv_oos += 1

    inv_stats = {
        'total': inv_total,
        'in_stock': inv_in,
        'low_stock': inv_low,
        'out_of_stock': inv_oos,
        'products_count': inv_products_count,
        'variants_count': inv_variants_count,
        'addons_count': inv_addons_count,
    }

    return render_template('seller_inventory.html', products=product_list, categories=categories, inv_stats=inv_stats)

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
    if session.get('role') not in ('seller', 'store_admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        # Get seller's store
        store = _seller_portal_manageable_store(session.get('user_id'))
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
        
        cost_price_val = request.form.get('cost_price')
        cost_price_float = None
        if cost_price_val not in (None, ''):
            try:
                cp = float(cost_price_val)
                if cp >= 0:
                    cost_price_float = cp
            except (ValueError, TypeError):
                cost_price_float = None
        if cost_price_float is None:
            cost_price_float = round(price_float * 0.60, 2)

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
        
        # Validate store_category_id if provided or resolve/create by store_category_name
        store_category_name = (request.form.get('store_category_name') or '').strip()
        from app.models import StoreCategory
        from sqlalchemy import func
        if store_category_id:
            store_category = StoreCategory.query.filter_by(
                id=store_category_id,
                store_id=store.id,
                main_category_id=main_category_id
            ).first()
            if not store_category and store_category_name:
                # Fallback: check by name for this store
                store_category = StoreCategory.query.filter(
                    StoreCategory.store_id == store.id,
                    StoreCategory.main_category_id == main_category_id,
                    func.lower(StoreCategory.name) == func.lower(store_category_name)
                ).first()
                if store_category:
                    store_category_id = store_category.id
            if not store_category and not store_category_name:
                return jsonify({'error': 'Invalid store subcategory'}), 400
        elif store_category_name:
            # Check if this store already has this subcategory (case-insensitive)
            store_category = StoreCategory.query.filter(
                StoreCategory.store_id == store.id,
                StoreCategory.main_category_id == main_category_id,
                func.lower(StoreCategory.name) == func.lower(store_category_name)
            ).first()
            if not store_category:
                # Check if standard platform capitalization exists
                plat_existing = StoreCategory.query.filter(
                    StoreCategory.main_category_id == main_category_id,
                    func.lower(StoreCategory.name) == func.lower(store_category_name)
                ).first()
                canon_name = plat_existing.name if plat_existing else (
                    store_category_name.title() if (store_category_name.islower() or store_category_name.isupper()) else store_category_name
                )
                import re as _re
                base_slug = _re.sub(r'[^a-z0-9]+', '-', canon_name.lower()).strip('-')
                store_category = StoreCategory(
                    store_id=store.id,
                    main_category_id=main_category_id,
                    name=canon_name,
                    slug=f"{base_slug}-{store.id}"
                )
                db.session.add(store_category)
                db.session.flush()
            store_category_id = store_category.id
        
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
            cost_price=cost_price_float,
            special_price=special_price_float,
            stock_quantity=stock_int,
            main_category_id=int(main_category_id),
            store_category_id=int(store_category_id) if store_category_id else None,
            is_available=is_available,
            keep_ymal_addons_when_unavailable=(
                (not is_available)
                and request.form.get('keep_ymal_addons_when_unavailable', 'false').lower()
                in ('true', '1', 'yes', 'on')
            ),
        )
        
        db.session.add(product)
        db.session.flush()  # Get product ID

        # Log initial inventory batch in StockReduction
        from app.models import StockReduction
        seller_user_id = session.get('user_id') or (store.seller_id if store else 1)
        if stock_int > 0:
            init_stock_log = StockReduction(
                product_id=product.id,
                reduction_amount=stock_int,
                reason='restock',
                reason_notes='Initial inventory on product creation',
                reduced_by=seller_user_id,
                unit_cost=cost_price_float,
                total_cost=round(cost_price_float * stock_int, 2)
            )
            db.session.add(init_stock_log)
        
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
                        
                        v_price_val = float(variant_data.get('price', price_float) or price_float)
                        v_cost_price = None
                        if variant_data.get('cost_price') not in (None, ''):
                            try:
                                vcp = float(variant_data['cost_price'])
                                if vcp >= 0:
                                    v_cost_price = Decimal(str(round(vcp, 2)))
                            except (ValueError, TypeError):
                                v_cost_price = None
                        if v_cost_price is None:
                            v_cost_price = Decimal(str(round(v_price_val * 0.60, 2)))

                        v_special_price = None
                        if variant_data.get('special_price'):
                            try:
                                sp = float(variant_data['special_price'])
                                v_special_price = sp if sp > 0 else None
                            except (ValueError, TypeError):
                                pass

                        v_stock_qty = int(variant_data.get('stock_quantity', 0))

                        variant = ProductVariant(
                            product_id=product.id,
                            name=variant_data.get('name'),
                            price=Decimal(str(variant_data.get('price'))),
                            cost_price=v_cost_price,
                            special_price=v_special_price,
                            stock_quantity=v_stock_qty,
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
                        db.session.flush()

                        if v_stock_qty > 0:
                            v_unit_cost = float(v_cost_price or 0.0)
                            seller_user_id = session.get('user_id') or (store.seller_id if store else 1)
                            db.session.add(StockReduction(
                                product_id=product.id,
                                variant_id=variant.id,
                                reduction_amount=v_stock_qty,
                                reason='restock',
                                reason_notes=f"Initial inventory for variant: {variant.name}",
                                reduced_by=seller_user_id,
                                unit_cost=v_unit_cost,
                                total_cost=round(v_unit_cost * v_stock_qty, 2)
                            ))
                    
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
    if session.get('role') not in ('seller', 'store_admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        store = _seller_portal_manageable_store(session.get('user_id'))
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
            if 'cost_price' in request.form:
                cp_val = request.form.get('cost_price')
                if cp_val not in (None, ''):
                    try:
                        product.cost_price = max(0.0, float(cp_val))
                    except (ValueError, TypeError):
                        pass
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
                    old_stock = int(product.stock_quantity or 0)
                    new_stock = int(request.form['stock_quantity'])
                    product.stock_quantity = new_stock
                    notify_low_stock_if_crossed(
                        store_id=product.store_id,
                        product=product,
                        stock_before=old_stock,
                        stock_after=new_stock,
                    )
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
            
            if 'store_category_id' in request.form or 'store_category_name' in request.form:
                store_category_id = request.form.get('store_category_id')
                store_category_name = (request.form.get('store_category_name') or '').strip()
                from app.models import StoreCategory
                from sqlalchemy import func
                if store_category_id:
                    store_category = StoreCategory.query.filter_by(
                        id=store_category_id,
                        store_id=store.id,
                        main_category_id=product.main_category_id
                    ).first()
                    if not store_category and store_category_name:
                        store_category = StoreCategory.query.filter(
                            StoreCategory.store_id == store.id,
                            StoreCategory.main_category_id == product.main_category_id,
                            func.lower(StoreCategory.name) == func.lower(store_category_name)
                        ).first()
                    if not store_category and not store_category_name:
                        return jsonify({'error': 'Invalid store subcategory'}), 400
                    product.store_category_id = store_category.id if store_category else None
                elif store_category_name:
                    store_category = StoreCategory.query.filter(
                        StoreCategory.store_id == store.id,
                        StoreCategory.main_category_id == product.main_category_id,
                        func.lower(StoreCategory.name) == func.lower(store_category_name)
                    ).first()
                    if not store_category:
                        plat_existing = StoreCategory.query.filter(
                            StoreCategory.main_category_id == product.main_category_id,
                            func.lower(StoreCategory.name) == func.lower(store_category_name)
                        ).first()
                        canon_name = plat_existing.name if plat_existing else (
                            store_category_name.title() if (store_category_name.islower() or store_category_name.isupper()) else store_category_name
                        )
                        import re as _re
                        base_slug = _re.sub(r'[^a-z0-9]+', '-', canon_name.lower()).strip('-')
                        store_category = StoreCategory(
                            store_id=store.id,
                            main_category_id=product.main_category_id,
                            name=canon_name,
                            slug=f"{base_slug}-{store.id}"
                        )
                        db.session.add(store_category)
                        db.session.flush()
                    product.store_category_id = store_category.id
                else:
                    product.store_category_id = None
            
            if 'is_available' in request.form:
                is_avail_str = request.form['is_available']
                product.is_available = is_avail_str.lower() in ['true', '1', 'yes']
                keep_ymal = request.form.get('keep_ymal_addons_when_unavailable', 'false').lower() in (
                    'true', '1', 'yes', 'on'
                )
                product.keep_ymal_addons_when_unavailable = (not product.is_available) and keep_ymal

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
                                    if variant_data.get('cost_price') not in (None, ''):
                                        try:
                                            variant.cost_price = Decimal(str(round(float(variant_data['cost_price']), 2)))
                                        except (ValueError, TypeError):
                                            pass
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
                                    v_old_stock = int(variant.stock_quantity or 0)
                                    v_new_stock = int(variant_data.get('stock_quantity', 0))
                                    variant.stock_quantity = v_new_stock
                                    notify_low_stock_if_crossed(
                                        store_id=product.store_id,
                                        product=product,
                                        stock_before=v_old_stock,
                                        stock_after=v_new_stock,
                                        variant=variant,
                                    )
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

                                v_cost_new = None
                                if variant_data.get('cost_price') not in (None, ''):
                                    try:
                                        v_cost_new = Decimal(str(round(float(variant_data['cost_price']), 2)))
                                    except (ValueError, TypeError):
                                        pass
                                if v_cost_new is None:
                                    v_cost_new = Decimal(str(round(float(variant_data.get('price', 0)) * 0.60, 2)))

                                v_stock_new = int(variant_data.get('stock_quantity', 0))

                                variant = ProductVariant(
                                    product_id=product.id,
                                    name=variant_data.get('name'),
                                    price=Decimal(str(variant_data.get('price'))),
                                    cost_price=v_cost_new,
                                    special_price=v_sp_new,
                                    stock_quantity=v_stock_new,
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

                                if v_stock_new > 0:
                                    v_unit_cost = float(v_cost_new or 0.0)
                                    seller_user_id = session.get('user_id') or (store.seller_id if store else 1)
                                    db.session.add(StockReduction(
                                        product_id=product.id,
                                        variant_id=variant.id,
                                        reduction_amount=v_stock_new,
                                        reason='restock',
                                        reason_notes=f"Initial inventory for new variant: {variant.name}",
                                        reduced_by=seller_user_id,
                                        unit_cost=v_unit_cost,
                                        total_cost=round(v_unit_cost * v_stock_new, 2)
                                    ))
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
    if session.get('role') not in ('seller', 'store_admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        # Get seller's store
        store = _seller_portal_manageable_store(session.get('user_id'))
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
        if product.is_available:
            product.keep_ymal_addons_when_unavailable = False
        else:
            product.keep_ymal_addons_when_unavailable = bool(
                data.get('keep_ymal_addons_when_unavailable')
            )
        product.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Product {"available" if is_available else "unavailable"}',
            'product_id': product.id,
            'is_available': product.is_available,
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating availability: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/seller/products/bulk-availability', methods=['PUT', 'POST'])
@seller_required
def bulk_update_product_availability():
    """Set availability for many products in one request."""
    store = _seller_portal_manageable_store(session.get('user_id'))
    if not store:
        return jsonify({'error': 'Store not found'}), 404

    data = request.get_json(silent=True) or {}
    raw_ids = data.get('product_ids') or []
    ids = []
    for value in raw_ids:
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue
    ids = list(dict.fromkeys(ids))
    if not ids:
        return jsonify({'error': 'No products selected'}), 400

    is_available = data.get('is_available')
    if is_available is None:
        return jsonify({'error': 'is_available field is required'}), 400
    is_available = bool(is_available)
    keep_ymal = bool(data.get('keep_ymal_addons_when_unavailable'))

    products = Product.query.filter(
        Product.id.in_(ids),
        Product.store_id == store.id,
    ).all()
    if not products:
        return jsonify({'error': 'No matching products found'}), 404

    now = datetime.utcnow()
    for product in products:
        product.is_available = is_available
        if is_available:
            product.keep_ymal_addons_when_unavailable = False
        else:
            product.keep_ymal_addons_when_unavailable = keep_ymal
        product.updated_at = now
    db.session.commit()

    updated_ids = [p.id for p in products]
    missing = [pid for pid in ids if pid not in updated_ids]
    return jsonify({
        'success': True,
        'updated': len(updated_ids),
        'updated_ids': updated_ids,
        'missing_ids': missing,
        'message': f'{len(updated_ids)} product(s) marked {"available" if is_available else "unavailable"}',
    })




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
    if session.get('role') not in ('seller', 'store_admin'):
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
            stock_before = int(variant.stock_quantity or 0)
            variant.stock_quantity -= amount
            variant.updated_at = datetime.utcnow()
            stock_after = int(variant.stock_quantity or 0)
            
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
            notify_low_stock_if_crossed(
                store_id=product.store_id,
                product=product,
                stock_before=stock_before,
                stock_after=stock_after,
                variant=variant,
            )
            
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
            stock_before = int(product.stock_quantity or 0)
            reduction = product.reduce_stock(amount, reason, user_id, reason_notes)
            stock_after = int(product.stock_quantity or 0)
            notify_low_stock_if_crossed(
                store_id=product.store_id,
                product=product,
                stock_before=stock_before,
                stock_after=stock_after,
            )
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
    if session.get('role') not in ('seller', 'store_admin'):
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
        unit_cost_val = data.get('unit_cost')
        unit_cost = None
        if unit_cost_val not in (None, ''):
            try:
                unit_cost = max(0.0, float(unit_cost_val))
            except (TypeError, ValueError):
                unit_cost = None
        
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

            old_stock = max(0, int(addon_opt.stock_quantity or 0))
            addon_opt.stock_quantity = old_stock + amount
            addon_opt.updated_at = datetime.utcnow()

            # Weighted Moving Average Cost (AVCO)
            batch_unit_cost = unit_cost if unit_cost is not None else float(addon_opt.cost_price or round(float(addon_opt.price or 0) * 0.60, 2))
            old_cost = float(addon_opt.cost_price or batch_unit_cost)
            total_units = old_stock + amount
            if total_units > 0:
                blended_cost = round(((old_stock * old_cost) + (amount * batch_unit_cost)) / total_units, 2)
                addon_opt.cost_price = Decimal(str(blended_cost))

            addition = StockReduction(
                product_id=product.id,
                variant_id=None,
                addon_option_id=addon_opt.id,
                reduction_amount=amount,
                unit_cost=batch_unit_cost,
                total_cost=round(batch_unit_cost * amount, 2),
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
            
            old_stock = max(0, int(variant.stock_quantity or 0))
            variant.stock_quantity = old_stock + amount
            variant.updated_at = datetime.utcnow()

            # Weighted Moving Average Cost (AVCO)
            batch_unit_cost = unit_cost if unit_cost is not None else float(variant.cost_price or round(float(variant.price or 0) * 0.60, 2))
            old_cost = float(variant.cost_price or batch_unit_cost)
            total_units = old_stock + amount
            if total_units > 0:
                blended_cost = round(((old_stock * old_cost) + (amount * batch_unit_cost)) / total_units, 2)
                variant.cost_price = Decimal(str(blended_cost))
            
            # Create audit entry for stock addition
            addition = StockReduction(
                product_id=product.id,
                variant_id=variant.id,
                reduction_amount=amount,  # Using the same field, positive for addition
                unit_cost=batch_unit_cost,
                total_cost=round(batch_unit_cost * amount, 2),
                reason=reason,
                reason_notes=reason_notes,
                reduced_by=user_id
            )
            db.session.add(addition)
            
            print(f"✅ Variant stock addition recorded:")
            print(f"   Product: {product.name} (ID: {product.id})")
            print(f"   Variant: {variant.name} (ID: {variant.id})")
            print(f"   Added: {amount} units @ ₱{batch_unit_cost} (Blended AVCO: ₱{variant.cost_price})")
            print(f"   Reason: {reason}")
            print(f"   New variant stock: {variant.stock_quantity}")
            
            # Update product's updated_at timestamp
            product.updated_at = datetime.utcnow()
            db.session.commit()
            
            # Clear stock alert notifications if replenished
            clear_resolved_stock_notifications(
                product_id=product.id,
                current_stock=variant.stock_quantity,
                store_id=store.id,
            )
            
            return jsonify({
                'success': True,
                'message': f'Stock added {amount} units for variant {variant.name}',
                'addition': addition.to_dict(),
                'product': product.to_dict(),
                'variant': variant.to_dict()
            }), 200
            
        else:
            old_stock = max(0, int(product.stock_quantity or 0))
            product.stock_quantity = old_stock + amount
            product.updated_at = datetime.utcnow()

            # Weighted Moving Average Cost (AVCO)
            batch_unit_cost = unit_cost if unit_cost is not None else float(product.cost_price or round(float(product.price or 0) * 0.60, 2))
            old_cost = float(product.cost_price or batch_unit_cost)
            total_units = old_stock + amount
            if total_units > 0:
                blended_cost = round(((old_stock * old_cost) + (amount * batch_unit_cost)) / total_units, 2)
                product.cost_price = blended_cost
            
            # Create audit entry for stock addition
            addition = StockReduction(
                product_id=product.id,
                variant_id=None,
                reduction_amount=amount,  # Using the same field, positive for addition
                unit_cost=batch_unit_cost,
                total_cost=round(batch_unit_cost * amount, 2),
                reason=reason,
                reason_notes=reason_notes,
                reduced_by=user_id
            )
            db.session.add(addition)
            db.session.commit()
            
            # Clear stock alert notifications if replenished
            clear_resolved_stock_notifications(
                product_id=product.id,
                current_stock=product.stock_quantity,
                store_id=store.id,
            )
            
            print(f"✅ Main product stock addition recorded:")
            print(f"   Product: {product.name} (ID: {product.id})")
            print(f"   Added: {amount} units @ ₱{batch_unit_cost} (Blended AVCO: ₱{product.cost_price})")
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
    if session.get('role') not in ('seller', 'store_admin'):
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
        
        def classify_reduction(reason, notes):
            r = (reason or '').lower()
            n = (notes or '').lower()
            if r == 'pos_sale' or 'pos sale' in n or 'pos order' in n:
                return 'pos'
            if 'online checkout' in n or 'buy now' in n or 'custom order' in n or r == 'sale' or ('order #' in n and 'pos' not in n):
                return 'online'
            if r in ('found_stock', 'receiving_error', 'restock') or 'initial inventory' in n or 'initial stock' in n or 'restocked' in n or 'restored after cancellation' in n:
                return 'addition'
            return 'reduction'

        def resolve_selling_price(reduction, category, default_product, variant=None, addon_opt=None):
            if getattr(reduction, 'unit_price', None) is not None and reduction.unit_price > 0:
                up = float(reduction.unit_price)
                tp = float(reduction.total_price) if getattr(reduction, 'total_price', None) is not None else round(up * reduction.reduction_amount, 2)
                return up, tp

            if category not in ('online', 'pos'):
                return None, None

            notes = reduction.display_reason_notes() or ''
            import re
            m = re.search(r'order\s*#?(\d+)', notes, re.IGNORECASE)
            order_id = int(m.group(1)) if m else None

            if category == 'pos' and order_id:
                from app.models import POSOrderItem
                query = POSOrderItem.query.filter_by(pos_order_id=order_id)
                if reduction.addon_option_id:
                    pos_item = query.filter_by(addon_option_id=reduction.addon_option_id).first()
                elif reduction.variant_id:
                    pos_item = query.filter_by(variant_id=reduction.variant_id).first()
                else:
                    pos_item = query.filter_by(product_id=reduction.product_id).first()
                if pos_item and pos_item.price is not None:
                    up = float(pos_item.price)
                    return up, round(up * reduction.reduction_amount, 2)

            if category == 'online' and order_id:
                if reduction.addon_option_id:
                    from app.models import OrderItemAddon, OrderItem
                    addon_item = OrderItemAddon.query.join(OrderItem).filter(
                        OrderItem.order_id == order_id,
                        OrderItemAddon.addon_option_id == reduction.addon_option_id
                    ).first()
                    if addon_item and addon_item.price is not None:
                        up = float(addon_item.price)
                        return up, round(up * reduction.reduction_amount, 2)
                else:
                    from app.models import OrderItem
                    oi = OrderItem.query.filter_by(
                        order_id=order_id,
                        product_id=reduction.product_id,
                        variant_id=reduction.variant_id
                    ).first()
                    if oi and oi.price is not None:
                        up = float(oi.price)
                        return up, round(up * reduction.reduction_amount, 2)

            if addon_opt and getattr(addon_opt, 'price', None) is not None:
                up = float(addon_opt.price)
            elif variant and getattr(variant, 'price', None) is not None:
                up = float(getattr(variant, 'special_price', None) or variant.price)
            elif default_product:
                up = float(default_product.effective_price)
            else:
                up = None

            if up is not None:
                return up, round(up * reduction.reduction_amount, 2)
            return None, None

        # Build main product reductions data
        main_history = []
        for r in main_reductions:
            notes_str = r.display_reason_notes()
            cat = classify_reduction(r.reason, notes_str)
            unit_p, tot_p = resolve_selling_price(r, cat, product)
            reduction_data = {
                'id': r.id,
                'product_id': r.product_id,
                'product_name': product.name,
                'product_image': primary_image,
                'reduction_amount': r.reduction_amount,
                'unit_cost': float(r.unit_cost) if r.unit_cost is not None else (float(product.cost_price) if product.cost_price is not None else None),
                'total_cost': float(r.total_cost) if r.total_cost is not None else (float(r.unit_cost * r.reduction_amount) if r.unit_cost is not None else None),
                'unit_price': unit_p,
                'total_price': tot_p,
                'reason': r.reason,
                'reason_notes': notes_str,
                'category': cat,
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
            var_cost = float(var.cost_price) if (var and var.cost_price is not None) else None
            unit_c = float(r.unit_cost) if r.unit_cost is not None else var_cost
            tot_c = float(r.total_cost) if r.total_cost is not None else ((unit_c * r.reduction_amount) if unit_c is not None else None)
            notes_str = r.display_reason_notes()
            cat = classify_reduction(r.reason, notes_str)
            unit_p, tot_p = resolve_selling_price(r, cat, product, variant=var)

            if var:
                variant_image = var.image_url  # Get variant's own image
                reduction_data = {
                    'id': r.id,
                    'product_id': r.product_id,
                    'variant_id': var.id,
                    'product_name': f"{product.name} - {var.name}",
                    'product_image': variant_image,  # Use variant image
                    'reduction_amount': r.reduction_amount,
                    'unit_cost': unit_c,
                    'total_cost': tot_c,
                    'unit_price': unit_p,
                    'total_price': tot_p,
                    'reason': r.reason,
                    'reason_notes': notes_str,
                    'category': cat,
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
                    'unit_cost': unit_c,
                    'total_cost': tot_c,
                    'unit_price': unit_p,
                    'total_price': tot_p,
                    'reason': r.reason,
                    'reason_notes': notes_str,
                    'category': cat,
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
            opt_cost = float(opt.cost_price) if (opt and opt.cost_price is not None) else None
            unit_c = float(r.unit_cost) if r.unit_cost is not None else opt_cost
            tot_c = float(r.total_cost) if r.total_cost is not None else ((unit_c * r.reduction_amount) if unit_c is not None else None)
            notes_str = r.display_reason_notes()
            cat = classify_reduction(r.reason, notes_str)
            unit_p, tot_p = resolve_selling_price(r, cat, product, addon_opt=opt)

            if opt:
                group_name = opt.group.name if opt.group else 'Add-on'
                addon_history.append({
                    'id': r.id,
                    'product_id': r.product_id,
                    'addon_option_id': opt.id,
                    'product_name': f"{product.name} — {group_name}: {opt.name}",
                    'product_image': opt.image_url,
                    'reduction_amount': r.reduction_amount,
                    'unit_cost': unit_c,
                    'total_cost': tot_c,
                    'unit_price': unit_p,
                    'total_price': tot_p,
                    'reason': r.reason,
                    'reason_notes': notes_str,
                    'category': cat,
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
                    'unit_cost': unit_c,
                    'total_cost': tot_c,
                    'unit_price': unit_p,
                    'total_price': tot_p,
                    'reason': r.reason,
                    'reason_notes': notes_str,
                    'category': cat,
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
def _parse_to_pht(value):
    if not value:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except Exception:
            return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = pytz.UTC.localize(value)
        return value.astimezone(pytz.timezone('Asia/Manila'))
    return None

@templates_bp.app_template_filter('time_format')
def time_format(value):
    """Format datetime to readable time in PHT"""
    dt = _parse_to_pht(value)
    if not dt:
        return value if isinstance(value, str) else ""
    return dt.strftime('%I:%M %p').lstrip('0')

@templates_bp.app_template_filter('date_format')
def date_format(value):
    """Format datetime to readable date in PHT"""
    dt = _parse_to_pht(value)
    if not dt:
        return value if isinstance(value, str) else ""
    return dt.strftime('%b %d, %Y')

_TITLE_LOWER_WORDS = {
    'a', 'an', 'the',
    'and', 'but', 'or', 'nor', 'for', 'yet', 'so',
    'in', 'on', 'at', 'to', 'from', 'by', 'with', 'of', 'off', 'as', 'into', 'onto', 'upon', 'via', 'vs', 'v.'
}

def _smart_title_format(text):
    if text is None:
        return ''
    if not isinstance(text, str):
        text = str(text)
    text = text.strip()
    if not text:
        return ''

    tokens = re.split(r'(\s+)', text)
    word_indices = [i for i, t in enumerate(tokens) if t and not t.isspace()]
    if not word_indices:
        return text

    first_idx = word_indices[0]
    last_idx = word_indices[-1]

    def cap_word(w):
        if '-' in w:
            parts = w.split('-')
            return '-'.join(cap_word(p) for p in parts)
        m = re.match(r'^([^a-zA-Z0-9]*)(.*?)([^a-zA-Z0-9]*)$', w)
        if not m:
            return w[:1].upper() + w[1:].lower()
        lead, core, trail = m.groups()
        if not core:
            return w
        if "'" in core:
            apos_parts = core.split("'")
            return lead + apos_parts[0][:1].upper() + apos_parts[0][1:].lower() + "'" + apos_parts[1].lower() + trail
        return lead + core[:1].upper() + core[1:].lower() + trail

    result = []
    for i, token in enumerate(tokens):
        if not token or token.isspace():
            result.append(token)
            continue
        
        clean = re.sub(r'[^a-zA-Z0-9]', '', token).lower()
        
        if i == first_idx or i == last_idx:
            result.append(cap_word(token))
        elif clean in _TITLE_LOWER_WORDS:
            m = re.match(r'^([^a-zA-Z0-9]*)(.*?)([^a-zA-Z0-9]*)$', token)
            if m:
                lead, core, trail = m.groups()
                result.append(lead + core.lower() + trail)
            else:
                result.append(token.lower())
        else:
            result.append(cap_word(token))

    return ''.join(result)

@templates_bp.app_template_filter('title_case')
def title_case_filter(value):
    """Format string to smart title case (e.g. 'bouquet of jewelry' -> 'Bouquet of Jewelry')."""
    return _smart_title_format(value)

@templates_bp.app_template_filter('smart_title')
def smart_title_filter(value):
    """Alias for title_case filter."""
    return _smart_title_format(value)


def _seller_orders_sync_token(store_id):
    """Cheap snapshot so the orders table can poll without reloading the page."""
    rows = (
        db.session.query(
            Order.id,
            Order.status,
            Order.payment_status,
            Order.rider_id,
            Order.updated_at,
            Order.payment_proof_url,
        )
        .filter(Order.store_id == store_id)
        .order_by(Order.id.asc())
        .all()
    )
    parts = [
        '%s:%s:%s:%s:%s:%s'
        % (
            r.id,
            r.status or '',
            r.payment_status or '',
            r.rider_id or 0,
            r.updated_at.isoformat() if r.updated_at else '',
            '1' if r.payment_proof_url else '0',
        )
        for r in rows
    ]
    digest = hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()
    return '%s:%s' % (digest, len(rows))


def _load_seller_orders_page_data(store, include_riders=True):
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

    orders_data = [_serialize_seller_order_for_template(order) for order in orders]
    today = datetime.now(PHT).date()
    today_str = today.strftime('%Y-%m-%d')
    order_stats = {
        'total': len(orders_data),
        'today': sum(
            1
            for order in orders
            if order.created_at and _fmt_pht(order.created_at, '%Y-%m-%d') == today_str
        ),
        'pending': sum(1 for order in orders if order.status == 'pending'),
        'payment_review': sum(1 for order in orders if order.payment_status == 'pending_verification' and order.status != 'cancelled'),
        'preparing': sum(1 for order in orders if order.status in ['accepted', 'preparing']),
        'on_delivery': sum(1 for order in orders if order.status == 'on_delivery'),
        'delivered': sum(1 for order in orders if order.status == 'delivered'),
        'completed': sum(1 for order in orders if order.status == 'completed'),
        'cancelled': sum(1 for order in orders if order.status == 'cancelled'),
        'revenue': float(sum(
            float(od.get('display_total') or od.get('total_amount') or 0)
            for od in orders_data
            if od.get('status') in ['delivered', 'completed']
        )),
    }

    payload = {
        'orders': orders_data,
        'store': store.to_dict(),
        'order_stats': order_stats,
        'today_str': today_str,
        'sync_token': _seller_orders_sync_token(store.id),
    }
    if include_riders:
        available_riders = (
            Rider.query
            .options(joinedload(Rider.user))
            .filter_by(store_id=store.id, is_active=True)
            .order_by(Rider.created_at.desc())
            .all()
        )
        payload['available_riders'] = [
            {
                'id': rider.id,
                'name': rider.user.full_name if rider.user else 'Rider',
                'vehicle': rider.vehicle_type,
                'is_active': rider.is_active,
            }
            for rider in available_riders
        ]
    return payload


@templates_bp.route('/seller/orders')
def seller_orders():
    if session.get('role') not in ('seller', 'store_admin'):
        return redirect(url_for('templates.dashboard'))
    _ensure_order_fulfillment_columns()

    def _load_page():
        store = _seller_portal_manageable_store(session['user_id'])
        if not store:
            return None
        return _load_seller_orders_page_data(store, include_riders=True)

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
    from app.utils.phone_bind import attach_order_customer_contact
    return attach_order_customer_contact(order_dict, customer)


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


def _session_notification_inbox_user_id():
    """Store admins share the shop owner's notification inbox."""
    user_id = session.get('user_id')
    if session.get('role') == 'store_admin':
        store = _seller_portal_manageable_store(user_id)
        if store and store.seller_id:
            return store.seller_id
    return user_id


@templates_bp.route('/api/seller/sidebar-badges', methods=['GET'])
def seller_sidebar_badges_api():
    """Live counts for seller sidebar Orders / POS Orders badges."""
    if session.get('role') not in ('seller', 'store_admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    store = _seller_portal_manageable_store(session.get('user_id'))
    orders, pos = _seller_sidebar_badge_counts(store)
    resp = jsonify({'orders': orders, 'pos_orders': pos})
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp, 200


@templates_bp.route('/api/seller/orders/sync', methods=['GET'])
def seller_orders_sync_api():
    """Lightweight fingerprint for live orders table updates."""
    if session.get('role') not in ('seller', 'store_admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    store = _seller_portal_manageable_store(session.get('user_id'))
    if not store:
        return jsonify({'error': 'No active store found'}), 404
    resp = jsonify({'sync_token': _seller_orders_sync_token(store.id)})
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resp, 200


@templates_bp.route('/api/seller/orders', methods=['GET'])
def seller_orders_list_api():
    """Full store orders payload for live table refresh."""
    if session.get('role') not in ('seller', 'store_admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    _ensure_order_fulfillment_columns()
    store = _seller_portal_manageable_store(session.get('user_id'))
    if not store:
        return jsonify({'error': 'No active store found'}), 404
    data = _load_seller_orders_page_data(store, include_riders=False)
    resp = jsonify(data)
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resp, 200


@templates_bp.route('/api/seller/notifications', methods=['GET'])
@templates_bp.route('/api/admin/notifications', methods=['GET'])
@templates_bp.route('/api/notifications', methods=['GET'])
def session_notifications_api():
    if session.get('role') not in ('seller', 'store_admin', 'admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = _session_notification_inbox_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    if session.get('role') in ('seller', 'store_admin'):
        store = _seller_portal_manageable_store(session.get('user_id'))
        if store:
            from app.utils.seller_notifications import clear_store_restocked_notifications
            clear_store_restocked_notifications(store.id)

    def _load_inbox():
        notes = (Notification.query.filter_by(user_id=user_id)
                 .order_by(Notification.created_at.desc()).limit(50).all())
        unread = Notification.query.filter_by(user_id=user_id, is_read=False).count()
        return notes, unread

    try:
        notifications, unread_count = _load_inbox()
    except OperationalError:
        db.session.rollback()
        db.session.remove()
        try:
            db.engine.dispose()
        except Exception:
            pass
        try:
            notifications, unread_count = _load_inbox()
        except OperationalError:
            return jsonify({
                'notifications': [],
                'unread_count': 0,
                'degraded': True,
            }), 200
    return jsonify({
        'notifications': [n.to_dict() for n in notifications],
        'unread_count': unread_count,
    }), 200


@templates_bp.route('/api/seller/notifications/read-all', methods=['POST'])
@templates_bp.route('/api/admin/notifications/read-all', methods=['POST'])
@templates_bp.route('/api/notifications/read-all', methods=['POST'])
def session_notifications_read_all_api():
    if session.get('role') not in ('seller', 'store_admin', 'admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = _session_notification_inbox_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    Notification.query.filter_by(user_id=user_id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True}), 200


@templates_bp.route('/api/seller/notifications/clear-all', methods=['POST', 'DELETE'])
@templates_bp.route('/api/admin/notifications/clear-all', methods=['POST', 'DELETE'])
@templates_bp.route('/api/notifications/clear-all', methods=['POST', 'DELETE'])
def session_notifications_clear_all_api():
    if session.get('role') not in ('seller', 'store_admin', 'admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = _session_notification_inbox_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    if session.get('role') in ('seller', 'store_admin'):
        from app.models import StoreAdmin
        store = _seller_portal_manageable_store(session.get('user_id'))
        if store:
            staff = StoreAdmin.query.filter_by(store_id=store.id, is_active=True, is_archived=False).all()
            target_ids = list({user_id, store.seller_id, *(s.user_id for s in staff if s.user_id)})
            Notification.query.filter(Notification.user_id.in_(target_ids)).delete(synchronize_session=False)
            db.session.commit()
            return jsonify({'success': True}), 200

    Notification.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({'success': True}), 200


@templates_bp.route('/api/seller/notifications/<int:notif_id>', methods=['DELETE'])
@templates_bp.route('/api/admin/notifications/<int:notif_id>', methods=['DELETE'])
@templates_bp.route('/api/notifications/<int:notif_id>', methods=['DELETE'])
def session_notification_delete_api(notif_id):
    if session.get('role') not in ('seller', 'store_admin', 'admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = _session_notification_inbox_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    notif = Notification.query.filter_by(id=notif_id, user_id=user_id).first()
    if notif:
        store = _seller_portal_manageable_store(session.get('user_id')) if session.get('role') in ('seller', 'store_admin') else None
        if store and notif.reference_id and notif.type in ('low_stock', 'out_of_stock', 'new_order'):
            from app.models import StoreAdmin
            staff = StoreAdmin.query.filter_by(store_id=store.id, is_active=True, is_archived=False).all()
            target_ids = list({user_id, store.seller_id, *(s.user_id for s in staff if s.user_id)})
            Notification.query.filter(
                Notification.user_id.in_(target_ids),
                Notification.type == notif.type,
                Notification.reference_id == notif.reference_id,
            ).delete(synchronize_session=False)
        else:
            db.session.delete(notif)
        db.session.commit()
    return jsonify({'success': True}), 200


@templates_bp.route('/api/seller/notifications/<int:notif_id>/read', methods=['POST'])
@templates_bp.route('/api/admin/notifications/<int:notif_id>/read', methods=['POST'])
@templates_bp.route('/api/notifications/<int:notif_id>/read', methods=['POST'])
def session_notification_read_api(notif_id):
    if session.get('role') not in ('seller', 'store_admin', 'admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = _session_notification_inbox_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    notif = Notification.query.filter_by(id=notif_id, user_id=user_id).first()
    if notif:
        notif.is_read = True
        db.session.commit()
    return jsonify({'success': True}), 200


@templates_bp.route('/api/seller/orders/<int:order_id>', methods=['GET'])
def seller_order_details_api(order_id):
    if session.get('role') not in ('seller', 'store_admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    _ensure_order_fulfillment_columns()

    store = _seller_portal_manageable_store(session['user_id'])
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
    if session.get('role') not in ('seller', 'store_admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    if not _ensure_order_fulfillment_columns():
        return jsonify({'error': 'Order fulfillment columns are not ready yet. Please refresh and try again.'}), 503
    store = _seller_portal_manageable_store(session['user_id'])
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
    allowed_statuses = {'pending', 'accepted', 'preparing', 'done_preparing', 'on_delivery', 'delivered', 'completed', 'cancelled'}

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
    if previous_status == 'cancelled' and new_status != 'cancelled':
        return jsonify({'error': 'This order has already been cancelled and cannot change status.'}), 400

    if new_status == 'cancelled' and previous_status != 'cancelled':
        # Ensure add-on rows are loaded before stock restore / history audit
        _ = [(item.addons, item.product, item.variant) for item in (order.items or [])]
        order.restore_stock_on_cancel(session['user_id'])
        order.cancelled_at = datetime.utcnow()
        order.cancellation_reason_code = f"seller_cancelled_{(order.payment_method or '').lower()}"
        order.cancellation_reason = data.get('reason') or 'Cancelled by seller'
        order.payment_status = 'cancelled'

    order.set_status(new_status)
    if new_status == 'completed' and getattr(order, 'fulfillment_type', '') == 'pickup' and order.payment_status in ('cop_pending', 'cop_approved', 'pending'):
        order.payment_status = 'paid'
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Order status updated',
        'order': _serialize_seller_order_for_template(order)
    }), 200


@templates_bp.route('/api/seller/orders/<int:order_id>/verify-payment', methods=['PUT'])
def seller_order_verify_payment_api(order_id):
    if session.get('role') not in ('seller', 'store_admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    store = _seller_portal_manageable_store(session['user_id'])
    if not store:
        return jsonify({'error': 'No active store found'}), 404

    order = Order.query.filter_by(id=order_id, store_id=store.id).first()
    if not order:
        return jsonify({'error': 'Order not found'}), 404

    if order.status == 'cancelled':
        return jsonify({'error': 'Cannot verify payment for a cancelled order.'}), 400
    if order.status in ('delivered', 'completed'):
        return jsonify({'error': f'Order is already {order.status}.'}), 400

    payment_status = (order.payment_status or '').lower()
    pay_method = (order.payment_method or '').lower()
    # Some older custom quotes were saved as `verified` rather than
    # `cod_pending`. The payment method is authoritative for COD/COP approval.
    if pay_method in ('cod', 'cop'):
        # COD / COP approval flow: no receipt required, seller confirms and moves to preparing.
        order.payment_status = 'cop_approved' if pay_method == 'cop' else 'cod_approved'
        order.set_status('preparing')
    else:
        if not order.payment_proof_url:
            return jsonify({'error': 'No payment proof uploaded'}), 400
        # GCash verification flow (also supports legacy custom quotes whose
        # receipt status was saved as `paid`).
        order.payment_status = 'verified'
        order.set_status('preparing')
    db.session.commit()

    current_app.logger.info(f"Order #{order_id} payment/{pay_method.upper()} approved, status changed to preparing")

    return jsonify({
        'success': True,
        'message': f'Order approved ({pay_method.upper() if pay_method in ("cod", "cop") else "Payment"}). Status changed to Preparing.',
        'order': _serialize_seller_order_for_template(order)
    }), 200


@templates_bp.route('/api/seller/orders/<int:order_id>/update-status', methods=['PUT'])
def seller_order_update_status(order_id):
    """Update order status (e.g., accepted → preparing)"""
    if session.get('role') not in ('seller', 'store_admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request'}), 400

    new_status = data.get('status', '').strip()
    valid_statuses = ['preparing', 'on_delivery', 'delivered', 'completed', 'cancelled']
    
    if new_status not in valid_statuses:
        return jsonify({'error': 'Invalid status'}), 400

    store = _seller_portal_manageable_store(session['user_id'])
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
    if new_status == 'completed' and getattr(order, 'fulfillment_type', '') == 'pickup' and order.payment_status in ('cop_pending', 'cop_approved', 'pending'):
        order.payment_status = 'paid'
    db.session.commit()

    current_app.logger.info(f"Order #{order_id} status updated: {current_status} → {new_status}")

    return jsonify({
        'success': True,
        'message': f'Order status updated to {new_status.replace("_", " ").title()}',
        'order': _serialize_seller_order_for_template(order)
    }), 200

@templates_bp.route('/seller/riders')
def seller_riders():
    if session.get('role') not in ('seller', 'store_admin'):
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
    if session.get('role') not in ('seller', 'store_admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    store = _seller_portal_manageable_store(session['user_id'])
    if not store:
        return jsonify({'error': 'No active store found'}), 404

    riders = Rider.query.filter_by(store_id=store.id).all()

    riders_data = []
    for rider in riders:
        rider_dict = rider.to_dict()
        total_deliveries = Order.query.filter(
            Order.rider_id == rider.id,
            Order.status.in_(['delivered', 'completed'])
        ).count()
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
    if session.get('role') not in ('seller', 'store_admin'):
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
    from app.utils.validators import normalize_ph_license_plate

    plate, plate_err = normalize_ph_license_plate(license_plate)
    if plate_err:
        return jsonify({'error': plate_err}), 400
    license_plate = plate

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
    if session.get('role') not in ('seller', 'store_admin'):
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
    if session.get('role') not in ('seller', 'store_admin'):
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
    if session.get('role') not in ('seller', 'store_admin'):
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
    if session.get('role') not in ('seller', 'store_admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    store = _seller_portal_manageable_store(session['user_id'])
    if not store:
        return jsonify({'error': 'No active store found'}), 404

    rider = Rider.query.filter_by(id=rider_id, store_id=store.id).first()
    if not rider:
        return jsonify({'error': 'Rider not found'}), 404

    rider_dict = rider.to_dict()
    total_deliveries = Order.query.filter(
        Order.rider_id == rider.id,
        Order.status.in_(['delivered', 'completed'])
    ).count()
    recent_orders = Order.query.filter_by(rider_id=rider.id).order_by(Order.created_at.desc()).limit(10).all()

    rider_dict['total_deliveries'] = total_deliveries
    rider_dict['recent_orders'] = [o.to_dict() for o in recent_orders]

    return jsonify({'success': True, 'rider': rider_dict}), 200


@templates_bp.route('/api/seller/riders/<int:rider_id>', methods=['PUT'])
def seller_update_rider_api(rider_id):
    if session.get('role') not in ('seller', 'store_admin'):
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
        from app.utils.validators import normalize_ph_license_plate
        plate, plate_err = normalize_ph_license_plate(data.get('license_plate'))
        if plate_err:
            return jsonify({'error': plate_err}), 400
        rider.license_plate = plate
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
    if session.get('role') not in ('seller', 'store_admin'):
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
    if session.get('role') not in ('seller', 'store_admin'):
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
    if session.get('role') not in ('seller', 'store_admin'):
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

    def _pos_variant_sellable(v):
        if not v:
            return False
        return (v.get('stock_quantity') or 0) > 0 and v.get('is_available') is not False

    def _pos_product_sellable(p):
        if p.get('is_available') is False:
            return False
        if (p.get('stock_quantity') or 0) > 0:
            return True
        return any(_pos_variant_sellable(v) for v in (p.get('variants') or []))

    for p in products:
        variants = p.get('variants') or []
        if variants:
            p['variants'] = sorted(
                variants,
                key=lambda v: (
                    0 if _pos_variant_sellable(v) else 1,
                    v.get('sort_order') or 0,
                    (v.get('name') or '').lower(),
                ),
            )

    cat_rank = {c.id: (c.sort_order or 0) for c in main_categories}
    products.sort(key=lambda p: (
        0 if _pos_product_sellable(p) else 1,
        cat_rank.get(p.get('main_category_id'), 999),
        (p.get('name') or '').lower(),
    ))

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

    # Familiar customers (ONLY customers who actually bought from this store, online or in-store)
    familiar_customers = []
    seen_cust_names = set()
    try:
        from app.models import Order
        online_rows = (
            db.session.query(User.full_name, User.phone)
            .join(Order, Order.customer_id == User.id)
            .filter(
                Order.store_id == store.id,
                Order.status != 'cancelled',
                User.full_name.isnot(None),
                User.full_name != ''
            )
            .distinct()
            .all()
        )
        for u_name, u_phone in online_rows:
            name = (u_name or '').strip()
            clean = name.lower()
            if name and clean not in seen_cust_names and not clean.startswith('deleted'):
                seen_cust_names.add(clean)
                familiar_customers.append({
                    'name': name,
                    'phone': (u_phone or '').strip(),
                    'type': 'Online'
                })
    except Exception as e:
        current_app.logger.warning(f"Error fetching online buyers for POS: {e}")

    try:
        from app.models import POSOrder
        pos_cust_rows = (
            db.session.query(POSOrder.customer_name, POSOrder.customer_contact)
            .filter(
                POSOrder.store_id == store.id,
                POSOrder.customer_name.isnot(None),
                POSOrder.customer_name != ''
            )
            .order_by(POSOrder.created_at.desc())
            .limit(150)
            .all()
        )
        for c_name, c_contact in pos_cust_rows:
            name = (c_name or '').strip()
            clean = name.lower()
            if not name or clean.startswith('walk') or clean.startswith('deleted'):
                continue
            phone = (c_contact or '').strip()
            if clean not in seen_cust_names:
                seen_cust_names.add(clean)
                familiar_customers.append({
                    'name': name,
                    'phone': phone,
                    'type': 'In-Store'
                })
            elif phone:
                for item in familiar_customers:
                    if item['name'].lower() == clean and not item.get('phone'):
                        item['phone'] = phone
                        break
    except Exception as e:
        current_app.logger.warning(f"Error fetching POS customers: {e}")

    familiar_customers.sort(key=lambda c: c['name'].lower())

    return render_template(
        'seller_pos.html',
        store=store,
        products=products,
        main_categories=main_categories,
        store_categories=store_categories,
        products_by_category=products_by_category,
        subcategories_by_main=subcategories_by_main,
        ymal_addon_options=ymal_addon_options,
        familiar_customers=familiar_customers,
    )

def get_store_pos_prefix(store):
    """3-letter uppercase prefix based on the store name (e.g. AKS, PRI, SPE)."""
    if not store or not store.name:
        return 'POS'
    import re
    clean = re.sub(r'[^A-Za-z0-9]', '', store.name).upper()
    return clean[:3] if len(clean) >= 3 else (clean + 'POS')[:3]


def get_next_pos_order_number(store_id):
    """Calculate the next sequential order number for a store (e.g. AKS-0089)."""
    store = Store.query.get(store_id)
    prefix = get_store_pos_prefix(store)
    existing = db.session.query(POSOrder.order_number).filter(
        POSOrder.store_id == store_id,
        POSOrder.order_number.like(f"{prefix}-%")
    ).all()
    max_seq = 0
    for (num_str,) in existing:
        if num_str:
            parts = num_str.split('-')
            if len(parts) >= 2 and parts[-1].isdigit():
                try:
                    seq = int(parts[-1])
                    if seq > max_seq:
                        max_seq = seq
                except ValueError:
                    pass
    return f"{prefix}-{max_seq + 1:04d}"


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
    cashier = User.query.get(user_id) if user_id else None
    cashier_name = (cashier.full_name if cashier else None) or 'Staff'
    
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Invalid JSON payload.'}), 400

    items_payload = data.get('items', [])
    if not items_payload:
        return jsonify({'error': 'Order must contain at least one item.'}), 400

    # ── Custom order & Dedication info ─────────────────────────────────────────
    is_custom_order = bool(data.get('is_custom_order'))
    dedication_to = (data.get('dedication_to') or '').strip() or None
    dedication_from = (data.get('dedication_from') or '').strip() or None
    dedication_message = (data.get('dedication_message') or '').strip() or None
    florist_notes = (data.get('florist_notes') or '').strip() or None

    # ── Validate every item before touching the DB ────────────────────────────
    from app.addon_helpers import (
        resolve_structured_addon_selections,
        structured_addons_subtotal,
        decrement_addon_option_stock,
    )
    from app.models import ProductAddonOption

    validated_items = []
    for entry in items_payload:
        is_custom_line = bool(entry.get('is_custom'))
        quantity   = int(entry.get('quantity', 1))
        unit_price = Decimal(str(entry.get('price', 0)))
        addon_raw  = entry.get('addons') or entry.get('addon_option_ids') or []

        if quantity < 1:
            return jsonify({'error': 'Quantity must be at least 1.'}), 400

        if is_custom_line:
            is_custom_order = True
            custom_title = (entry.get('custom_title') or entry.get('name') or 'Custom Arrangement').strip()
            custom_inclusions = (entry.get('custom_inclusions') or entry.get('inclusions') or '').strip() or None
            custom_category = (entry.get('custom_category') or entry.get('category') or 'bouquets').strip()
            labor_cost = Decimal(str(entry.get('labor_cost') or 0))

            if labor_cost > 0:
                labor_note = f"Labor/Assembly: ₱{labor_cost:.2f}"
                if custom_inclusions:
                    if "Labor/Assembly" not in custom_inclusions:
                        custom_inclusions = f"{custom_inclusions} | {labor_note}"
                else:
                    custom_inclusions = labor_note

            if unit_price < 0:
                return jsonify({'error': 'Custom arrangement price cannot be negative.'}), 400

            # Resolve add-ons if chosen under custom arrangement
            addon_lines = []
            if addon_raw:
                for a in addon_raw:
                    opt_id = a.get('addon_option_id') or a.get('option_id')
                    if opt_id:
                        opt = ProductAddonOption.query.get(opt_id)
                        if opt:
                            opt_qty = int(a.get('quantity') or a.get('qty') or 1) * quantity
                            stock_qty = opt.stock_quantity or 0
                            if stock_qty < opt_qty and opt.is_available is not False:
                                return jsonify({
                                    'error': f'Insufficient stock for add-on "{opt.name}". Available: {stock_qty}, requested: {opt_qty}.'
                                }), 400
                            addon_lines.append({
                                'option': opt,
                                'name': opt.name,
                                'price': Decimal(str(opt.price or 0)),
                                'quantity': opt_qty,
                                'image_url': opt.image_url,
                            })

            validated_items.append({
                'is_custom': True,
                'custom_title': custom_title,
                'custom_inclusions': custom_inclusions,
                'custom_category': custom_category,
                'product': None,
                'variant_id': None,
                'quantity': quantity,
                'price': unit_price,
                'addon_lines': addon_lines,
                'addons_only': False,
            })
            continue

        product_id = entry.get('product_id') or entry.get('id')
        variant_id = entry.get('variant_id')  # May be None

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
            'is_custom': False,
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

    # Generate store-specific sequential order number
    order_number = get_next_pos_order_number(store.id)

    # Create the order with discount & custom metadata
    pos_order = POSOrder(
        store_id=store.id,
        order_number=order_number,
        total_amount=total,
        amount_given=amount_given,
        change_amount=change_amount,
        payment_method=payment_method,
        customer_name=customer_name,
        customer_contact=customer_contact,
        is_seen_by_seller=False,
        is_custom_order=is_custom_order,
        dedication_to=dedication_to,
        dedication_from=dedication_from,
        dedication_message=dedication_message,
        florist_notes=florist_notes,
        discount=discount,
        created_by=user_id,
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
            addon_lines = item.get('addon_lines') or []

            if item.get('is_custom'):
                # Custom bespoke arrangement line
                custom_title = item.get('custom_title') or 'Custom Arrangement'
                addon_names = [str(l.get('name') or '').strip() for l in addon_lines if l.get('name')]
                addon_names = [n for n in addon_names if n]
                if addon_names:
                    line_name = f"{custom_title} (+ {', '.join(addon_names)})"
                else:
                    line_name = custom_title

                pos_item = POSOrderItem(
                    pos_order=pos_order,
                    product_id=None,
                    variant_id=None,
                    quantity=item['quantity'],
                    price=item['price'] + extra_per_unit,
                    cost_price=Decimal(str(round(float(item['price']) * 0.60, 2))),
                    line_name=line_name,
                    line_image_url=None,
                    addon_option_id=None,
                    is_custom=True,
                    custom_title=custom_title,
                    custom_inclusions=item.get('custom_inclusions'),
                    custom_category=item.get('custom_category'),
                )
                db.session.add(pos_item)

                # Decrement add-on options stock if any
                if addon_lines:
                    decrement_addon_option_stock(
                        addon_lines,
                        user_id=user_id,
                        reason='pos_sale',
                        reason_notes=f'POS Custom Sale add-on - Order #{pos_order.id} by {cashier_name}',
                    )
                continue

            product_id_for_row = item['product'].id
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
                addon_cost = 0.0
                if addon_option_id:
                    opt_obj = ProductAddonOption.query.get(addon_option_id)
                    if opt_obj and opt_obj.cost_price is not None:
                        addon_cost = float(opt_obj.cost_price)
                    else:
                        addon_cost = round(float(unit_price) * 0.60, 2)
                else:
                    addon_cost = round(float(unit_price) * 0.60, 2)
                item_unit_cost = addon_cost
                base_stock_cost = addon_cost
            else:
                # Flower/variant line: bake structured add-on cost into unit price for history totals
                unit_price = item['price'] + extra_per_unit
                if item.get('variant_id'):
                    v_obj = ProductVariant.query.get(item['variant_id'])
                    base_stock_cost = float(v_obj.cost_price if (v_obj and v_obj.cost_price is not None) else (item['product'].cost_price or round(float(unit_price) * 0.60, 2)))
                else:
                    base_stock_cost = float(item['product'].cost_price if item['product'].cost_price is not None else round(float(unit_price) * 0.60, 2))
                
                addon_lines_cost = 0.0
                for al in addon_lines:
                    al_opt = al.get('option')
                    if al_opt and getattr(al_opt, 'cost_price', None) is not None:
                        addon_lines_cost += float(al_opt.cost_price)
                    else:
                        addon_lines_cost += round(float(al.get('price') or 0) * 0.60, 2)
                extra_cost_per_unit = (addon_lines_cost / float(qty)) if qty else 0.0
                item_unit_cost = round(base_stock_cost + extra_cost_per_unit, 2)

            pos_item = POSOrderItem(
                pos_order=pos_order,
                product_id=product_id_for_row,
                variant_id=item['variant_id'],
                quantity=item['quantity'],
                price=unit_price,
                cost_price=Decimal(str(item_unit_cost)),
                line_name=line_name,
                line_image_url=line_image_url,
                addon_option_id=addon_option_id,
                is_custom=False,
            )
            db.session.add(pos_item)

            # Update stock based on variant or product (skip for add-on-only lines)
            if not item.get('addons_only'):
                if item['variant_id']:
                    variant = ProductVariant.query.get(item['variant_id'])
                    stock_before = int(variant.stock_quantity or 0)
                    variant.stock_quantity -= item['quantity']
                    stock_after = int(variant.stock_quantity or 0)
                    
                    # Create StockReduction record for variant
                    stock_reduction = StockReduction(
                        product_id=item['product'].id,
                        variant_id=item['variant_id'],
                        reduction_amount=item['quantity'],
                        unit_cost=base_stock_cost,
                        total_cost=round(base_stock_cost * item['quantity'], 2),
                        unit_price=float(unit_price),
                        total_price=round(float(unit_price) * item['quantity'], 2),
                        reason='pos_sale',
                        reason_notes=f'POS Sale - Order #{pos_order.id} by {cashier_name}',
                        reduced_by=user_id
                    )
                    db.session.add(stock_reduction)
                    notify_low_stock_if_crossed(
                        store_id=store.id,
                        product=item['product'],
                        stock_before=stock_before,
                        stock_after=stock_after,
                        variant=variant,
                    )
                else:
                    stock_before = int(item['product'].stock_quantity or 0)
                    item['product'].stock_quantity -= item['quantity']
                    stock_after = int(item['product'].stock_quantity or 0)
                    
                    # Create StockReduction record for main product
                    stock_reduction = StockReduction(
                        product_id=item['product'].id,
                        variant_id=None,
                        reduction_amount=item['quantity'],
                        unit_cost=base_stock_cost,
                        total_cost=round(base_stock_cost * item['quantity'], 2),
                        unit_price=float(unit_price),
                        total_price=round(float(unit_price) * item['quantity'], 2),
                        reason='pos_sale',
                        reason_notes=f'POS Sale - Order #{pos_order.id} by {cashier_name}',
                        reduced_by=user_id
                    )
                    db.session.add(stock_reduction)
                    notify_low_stock_if_crossed(
                        store_id=store.id,
                        product=item['product'],
                        stock_before=stock_before,
                        stock_after=stock_after,
                    )

            # Structured add-ons: include cost in order total (already) and decrement stock
            if item.get('addon_lines'):
                decrement_addon_option_stock(
                    item['addon_lines'],
                    user_id=user_id,
                    reason='pos_sale',
                    reason_notes=f'POS Sale add-on - Order #{pos_order.id} by {cashier_name}',
                )

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error creating POS order: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to process order: {str(e)}'}), 500

    # Collect latest stock levels for all products, variants, and addons updated by this order
    updated_stocks = {
        'products': {},
        'variants': {},
        'addons': {}
    }
    for item in validated_items:
        prod = item.get('product')
        if prod:
            updated_stocks['products'][str(prod.id)] = {
                'id': prod.id,
                'stock_quantity': int(prod.stock_quantity or 0),
                'is_available': bool(prod.is_available),
            }
        var_id = item.get('variant_id')
        if var_id:
            v_rec = ProductVariant.query.get(var_id)
            if v_rec:
                updated_stocks['variants'][str(v_rec.id)] = {
                    'id': v_rec.id,
                    'product_id': v_rec.product_id,
                    'stock_quantity': int(v_rec.stock_quantity or 0),
                    'is_available': bool(v_rec.is_available),
                }
        for al in item.get('addon_lines', []):
            al_opt = al.get('option')
            if al_opt:
                updated_stocks['addons'][str(al_opt.id)] = {
                    'id': al_opt.id,
                    'stock_quantity': int(al_opt.stock_quantity or 0),
                    'is_available': bool(al_opt.is_available),
                }

    return jsonify({
        'success': True,
        'pos_order_id': pos_order.id,
        'order_number': pos_order.order_number,
        'updated_stocks': updated_stocks,
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
    next_order_number = get_next_pos_order_number(store.id)
    
    return jsonify({
        'next_id': next_id,
        'next_order_number': next_order_number
    })


@templates_bp.route('/api/seller/pos/customers')
@seller_required
def pos_search_customers():
    store = _get_seller_store()
    if not store:
        return jsonify({'error': 'No active store found'}), 403
    q = (request.args.get('q') or '').strip().lower()

    customers = []
    seen = set()
    try:
        from app.models import Order
        query = (
            db.session.query(User.full_name, User.phone)
            .join(Order, Order.customer_id == User.id)
            .filter(
                Order.store_id == store.id,
                Order.status != 'cancelled',
                User.full_name.isnot(None),
                User.full_name != ''
            )
        )
        if q:
            query = query.filter(User.full_name.ilike(f'%{q}%'))
        for u_name, u_phone in query.distinct().limit(30).all():
            name = (u_name or '').strip()
            clean = name.lower()
            if name and clean not in seen and not clean.startswith('deleted'):
                seen.add(clean)
                customers.append({
                    'name': name,
                    'phone': (u_phone or '').strip(),
                    'type': 'Online'
                })
    except Exception as e:
        current_app.logger.warning(f"Error searching online customers: {e}")

    try:
        from app.models import POSOrder
        query = db.session.query(POSOrder.customer_name, POSOrder.customer_contact).filter(
            POSOrder.store_id == store.id,
            POSOrder.customer_name.isnot(None),
            POSOrder.customer_name != ''
        )
        if q:
            query = query.filter(POSOrder.customer_name.ilike(f'%{q}%'))
        for c_name, c_contact in query.order_by(POSOrder.created_at.desc()).limit(50).all():
            name = (c_name or '').strip()
            clean = name.lower()
            if not name or clean.startswith('walk') or clean.startswith('deleted'):
                continue
            phone = (c_contact or '').strip()
            if clean not in seen:
                seen.add(clean)
                customers.append({
                    'name': name,
                    'phone': phone,
                    'type': 'In-Store'
                })
            elif phone:
                for item in customers:
                    if item['name'].lower() == clean and not item.get('phone'):
                        item['phone'] = phone
                        break
    except Exception as e:
        current_app.logger.warning(f"Error searching POS customers: {e}")

    customers.sort(key=lambda c: c['name'].lower())
    return jsonify({'customers': customers})


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
        'cash_orders': POSOrder.query.filter(POSOrder.store_id == store.id, db.func.lower(POSOrder.payment_method) == 'cash').count(),
        'gcash_orders': POSOrder.query.filter(POSOrder.store_id == store.id, db.func.lower(POSOrder.payment_method) == 'gcash').count(),
        'card_orders': POSOrder.query.filter(POSOrder.store_id == store.id, db.func.lower(POSOrder.payment_method) == 'card').count(),
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
                clear_resolved_stock_notifications(
                    product_id=variant.product_id,
                    current_stock=variant.stock_quantity,
                    store_id=store.id,
                )
        else:
            product = Product.query.get(item.product_id)
            if product:
                product.stock_quantity += item.quantity
                clear_resolved_stock_notifications(
                    product_id=product.id,
                    current_stock=product.stock_quantity,
                    store_id=store.id,
                )
    
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
    from app.utils.report_service import pht_sql_date, period_range
    import pytz
    today_pht = datetime.now(pytz.timezone('Asia/Manila')).date()
    start_pht = today_pht - timedelta(days=max(days - 1, 0))
    range_start, range_end, _ = period_range(
        'custom',
        custom_from=start_pht.isoformat(),
        custom_to=today_pht.isoformat(),
    )
    ph_date = pht_sql_date(POSOrder.created_at)

    daily_sales = db.session.query(
        ph_date.label('date'),
        db.func.count(POSOrder.id).label('order_count'),
        db.func.sum(POSOrder.total_amount).label('revenue')
    ).filter(
        POSOrder.store_id == store.id,
        POSOrder.created_at >= range_start,
        POSOrder.created_at < range_end,
    ).group_by(
        ph_date
    ).order_by(
        ph_date
    ).all()

    payment_breakdown = db.session.query(
        func.lower(POSOrder.payment_method).label('payment_method'),
        db.func.count(POSOrder.id).label('count'),
        db.func.sum(POSOrder.total_amount).label('total')
    ).filter(
        POSOrder.store_id == store.id,
        POSOrder.created_at >= range_start,
        POSOrder.created_at < range_end,
    ).group_by(
        func.lower(POSOrder.payment_method)
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
        POSOrder.created_at >= range_start,
        POSOrder.created_at < range_end,
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


def _report_requester_name():
    """Real name of the logged-in user generating a report."""
    requester = User.query.get(session.get('user_id')) if session.get('user_id') else None
    if requester:
        name = (requester.full_name or '').strip()
        if name:
            return name
        email = (requester.email or '').strip()
        if email:
            return email
    session_name = (session.get('user_name') or '').strip()
    if session_name:
        return session_name
    return 'Unknown user'


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
            forecasting={
                'revenue': {
                    'labels': [], 'values': [], 'lower': [], 'upper': [],
                    'method': 'simple_exponential', 'method_label': 'Collecting data',
                    'projected_total': 0, 'growth_rate_pct': None,
                    'peak_projected_day': None, 'is_insufficient_data': True, 'metrics': {},
                },
                'demand': {
                    'labels': [], 'values': [], 'lower': [], 'upper': [],
                    'method': 'simple_exponential', 'method_label': 'Collecting data',
                    'projected_total': 0, 'growth_rate_pct': None,
                    'peak_projected_day': None, 'is_insufficient_data': True, 'metrics': {},
                },
                'history': {'labels': [], 'revenue': [], 'orders': []},
                'products': [],
                'is_insufficient_data': True,
            },
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
        'forecasting': ctx.get('forecasting'),
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

    payload['requested_by'] = _report_requester_name()
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
        'generated_at': payload.get('generated_at') or datetime.now(PHT).strftime('%b %d, %Y %I:%M %p PHT'),
        'types': payload['types'],
        'sections': [{
            'key': s['key'],
            'title': s['title'],
            'columns': s['columns'],
            'rows': [[
                f"{float(c):.2f}" if isinstance(c, (float, Decimal)) and not isinstance(c, bool)
                else c
                for c in r
            ] for r in s['rows']],
            'summary': [list(t) for t in s['summary']],
            'row_count': len(s['rows']),
            'pos_title': s.get('pos_title'),
            'pos_columns': s.get('pos_columns'),
            'pos_rows': [[
                f"{float(c):.2f}" if isinstance(c, (float, Decimal)) and not isinstance(c, bool)
                else c
                for c in r
            ] for r in (s.get('pos_rows') or [])] if s.get('pos_rows') is not None else None,
            'pos_row_count': len(s.get('pos_rows') or []) if s.get('pos_rows') is not None else None,
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

    from app.utils.report_service import apply_php_sort, render_pdf, render_csv_bundle

    php_sort = (
        request.values.get('php_sort')
        or (request.get_json(silent=True) or {}).get('php_sort')
        or 'original'
    )

    if session.get('role') == 'admin':
        from app.utils.report_service import build_admin_report_payload
        payload = build_admin_report_payload(raw_types, period=period, custom_from=fr, custom_to=to)
    else:
        store = _resolve_report_store()
        if not store:
            return jsonify({'error': 'No store found for this seller'}), 404
        from app.utils.report_service import build_report_payload
        payload = build_report_payload(store, raw_types, period=period, custom_from=fr, custom_to=to)

    apply_php_sort(payload, php_sort)
    payload['requested_by'] = _report_requester_name()
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
    response.heade
... [truncated for diff preview]