import sys
from app import create_app
from app.models import User, Conversation
from app.chat import list_conversations

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

app = create_app()

with app.app_context():
    # Find a valid user to test with
    user = User.query.filter_by(role='customer').first()
    if not user:
        print("No customer found.")
        sys.exit(1)
        
    print(f"Testing as user ID {user.id}")
    
    with app.test_request_context(environ_base={'REMOTE_ADDR': '127.0.0.1'}):
        from flask_jwt_extended import create_access_token
        from flask import g
        # set g.user_id since some code might rely on it directly, though typically flask_jwt_extended uses get_jwt_identity()
        g.user_id = user.id
        
        # Mock flask_jwt_extended get_jwt_identity
        import flask_jwt_extended
        flask_jwt_extended.get_jwt_identity = lambda: user.id
        
        try:
            res, status = list_conversations()
            print("Status:", status)
            print("Response:", res.get_json())
        except Exception as e:
            import traceback
            traceback.print_exc()
