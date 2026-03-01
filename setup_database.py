#!/usr/bin/env python3
"""
Database setup script for E-FLOWERS & PLANTS System
Run this script to create the database and tables
"""

import os
import sys
from app import create_app, db
from app.models import User, Store, Product, Order, Rider, OrderItem, RiderLocation, \
                      POSOrder, POSOrderItem, Testimonial, OrderAnalytics

def setup_database():
    app = create_app('default')
    
    with app.app_context():
        # Create all tables
        print("Creating database tables...")
        db.create_all()
        
        # Create admin user if not exists
        admin = User.query.filter_by(email='admin@eflowers.com').first()
        if not admin:
            admin = User(
                full_name='System Administrator',
                email='admin@eflowers.com',
                role='admin',
                status='active'
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("Admin user created: admin@eflowers.com / admin123")
        
        print("Database setup completed successfully!")

if __name__ == '__main__':
    setup_database()