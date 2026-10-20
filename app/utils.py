import os
import uuid
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from app.models import User

def allowed_file(filename, allowed_extensions):
    """
    Check if file extension is allowed
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def save_uploaded_file(file, upload_folder, prefix=''):
    """
    Save uploaded file with unique filename
    """
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)
    
    # Generate unique filename
    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f"{prefix}_{uuid.uuid4().hex}.{ext}"
    file_path = os.path.join(upload_folder, filename)
    
    file.save(file_path)
    return filename, file_path

def role_required(*roles):
    """
    Decorator to require specific role(s)
    """
    def wrapper(fn):
        @wraps(fn)
        def decorator(*args, **kwargs):
            verify_jwt_in_request()
            user_id = get_jwt_identity()
            user = User.query.get(user_id)
            
            if not user or user.role not in roles:
                return jsonify({'error': 'Insufficient permissions'}), 403
            
            return fn(*args, **kwargs)
        return decorator
    return wrapper

def paginate_query(query, page=1, per_page=20):
    """
    Paginate SQLAlchemy query
    """
    page = max(1, page)
    per_page = min(max(1, per_page), 100)  # Limit to 100 per page
    
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return {
        'items': [item.to_dict() for item in paginated.items],
        'total': paginated.total,
        'page': paginated.page,
        'per_page': paginated.per_page,
        'pages': paginated.pages
    }

def format_currency(amount):
    """
    Format amount as currency
    """
    return f"₱{amount:,.2f}"

def validate_email(email):
    """
    Simple email validation
    """
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def get_date_range(period='month'):
    """
    Get date range for given period
    """
    today = datetime.utcnow().date()
    
    if period == 'today':
        start_date = today
        end_date = today
    elif period == 'week':
        start_date = today - timedelta(days=7)
        end_date = today
    elif period == 'month':
        start_date = today - timedelta(days=30)
        end_date = today
    elif period == 'year':
        start_date = today - timedelta(days=365)
        end_date = today
    else:
        start_date = today - timedelta(days=30)
        end_date = today
    
    return start_date, end_date


def get_realistic_margin_rate(product_name='', category_path='', item_id=None):
    """
    Determine a realistic market gross margin percentage for a flower, plant, or garden product.
    Returns a float between 0.20 and 0.80 (e.g., 0.62 for 62% margin).
    """
    p_name = (product_name or '').lower()
    cat = (category_path or '').lower()

    # Deterministic organic variation (+/- 3%) based on item ID if provided
    var_pct = (((item_id or 1) * 17) % 7 - 3) * 0.01 if item_id else 0.0

    if any(k in p_name for k in ['money', 'ribbon', 'satin', 'artificial', 'handmade', 'shiny violet', 'crochet']) or \
       'money' in cat or 'artificial' in cat:
        base = 0.70
    elif any(k in p_name for k in ['soil', 'fertilizer', 'yaramila', 'yaravera', 'insecticide', 'cymbush', 'chemical', 'seedling tray', 'balde', 'floral foam']) or \
         any(k in cat for k in ['fertilizer', 'seedling', 'balde']):
        base = 0.26
    elif any(k in p_name for k in ['pot', 'wallpot', 'planter', 'robol', 'udalo']) or 'pots' in cat:
        base = 0.35
    elif any(k in p_name for k in ['wire', 'sprayer', 'pruning', 'shear']) or 'tools' in cat:
        base = 0.38
    elif any(k in p_name for k in ['candle', 'esperma', 'scented']) or 'candle' in cat:
        base = 0.42
    elif any(k in p_name for k in ['bonsai', 'fukienta', 'fig', 'poinsettia', 'swiss cheese', 'monstera', 'calathea', 'ficus', 'potted', 'plant']) or \
         'potted' in cat or 'bonsai' in cat:
        base = 0.52
    elif any(k in p_name for k in ['standee', 'wedding package', 'sympathy standee']) or \
         ('sympathy' in cat and 'standee' in p_name):
        base = 0.54
    elif any(k in p_name for k in ['arrangement', 'tambilina', 'basket']) or 'arrangement' in cat:
        base = 0.58
    elif ('fresh flowers' in cat or any(k in p_name for k in ['bundle', '1pc', 'stem', 'radus', 'aster', 'mum', 'rose'])) and 'bouquet' not in p_name:
        base = 0.50
    elif 'bouquet' in p_name or 'bouquet' in cat or 'valentines' in cat:
        base = 0.62
    else:
        base = 0.50

    return max(0.20, min(0.80, base + var_pct))


def calculate_realistic_cost(price, margin_rate=None, product_name='', category_path='', item_id=None):
    """
    Calculate a realistic wholesale / capital cost price based on retail price and product category.
    Rounds to clean commercial price points (e.g. nearest ₱0.50, ₱1, ₱5, or ₱50).
    """
    try:
        p = float(price or 0.0)
    except (ValueError, TypeError):
        return 0.0
    if p <= 0:
        return 0.0

    if margin_rate is None:
        margin_rate = get_realistic_margin_rate(product_name, category_path, item_id)

    raw_cost = p * (1.0 - margin_rate)
    if p < 50:
        cost = round(raw_cost * 2) / 2
    elif p < 250:
        cost = round(raw_cost)
    elif p < 1000:
        cost = round(raw_cost / 5.0) * 5.0
    else:
        cost = round(raw_cost / 50.0) * 50.0

    if cost >= p:
        cost = round(p * 0.85, 2)
    elif cost <= 0:
        cost = round(p * 0.30, 2)
    return round(cost, 2)