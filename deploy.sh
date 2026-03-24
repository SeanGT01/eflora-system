#!/bin/bash
# E-Flowers System - Railway Deployment Helper Script (Linux/macOS)
# This script helps with local preparation before deployment

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║   E-FLOWERS SYSTEM - RAILWAY DEPLOYMENT HELPER                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check if git is initialized
if [ ! -d .git ]; then
    echo "[1] Initializing Git repository..."
    git init
    git add .
    git commit -m "Initial commit: eflowers system ready for deployment"
    echo "✓ Git initialized"
else
    echo "✓ Git repository already exists"
fi

echo ""
echo "[2] Verifying deployment files..."
[ -f Dockerfile ] && echo "✓ Dockerfile found" || echo "✗ Dockerfile missing"
[ -f railway.toml ] && echo "✓ railway.toml found" || echo "✗ railway.toml missing"
[ -f requirements.txt ] && echo "✓ requirements.txt found" || echo "✗ requirements.txt missing"

echo ""
echo "[3] Checking Python environment..."
python --version
pip --version

echo ""
echo "[4] Installing Railway CLI (requires npm)..."
echo "    Checking for npm..."
if ! command -v npm &> /dev/null; then
    echo "✗ NPM not found. Install from https://nodejs.org"
else
    echo "✓ NPM found, installing @railway/cli..."
    npm install -g @railway/cli
    railway --version
fi

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║   NEXT STEPS                                                   ║"
echo "╠════════════════════════════════════════════════════════════════╣"
echo "║ 1. Push code to GitHub:                                        ║"
echo "║    git remote add origin https://github.com/YOUR/REPO.git     ║"
echo "║    git push -u origin main                                    ║"
echo "║                                                                ║"
echo "║ 2. Go to Railway: https://railway.app/dashboard               ║"
echo "║                                                                ║"
echo "║ 3. Create project → Deploy from GitHub                        ║"
echo "║                                                                ║"
echo "║ 4. Add environment variables in Railway:                      ║"
echo "║    - DATABASE_URL (your existing PostGIS)                     ║"
echo "║    - SECRET_KEY                                               ║"
echo "║    - JWT_SECRET_KEY                                           ║"
echo "║    - CLOUDINARY_CLOUD_NAME                                    ║"
echo "║    - CLOUDINARY_API_KEY                                       ║"
echo "║    - CLOUDINARY_API_SECRET                                    ║"
echo "║                                                                ║"
echo "║ 5. Railway will auto-deploy when you push to GitHub           ║"
echo "║                                                                ║"
echo "║ 6. Update Flutter app API URL to Railway service URL          ║"
echo "║                                                                ║"
echo "║ For detailed guide, see: DEPLOYMENT_GUIDE.md                  ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
