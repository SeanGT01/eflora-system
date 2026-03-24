# run.py — Production-ready entry point
import os
import sys
from app import create_app

# Log startup
print("🚀 E-Flowers system starting...", file=sys.stderr)

try:
    app = create_app()
    print("✅ App created successfully", file=sys.stderr)
    
    # Log loaded config
    print(f"📦 Database URL configured: {bool(app.config.get('DATABASE_URL'))}", file=sys.stderr)
    print(f"🔐 Secret key configured: {bool(app.config.get('SECRET_KEY'))}", file=sys.stderr)
    
except Exception as e:
    print(f"❌ FATAL: Failed to create app: {str(e)}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)

if __name__ == '__main__':
    # Only run in debug mode if explicitly set
    debug_mode = os.getenv('FLASK_ENV') == 'development'
    port = int(os.getenv('PORT', 5000))
    
    print(f"🎯 Starting Flask on 0.0.0.0:{port} (debug={debug_mode})", file=sys.stderr)
    app.run(debug=debug_mode, host='0.0.0.0', port=port)