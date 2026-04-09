# run.py — Production-ready entry point
import os
import sys
from app import create_app
from app.chat_socket import socketio

# Log startup
print("🚀 E-Flowers system starting...", file=sys.stderr)

try:
    app = create_app()
    # Initialize Socket.IO with the Flask app (threading mode for broad compatibility)
    socketio.init_app(app, cors_allowed_origins='*', async_mode='threading')
    print("✅ App created successfully (Socket.IO enabled)", file=sys.stderr)
    
    # Log loaded config
    print(f"📦 Database URL configured: {bool(app.config.get('DATABASE_URL'))}", file=sys.stderr)
    print(f"🔐 Secret key configured: {bool(app.config.get('SECRET_KEY'))}", file=sys.stderr)
    
except Exception as e:
    print(f"❌ FATAL: Failed to create app: {str(e)}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)

# For Gunicorn - expose the app object at module level
# Gunicorn will import 'app' from this module
# The 'app' variable is already created above

if __name__ == '__main__':
    # Only run in debug mode when executing directly (not via Gunicorn)
    debug_mode = os.getenv('FLASK_ENV') == 'development'
    port = int(os.getenv('PORT', 8000))  # Changed from 5000 to 8000
    
    print(f"🎯 Starting Flask+SocketIO on 0.0.0.0:{port} (debug={debug_mode})", file=sys.stderr)
    socketio.run(app, debug=debug_mode, host='0.0.0.0', port=port)