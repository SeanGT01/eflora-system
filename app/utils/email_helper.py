import secrets
import socket
import threading
import smtplib
import time
from flask import current_app, url_for, request
from flask_mail import Message
from app.extensions import mail

# Force IPv4 for SMTP — Railway containers often lack IPv6 routing
_original_getaddrinfo = socket.getaddrinfo

def _ipv4_getaddrinfo(*args, **kwargs):
    results = _original_getaddrinfo(*args, **kwargs)
    ipv4 = [r for r in results if r[0] == socket.AF_INET]
    return ipv4 if ipv4 else results


def generate_verification_token():
    """Generate a secure URL-safe verification token."""
    return secrets.token_urlsafe(32)


def _send_email_async(app, msg, recipient_email):
    """Send email in a background thread with its own app context.
    
    Uses direct SMTP with detailed logging to diagnose timeout issues.
    """
    old_timeout = socket.getdefaulttimeout()
    old_getaddrinfo = socket.getaddrinfo
    socket.setdefaulttimeout(60)  # Increased from 30 to 60 seconds
    socket.getaddrinfo = _ipv4_getaddrinfo
    
    with app.app_context():
        try:
            server = app.config.get('MAIL_SERVER', 'smtp.gmail.com')
            port = app.config.get('MAIL_PORT', 587)
            username = app.config.get('MAIL_USERNAME', '')
            password = app.config.get('MAIL_PASSWORD', '')
            use_tls = app.config.get('MAIL_USE_TLS', True)
            use_ssl = app.config.get('MAIL_USE_SSL', False)
            
            app.logger.info(f"📧 Connecting to {server}:{port}...")
            start = time.time()
            
            if use_ssl:
                smtp = smtplib.SMTP_SSL(server, port, timeout=60)
            else:
                smtp = smtplib.SMTP(server, port, timeout=60)
            
            elapsed = time.time() - start
            app.logger.info(f"📧 Connected in {elapsed:.2f}s, sending EHLO...")
            
            smtp.ehlo()
            
            if use_tls and not use_ssl:
                app.logger.info(f"📧 Starting TLS...")
                smtp.starttls()
                smtp.ehlo()
            
            if username and password:
                app.logger.info(f"📧 Logging in as {username}...")
                smtp.login(username, password)
            
            app.logger.info(f"📧 Sending email to {recipient_email}...")
            smtp.send_message(msg)
            smtp.quit()
            
            app.logger.info(f"✅ Verification email sent to {recipient_email}")
        
        except socket.timeout as e:
            app.logger.error(f"❌ SMTP timeout to {server}:{port} - {e}")
        except smtplib.SMTPAuthenticationError as e:
            app.logger.error(f"❌ SMTP auth failed for {username} - {e}")
        except smtplib.SMTPException as e:
            app.logger.error(f"❌ SMTP error sending to {recipient_email} - {e}")
        except Exception as e:
            app.logger.error(f"❌ Failed to send verification email to {recipient_email}: {type(e).__name__}: {e}")
        
        finally:
            socket.setdefaulttimeout(old_timeout)
            socket.getaddrinfo = old_getaddrinfo


def send_rider_verification_email(recipient_email, verification_token, store_name, seller_name):
    """
    Send a verification link email to a new rider (async via thread).
    Returns True immediately — email is sent in background.
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
        
        msg = Message(
            subject=subject,
            recipients=[recipient_email],
            html=html_body
        )
        
        # Send in background thread so the API response returns immediately
        app = current_app._get_current_object()
        thread = threading.Thread(target=_send_email_async, args=(app, msg, recipient_email))
        thread.daemon = True
        thread.start()
        
        current_app.logger.info(f"📧 Verification email queued for {recipient_email}")
        return True
        
    except Exception as e:
        current_app.logger.error(f"❌ Failed to queue verification email to {recipient_email}: {e}")
        return False
