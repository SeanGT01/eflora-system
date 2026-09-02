from app import create_app
from app.models import Category, ensure_default_main_categories


def seed_categories():
    app = create_app()
    with app.app_context():
        print("🌱 Ensuring default main categories...")
        ensure_default_main_categories()
        print("✅ Categories:")
        for cat in Category.query.order_by(Category.sort_order, Category.name).all():
            print(f"  - {cat.name} ({cat.slug})")


if __name__ == '__main__':
    seed_categories()
