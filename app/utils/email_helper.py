import random
import secrets
import threading
import time
import base64
import json
import string
from datetime import datetime
from flask import current_app, url_for, request
from flask_mail import Message
from app.extensions import mail


def generate_verification_token():
    """Generate a secure URL-safe verification token."""
    return secrets.token_urlsafe(32)


def generate_otp_code():
    """Generate a 6-digit numeric OTP code."""
    return ''.join(random.choices(string.digits, k=6))


def generate_default_password():
    """Generate a random default password for rider accounts."""
    chars = string.ascii_letters + string.digits
    suffix = ''.join(random.choices(chars, k=6))
    return f"Rider@{suffix}"


def _get_gmail_access_token():
    """
    Get a fresh Gmail API access token using the refresh token.
    Returns: access_token or None if failed
    """
    try:
        import requests
        
        refresh_token = current_app.config.get('GMAIL_REFRESH_TOKEN', '')
        client_id = current_app.config.get('GMAIL_CLIENT_ID', '')
        client_secret = current_app.config.get('GMAIL_CLIENT_SECRET', '')
        
        if not refresh_token or not client_id or not client_secret:
            current_app.logger.error("❌ Gmail OAuth2: Missing GMAIL_REFRESH_TOKEN, GMAIL_CLIENT_ID, or GMAIL_CLIENT_SECRET")
            return None
        
        token_url = 'https://oauth2.googleapis.com/token'
        payload = {
            'client_id': client_id,
            'client_secret': client_secret,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token'
        }
        
        response = requests.post(token_url, data=payload, timeout=10)
        
        if response.status_code == 200:
            token_data = response.json()
            access_token = token_data.get('access_token')
            current_app.logger.info("✅ Gmail OAuth2: Got new access token")
            return access_token
        else:
            current_app.logger.error(f"❌ Gmail OAuth2: Failed to refresh token - {response.status_code}: {response.text}")
            return None
            
    except Exception as e:
        current_app.logger.error(f"❌ Gmail OAuth2 error: {type(e).__name__}: {e}")
        return None


def _send_email_gmail_oauth(recipient_email, subject, html_body, sender_email):
    """
    Send email via Gmail API using OAuth2 refresh token.
    No domain-wide delegation needed - works with regular Gmail accounts.
    """
    try:
        from googleapiclient.discovery import build
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        
        # Get fresh access token using refresh token
        access_token = _get_gmail_access_token()
        if not access_token:
            return False
        
        # Create credentials object with just the access token
        credentials = Credentials(token=access_token)
        service = build('gmail', 'v1', credentials=credentials)
        
        # Create MIME message
        from email.mime.text import MIMEText
        message = MIMEText(html_body, 'html')
        message['to'] = recipient_email
        message['from'] = sender_email
        message['subject'] = subject
        
        # Send via Gmail API
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        send_message = {'raw': raw}
        service.users().messages().send(userId='me', body=send_message).execute()
        
        current_app.logger.info(f"✅ Email sent via Gmail OAuth2 API to {recipient_email}")
        return True
        
    except Exception as e:
        current_app.logger.error(f"❌ Gmail OAuth2 API error: {type(e).__name__}: {e}")
        return False


def _send_email_async(app, recipient_email, subject, html_body, sender_email):
    """Send email in background thread via Gmail OAuth2 API."""
    with app.app_context():
        refresh_token = app.config.get('GMAIL_REFRESH_TOKEN', '')
        
        if not refresh_token:
            current_app.logger.error(
                f"❌ Gmail OAuth2 not configured. Please set GMAIL_REFRESH_TOKEN, GMAIL_CLIENT_ID, and GMAIL_CLIENT_SECRET environment variables."
            )
            return
        
        _send_email_gmail_oauth(recipient_email, subject, html_body, sender_email)


