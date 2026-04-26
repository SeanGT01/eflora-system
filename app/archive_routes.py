# app/archive_routes.py
from flask import Blueprint, request, jsonify, session, render_template
from app.models import Product, Store, User, CartItem
from app.extensions import db
from datetime import datetime
from functools import wraps
from app.utils.cloudinary_helper import delete_from_cloudinary

archive_bp = Blueprint('archive', __name__, url_prefix='/api/v1/seller/archive')

def seller_required(f):
    """Require user to be logged in as a seller."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Not logged in'}), 401
        if session.get('role') != 'seller':
            return jsonify({'error': 'Seller access required'}), 403
        return f(*args, **kwargs)
    return decorated

def get_seller_store():
    """Return the active store for the logged-in seller, or None."""
    return Store.query.filter_by(seller_id=session.get('user_id'), status='active').first()

@archive_bp.route('/products', methods=['GET'])
@seller_required
def get_archived_products():
    """Get all archived products for the seller"""
    try:
        store = get_seller_store()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        # Get only archived products
        products = Product.query.filter_by(
            store_id=store.id,
            is_archived=True
        ).order_by(Product.archived_at.desc()).all()
        
        return jsonify({
            'success': True,
            'products': [p.to_dict() for p in products]  # Remove include_archived=True
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@archive_bp.route('/products/<int:product_id>/archive', methods=['POST'])
@seller_required
def archive_product(product_id):
    """Move product to archive (soft delete)"""
    try:
        store = get_seller_store()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        # Check if already archived
        if product.is_archived:
            return jsonify({'error': 'Product is already archived'}), 400
        
        # Archive the product
        product.archive(session['user_id'])
        
        # Check if product is in any active carts
        carts_with_product = CartItem.query.filter_by(
            product_id=product_id
        ).count()
        
        db.session.commit()
        
        message = f'Product "{product.name}" moved to archive.'
        if carts_with_product > 0:
            message += f' It will be removed from {carts_with_product} customer carts.'
        
        return jsonify({
            'success': True,
            'message': message,
            'product': product.to_dict(include_archived=True),
            'affected_carts': carts_with_product
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@archive_bp.route('/products/<int:product_id>/restore', methods=['POST'])
@seller_required
def restore_product(product_id):
    """Restore product from archive"""
    try:
        store = get_seller_store()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        if not product.is_archived:
            return jsonify({'error': 'Product is not archived'}), 400
        
        # Restore the product
        product.restore()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Product "{product.name}" restored successfully',
            'product': product.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@archive_bp.route('/products/<int:product_id>/permanent-delete', methods=['DELETE'])
@seller_required
def permanent_delete_product(product_id):
    """Permanently delete product (only if archived)"""
    try:
        store = get_seller_store()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        # Safety check - only allow permanent delete if product is archived
        if not product.is_archived:
            return jsonify({
                'error': 'Product must be archived first. Use archive endpoint.'
            }), 400
        
        # Double-check if product is in any carts (safety)
        carts_with_product = CartItem.query.filter_by(product_id=product_id).count()
        if carts_with_product > 0:
            return jsonify({
                'error': f'Cannot permanently delete. Product is in {carts_with_product} carts.'
            }), 400
        
        # Delete associated media from Cloudinary (best effort per asset)
        for image in product.images:
            if image.public_id:
                try:
                    delete_from_cloudinary(image.public_id)
                except Exception:
                    pass

        for variant in product.variants:
            if variant.image_public_id:
                try:
                    delete_from_cloudinary(variant.image_public_id)
                except Exception:
                    pass
        
        # Store name for message
        product_name = product.name
        
        # Delete the product (cascade will delete images from DB)
        db.session.delete(product)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Product "{product_name}" permanently deleted'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@archive_bp.route('/products/bulk/archive', methods=['POST'])
@seller_required
def bulk_archive_products():
    """Archive multiple products at once"""
    try:
        store = get_seller_store()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        data = request.get_json()
        product_ids = data.get('product_ids', [])
        
        if not product_ids:
            return jsonify({'error': 'No product IDs provided'}), 400
        
        archived_count = 0
        affected_carts_total = 0
        
        for product_id in product_ids:
            product = Product.query.filter_by(id=product_id, store_id=store.id).first()
            if product and not product.is_archived:
                # Check carts before archiving
                carts_count = CartItem.query.filter_by(product_id=product_id).count()
                affected_carts_total += carts_count
                
                product.archive(session['user_id'])
                archived_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Archived {archived_count} products',
            'archived_count': archived_count,
            'affected_carts': affected_carts_total
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@archive_bp.route('/products/bulk/restore', methods=['POST'])
@seller_required
def bulk_restore_products():
    """Restore multiple products from archive"""
    try:
        store = get_seller_store()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        data = request.get_json()
        product_ids = data.get('product_ids', [])
        
        if not product_ids:
            return jsonify({'error': 'No product IDs provided'}), 400
        
        restored_count = 0
        
        for product_id in product_ids:
            product = Product.query.filter_by(id=product_id, store_id=store.id).first()
            if product and product.is_archived:
                product.restore()
                restored_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Restored {restored_count} products',
            'restored_count': restored_count
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@archive_bp.route('/products/bulk/permanent-delete', methods=['POST'])
@seller_required
def bulk_permanent_delete():
    """Permanently delete multiple archived products"""
    try:
        store = get_seller_store()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        data = request.get_json()
        product_ids = data.get('product_ids', [])
        
        if not product_ids:
            return jsonify({'error': 'No product IDs provided'}), 400
        
        deleted_count = 0
        failed_products = []
        
        for product_id in product_ids:
            product = Product.query.filter_by(id=product_id, store_id=store.id).first()
            if product and product.is_archived:
                # Check if in any carts
                carts_count = CartItem.query.filter_by(product_id=product_id).count()
                if carts_count > 0:
                    failed_products.append({
                        'id': product.id,
                        'name': product.name,
                        'reason': f'In {carts_count} carts'
                    })
                    continue
                
                # Delete associated media from Cloudinary (best effort per asset)
                for image in product.images:
                    if image.public_id:
                        try:
                            delete_from_cloudinary(image.public_id)
                        except Exception:
                            pass

                for variant in product.variants:
                    if variant.image_public_id:
                        try:
                            delete_from_cloudinary(variant.image_public_id)
                        except Exception:
                            pass
                
                db.session.delete(product)
                deleted_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Permanently deleted {deleted_count} products',
            'deleted_count': deleted_count,
            'failed_products': failed_products
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@archive_bp.route('/stats', methods=['GET'])
@seller_required
def archive_stats():
    """Get archive statistics for the seller"""
    try:
        store = get_seller_store()
        if not store:
            return jsonify({'error': 'Store not found'}), 404
        
        total_archived = Product.query.filter_by(
            store_id=store.id,
            is_archived=True
        ).count()
        
        # Get archive history (last 10 archived products)
        recent_archives = Product.query.filter_by(
            store_id=store.id,
            is_archived=True
        ).order_by(Product.archived_at.desc()).limit(10).all()
        
        # Count products in carts that are archived
        products_in_carts = db.session.query(CartItem)\
            .join(Product)\
            .filter(
                Product.store_id == store.id,
                Product.is_archived == True
            ).count()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_archived': total_archived,
                'products_in_carts': products_in_carts,
                'recent_archives': [{
                    'id': p.id,
                    'name': p.name,
                    'archived_at': p.archived_at.isoformat() if p.archived_at else None,
                    'archived_by': p.archived_by_user.full_name if p.archived_by_user else None
                } for p in recent_archives]
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500