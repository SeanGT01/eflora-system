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


# Returned to clients when Gmail OAuth / outbound email fails during OTP flows.
EMAIL_SERVICE_UNAVAILABLE_CODE = 'email_service_unavailable'
EMAIL_SERVICE_UNAVAILABLE_MESSAGE = (
    "We couldn't send your verification email right now. "
    "This is a temporary system issue on our side — not a problem with your details. "
    "Please contact the developer or support team so they can restore email delivery, "
    "then try signing up again. "
    "Support: efloralaguna@gmail.com"
)


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


def generate_store_admin_password():
    chars = string.ascii_letters + string.digits
    suffix = ''.join(random.choices(chars, k=6))
    return f"Admin@{suffix}"


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
        try:
            refresh_token = app.config.get('GMAIL_REFRESH_TOKEN', '')
            
            if not refresh_token:
                current_app.logger.error(
                    f"❌ Gmail OAuth2 not configured. Please set GMAIL_REFRESH_TOKEN, GMAIL_CLIENT_ID, and GMAIL_CLIENT_SECRET environment variables."
                )
                return
            
            _send_email_gmail_oauth(recipient_email, subject, html_body, sender_email)
        except Exception as e:
            current_app.logger.error(f"❌ Error in _send_email_async for {recipient_email}: {e}")


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


def send_customer_otp_email(recipient_email, otp_code, full_name=None, expiry_minutes=10):
    """
    Send a 6-digit OTP code to a prospective customer for self-registration
    via the same Gmail OAuth2 pipeline used by the rider flow.
    """
    try:
        subject = "E-Flora - Confirm your email address"
        greeting = f"Hi {full_name}!" if full_name else "Hi there!"

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0;">&#127800; E-Flora</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 5px 0 0 0;">Email Verification</p>
            </div>

            <div style="background: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-top: none;">
                <h2 style="color: #333; margin-top: 0;">{greeting}</h2>

                <p style="color: #555; font-size: 16px;">
                    Welcome to E-Flora! Use the verification code below to finish creating
                    your customer account.
                </p>

                <div style="text-align: center; margin: 30px 0;">
                    <div style="display: inline-block; background: #f4f4f8; border: 2px dashed #667eea;
                                border-radius: 12px; padding: 20px 40px;">
                        <span style="font-family: 'Courier New', monospace; font-size: 36px; font-weight: bold;
                                     letter-spacing: 8px; color: #333;">{otp_code}</span>
                    </div>
                </div>

                <p style="color: #888; font-size: 14px; text-align: center;">
                    This code expires in <strong>{expiry_minutes} minutes</strong>.
                </p>

                <hr style="border: none; border-top: 1px solid #eee; margin: 25px 0;">

                <p style="color: #888; font-size: 13px;">
                    If you did not request this code, you can safely ignore this email.
                    No account will be created without verification.
                </p>
            </div>

            <div style="text-align: center; padding: 15px; background: #f9f9f9; border-radius: 0 0 10px 10px; border: 1px solid #e0e0e0; border-top: none;">
                <p style="color: #aaa; font-size: 12px; margin: 0;">
                    &copy; E-Flora Online Flower Shop
                </p>
            </div>
        </div>
        """

        sender = current_app.config.get('MAIL_DEFAULT_SENDER', 'noreply@eflowers.com')

        # Send synchronously so registration can fail loudly if Gmail OAuth is broken
        # (async queue previously returned success even when the background send failed).
        ok = _send_email_gmail_oauth(recipient_email, subject, html_body, sender)
        if ok:
            current_app.logger.info(f"📧 Customer OTP email sent to {recipient_email}")
        else:
            current_app.logger.error(f"❌ Customer OTP email failed for {recipient_email}")
        return ok

    except Exception as e:
        current_app.logger.error(f"❌ Failed to send customer OTP email for {recipient_email}: {e}")
        return False


def send_password_reset_otp_email(recipient_email, otp_code, full_name=None, expiry_minutes=10):
    """Send a 6-digit OTP for forgot-password via the Gmail OAuth pipeline."""
    try:
        subject = "E-Flora - Reset your password"
        greeting = f"Hi {full_name}!" if full_name else "Hi there!"

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #c24e68 0%, #d878a0 55%, #b070c8 100%); border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0;">&#127800; E-Flora</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 5px 0 0 0;">Password Reset</p>
            </div>

            <div style="background: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-top: none;">
                <h2 style="color: #333; margin-top: 0;">{greeting}</h2>

                <p style="color: #555; font-size: 16px;">
                    We received a request to reset your E-Flora password. Use the
                    verification code below to continue.
                </p>

                <div style="text-align: center; margin: 30px 0;">
                    <div style="display: inline-block; background: #f4f4f8; border: 2px dashed #c24e68;
                                border-radius: 12px; padding: 20px 40px;">
                        <span style="font-family: 'Courier New', monospace; font-size: 36px; font-weight: bold;
                                     letter-spacing: 8px; color: #333;">{otp_code}</span>
                    </div>
                </div>

                <p style="color: #888; font-size: 14px; text-align: center;">
                    This code expires in <strong>{expiry_minutes} minutes</strong>.
                </p>

                <hr style="border: none; border-top: 1px solid #eee; margin: 25px 0;">

                <p style="color: #888; font-size: 13px;">
                    If you did not request a password reset, you can safely ignore this email.
                    Your password will not change without this code.
                </p>
            </div>

            <div style="text-align: center; padding: 15px; background: #f9f9f9; border-radius: 0 0 10px 10px; border: 1px solid #e0e0e0; border-top: none;">
                <p style="color: #aaa; font-size: 12px; margin: 0;">
                    &copy; E-Flora Online Flower Shop
                </p>
            </div>
        </div>
        """

        sender = current_app.config.get('MAIL_DEFAULT_SENDER', 'noreply@eflowers.com')
        ok = _send_email_gmail_oauth(recipient_email, subject, html_body, sender)
        if ok:
            current_app.logger.info(f"📧 Password reset OTP email sent to {recipient_email}")
        else:
            current_app.logger.error(f"❌ Password reset OTP email failed for {recipient_email}")
        return ok

    except Exception as e:
        current_app.logger.error(f"❌ Failed to send password reset OTP for {recipient_email}: {e}")
        return False


