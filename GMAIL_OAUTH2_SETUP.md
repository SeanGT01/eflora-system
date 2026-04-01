# Gmail OAuth2 Setup Guide

This guide walks you through setting up Gmail OAuth2 for sending verification and OTP emails in eflowers.

## Overview

We're using Gmail OAuth2 (with refresh tokens) instead of SendGrid because:
- ✅ **Free** - No SendGrid API costs
- ✅ **Works on Railway** - SMTP blocked, but Gmail API works
- ✅ **Reliable** - Gmail's infrastructure, no DMARC issues
- ✅ **Scalable** - Can send up to 500 emails/day on free tier

## Prerequisites

You'll need:
- A Google Account (the @gmail.com address that will send emails)
- Google Cloud Account (free tier available)
- Python 3.7+ with pip

## Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a Project** → **New Project**
3. Name it `eflowers-email-service` (or similar)
4. Click **Create**
5. Wait for the project to be created

## Step 2: Enable Gmail API

1. In Google Cloud Console, go to **APIs & Services** → **Library**
2. Search for `Gmail API`
3. Click on **Gmail API**
4. Click **Enable**
5. Wait for it to be enabled

## Step 3: Create OAuth2 Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **+ Create Credentials** → **OAuth 2.0 Client IDs**
3. You'll see "To create an OAuth client ID, you must first set up the OAuth consent screen"
4. Click **Configure Consent Screen**

### Setting up the Consent Screen:

1. Choose **External** user type (unless you have a Google Workspace)
2. Click **Create**
3. Fill in the form:
   - **App name**: `eflowers Email Service`
   - **User support email**: (your Gmail address)
   - **Developer contact info**: (your Gmail address)
4. Click **Save and Continue** through all screens
5. Skip optional scopes/test users (not needed for this)
6. Review and click **Back to Dashboard**

### Create the OAuth Client:

1. Go back to **Credentials**
2. Click **+ Create Credentials** → **OAuth 2.0 Client IDs**
3. **Application type**: Select `Desktop app`
4. **Name**: `eflowers Email OAuth`
5. Click **Create**
6. You should see a dialog with your Client ID and Secret
7. Click **Download JSON** - save this as `client_secret.json` in the `eflowers-system` folder

## Step 4: Generate Refresh Token

1. Place the `client_secret.json` file in the `eflowers-system/` folder (same directory as `run.py`)

2. Run the token generation script:
   ```bash
   cd eflowers-system/
   python generate_gmail_oauth_token.py
   ```

3. A browser window will open asking for Gmail authorization

4. **Log in with the Gmail account** that will send the emails
   - If you created a new email for this, use that
   - Example: `eflowers.verification@gmail.com`

5. Review permissions and click **Allow**

6. The script will display:
   ```
   ✅ SUCCESS! Here's your Gmail OAuth2 refresh token:
   ============================================================
   Refresh Token: 1//0gX... (very long string)
   ============================================================
   ```

7. Copy the refresh token somewhere safe (you'll need it soon)

## Step 5: Get Client Credentials

1. Open the `client_secret.json` file you downloaded
2. Find and copy these values:
   - `"client_id"` → This is your `GMAIL_CLIENT_ID`
   - `"client_secret"` → This is your `GMAIL_CLIENT_SECRET`

Save all three values:
- `GMAIL_REFRESH_TOKEN` (from Step 4)
- `GMAIL_CLIENT_ID` (from client_secret.json)
- `GMAIL_CLIENT_SECRET` (from client_secret.json)

## Step 6: Add to Railway Environment

1. Go to [Railway Dashboard](https://railway.app/)
2. Open the `eflora-system-production` project
3. Click **Variables** (or **Plugins** → **Variables**)
4. Add the following variables:

   ```
   GMAIL_REFRESH_TOKEN = [paste from Step 4]
   GMAIL_CLIENT_ID = [paste from client_secret.json]
   GMAIL_CLIENT_SECRET = [paste from client_secret.json]
   GMAIL_SENDER_EMAIL = eflowers.verification@gmail.com
   ```

5. Click **Save** or **Deploy**

## Step 7: (Optional) Deploy to Production

If you made changes locally, deploy:

```bash
git add app/config.py
git commit -m "Update: Use Gmail OAuth2 for email sending"
git push origin main
```

Railway will automatically redeploy with the new environment variables.

## Testing Email Sending

Once variables are set, test by:

1. Creating a new rider account
2. Checking the rider's email for the OTP code
3. Checking the admin dashboard logs for any email errors

Expected log output:
```
🔐 Gmail OAuth2: Getting access token...
📧 Gmail OAuth2: Sending email to user@example.com
✅ Email sent successfully
```

## Troubleshooting

### Issue: "Precondition check failed" error
- **Cause**: Old service account configuration still in use
- **Fix**: Make sure env variables use GMAIL_REFRESH_TOKEN, not GMAIL_API_CREDENTIALS

### Issue: "Invalid grant" error
- **Cause**: Refresh token expired or invalid
- **Fix**: Run `python generate_gmail_oauth_token.py` again to get a new one

### Issue: "Invalid credentials" error
- **Cause**: GMAIL_CLIENT_ID or GMAIL_CLIENT_SECRET is wrong
- **Fix**: Copy the exact values from client_secret.json

### Issue: "Email quota exceeded"
- **Cause**: Sending more than 500 emails/day (Gmail free limit)
- **Fix**: Upgrade to Gmail business plan or implement email throttling

### Issue: "Failed to import google_auth_oauthlib"
- **Fix**: Install the required package:
   ```bash
   pip install google-auth-oauthlib google-auth-httplib2
   ```

## File References

- **Token generation script**: `generate_gmail_oauth_token.py`
- **Email sending logic**: `app/email_helper.py`
- **Configuration**: `app/config.py`
- **OAuth2 functions**:
  - `_get_gmail_access_token()` - Refreshes access token
  - `_send_email_gmail_oauth()` - Sends via Gmail API
  - `_send_email_async()` - Background thread wrapper

## Security Notes

⚠️ **Important**: Never commit environment variables to git!

- `.env` file should be in `.gitignore`
- Use Railway Variables for production secrets
- Rotate the refresh token annually for security

## Next Steps

- ✅ Set up Gmail OAuth2
- ✅ Test email sending on production
- (Optional) Implement email templates for better UX
- (Optional) Add email logging/analytics

---

**Questions?** Check the logs on Railway or test locally with:
```bash
python -m pytest tests/test_email.py
```