def send_rider_verification_email(recipient_email, verification_token, store_name, seller_name):
    """
    Send a verification link email to a new rider (async via thread).
    Uses SendGrid for production, SMTP for local development.
    """
    try:
        base_url = current_app.config.get('APP_BASE_URL') or request.host_url.rstrip('/')
        verify_url = f"{base_url.rstrip('/')}/verify-rider/{verification_token}"
        subject = f"E-Flora Rider Invitation - {store_name}"
        
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0;">&#127800; E-Flora</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 5px 0 0 0;">Rider Account Invitation</p>
            </div>
            
            <div style="background: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-top: none;">
                <h2 style="color: #333; margin-top: 0;">Hello!</h2>
                
                <p style="color: #555; font-size: 16px;">
                    <strong>{seller_name}</strong> from <strong>{store_name}</strong> has invited you 
                    to join as a delivery rider on E-Flora.
                </p>
                
                <p style="color: #555; font-size: 16px;">
                    Click the button below to verify your account and get started:
                </p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{verify_url}" 
                       style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                              color: white; text-decoration: none; padding: 16px 48px; border-radius: 8px; 
                              font-size: 18px; font-weight: bold; letter-spacing: 0.5px;">
                        &#10003; Verify My Account
                    </a>
                </div>
                
                <p style="color: #888; font-size: 14px; text-align: center;">
                    This invitation expires in <strong>24 hours</strong>.
                </p>
                
                <p style="color: #888; font-size: 12px; text-align: center; word-break: break-all;">
                    If the button doesn't work, copy and paste this link:<br>
                    <a href="{verify_url}" style="color: #667eea;">{verify_url}</a>
                </p>
                
                <hr style="border: none; border-top: 1px solid #eee; margin: 25px 0;">
                
                <p style="color: #888; font-size: 13px;">
                    If you did not expect this email, you can safely ignore it. 
                    No account will be created without verification.
                </p>
            </div>
            
            <div style="text-align: center; padding: 15px; background: #f9f9f9; border-radius: 0 0 10px 10px; border: 1px solid #e0e0e0; border-top: none;">
                <p style="color: #aaa; font-size: 12px; margin: 0;">
                    &copy; E-Flora Delivery System
                </p>
            </div>
        </div>
        """
        
        sender = current_app.config.get('MAIL_DEFAULT_SENDER', 'noreply@eflowers.com')
        
        # Send in background thread
        app = current_app._get_current_object()
        thread = threading.Thread(
            target=_send_email_async,
            args=(app, recipient_email, subject, html_body, sender)
        )
        thread.daemon = True
        thread.start()
        
        current_app.logger.info(f"📧 Email sending queued for {recipient_email}")
        return True
        
    except Exception as e:
        current_app.logger.error(f"❌ Failed to queue email for {recipient_email}: {e}")
        return False


def send_rider_otp_email(recipient_email, otp_code, store_name, seller_name):
    """
    Send a 6-digit OTP code to a rider's email via SMTP.
    The seller will then enter this OTP on the dashboard to verify.
    """
    try:
        subject = f"E-Flora Rider Verification Code - {store_name}"

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0;">&#127800; E-Flora</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 5px 0 0 0;">Rider Verification Code</p>
            </div>

            <div style="background: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-top: none;">
                <h2 style="color: #333; margin-top: 0;">Hello!</h2>

                <p style="color: #555; font-size: 16px;">
                    <strong>{seller_name}</strong> from <strong>{store_name}</strong> is setting up your
                    rider account on E-Flora. Please share the verification code below with your seller.
                </p>

                <div style="text-align: center; margin: 30px 0;">
                    <div style="display: inline-block; background: #f4f4f8; border: 2px dashed #667eea;
                                border-radius: 12px; padding: 20px 40px;">
                        <span style="font-family: 'Courier New', monospace; font-size: 36px; font-weight: bold;
                                     letter-spacing: 8px; color: #333;">{otp_code}</span>
                    </div>
                </div>

                <p style="color: #888; font-size: 14px; text-align: center;">
                    This code expires in <strong>10 minutes</strong>.
                </p>

                <hr style="border: none; border-top: 1px solid #eee; margin: 25px 0;">

                <p style="color: #888; font-size: 13px;">
                    If you did not expect this email, you can safely ignore it.
                    No account will be created without verification.
                </p>
            </div>

            <div style="text-align: center; padding: 15px; background: #f9f9f9; border-radius: 0 0 10px 10px; border: 1px solid #e0e0e0; border-top: none;">
                <p style="color: #aaa; font-size: 12px; margin: 0;">
                    &copy; E-Flora Delivery System
                </p>
            </div>
        </div>
        """

        sender = current_app.config.get('MAIL_DEFAULT_SENDER', 'noreply@eflowers.com')

        # Send via SendGrid (SMTP blocked on Railway)
        app = current_app._get_current_object()
        thread = threading.Thread(
            target=_send_email_async,
            args=(app, recipient_email, subject, html_body, sender)
        )
        thread.daemon = True
        thread.start()

        current_app.logger.info(f"📧 OTP email queued for {recipient_email}")
        return True

    except Exception as e:
        current_app.logger.error(f"❌ Failed to queue OTP email for {recipient_email}: {e}")
        return False