def send_seller_signup_otp_email(recipient_email, otp_code, full_name=None, expiry_minutes=10):
    """Gmail OTP for standalone seller registration (same delivery pipeline as customer OTP)."""
    try:
        subject = "E-Flora Seller — verify your email"
        greeting = f"Hi {full_name}!" if full_name else "Hi there!"

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #2c2520 0%, #b5445a 100%); border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0;">&#127800; E-Flora Seller</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 5px 0 0 0;">Email verification</p>
            </div>

            <div style="background: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-top: none;">
                <h2 style="color: #333; margin-top: 0;">{greeting}</h2>

                <p style="color: #555; font-size: 16px;">
                    Use the code below to continue your seller application on E-Flora.
                </p>

                <div style="text-align: center; margin: 30px 0;">
                    <div style="display: inline-block; background: #f4f4f8; border: 2px dashed #b5445a;
                                border-radius: 12px; padding: 20px 40px;">
                        <span style="font-family: 'Courier New', monospace; font-size: 36px; font-weight: bold;
                                     letter-spacing: 8px; color: #333;">{otp_code}</span>
                    </div>
                </div>

                <p style="color: #888; font-size: 14px; text-align: center;">
                    This code expires in <strong>{expiry_minutes} minutes</strong>.
                </p>

                <hr style="border: none; border-top: 1px solid #eee; margin: 25px 0;">

                <p style="color: #888; font-size: 13px;">
                    If you did not start a seller application, you can ignore this email.
                </p>
            </div>

            <div style="text-align: center; padding: 15px; background: #f9f9f9; border-radius: 0 0 10px 10px; border: 1px solid #e0e0e0; border-top: none;">
                <p style="color: #aaa; font-size: 12px; margin: 0;">
                    &copy; E-Flora Online Flower Shop
                </p>
            </div>
        </div>
        """

        sender = current_app.config.get('MAIL_DEFAULT_SENDER', 'noreply@eflowers.com')

        ok = _send_email_gmail_oauth(recipient_email, subject, html_body, sender)
        if ok:
            current_app.logger.info(f"📧 Seller signup OTP email sent to {recipient_email}")
        else:
            current_app.logger.error(f"❌ Seller signup OTP email failed for {recipient_email}")
        return ok

    except Exception as e:
        current_app.logger.error(f"❌ Failed to send seller signup OTP for {recipient_email}: {e}")
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


def send_store_admin_otp_email(recipient_email, otp_code, store_name, seller_name):
    """6-digit OTP for inviting a store admin (seller dashboard)."""
    try:
        subject = f"E-Flora Store Admin Verification Code - {store_name}"
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #b5445a 0%, #d4788a 100%); border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0;">&#127800; E-Flora</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 5px 0 0 0;">Store Admin Verification Code</p>
            </div>
            <div style="background: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-top: none;">
                <h2 style="color: #333; margin-top: 0;">Hello!</h2>
                <p style="color: #555; font-size: 16px;">
                    <strong>{seller_name}</strong> from <strong>{store_name}</strong> is setting up your
                    store admin account on E-Flora. Share this code with the store owner so they can verify you.
                </p>
                <div style="text-align: center; margin: 30px 0;">
                    <div style="display: inline-block; background: #f4f4f8; border: 2px dashed #b5445a;
                                border-radius: 12px; padding: 20px 40px;">
                        <span style="font-family: 'Courier New', monospace; font-size: 36px; font-weight: bold;
                                     letter-spacing: 8px; color: #333;">{otp_code}</span>
                    </div>
                </div>
                <p style="color: #888; font-size: 14px; text-align: center;">
                    This code expires in <strong>10 minutes</strong>.
                </p>
            </div>
        </div>
        """
        sender = current_app.config.get('MAIL_DEFAULT_SENDER', 'noreply@eflowers.com')
        app = current_app._get_current_object()
        thread = threading.Thread(
            target=_send_email_async,
            args=(app, recipient_email, subject, html_body, sender)
        )
        thread.daemon = True
        thread.start()
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to queue store admin OTP email: {e}")
        return False


