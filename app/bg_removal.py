from flask import Blueprint, request, jsonify, current_app
from PIL import Image
from rembg import remove
import io
import base64
import os
from werkzeug.utils import secure_filename
import time

bg_removal_bp = Blueprint('bg_removal', __name__, url_prefix='/api/bg-removal')

# Allowed extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@bg_removal_bp.route('/remove', methods=['POST'])
def remove_background():
    """
    Remove background from uploaded image
    Returns: Base64 encoded PNG with transparency
    """
    try:
        # Check if file exists
        if 'image' not in request.files:
            return jsonify({'error': 'No image provided'}), 400
        
        file = request.files['image']
        
        if file.filename == '':
            return jsonify({'error': 'Empty filename'}), 400
            
        if not allowed_file(file.filename):
            return jsonify({'error': 'File type not allowed'}), 400
        
        # Read and process image
        input_image = Image.open(file.stream)
        
        # Optional: Resize large images for better performance
        max_size = (1920, 1080)
        input_image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Remove background (this is the magic line!)
        output_image = remove(input_image)
        
        # Convert to base64 for easy frontend display
        buffer = io.BytesIO()
        output_image.save(buffer, format='PNG')
        buffer.seek(0)
        
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        return jsonify({
            'success': True,
            'image': f'data:image/png;base64,{img_base64}',
            'message': 'Background removed successfully'
        })
        
    except Exception as e:
        print(f"Background removal error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@bg_removal_bp.route('/remove-and-save', methods=['POST'])
def remove_and_save():
    """
    Remove background and save to server
    Returns: URL of saved image
    """
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image provided'}), 400
        
        file = request.files['image']
        
        if file.filename == '':
            return jsonify({'error': 'Empty filename'}), 400
        
        # Process image
        input_image = Image.open(file.stream)
        output_image = remove(input_image)
        
        # Generate unique filename
        timestamp = int(time.time())
        original_filename = secure_filename(file.filename)
        name_without_ext = os.path.splitext(original_filename)[0]
        new_filename = f"no-bg-{timestamp}-{name_without_ext}.png"
        
        # Save to uploads folder
        upload_folder = os.path.join(current_app.config.get('BASE_DIR', os.path.dirname(current_app.root_path)), 
                                     'static', 'uploads', 'processed')
        os.makedirs(upload_folder, exist_ok=True)
        
        save_path = os.path.join(upload_folder, new_filename)
        output_image.save(save_path, 'PNG')
        
        # Return URL
        image_url = f'/static/uploads/processed/{new_filename}'
        
        return jsonify({
            'success': True,
            'image_url': image_url,
            'message': 'Background removed and saved'
        })
        
    except Exception as e:
        print(f"Background removal error: {str(e)}")
        return jsonify({'error': str(e)}), 500