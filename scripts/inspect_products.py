import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.stdout.reconfigure(encoding='utf-8')
from app import create_app
from app.models import Store, Product

app = create_app()
with app.app_context():
    for sid in [21, 18, 22]:
        s = Store.query.filter_by(id=sid).first()
        print(f"\n=== {s.name} (ID: {sid}) ===")
        prods = Product.query.filter_by(store_id=sid, is_archived=False).all()
        for p in prods:
            print(f"ID: {p.id:3d} | {p.name[:35]:35s} | ₱{float(p.price):7.2f} | img: {p.image_url}")
