from app import create_app
from app.extensions import db
from app.models import Category

def seed_categories():
    app = create_app()
    with app.app_context():
        # Check if categories already exist
        if Category.query.count() > 0:
            print("✅ Categories already exist:")
            for cat in Category.query.all():
                print(f"  - {cat.name}")
            return
        
        print("🌱 Creating default categories...")
        
        categories = [
            Category(
                name='Fresh Flowers',
                slug='fresh-flowers',
                icon='ri-flower-line',
                description='Fresh cut flowers arranged beautifully',
                sort_order=1
            ),
            Category(
                name='Potted Plants',
                slug='potted-plants',
                icon='ri-plant-line',
                description='Live plants in pots for your home or garden',
                sort_order=2
            ),
            Category(
                name='Bouquets',
                slug='bouquets',
                icon='ri-gift-line',
                description='Hand-tied bouquets for any occasion',
                sort_order=3
            ),
            Category(
                name='Succulents',
                slug='succulents',
                icon='ri-leaf-line',
                description='Low-maintenance succulent plants',
                sort_order=4
            )
        ]
        
        db.session.add_all(categories)
        db.session.commit()
        print("✅ Categories created successfully!")

if __name__ == '__main__':
    seed_categories()