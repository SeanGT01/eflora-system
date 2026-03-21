from app import create_app
from app.models import Product, Store

app = create_app()
ctx = app.app_context()
ctx.push()

p = Product.query.filter_by(id=40).first()
if p:
    print(f"✅ Product 40 found: {p.name}")
    print(f"   Store ID: {p.store_id}")
    s = Store.query.filter_by(id=p.store_id).first()
    if s:
        print(f"   Store: {s.name}")
        print(f"   Seller ID: {s.seller_id}")
        print(f"   Status: {s.status}")
    else:
        print("   ❌ Store not found")
else:
    print("❌ Product 40 NOT FOUND")
    print("Available products:")
    all_products = Product.query.limit(5).all()
    for prod in all_products:
        print(f"  - ID: {prod.id}, Name: {prod.name}")
