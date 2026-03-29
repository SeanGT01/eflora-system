# app/utils/cloudinary_helper.py
from flask import current_app
import cloudinary
import cloudinary.uploader
import cloudinary.api
import cloudinary.utils
import os
from werkzeug.utils import secure_filename
import uuid
import time
from typing import Optional, Dict, Any, List

def configure_cloudinary():
    """Configure Cloudinary with current app config"""
    cloudinary.config(
        cloud_name=current_app.config.get('CLOUDINARY_CLOUD_NAME'),
        api_key=current_app.config.get('CLOUDINARY_API_KEY'),
        api_secret=current_app.config.get('CLOUDINARY_API_SECRET'),
        secure=True
    )

def should_use_cloudinary():
    """Simple check if Cloudinary is configured"""
    try:
        return all([
            current_app.config.get('CLOUDINARY_CLOUD_NAME'),
            current_app.config.get('CLOUDINARY_API_KEY'),
            current_app.config.get('CLOUDINARY_API_SECRET')
        ])
    except:
        return False

def delete_from_cloudinary(public_id):
    """Delete from Cloudinary"""
    try:
        if not should_use_cloudinary():
            return False
        configure_cloudinary()
        result = cloudinary.uploader.destroy(public_id)
        return result.get('result') == 'ok'
    except Exception as e:
        print(f"Error deleting from Cloudinary: {e}")
        return False

def bulk_delete_from_cloudinary(public_ids: List[str]) -> Dict[str, Any]:
    """Delete multiple images from Cloudinary"""
    results = {
        'success': [],
        'failed': []
    }
    
    for public_id in public_ids:
        if delete_from_cloudinary(public_id):
            results['success'].append(public_id)
        else:
            results['failed'].append(public_id)
    
    return results

def upload_to_cloudinary(file, folder, public_id=None, transformation=None, **options):
    """Upload to Cloudinary - RETURNS ALL DATA NEEDED FOR MODELS"""
    try:
        if not should_use_cloudinary():
            return {'success': False, 'error': 'Cloudinary not configured'}
        
        configure_cloudinary()
        
        # Generate public_id if not provided
        if not public_id:
            original_filename = secure_filename(file.filename)
            name_without_ext = os.path.splitext(original_filename)[0]
            clean_name = ''.join(e for e in name_without_ext if e.isalnum() or e == '_')[:30]
            unique_id = uuid.uuid4().hex[:8]
            timestamp = str(int(time.time()))[-6:]
            public_id = f"{clean_name}_{timestamp}_{unique_id}"
        
        upload_options = {
            'public_id': public_id,
            'folder': folder,
            'resource_type': 'auto',
            'overwrite': True,
        }
        
        if transformation:
            upload_options['transformation'] = transformation
        
        upload_options.update(options)
        
        result = cloudinary.uploader.upload(file, **upload_options)
        
        # Extract version from the URL or response
        version = result.get('version')
        if not version and 'url' in result:
            # Try to extract from URL
            import re
            version_match = re.search(r'/v(\d+)/', result.get('secure_url', ''))
            if version_match:
                version = version_match.group(1)
        
        # Return COMPLETE data for models
        return {
            'success': True,
            'public_id': result['public_id'],  # For public_id field
            'url': result['secure_url'],       # For cloudinary_url/image_url field
            'filename': file.filename,          # For filename field (metadata)
            'format': result.get('format'),     # For cloudinary_format/image_format field
            'version': str(version) if version else None,  # For cloudinary_version field
            'width': result.get('width'),
            'height': result.get('height'),
            'bytes': result.get('bytes'),
            'created_at': result.get('created_at')
        }
    except Exception as e:
        print(f"Cloudinary upload error: {e}")
        return {'success': False, 'error': str(e)}

def get_transformed_url(public_id, width=None, height=None, crop='fill', format=None):
    """Generate transformed URL - matches model's get_transformed_url method"""
    if not public_id:
        return None
    
    try:
        configure_cloudinary()
        transformations = {}
        if width:
            transformations['width'] = width
        if height:
            transformations['height'] = height
        if crop:
            transformations['crop'] = crop
        if format:
            transformations['format'] = format
            
        url, _ = cloudinary.utils.cloudinary_url(
            public_id,
            **transformations,
            secure=True
        )
        return url
    except Exception as e:
        print(f"Error generating transformed URL: {e}")
        return None

def get_image_urls(public_id: str) -> Dict[str, Optional[str]]:
    """Get all size variants of an image - matches the view in migration"""
    if not public_id:
        return {
            'original': None,
            'thumbnail': None,
            'medium': None,
            'large': None
        }
    
    return {
        'original': get_transformed_url(public_id),
        'thumbnail': get_transformed_url(public_id, width=200, height=200),
        'medium': get_transformed_url(public_id, width=400, height=400),
        'large': get_transformed_url(public_id, width=800, height=800)
    }

def upload_avatar(file, user_id):
    """Upload user avatar to Cloudinary"""
    try:
        folder = f"e-flowers/users/{user_id}/avatar"
        result = upload_to_cloudinary(
            file,
            folder=folder,
            transformation=current_app.config.get('CLOUDINARY_PRESETS', {}).get('avatar', {})
        )
        return result
    except Exception as e:
        print(f"Error uploading avatar: {e}")
        return {'success': False, 'error': str(e)}

