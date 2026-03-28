#!/usr/bin/env python
"""
Fix script to link stores with their seller applications.
Run this once to populate seller_application_id on stores.
"""

import sys
from app import create_app, db
from app.models import Store, SellerApplication, User

app = create_app()

with app.app_context():
    print("=" * 60)
    print("Fixing Store → SellerApplication Links")
    print("=" * 60)
    
    # Get all stores without seller_application_id
    stores_without_app_id = Store.query.filter(
        Store.seller_application_id.is_(None)
    ).all()
    
    print(f"\nFound {len(stores_without_app_id)} stores without seller_application_id\n")
    
    updated_count = 0
    
    for store in stores_without_app_id:
        print(f"Processing Store: {store.id} - {store.name} (Seller ID: {store.seller_id})")
        
        # Find the seller application for this store's seller
        seller_app = SellerApplication.query.filter_by(
            user_id=store.seller_id
        ).first()
        
        if seller_app:
            print(f"  ✓ Found SellerApplication ID: {seller_app.id}")
            print(f"  ✓ Status: {seller_app.status}")
            print(f"  ✓ Logo URL: {seller_app.store_logo_url}")
            
            # Link the store to the seller application
            store.seller_application_id = seller_app.id
            updated_count += 1
            print(f"  → Updated store.seller_application_id = {seller_app.id}")
        else:
            print(f"  ✗ No SellerApplication found for seller_id {store.seller_id}")
        
        print()
    
    # Commit changes
    if updated_count > 0:
        print(f"\n{'=' * 60}")
        print(f"Committing {updated_count} updates to database...")
        print(f"{'=' * 60}\n")
        db.session.commit()
        print(f"✓ Successfully updated {updated_count} stores!\n")
    else:
        print("No stores needed updating.\n")
    
    # Verify logo URLs are now working
    print("=" * 60)
    print("Verifying Store Logo URLs")
    print("=" * 60 + "\n")
    
    active_stores = Store.query.filter_by(status='active').limit(4).all()
    for store in active_stores:
        print(f"Store: {store.id} - {store.name}")
        print(f"  Seller ID: {store.seller_id}")
        print(f"  App ID: {store.seller_application_id}")
        print(f"  Logo URL: {store.logo_url}")
        print()
