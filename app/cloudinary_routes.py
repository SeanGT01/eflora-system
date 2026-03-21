# app/cloudinary_routes.py
from flask import Blueprint, request, jsonify, current_app, session
from app.utils.cloudinary_helper import (
    upload_to_cloudinary, 
    delete_from_cloudinary, 
    should_use_cloudinary,
    upload_avatar,
    upload_product_image,
    upload_variant_image,
    upload_gcash_qr,
    upload_seller_document,
    upload_payment_proof
)
from app.extensions import db
from app.models import User, Product, ProductImage, ProductVariant, Store, GCashQR, Order, SellerApplication
from functools import wraps
import os
from werkzeug.utils import secure_filename
import time
import uuid

cloudinary_bp = Blueprint('cloudinary', __name__)

# Custom decorator for session-based authentication
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function

# Allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@cloudinary_bp.route('/upload', methods=['POST'])
@login_required
def upload_image():
    """Generic image upload endpoint"""
    if not should_use_cloudinary():
        return jsonify({'success': False, 'error': 'Cloudinary not configured'}), 400
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'File type not allowed'}), 400
    
    # Get folder from request or use default
    folder = request.form.get('folder', 'e-flowers/uploads')
    
    # Upload to Cloudinary
    result = upload_to_cloudinary(file, folder)
    
    if result['success']:
        return jsonify({
            'success': True,
            'public_id': result['public_id'],
            'url': result['url']
        }), 200
    else:
        return jsonify({'success': False, 'error': result['error']}), 500

@cloudinary_bp.route('/delete', methods=['POST'])
@login_required
def delete_image():
    """Delete image from Cloudinary"""
    if not should_use_cloudinary():
        return jsonify({'success': False, 'error': 'Cloudinary not configured'}), 400
    
    data = request.get_json()
    public_id = data.get('public_id')
    
    if not public_id:
        return jsonify({'success': False, 'error': 'No public_id provided'}), 400
    
    success = delete_from_cloudinary(public_id)
    return jsonify({'success': success}), 200 if success else 400

# ===== USER AVATAR ENDPOINTS =====

@cloudinary_bp.route('/user/avatar', methods=['POST'])
@login_required
def upload_user_avatar():
    """Upload user avatar"""
    user_id = session.get('user_id')
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    if not file or not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'Invalid file'}), 400
    
    # Upload to Cloudinary
    result = upload_avatar(file, user_id)
    
    if not result:
        return jsonify({'success': False, 'error': 'Upload failed'}), 500
    
    # Update user in database
    user = User.query.get(user_id)
    if user:
        # Delete old avatar if exists
        if user.avatar_public_id:
            delete_from_cloudinary(user.avatar_public_id)
        
        user.avatar_public_id = result['public_id']
        user.avatar_url = result['url']
        db.session.commit()
        
        return jsonify({
            'success': True,
            'public_id': result['public_id'],
            'url': result['url']
        })
    
    return jsonify({'success': False, 'error': 'User not found'}), 404

# ===== PRODUCT IMAGE ENDPOINTS =====

@cloudinary_bp.route('/product/<int:product_id>/image', methods=['POST'])
@login_required
def upload_product_image_endpoint(product_id):
    """Upload image for a specific product"""
    user_id = session.get('user_id')
    
    # Check if product belongs to user's store
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'success': False, 'error': 'Product not found'}), 404
    
    store = Store.query.filter_by(seller_id=user_id).first()
    if not store or product.store_id != store.id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    if not file or not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'Invalid file'}), 400
    
    # Get sort order from form
    is_primary = request.form.get('is_primary', 'false').lower() == 'true'
    sort_order = request.form.get('sort_order', 0, type=int)
    
    # Upload to Cloudinary
    result = upload_product_image(file, product_id, is_primary, sort_order)
    
    if not result or not result.get('success'):
        return jsonify({'success': False, 'error': 'Upload failed'}), 500
    
    # Save to database
    product_image = ProductImage(
        product_id=product_id,
        filename=secure_filename(file.filename),
        public_id=result['public_id'],
        cloudinary_url=result['url'],
        is_primary=is_primary,
        sort_order=sort_order
    )
    db.session.add(product_image)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'image_id': product_image.id,
        'public_id': result['public_id'],
        'url': result['url']
    })

@cloudinary_bp.route('/product/image/<int:image_id>', methods=['DELETE'])
@login_required
def delete_product_image(image_id):
    """Delete a product image"""
    user_id = session.get('user_id')
    
    image = ProductImage.query.get(image_id)
    if not image:
        return jsonify({'success': False, 'error': 'Image not found'}), 404
    
    # Check authorization
    product = image.product
    store = Store.query.filter_by(seller_id=user_id).first()
    if not store or product.store_id != store.id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    # Delete from Cloudinary
    if image.public_id:
        delete_from_cloudinary(image.public_id)
    
    # Delete from database
    db.session.delete(image)
    db.session.commit()
    
    return jsonify({'success': True})

# ===== VARIANT IMAGE ENDPOINTS =====

