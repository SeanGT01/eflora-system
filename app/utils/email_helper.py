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


def _send_email_gmail_api(recipient_email, subject, html_body, sender_email):
    """
    Send email via Gmail API (free, no DMARC issues, works on Railway).
    Requires valid Google service account credentials and OAuth2 setup.
    """
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        
        gmail_creds = current_app.config.get('GMAIL_API_CREDENTIALS', '')
        sender_email_override = current_app.config.get('GMAIL_SENDER_EMAIL', '')
        
        if not gmail_creds or not sender_email_override:
            current_app.logger.error("❌ Gmail API: Missing GMAIL_API_CREDENTIALS or GMAIL_SENDER_EMAIL config")
            return False
        
        # Parse credentials (could be base64 encoded or raw JSON string)
        try:
            if gmail_creds.startswith('{'):
                # Raw JSON string
                creds_dict = json.loads(gmail_creds)
            else:
                # Try base64 decoding
                creds_dict = json.loads(base64.b64decode(gmail_creds).decode('utf-8'))
        except Exception as e:
            current_app.logger.error(f"❌ Gmail API: Invalid credentials format: {e}")
            return False
        
        # Create service account credentials
        credentials = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/gmail.send']
        )
        
        service = build('gmail', 'v1', credentials=credentials)
        
        # Create MIME message - use service account email as sender (no domain-wide delegation needed)
        from email.mime.text import MIMEText
        message = MIMEText(html_body, 'html')
        message['to'] = recipient_email
        message['from'] = sender_email_override  # Service account email
        message['subject'] = subject
        
        # Send via Gmail API
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        send_message = {'raw': raw}
        # Use the service account's email (extracted from credentials) as userId instead of 'me'
        service_account_email = creds_dict.get('client_email', sender_email_override)
        service.users().messages().send(userId=service_account_email, body=send_message).execute()
        
        current_app.logger.info(f"✅ Email sent via Gmail API to {recipient_email}")
        return True
        
    except Exception as e:
        current_app.logger.error(f"❌ Gmail API error: {type(e).__name__}: {e}")
        return False








def _send_email_async(app, recipient_email, subject, html_body, sender_email):
    """Send email in background thread via Gmail API."""
    with app.app_context():
        gmail_creds = app.config.get('GMAIL_API_CREDENTIALS', '')
        
        if not gmail_creds or not app.config.get('GMAIL_SENDER_EMAIL'):
            current_app.logger.error(
                f"❌ Gmail API not configured. Please set GMAIL_API_CREDENTIALS and GMAIL_SENDER_EMAIL environment variables."
            )
            return
        
        _send_email_gmail_api(recipient_email, subject, html_body, sender_email)


def send_rider_verification_email(recipient_email, verification_token, store_name, seller_name):
    """
    Send a verification link email to a new rider (async via thread via Gmail API).
    """
    try:
        base_url = current_app.config.get('APP_BASE_URL') or request.host_url.rstrip('/')
        verify_url = f"{base_url.rstrip('/')}/verify-rider/{verification_token}"
        subject = f"E-Flowers Rider Invitation - {store_name}"
        
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0;">&#127800; E-Flowers</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 5px 0 0 0;">Rider Account Invitation</p>
            </div>
            
            <div style="background: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-top: none;">
                <h2 style="color: #333; margin-top: 0;">Hello!</h2>
                
                <p style="color: #555; font-size: 16px;">
                    <strong>{seller_name}</strong> from <strong>{store_name}</strong> has invited you 
                    to join as a delivery rider on E-Flowers.
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
                    &copy; E-Flowers Delivery System
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
    Send a 6-digit OTP code to a rider's email via Gmail API.
    The seller will then enter this OTP on the dashboard to verify.
    """
    try:
        subject = f"E-Flowers Rider Verification Code - {store_name}"

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0;">&#127800; E-Flowers</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 5px 0 0 0;">Rider Verification Code</p>
            </div>

            <div style="background: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-top: none;">
                <h2 style="color: #333; margin-top: 0;">Hello!</h2>

                <p style="color: #555; font-size: 16px;">
                    <strong>{seller_name}</strong> from <strong>{store_name}</strong> is setting up your
                    rider account on E-Flowers. Please share the verification code below with your seller.
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
                    &copy; E-Flowers Delivery System
                </p>
            </div>
        </div>
        """

        sender = current_app.config.get('MAIL_DEFAULT_SENDER', 'noreply@eflowers.com')

        # Send via Gmail API
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
    Send rider their account credentials after successful OTP verification via Gmail API.
    """
    try:
        subject = f"E-Flowers Rider Account Created - {store_name}"

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0;">&#127800; E-Flowers</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 5px 0 0 0;">Welcome, Rider!</p>
            </div>

            <div style="background: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-top: none;">
                <h2 style="color: #333; margin-top: 0;">Hi {full_name}!</h2>

                <p style="color: #555; font-size: 16px;">
                    Your rider account for <strong>{store_name}</strong> has been successfully created.
                    You can now log in to the E-Flowers app using the credentials below.
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
                    &copy; E-Flowers Delivery System
                </p>
            </div>
        </div>
        """

        sender = current_app.config.get('MAIL_DEFAULT_SENDER', 'noreply@eflowers.com')

        # Send via Gmail API
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
