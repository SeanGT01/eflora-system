# 🚀 E-Flowers System - Railway Deployment Guide

## ✅ Pre-Deployment Checklist

Before starting, ensure you have:
- [x] Railway CLI installed (`npm install -g @railway/cli`)
- [x] Railway account at https://railway.app
- [x] Your existing PostGIS database running on Railway
- [x] Cloudinary account for image uploads
- [x] Git repository initialized

---

## 📋 STEP-BY-STEP DEPLOYMENT INSTRUCTIONS

### **Step 1: Prepare Your Repository**

1. **Initialize Git** (if not already done):
```bash
cd c:\Users\seanm\OneDrive\Desktop\eflowers-system
git init
git add .
git commit -m "Initial commit: eflowers system ready for deployment"
```

2. **Create a `.gitignore`** file (if it doesn't exist):
```
venv/
__pycache__/
*.pyc
.env
.env.local
.DS_Store
*.log
logs/
build/
dist/
.dart_tool/
```

3. **Verify these files exist** (I created them for you):
   - ✅ `Dockerfile` - Container configuration
   - ✅ `railway.toml` - Railway deployment config
   - ✅ `requirements.txt` - Updated with gunicorn

---

### **Step 2: Set Up Environment Variables on Railway**

Your app needs these environment variables. You'll configure them in Railway:

| Variable | Value | Source |
|----------|-------|--------|
| `DATABASE_URL` | `postgresql://user:password@host:port/eflowers_db` | Your existing Railway PostGIS DB |
| `SECRET_KEY` | Generate a secure random string | Use `python -c "import secrets; print(secrets.token_hex(32))"` |
| `JWT_SECRET_KEY` | Generate another secure random string | Same as above |
| `CLOUDINARY_CLOUD_NAME` | Your Cloudinary cloud name | Cloudinary dashboard |
| `CLOUDINARY_API_KEY` | Your Cloudinary API key | Cloudinary dashboard |
| `CLOUDINARY_API_SECRET` | Your Cloudinary API secret | Cloudinary dashboard |
| `MAPBOX_PUBLIC_TOKEN` | Your Mapbox token | Mapbox dashboard (optional) |

---

### **Step 3: Push Code to GitHub (Recommended)**

Railway can deploy directly from GitHub:

```bash
# Create a GitHub repository first at github.com/new

# Then:
git remote add origin https://github.com/YOUR_USERNAME/eflowers-system.git
git branch -M main
git push -u origin main
```

---

### **Step 4: Deploy on Railway Using Web Interface** (EASIEST METHOD)

1. **Go to Railway Dashboard**: https://railway.app/dashboard

2. **Create a New Project**:
   - Click "Create New Project"
   - Choose "Deploy from GitHub"
   - Select your `eflowers-system` repository
   - Authorize Railway to access GitHub

3. **Configure Environment Variables**:
   - In Railway project → Variables
   - Add all variables from **Step 2** above
   - Make sure you have your existing PostGIS `DATABASE_URL`

4. **Railway Auto-Deploys**:
   - Once you push to GitHub, Railway automatically builds and deploys
   - Monitor the build in the "Deployments" tab

---

### **Step 5: Link Your Existing PostGIS Database**

**Important**: You already have a PostGIS database running on Railway. Link it:

1. In Railway Dashboard, open your eflowers project
2. Click **Add** → **Add Existing Service**
3. Select your existing PostgreSQL/PostGIS database
4. Railway will automatically set the `DATABASE_URL` variable

**Verify the connection string is correct:**
```
postgresql://user:password@host:5432/eflowers_db
```

---

### **Step 6: Run Database Migrations**

Once deployed, you need to run migrations:

**Option A: Using Railway CLI** (Recommended)
```bash
railway link              # Connect to your Railway project
railway run python -c "from app import create_app; from app.extensions import db; app = create_app(); db.create_all()"
```

**Option B: Using One-Off Dyno**
```bash
railway run flask db upgrade
```

---

### **Step 7: Verify Deployment**

1. **Get Your Railway URL**:
   - Go to Railway Dashboard → Your Project
   - Copy the "Web" service URL (e.g., `https://eflowers-prod.up.railway.app`)

2. **Test the API**:
```bash
curl https://eflowers-prod.up.railway.app/
```

3. **Check Health Status**:
```bash
curl https://eflowers-prod.up.railway.app/health
```

---

### **Step 8: Update Your Flutter App**

Update the API base URL in your Flutter app:

**File**: `lib/services/api_service.dart`

```dart
class ApiService {
  static const String baseUrl = 'https://eflowers-prod.up.railway.app';
  // Change from 'http://localhost:5000' to your Railway URL
}
```

Then rebuild:
```bash
flutter clean
flutter pub get
flutter run
```

---

## 🔧 ALTERNATIVE: Command-Line Deployment (Using Railway CLI)

If you prefer CLI:

```bash
# 1. Install Railway CLI
npm install -g @railway/cli

# 2. Login
railway login

# 3. Create new project
railway init

# 4. Configure environment variables
railway variables set DATABASE_URL "postgresql://..."
railway variables set SECRET_KEY "your-secret-key"
railway variables set CLOUDINARY_CLOUD_NAME "your-cloud-name"
# ... set all other variables

# 5. Deploy
railway up
```

---

## 🚨 TROUBLESHOOTING

### **Build Fails: "psycopg2 not found"**
- This is normal on first build (PostgreSQL client dependencies installing)
- Railway will retry automatically

### **Database Connection Error**
- Verify `DATABASE_URL` is exactly correct
- Check your Railway PostgreSQL service is running
- Make sure credentials include PostGIS

### **Static Files Not Loading**
- Your app uses Cloudinary, so no static file issues
- Verify Cloudinary credentials in environment variables

### **App Crashes on Startup**
- Check logs: `railway logs --service web`
- Verify all required environment variables are set
- Run migrations manually if needed

---

## 📊 Monitoring & Logs

View real-time logs:
```bash
railway logs --service web --follow
```

View deployment history:
- Railway Dashboard → Deployments tab

---

## 💡 Production Best Practices

1. ✅ Use strong `SECRET_KEY` and `JWT_SECRET_KEY`
2. ✅ Set `SESSION_COOKIE_SECURE = True` in config
3. ✅ Use HTTPS only (Railway handles this)
4. ✅ Monitor logs regularly
5. ✅ Set up error tracking (Sentry)
6. ✅ Backup your PostGIS database regularly

---

## 🎯 QUICK SUMMARY OF WHAT I CREATED FOR YOU

| File | Purpose |
|------|---------|
| `Dockerfile` | Builds Docker image with Python 3.11 + gunicorn |
| `railway.toml` | Tells Railway how to build & run your app |
| `requirements.txt` | Updated with `gunicorn` and `cloudinary` |

These files handle:
- ✅ Building with all dependencies
- ✅ Running with 4 workers (production-grade)
- ✅ Health checks
- ✅ Proper logging
- ✅ PORT environment variable support

---

## ✨ NEXT STEPS

1. **Push to GitHub** (if not already done)
2. **Open Railway.app → Create Project → Deploy from GitHub**
3. **Add environment variables** (copy from Step 2)
4. **Link your existing PostGIS database**
5. **Test your Flutter app** with the new URL
6. **Monitor logs** for any issues

**You're ready to go!** 🚀

---

## 📞 Need Help?

- Railway Docs: https://docs.railway.app/
- Flask Deployment: https://flask.palletsprojects.com/en/2.3.x/deploying/
- Railway Support: support@railway.app
