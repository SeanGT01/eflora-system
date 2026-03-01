#!/usr/bin/env python3
"""
Comprehensive test for product creation issue
"""

from app import create_app
from app.extensions import db
from app.models import User, Store, Product
from flask import session
import sys

def test_complete_flow():
    print("\n" + "="*70)
    print("COMPREHENSIVE PRODUCT CREATION TEST")
    print("="*70 + "\n")
    
    app = create_app('default')
    
    with app.app_context():
        # Print database URL (hide password)
        db_url = app.config['SQLALCHEMY_DATABASE_URI']
        if 'postgresql' in db_url:
            safe_url = db_url.split('@')[1] if '@' in db_url else db_url
            print(f"Database: PostgreSQL @ {safe_url}")
        else:
            print(f"Database: {db_url}")
        
        # Test 1: Connection
        print("\n[1/8] Testing database connection...")
        try:
            db.session.execute(db.text("SELECT version()"))
            print("    ✓ Connected successfully")
        except Exception as e:
            print(f"    ✗ Connection failed: {e}")
            return False
        
        # Test 2: Tables
        print("\n[2/8] Checking tables...")
        try:
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            
            required_tables = ['users', 'stores', 'products']
            missing = [t for t in required_tables if t not in tables]
            
            if missing:
                print(f"    ✗ Missing tables: {', '.join(missing)}")
                print(f"    → Run: python setup_database.py")
                return False
            
            print(f"    ✓ All required tables exist")
            print(f"      Found: {', '.join(tables)}")
        except Exception as e:
            print(f"    ✗ Error: {e}")
            return False
        
        # Test 3: Find/Create Seller
        print("\n[3/8] Setting up test seller...")
        try:
            seller = User.query.filter_by(email='testseller@eflowers.com').first()
            
            if not seller:
                seller = User(
                    full_name='Test Seller',
                    email='testseller@eflowers.com',
                    role='seller',
                    status='active'
                )
                seller.set_password('test123')
                db.session.add(seller)
                db.session.commit()
                print(f"    ✓ Created new seller (ID: {seller.id})")
            else:
                print(f"    ✓ Using existing seller (ID: {seller.id})")
                
            print(f"      Email: {seller.email}")
            print(f"      Role: {seller.role}")
            print(f"      Status: {seller.status}")
        except Exception as e:
            print(f"    ✗ Error: {e}")
            db.session.rollback()
            return False
        
        # Test 4: Find/Create Store
        print("\n[4/8] Setting up seller's store...")
        try:
            store = Store.query.filter_by(seller_id=seller.id).first()
            
            if not store:
                store = Store(
                    seller_id=seller.id,
                    name="Test Flower Shop",
                    address="123 Test Street, Test City",
                    status='active'
                )
                db.session.add(store)
                db.session.commit()
                print(f"    ✓ Created new store (ID: {store.id})")
            else:
                print(f"    ✓ Using existing store (ID: {store.id})")
                
            print(f"      Name: {store.name}")
            print(f"      Status: {store.status}")
            print(f"      Seller ID: {store.seller_id}")
        except Exception as e:
            print(f"    ✗ Error: {e}")
            db.session.rollback()
            return False
        
        # Test 5: Check existing products
        print("\n[5/8] Checking existing products...")
        try:
            product_count = Product.query.filter_by(store_id=store.id).count()
            print(f"    ✓ Current products in store: {product_count}")
            
            if product_count > 0:
                latest = Product.query.filter_by(store_id=store.id)\
                    .order_by(Product.created_at.desc()).first()
                print(f"      Latest: '{latest.name}' (ID: {latest.id})")
        except Exception as e:
            print(f"    ✗ Error: {e}")
            return False
        
        # Test 6: Create product (mimicking your route)
        print("\n[6/8] Creating test product...")
        try:
            product_data = {
                'name': 'Test Product ' + str(db.session.execute(db.text("SELECT COUNT(*) FROM products")).scalar() + 1),
                'description': 'This is a test product created by test script',
                'price': 499.99,
                'stock_quantity': 100,
                'category': 'flowers'
            }
            
            print(f"    Product data:")
            for key, value in product_data.items():
                print(f"      {key}: {value}")
            
            # Create product object
            product = Product(
                store_id=store.id,
                name=product_data['name'],
                description=product_data['description'],
                price=product_data['price'],
                stock_quantity=product_data['stock_quantity'],
                category=product_data['category'],
                is_available=True
            )
            
            print(f"\n    Adding to session...")
            db.session.add(product)
            
            print(f"    Flushing...")
            db.session.flush()
            print(f"    → Product ID after flush: {product.id}")
            
            print(f"    Committing...")
            db.session.commit()
            print(f"    ✓ Commit successful!")
            
        except Exception as e:
            print(f"    ✗ Error during creation: {e}")
            import traceback
            traceback.print_exc()
            db.session.rollback()
            return False
        
        # Test 7: Verify in database
        print("\n[7/8] Verifying product in database...")
        try:
            # Retrieve by ID
            saved = Product.query.get(product.id)
            if not saved:
                print(f"    ✗ Product not found by ID!")
                return False
            
            print(f"    ✓ Product retrieved successfully!")
            print(f"      ID: {saved.id}")
            print(f"      Name: {saved.name}")
            print(f"      Price: ${saved.price}")
            print(f"      Stock: {saved.stock_quantity}")
            print(f"      Category: {saved.category}")
            print(f"      Store ID: {saved.store_id}")
            
            # Count total products
            new_count = Product.query.filter_by(store_id=store.id).count()
            print(f"\n    Total products in store: {new_count}")
            
        except Exception as e:
            print(f"    ✗ Error verifying: {e}")
            return False
        
        # Test 8: Test with session (like web request)
        print("\n[8/8] Testing with Flask session (web request simulation)...")
        with app.test_request_context():
            try:
                from flask import session
                
                # Simulate logged-in seller
                session['user_id'] = seller.id
                session['role'] = 'seller'
                session['email'] = seller.email
                
                # Try to find store (like in your route)
                test_store = Store.query.filter_by(seller_id=session.get('user_id')).first()
                
                if not test_store:
                    print(f"    ✗ Could not find store in session context!")
                    return False
                
                print(f"    ✓ Session test passed")
                print(f"      Session user_id: {session.get('user_id')}")
                print(f"      Found store: {test_store.name} (ID: {test_store.id})")
                
            except Exception as e:
                print(f"    ✗ Session test failed: {e}")
                import traceback
                traceback.print_exc()
                return False
        
        print("\n" + "="*70)
        print("ALL TESTS PASSED! ✓")
        print("="*70)
        print("\n✓ Database is configured correctly")
        print("✓ Product creation works")
        print("✓ Session handling works")
        print("\nTest Credentials:")
        print(f"  Email: {seller.email}")
        print(f"  Password: test123")
        print(f"  Role: seller")
        print(f"\nYou can now login and try creating products through the web interface.")
        print("If it still doesn't work, the issue is in the web request handling.\n")
        
        return True

if __name__ == '__main__':
    success = test_complete_flow()
    sys.exit(0 if success else 1)