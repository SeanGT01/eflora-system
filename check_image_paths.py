# create a file check_image_paths.py
from app import create_app
from app.models import Product, ProductImage
from app.extensions import db
import os

app = create_app()
with app.app_context():
    print("\n=== CHECKING PRODUCT IMAGES ===\n")
    
    # Get all products with images
    products = Product.query.all()
    for product in products:
        print(f"\n📦 Product ID: {product.id}, Name: {product.name}")
        images = ProductImage.query.filter_by(product_id=product.id).all()
        if images:
            for img in images:
                print(f"   📸 Image filename: {img.filename}")
                print(f"      Is primary: {img.is_primary}")
                
                # Check multiple possible locations
                possible_paths = [
                    os.path.join('static', 'uploads', 'products', img.filename),
                    os.path.join('uploads', 'products', img.filename),
                    os.path.join('app', 'static', 'uploads', 'products', img.filename),
                    os.path.join('..', 'uploads', 'products', img.filename),
                ]
                
                print(f"      Checking locations:")
                for path in possible_paths:
                    full_path = os.path.join(os.path.dirname(__file__), path)
                    exists = os.path.exists(full_path)
                    print(f"        {path}: {'✅ Found' if exists else '❌ Not found'}")
        else:
            print(f"   ❌ No images for this product")