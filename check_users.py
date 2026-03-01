# check_users.py
from app import create_app
from app.models import User
from app.extensions import db

app = create_app()
with app.app_context():
    users = User.query.all()
    print("\n=== USERS IN DATABASE ===")
    for user in users:
        print(f"ID: {user.id}, Email: {user.email}, Role: {user.role}, Name: {user.full_name}")
        # Don't print passwords, they're hashed
    print("========================\n")
    
    # Specifically check customer1
    customer = User.query.filter_by(email='customer1@gmail.com').first()
    if customer:
        print(f"Customer1 found: ID={customer.id}, Email={customer.email}, Role={customer.role}")
        # Test a password - try common ones
        test_passwords = ['password', 'customer1', '123456', 'password123', 'admin123']
        for pwd in test_passwords:
            if customer.check_password(pwd):
                print(f"✅ Password '{pwd}' works!")
                break
        else:
            print("❌ None of the test passwords worked")
    else:
        print("❌ customer1@gmail.com not found in database")