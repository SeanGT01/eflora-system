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