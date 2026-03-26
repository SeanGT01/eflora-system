import random
import secrets
import socket
import string
import threading
import smtplib
import time
from datetime import datetime
from flask import current_app, url_for, request
from flask_mail import Message
from app.extensions import mail

# ================================================================
# EMAIL THROTTLING (prevent SendGrid rate limits)
# ================================================================
_email_lock = threading.Lock()
_last_email_time = 0
_min_email_interval = 0.5  # Minimum 500ms between emails (120 emails/min max)

def _throttle_email():
    """Enforce minimum interval between email sends to avoid rate limiting."""
    global _last_email_time
    with _email_lock:
        now = time.time()
        time_since_last = now - _last_email_time
        if time_since_last < _min_email_interval:
            sleep_time = _min_email_interval - time_since_last
            current_app.logger.info(f"⏳ Email throttle: sleeping {sleep_time:.2f}s to avoid rate limits")
            time.sleep(sleep_time)
        _last_email_time = time.time()


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


def _send_email_sendgrid(recipient_email, subject, html_body, sender_email, retry_count=0, max_retries=3):
    """
    Send email via SendGrid API with exponential backoff for rate limits.
    
    Handles 429 (rate limit) responses by waiting and retrying.
    """
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail
        
        sendgrid_api_key = current_app.config.get('SENDGRID_API_KEY')
        if not sendgrid_api_key:
            return False
        
        # Apply throttling to space out requests
        _throttle_email()
        
        message = Mail(
            from_email=sender_email,
            to_emails=recipient_email,
            subject=subject,
            html_content=html_body
        )
        
        sg = SendGridAPIClient(sendgrid_api_key)
        response = sg.send(message)
        
        if response.status_code in (200, 201, 202):
            current_app.logger.info(f"✅ Email sent via SendGrid to {recipient_email}")
            return True
        elif response.status_code == 429:
            # Rate limited by SendGrid
            if retry_count < max_retries:
                # Exponential backoff: 1s, 2s, 4s
                wait_time = 2 ** retry_count
                current_app.logger.warning(
                    f"⚠️  SendGrid rate limit (429). "
                    f"Retrying in {wait_time}s (attempt {retry_count + 1}/{max_retries})..."
                )
                time.sleep(wait_time)
                return _send_email_sendgrid(
                    recipient_email, subject, html_body, sender_email,
                    retry_count=retry_count + 1, max_retries=max_retries
                )
            else:
                current_app.logger.error(
                    f"❌ SendGrid rate limit (429) - Max retries exceeded for {recipient_email}"
                )
                return False
        else:
            error_msg = response.body.decode() if hasattr(response.body, 'decode') else str(response.body)
            current_app.logger.error(f"❌ SendGrid error {response.status_code}: {error_msg}")
            return False
        
    except Exception as e:
        current_app.logger.error(f"❌ SendGrid error: {type(e).__name__}: {e}")
        return False


def _send_email_smtp(recipient_email, subject, html_body, sender_email):
    """Fallback: Send email via SMTP (for local development)."""
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(60)
    
    with current_app.app_context():
        try:
            server = current_app.config.get('MAIL_SERVER', 'smtp.gmail.com')
            port = current_app.config.get('MAIL_PORT', 587)
            username = current_app.config.get('MAIL_USERNAME', '')
            password = current_app.config.get('MAIL_PASSWORD', '')
            use_tls = current_app.config.get('MAIL_USE_TLS', True)
            use_ssl = current_app.config.get('MAIL_USE_SSL', False)
            
            current_app.logger.info(f"📧 Resolving {server}...")
            try:
                addrs = socket.getaddrinfo(server, port)
                ipv4 = [a for a in addrs if a[0] == socket.AF_INET]
                if not ipv4:
                    current_app.logger.error(f"❌ No IPv4 addresses for {server}")
                    return False
                resolved_ip = ipv4[0][4][0]
                current_app.logger.info(f"📧 Resolved to {resolved_ip}, connecting (5s timeout)...")
            except Exception as e:
                current_app.logger.error(f"❌ DNS resolution failed: {e}")
                return False
            
            try:
                if use_ssl:
                    smtp = smtplib.SMTP_SSL(server, port, timeout=5)
                else:
                    smtp = smtplib.SMTP(server, port, timeout=5)
            except socket.timeout:
                current_app.logger.error(f"❌ SMTP connection timeout. If on Railway, use SendGrid instead.")
                return False
            
            if smtp.sock:
                smtp.sock.settimeout(30)
            smtp.ehlo()
            
            if use_tls and not use_ssl:
                current_app.logger.info(f"📧 Starting TLS...")
                smtp.starttls()
                smtp.ehlo()
            
            if username and password:
                current_app.logger.info(f"📧 Logging in...")
                smtp.login(username, password)
            
            current_app.logger.info(f"📧 Sending email...")
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = sender_email
            msg['To'] = recipient_email
            msg.attach(MIMEText(html_body, 'html'))
            
            smtp.sendmail(sender_email, [recipient_email], msg.as_string())
            smtp.quit()
            
            current_app.logger.info(f"✅ Email sent via SMTP to {recipient_email}")
            return True
        
        except Exception as e:
            current_app.logger.error(f"❌ SMTP error: {type(e).__name__}: {e}")
            return False
        
        finally:
            socket.setdefaulttimeout(old_timeout)


def _send_email_async(app, recipient_email, subject, html_body, sender_email):
    """Send email in background thread, trying SendGrid first, then SMTP fallback."""
    with app.app_context():
        sendgrid_key = app.config.get('SENDGRID_API_KEY')
        
        if sendgrid_key:
            # Use SendGrid for production
            _send_email_sendgrid(recipient_email, subject, html_body, sender_email)
        else:
            # Fallback to SMTP for local development
            _send_email_smtp(recipient_email, subject, html_body, sender_email)


def send_rider_verification_email(recipient_email, verification_token, store_name, seller_name):
    """
    Send a verification link email to a new rider (async via thread).
    Uses SendGrid for production, SMTP for local development.
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
    Send a 6-digit OTP code to a rider's email via SMTP.
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

        # Send via SMTP directly (not SendGrid) to avoid DMARC/auth issues
        app = current_app._get_current_object()
        thread = threading.Thread(
            target=_send_smtp_only_async,
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
    Send rider their account credentials after successful OTP verification.
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

        # Send via SMTP directly
        app = current_app._get_current_object()
        thread = threading.Thread(
            target=_send_smtp_only_async,
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
    """Send email via SMTP only (bypasses SendGrid entirely)."""
    with app.app_context():
        _send_email_smtp(recipient_email, subject, html_body, sender_email)