def upload_product_image(file, product_id, is_primary=False, sort_order=0):
    """Upload a product image to Cloudinary"""
    try:
        folder = f"e-flowers/products/{product_id}"
        result = upload_to_cloudinary(
            file,
            folder=folder,
            transformation=current_app.config.get('CLOUDINARY_PRESETS', {}).get('product', {})
        )
        
        if result['success']:
            result['is_primary'] = is_primary
            result['sort_order'] = sort_order
        return result
    except Exception as e:
        print(f"Error uploading product image: {e}")
        return {'success': False, 'error': str(e)}

def upload_variant_image(file, product_id, variant_name):
    """Upload a variant image to Cloudinary"""
    try:
        folder = f"e-flowers/products/{product_id}/variants"
        
        # Clean variant name for public_id
        clean_name = ''.join(e for e in variant_name if e.isalnum() or e == '_')[:20]
        
        result = upload_to_cloudinary(
            file,
            folder=folder,
            public_id=clean_name,
            transformation=current_app.config.get('CLOUDINARY_PRESETS', {}).get('product_thumbnail', {})
        )
        
        return result
    except Exception as e:
        print(f"Error uploading variant image: {e}")
        return {'success': False, 'error': str(e)}

def upload_gcash_qr(file, store_id):
    """Upload GCash QR code to Cloudinary"""
    try:
        folder = f"e-flowers/stores/{store_id}/gcash"
        result = upload_to_cloudinary(
            file,
            folder=folder,
            transformation=current_app.config.get('CLOUDINARY_PRESETS', {}).get('gcash_qr', {})
        )
        return result
    except Exception as e:
        print(f"Error uploading GCash QR: {e}")
        return {'success': False, 'error': str(e)}

def upload_seller_document(file, user_id, doc_type):
    """Upload seller application document (logo or ID)"""
    try:
        folder = f"e-flowers/sellers/{user_id}/{doc_type}"
        result = upload_to_cloudinary(
            file,
            folder=folder,
            transformation=current_app.config.get('CLOUDINARY_PRESETS', {}).get('govt_id', {})
        )
        return result
    except Exception as e:
        print(f"Error uploading seller document: {e}")
        return {'success': False, 'error': str(e)}

def upload_payment_proof(file, order_id):
    """Upload payment proof to Cloudinary"""
    try:
        folder = f"e-flowers/orders/{order_id}/payment"
        result = upload_to_cloudinary(
            file,
            folder=folder,
            transformation=current_app.config.get('CLOUDINARY_PRESETS', {}).get('product', {})
        )
        return result
    except Exception as e:
        print(f"Error uploading payment proof: {e}")
        return {'success': False, 'error': str(e)}

def upload_delivery_proof(file, order_id):
    """Upload delivery proof to Cloudinary"""
    try:
        folder = f"e-flowers/orders/{order_id}/delivery"
        result = upload_to_cloudinary(
            file,
            folder=folder,
            transformation=current_app.config.get('CLOUDINARY_PRESETS', {}).get('product', {})
        )
        return result
    except Exception as e:
        print(f"Error uploading delivery proof: {e}")
        return {'success': False, 'error': str(e)}


def get_optimized_url(public_id, preset='product'):
    """Get optimized URL using preset configurations"""
    if not public_id:
        return None
    try:
        configure_cloudinary()
        preset_config = current_app.config.get('CLOUDINARY_PRESETS', {}).get(preset, {})
        return cloudinary.CloudinaryImage(public_id).build_url(**preset_config)
    except:
        return cloudinary.CloudinaryImage(public_id).build_url()

def process_cleanup_queue():
    """Process the cloudinary_cleanup_queue table - run via cron/job"""
    from app.extensions import db
    from sqlalchemy import text
    
    # Get pending cleanup items
    result = db.session.execute(
        text("SELECT * FROM cloudinary_cleanup_queue WHERE status = 'pending' LIMIT 100")
    )
    
    for row in result:
        try:
            success = delete_from_cloudinary(row.public_id)
            if success:
                db.session.execute(
                    text("UPDATE cloudinary_cleanup_queue SET status = 'processed', processed_at = NOW() WHERE id = :id"),
                    {'id': row.id}
                )
            else:
                db.session.execute(
                    text("UPDATE cloudinary_cleanup_queue SET status = 'failed', error_message = 'Delete failed' WHERE id = :id"),
                    {'id': row.id}
                )
        except Exception as e:
            db.session.execute(
                text("UPDATE cloudinary_cleanup_queue SET status = 'failed', error_message = :error WHERE id = :id"),
                {'error': str(e), 'id': row.id}
            )
    
    db.session.commit()
    return True

# =====================================================
# EXAMPLE USAGE WITH NEW MODELS
# =====================================================
"""
# When uploading a product image:
result = upload_product_image(file, product.id, is_primary=True)

# In your route, create ProductImage:
product_image = ProductImage(
    product_id=product.id,
    filename=result['filename'],
    public_id=result['public_id'],
    cloudinary_url=result['url'],
    cloudinary_format=result['format'],
    cloudinary_version=result['version'],
    is_primary=result.get('is_primary', False),
    sort_order=result.get('sort_order', 0)
)
db.session.add(product_image)

# When displaying images:
thumbnail = get_transformed_url(product_image.public_id, width=200, height=200)
medium = get_transformed_url(product_image.public_id, width=400, height=400)
"""