def send_rider_credentials_email(recipient_email, full_name, default_password, store_name):
    """
    Send rider their account credentials after successful OTP verification via SendGrid.
    """
    try:
        subject = f"E-Flora Rider Account Created - {store_name}"

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0;">&#127800; E-Flora</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 5px 0 0 0;">Welcome, Rider!</p>
            </div>

            <div style="background: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-top: none;">
                <h2 style="color: #333; margin-top: 0;">Hi {full_name}!</h2>

                <p style="color: #555; font-size: 16px;">
                    Your rider account for <strong>{store_name}</strong> has been successfully created.
                    You can now log in to the E-Flora app using the credentials below.
                </p>

                <div style="background: #f4f4f8; border-radius: 10px; padding: 20px; margin: 25px 0;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0; color: #888; font-size: 14px; width: 120px;">Email:</td>
                            <td style="padding: 8px 0; color: #333; font-size: 16px; font-weight: bold;">{recipient_email}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #888; font-size: 14px;">Password:</td>
                            <td style="padding: 8px 0; font-family: 'Courier New', monospace; font-size: 18px; font-weight: bold; color: #333;">{default_password}</td>
                        </tr>
                    </table>
                </div>

                <p style="color: #c0392b; font-size: 14px; text-align: center;">
                    &#9888; Please change your password after logging in for security.
                </p>

                <hr style="border: none; border-top: 1px solid #eee; margin: 25px 0;">

                <p style="color: #888; font-size: 13px;">
                    If you have any questions, please contact the store seller directly.
                </p>
            </div>

            <div style="text-align: center; padding: 15px; background: #f9f9f9; border-radius: 0 0 10px 10px; border: 1px solid #e0e0e0; border-top: none;">
                <p style="color: #aaa; font-size: 12px; margin: 0;">
                    &copy; E-Flora Delivery System
                </p>
            </div>
        </div>
        """

        sender = current_app.config.get('MAIL_DEFAULT_SENDER', 'noreply@eflowers.com')

        # Send via SendGrid (SMTP blocked on Railway)
        app = current_app._get_current_object()
        thread = threading.Thread(
            target=_send_email_async,
            args=(app, recipient_email, subject, html_body, sender)
        )
        thread.daemon = True
        thread.start()

        current_app.logger.info(f"📧 Credentials email queued for {recipient_email}")
        return True

    except Exception as e:
        current_app.logger.error(f"❌ Failed to queue credentials email for {recipient_email}: {e}")
        return False


def _send_smtp_only_async(app, recipient_email, subject, html_body, sender_email):
    """Deprecated: SMTP is blocked on Railway. Use SendGrid instead."""
    with app.app_context():
        current_app.logger.warning(f"⚠️  SMTP not available on production. Ensure SENDGRID_API_KEY is configured.")