def send_store_admin_credentials_email(recipient_email, full_name, default_password, store_name):
    try:
        subject = f"E-Flora Store Admin Account - {store_name}"
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #b5445a 0%, #d4788a 100%); border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0;">&#127800; E-Flora</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 5px 0 0 0;">Welcome, Store Admin!</p>
            </div>
            <div style="background: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-top: none;">
                <h2 style="color: #333; margin-top: 0;">Hi {full_name}!</h2>
                <p style="color: #555; font-size: 16px;">
                    Your store admin account for <strong>{store_name}</strong> is ready.
                    Log in on the E-Flora website with:
                </p>
                <div style="background: #f4f4f8; border-radius: 10px; padding: 20px; margin: 25px 0;">
                    <p style="margin: 0 0 8px;"><strong>Login:</strong> {recipient_email}</p>
                    <p style="margin: 0;"><strong>Password:</strong> {default_password}</p>
                </div>
                <p style="color: #888; font-size: 13px;">Please change your password after you sign in.</p>
            </div>
        </div>
        """
        sender = current_app.config.get('MAIL_DEFAULT_SENDER', 'noreply@eflowers.com')
        app = current_app._get_current_object()
        thread = threading.Thread(
            target=_send_email_async,
            args=(app, recipient_email, subject, html_body, sender)
        )
        thread.daemon = True
        thread.start()
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to queue store admin credentials email: {e}")
        return False


def send_stock_alert_email(
    recipient_email: str,
    seller_name: str,
    store_name: str,
    product_name: str,
    current_stock: int,
    alert_type: str = 'low_stock',
    threshold: int = 5,
    variant_name: str = None,
    addon_name: str = None,
    product_id: int = None,
    image_url: str = None,
) -> bool:
    """
    Send low stock or out of stock email notification to seller via the same Gmail OAuth pipeline
    used for registration OTPs.
    """
    try:
        is_out_of_stock = (alert_type == 'out_of_stock' or current_stock <= 0)
        
        # Build display item name
        if variant_name:
            item_display_name = f"{product_name} ({variant_name})"
            item_subdetail = f"Variant: <strong>{variant_name}</strong>"
        elif addon_name:
            item_display_name = f"{product_name} - {addon_name}"
            item_subdetail = f"Add-on Option: <strong>{addon_name}</strong>"
        else:
            item_display_name = product_name
            item_subdetail = None

        if is_out_of_stock:
            subject = f"🚨 [Out of Stock Alert] {item_display_name} has reached 0 units — {store_name}"
            badge_bg = "#fee2e2"
            badge_color = "#b91c1c"
            badge_border = "#fca5a5"
            badge_text = "0 Units (Out of Stock)"
            banner_gradient = "linear-gradient(135deg, #7f1d1d 0%, #b91c1c 50%, #dc2626 100%)"
            banner_icon = "&#128680;"  # 🚨
            banner_title = "Out of Stock Alert"
            banner_sub = f"Urgent restock needed for {store_name}"
            notice_text = (
                f"Your inventory item <strong>{item_display_name}</strong> has completely run out of stock "
                f"(<strong>0 units remaining</strong>). Customers browsing your store cannot purchase this item until stock is replenished."
            )
        else:
            subject = f"⚠️ [Low Stock Alert] {item_display_name} is running low ({current_stock} left) — {store_name}"
            badge_bg = "#fef3c7"
            badge_color = "#92400e"
            badge_border = "#fcd34d"
            badge_text = f"{current_stock} Units Remaining"
            banner_gradient = "linear-gradient(135deg, #78350f 0%, #b45309 50%, #d97706 100%)"
            banner_icon = "&#9888;&#65039;"  # ⚠️
            banner_title = "Low Stock Alert"
            banner_sub = f"Inventory threshold crossed for {store_name}"
            notice_text = (
                f"Your inventory item <strong>{item_display_name}</strong> has dropped to <strong>{current_stock} unit{'s' if current_stock != 1 else ''}</strong>, "
                f"crossing your store's low stock threshold of <strong>{threshold} units</strong>. Please consider restocking soon to prevent stockouts."
            )

        # Base URL resolution
        base_url = (current_app.config.get('APP_BASE_URL') or '').strip().rstrip('/')
        if not base_url:
            try:
                base_url = request.host_url.rstrip('/')
            except Exception:
                base_url = 'https://eflowers.ph'

        inventory_url = f"{base_url}/seller/inventory"

        # Item image markup
        img_src = None
        if image_url and str(image_url).strip():
            clean_url = str(image_url).strip()
            # If Cloudinary URL, convert to universal email-safe JPEG square thumbnail
            if 'res.cloudinary.com' in clean_url and '/image/upload/' in clean_url:
                try:
                    import re
                    parts = clean_url.split('/image/upload/')
                    base_part = parts[0] + '/image/upload/'
                    rest = parts[1]
                    segments = rest.split('/')
                    if len(segments) > 1 and not re.match(r'^v\d+$', segments[0]):
                        rest = '/'.join(segments[1:])
                    clean_url = f"{base_part}f_jpg,q_auto,w_160,h_160,c_fill/{rest}"
                except Exception:
                    pass
            elif not clean_url.startswith(('http://', 'https://')):
                clean_url = f"{base_url}/{clean_url.lstrip('/')}"
            img_src = clean_url

        if img_src:
            img_html = f"""
            <td style="width: 80px; min-width: 80px; vertical-align: middle; padding-right: 16px;">
                <a href="{inventory_url}" target="_blank" style="text-decoration: none; display: block;">
                    <img src="{img_src}" alt="{product_name}" width="76" height="76" style="width: 76px; height: 76px; min-width: 76px; max-width: 76px; border-radius: 8px; border: 1px solid #e2e8f0; object-fit: cover; display: block;" />
                </a>
            </td>
            """
        else:
            img_html = f"""
            <td style="width: 60px; min-width: 60px; vertical-align: middle; padding-right: 14px;">
                <a href="{inventory_url}" target="_blank" style="text-decoration: none; display: block;">
                    <div style="width: 56px; height: 56px; border-radius: 8px; background: #e0e7ff; color: #4338ca; display: flex; align-items: center; justify-content: center; font-size: 24px; text-align: center; line-height: 56px;">
                        &#127800;
                    </div>
                </a>
            </td>
            """

        subdetail_html = f'<p style="margin: 3px 0 0; font-size: 13px; color: #64748b;">{item_subdetail}</p>' if item_subdetail else ''

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{subject}</title>
        </head>
        <body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
            <div style="max-width: 600px; margin: 24px auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);">
                
                <!-- Alert Banner -->
                <div style="background: {banner_gradient}; padding: 28px 24px; text-align: center; color: #ffffff;">
                    <div style="font-size: 36px; line-height: 1; margin-bottom: 8px;">{banner_icon}</div>
                    <h1 style="margin: 0; font-size: 22px; font-weight: 700; letter-spacing: -0.01em; color: #ffffff;">{banner_title}</h1>
                    <p style="margin: 6px 0 0; font-size: 14px; color: rgba(255, 255, 255, 0.9); font-weight: 500;">{banner_sub}</p>
                </div>

                <!-- Main Content -->
                <div style="padding: 28px 24px;">
                    <p style="margin: 0 0 14px; font-size: 16px; color: #1e293b; font-weight: 600;">
                        Hi {seller_name or 'Store Manager'},
                    </p>
                    
                    <p style="margin: 0 0 22px; font-size: 14px; color: #475569; line-height: 1.6;">
                        {notice_text}
                    </p>

                    <!-- Item Summary Box -->
                    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 18px; margin-bottom: 24px;">
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                {img_html}
                                <td style="vertical-align: middle;">
                                    <h3 style="margin: 0; font-size: 16px; font-weight: 700; color: #0f172a;">{product_name}</h3>
                                    {subdetail_html}
                                    <div style="margin-top: 10px;">
                                        <span style="display: inline-block; background-color: {badge_bg}; color: {badge_color}; border: 1px solid {badge_border}; font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 6px; letter-spacing: 0.02em;">
                                            {badge_text}
                                        </span>
                                    </div>
                                    <p style="margin: 8px 0 0; font-size: 12px; color: #64748b;">
                                        <strong>Store:</strong> {store_name} &bull; <strong>Threshold:</strong> {threshold} units
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </div>

                    <!-- Call to action button -->
                    <div style="text-align: center; margin: 26px 0 16px;">
                        <a href="{inventory_url}" 
                           style="display: inline-block; background: #15803d; color: #ffffff; text-decoration: none; padding: 13px 32px; border-radius: 8px; font-size: 15px; font-weight: 600; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                            &#128230; Open Seller Inventory
                        </a>
                    </div>

                    <p style="margin: 0; font-size: 12px; color: #94a3b8; text-align: center; line-height: 1.5;">
                        Clicking the button will take you directly to your inventory management screen where you can add stock.
                    </p>
                </div>

                <!-- Footer -->
                <div style="background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 18px 24px; text-align: center;">
                    <p style="margin: 0 0 4px; font-size: 12px; font-weight: 600; color: #64748b;">
                        &#127800; E-Flora Online Delivery System
                    </p>
                    <p style="margin: 0; font-size: 11px; color: #94a3b8;">
                        This automated notification was sent to <strong>{recipient_email}</strong> via E-Flora's Gmail alert service.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        sender = current_app.config.get('GMAIL_SENDER_EMAIL') or current_app.config.get('MAIL_DEFAULT_SENDER', 'eflowers.verification@gmail.com')

        app = current_app._get_current_object()
        thread = threading.Thread(
            target=_send_email_async,
            args=(app, recipient_email, subject, html_body, sender)
        )
        thread.daemon = True
        thread.start()

        current_app.logger.info(f"📧 Stock alert email ({alert_type}) queued for {recipient_email}")
        return True

    except Exception as e:
        current_app.logger.error(f"❌ Failed to queue stock alert email for {recipient_email}: {e}")
        return False



def send_email_bind_otp_email(recipient_email, otp_code, full_name=None, store_name=None, expiry_minutes=10):
    """
    Send a 6-digit OTP code to verify and bind a Gmail address to a seller account.
    Once verified, inventory alerts and business notifications are delivered to this email.
    """
    try:
        subject = "E-Flora — Verify your store alert email"
        greeting = f"Hi {full_name}!" if full_name else "Hello!"
        store_clause = f" for <strong>{store_name}</strong>" if store_name else ""

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{subject}</title>
        </head>
        <body style="margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #faf6f0; color: #2c2520;">
            <div style="max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 14px; overflow: hidden; box-shadow: 0 4px 20px rgba(44, 37, 32, 0.08); border: 1px solid rgba(181, 68, 90, 0.15);">
                
                <!-- Header -->
                <div style="background: linear-gradient(135deg, #2c2520 0%, #b5445a 100%); padding: 26px 24px; text-align: center;">
                    <h1 style="color: #ffffff; margin: 0; font-size: 22px; font-weight: 700; letter-spacing: 0.5px;">
                        &#127800; E-FLORA SELLER PORTAL
                    </h1>
                    <p style="color: rgba(255, 255, 255, 0.88); margin: 6px 0 0; font-size: 13px;">
                        Store Notification Email Verification
                    </p>
                </div>

                <!-- Body -->
                <div style="padding: 28px 24px;">
                    <h2 style="color: #2c2520; font-size: 18px; margin: 0 0 12px; font-weight: 600;">{greeting}</h2>

                    <p style="margin: 0 0 14px; font-size: 14px; color: #554841; line-height: 1.6;">
                        You requested to connect this Gmail address to your E-Flora seller account{store_clause}.
                        Once connected, you will receive real-time <strong>low-stock</strong> and <strong>out-of-stock</strong> picture alerts directly in this inbox.
                    </p>

                    <p style="margin: 0 0 20px; font-size: 14px; color: #554841; line-height: 1.6;">
                        Please enter the 6-digit verification code below in your seller dashboard to complete the connection:
                    </p>

                    <!-- OTP Code Box -->
                    <div style="text-align: center; margin: 24px 0;">
                        <div style="display: inline-block; background: #fff5f7; border: 2px dashed #b5445a; border-radius: 12px; padding: 18px 36px;">
                            <span style="font-family: 'Courier New', Courier, monospace; font-size: 34px; font-weight: 700; letter-spacing: 8px; color: #b5445a;">{otp_code}</span>
                        </div>
                    </div>

                    <p style="margin: 0; font-size: 13px; color: #9a8d85; text-align: center;">
                        This code will expire in <strong>{expiry_minutes} minutes</strong>.
                    </p>

                    <div style="margin: 24px 0 0; padding-top: 18px; border-top: 1px solid #f1ece5;">
                        <p style="margin: 0; font-size: 12px; color: #9a8d85; line-height: 1.5;">
                            &#128274; <strong>Security note:</strong> If you did not request to connect this email to an E-Flora store, please ignore this message. No changes will be made to any account without this verification code.
                        </p>
                    </div>
                </div>

                <!-- Footer -->
                <div style="background-color: #fbf8f5; border-top: 1px solid #f1ece5; padding: 16px 24px; text-align: center;">
                    <p style="margin: 0 0 4px; font-size: 12px; font-weight: 600; color: #6b4c3b;">
                        &#127800; E-Flora Online Flower Marketplace
                    </p>
                    <p style="margin: 0; font-size: 11px; color: #9a8d85;">
                        Automated verification email sent via E-Flora's Gmail notification service.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        sender = current_app.config.get('GMAIL_SENDER_EMAIL') or current_app.config.get('MAIL_DEFAULT_SENDER', 'eflowers.verification@gmail.com')
        ok = _send_email_gmail_oauth(recipient_email, subject, html_body, sender)
        if ok:
            current_app.logger.info(f"📧 Email bind OTP sent to {recipient_email}")
        else:
            current_app.logger.error(f"❌ Failed to send email bind OTP to {recipient_email}")
        return ok

    except Exception as e:
        current_app.logger.error(f"❌ Error in send_email_bind_otp_email for {recipient_email}: {e}")
        return False


def _send_smtp_only_async(app, recipient_email, subject, html_body, sender_email):
    """Deprecated: SMTP is blocked on Railway. Use SendGrid instead."""
    with app.app_context():
        current_app.logger.warning(f"⚠️  SMTP not available on production. Ensure SENDGRID_API_KEY is configured.")