@cloudinary_bp.route('/variant/<int:variant_id>/image', methods=['POST'])
@login_required
def upload_variant_image_endpoint(variant_id):
    """Upload image for a product variant"""
    user_id = session.get('user_id')
    
    variant = ProductVariant.query.get(variant_id)
    if not variant:
        return jsonify({'success': False, 'error': 'Variant not found'}), 404
    
    # Check authorization
    product = variant.product
    store = Store.query.filter_by(seller_id=user_id).first()
    if not store or product.store_id != store.id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    if not file or not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'Invalid file'}), 400
    
    # Upload to Cloudinary
    result = upload_variant_image(file, product.id, variant.name)
    
    if not result or not result.get('success'):
        return jsonify({'success': False, 'error': 'Upload failed'}), 500
    
    # Delete old image if exists
    if variant.image_public_id:
        delete_from_cloudinary(variant.image_public_id)
    
    # Update variant
    variant.image_public_id = result['public_id']
    variant.image_url = result['url']
    variant.image_filename = secure_filename(file.filename)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'public_id': result['public_id'],
        'url': result['url']
    })

# ===== GCASH QR ENDPOINTS =====

@cloudinary_bp.route('/store/<int:store_id>/gcash-qr', methods=['POST'])
@login_required
def upload_gcash_qr_endpoint(store_id):
    """Upload GCash QR code for a store"""
    user_id = session.get('user_id')
    
    store = Store.query.get(store_id)
    if not store:
        return jsonify({'success': False, 'error': 'Store not found'}), 404
    
    if store.seller_id != user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    if not file or not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'Invalid file'}), 400
    
    # Upload to Cloudinary
    result = upload_gcash_qr(file, store_id)
    
    if not result or not result.get('success'):
        return jsonify({'success': False, 'error': 'Upload failed'}), 500
    
    # Get sort order
    sort_order = GCashQR.query.filter_by(store_id=store_id).count()
    is_primary = (sort_order == 0)
    
    # Save to database
    gcash_qr = GCashQR(
        store_id=store_id,
        filename=secure_filename(file.filename),
        public_id=result['public_id'],
        cloudinary_url=result['url'],
        is_primary=is_primary,
        sort_order=sort_order
    )
    db.session.add(gcash_qr)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'qr_id': gcash_qr.id,
        'public_id': result['public_id'],
        'url': result['url']
    })

# ===== SELLER APPLICATION ENDPOINTS =====

@cloudinary_bp.route('/seller-application/upload-document', methods=['POST'])
@login_required
def upload_seller_document_endpoint():
    """Upload document for seller application"""
    user_id = session.get('user_id')
    doc_type = request.form.get('doc_type')  # 'logo' or 'id'
    
    if doc_type not in ['logo', 'id']:
        return jsonify({'success': False, 'error': 'Invalid document type'}), 400
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    if not file or not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'Invalid file'}), 400
    
    # Upload to Cloudinary
    result = upload_seller_document(file, user_id, doc_type)
    
    if not result or not result.get('success'):
        return jsonify({'success': False, 'error': 'Upload failed'}), 500
    
    return jsonify({
        'success': True,
        'public_id': result['public_id'],
        'url': result['url']
    })

# ===== PAYMENT PROOF ENDPOINTS =====

@cloudinary_bp.route('/order/<int:order_id>/payment-proof', methods=['POST'])
@login_required
def upload_payment_proof_endpoint(order_id):
    """Upload payment proof for an order"""
    user_id = session.get('user_id')
    
    order = Order.query.get(order_id)
    if not order:
        return jsonify({'success': False, 'error': 'Order not found'}), 404
    
    if order.customer_id != user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    if not file or not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'Invalid file'}), 400
    
    # Upload to Cloudinary
    result = upload_payment_proof(file, order_id)
    
    if not result or not result.get('success'):
        return jsonify({'success': False, 'error': 'Upload failed'}), 500
    
    # Delete old proof if exists
    if order.payment_proof_public_id:
        delete_from_cloudinary(order.payment_proof_public_id)
    
    # Update order
    order.payment_proof_public_id = result['public_id']
    order.payment_proof_url = result['url']
    order.payment_proof = secure_filename(file.filename)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'public_id': result['public_id'],
        'url': result['url']
    })

# ===== SIGNATURE FOR DIRECT BROWSER UPLOADS =====

@cloudinary_bp.route('/signature', methods=['GET'])
@login_required
def get_upload_signature():
    """Get signature for direct browser uploads"""
    if not should_use_cloudinary():
        return jsonify({'success': False, 'error': 'Cloudinary not configured'}), 400
    
    timestamp = int(time.time())
    folder = request.args.get('folder', 'e-flowers/uploads')
    
    # Generate signature
    params = {
        'timestamp': timestamp,
        'folder': folder
    }
    
    signature = cloudinary.utils.api_sign_request(
        params,
        current_app.config['CLOUDINARY_API_SECRET']
    )
    
    return jsonify({
        'success': True,
        'signature': signature,
        'timestamp': timestamp,
        'folder': folder,
        'cloud_name': current_app.config['CLOUDINARY_CLOUD_NAME'],
        'api_key': current_app.config['CLOUDINARY_API_KEY']
    })

# ===== TEST ENDPOINT =====

@cloudinary_bp.route('/test', methods=['GET'])
def test_cloudinary():
    """Test endpoint to verify Cloudinary is working"""
    if should_use_cloudinary():
        return jsonify({
            'success': True,
            'message': 'Cloudinary is configured',
            'cloud_name': current_app.config.get('CLOUDINARY_CLOUD_NAME')
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Cloudinary is not configured'
        })