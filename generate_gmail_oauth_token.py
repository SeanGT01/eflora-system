#!/usr/bin/env python3
"""
Generate Gmail OAuth2 refresh token for email sending.
Run this ONCE locally to get the refresh token, then save it in Railway Variables.

Steps:
1. Go to https://console.cloud.google.com
2. Create a new project
3. Enable Gmail API
4. Create OAuth2 Desktop app credentials
5. Download the client_secret.json file
6. Edit the paths below to point to your client_secret.json
7. Run this script
8. Browser will open - log in with your Gmail account
9. Copy the refresh_token and save to Railway
"""

import os
import pickle
import base64
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Path to your Google OAuth2 credentials JSON file
CLIENT_SECRET_FILE = 'client_secret.json'  # Download from Google Cloud Console
OAUTH_SCOPES = ['https://www.googleapis.com/auth/gmail.send']
TOKEN_PICKLE_FILE = 'gmail_token.pickle'

def generate_refresh_token():
    """
    Generate Gmail OAuth2 refresh token.
    Opens browser for user to authorize, then saves tokens.
    """
    creds = None
    
    # Load existing token if available
    if os.path.exists(TOKEN_PICKLE_FILE):
        with open(TOKEN_PICKLE_FILE, 'rb') as token:
            creds = pickle.load(token)
    
    # If no valid credentials, get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Refreshing existing credentials...")
            creds.refresh(Request())
        else:
            print("🌐 Opening browser for Gmail authorization...")
            print(f"   Make sure {CLIENT_SECRET_FILE} exists in this directory!")
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE,
                OAUTH_SCOPES
            )
            
            # Try different ports in case 8080 is blocked/in use
            port = None
            for try_port in [8080, 8081, 8082, 8090, 9090]:
                try:
                    print(f"   Trying port {try_port}...")
                    creds = flow.run_local_server(port=try_port)
                    port = try_port
                    print(f"   ✓ Using port {port}")
                    break
                except OSError as e:
                    print(f"   Port {try_port} blocked/in use, trying next...")
                    continue
            
            if not creds:
                print("❌ Could not bind to any port (8080-9090)")
                print("   Your firewall or another app may be blocking local server.")
                print("   Try:")
                print("   1. Disable Windows Defender Firewall temporarily")
                print("   2. Or run from Admin PowerShell")
                exit(1)
        
        # Save the credentials for next time
        with open(TOKEN_PICKLE_FILE, 'wb') as token:
            pickle.dump(creds, token)
            print(f"✅ Credentials saved to {TOKEN_PICKLE_FILE}")
    
    # Extract and display the refresh token
    if creds.refresh_token:
        print("\n" + "="*70)
        print("✅ SUCCESS! Here's your Gmail OAuth2 refresh token:")
        print("="*70)
        print(f"\nRefresh Token:\n{creds.refresh_token}\n")
        print("="*70)
        print("\nNow add these to Railway Variables:")
        print("  GMAIL_REFRESH_TOKEN = (paste the token above)")
        print("  GMAIL_CLIENT_ID = (from your client_secret.json)")
        print("  GMAIL_CLIENT_SECRET = (from your client_secret.json)")
        print("\nTo find GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET:")
        print("  1. Open client_secret.json")
        print("  2. Copy the 'client_id' and 'client_secret' values")
        print("="*70)
        
        # Also save to file for reference
        with open('gmail_oauth_credentials.txt', 'w') as f:
            f.write(f"Refresh Token: {creds.refresh_token}\n")
            f.write(f"Access Token: {creds.token}\n")
            f.write(f"Token URI: {creds.token_uri}\n")
        print(f"\n💾 Credentials also saved to gmail_oauth_credentials.txt")
    else:
        print("❌ Failed to get refresh token. Try again.")

if __name__ == '__main__':
    generate_refresh_token()
