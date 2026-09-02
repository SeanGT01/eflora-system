# Store-owner invites for seller-side admin accounts (OTP email/SMS, same as riders).
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request, session, redirect, url_for, render_template
from app.extensions import db
from app.models import User, StoreAdmin, StoreAdminOTP

store_admin_bp = Blueprint('store_admin', __name__)


@store_admin_bp.context_processor
def _inject_layout_context():
    from app.templates_routes import inject_user
    return inject_user()


def _owner_ok():
    if 'user_id' not in session:
        return False, (jsonify({'error': 'Unauthorized'}), 401)
    if session.get('role') != 'seller':
        return False, (jsonify({'error': 'Only the store owner can manage admins'}), 403)
    return True, None


def _owner_store():
    from app.templates_routes import _seller_portal_manageable_store
    return _seller_portal_manageable_store(session.get('user_id'))


@store_admin_bp.route('/seller/admins')
def seller_admins_page():
    if session.get('role') != 'seller':
        return redirect(url_for('templates.dashboard'))
    return render_template('seller_admins.html')


@store_admin_bp.route('/api/seller/admins', methods=['GET'])
def list_store_admins():
    ok, err = _owner_ok()
    if not ok:
        return err
    store = _owner_store()
    if not store:
        return jsonify({'error': 'No active store found'}), 404

    admins = StoreAdmin.query.filter_by(store_id=store.id).all()
    pending = StoreAdminOTP.query.filter_by(
        store_id=store.id, is_verified=False
    ).filter(StoreAdminOTP.expires_at > datetime.utcnow()).all()

    return jsonify({
        'success': True,
        'admins': [a.to_dict() for a in admins],
        'pending_invitations': [o.to_dict() for o in pending],
        'stats': {
            'total': sum(1 for a in admins if not a.is_archived),
            'active': sum(1 for a in admins if a.is_active and not a.is_archived),
            'inactive': sum(1 for a in admins if (not a.is_active) and not a.is_archived),
        }
    }), 200


@store_admin_bp.route('/api/seller/admins', methods=['POST'])
def invite_store_admin():
    ok, err = _owner_ok()
    if not ok:
        return err
    user_id = session['user_id']
    user = User.query.get(user_id)
    store = _owner_store()
    if not store:
        return jsonify({'error': 'No active store found'}), 404

    data = request.get_json() or {}
    full_name = (data.get('full_name') or '').strip()
    if not full_name:
        return jsonify({'error': 'Full name is required'}), 400

    from app.utils.otp_delivery import deliver_otp, sync_plain_otp_record
    from app.utils.phone_utils import parse_email_or_phone_identifier
    from app.utils.email_helper import generate_otp_code, send_store_admin_otp_email

    raw_id = data.get('identifier')
    if raw_id is None or str(raw_id).strip() == '':
        raw_id = (data.get('phone') or data.get('email') or '')
    parsed, parse_err = parse_email_or_phone_identifier(raw_id)
    if parse_err:
        return jsonify({'error': parse_err}), 400

    email = parsed['email']
    phone = parsed['phone']
    channel = parsed['otp_channel']
    login_id = parsed['login_id']

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        existing_staff = StoreAdmin.query.filter_by(
            user_id=existing_user.id, store_id=store.id
        ).first()
        if existing_staff:
            return jsonify({'error': 'This contact is already a store admin'}), 409
        if existing_user.role not in ('store_admin',):
            return jsonify({
                'error': 'This email or phone is already registered. Use a different contact.',
            }), 409

    existing_otp = StoreAdminOTP.query.filter_by(
        email=email, store_id=store.id, is_verified=False
    ).filter(StoreAdminOTP.expires_at > datetime.utcnow()).first()
    if existing_otp:
        return jsonify({'error': 'An invitation is already pending for this contact.'}), 409

    otp_code = generate_otp_code()
    rec = StoreAdminOTP(
        email=email,
        verification_token=otp_code,
        admin_data={
            'full_name': full_name,
            'phone': phone,
            'otp_channel': channel,
            'login_id': login_id,
        },
        store_id=store.id,
        created_by=user_id,
        expires_at=datetime.utcnow() + timedelta(minutes=10),
    )
    db.session.add(rec)
    db.session.commit()

    ok_send, fail, meta = deliver_otp(
        channel,
        otp_code=otp_code,
        email=email,
        phone=phone,
        email_sender_fn=send_store_admin_otp_email,
        email_sender_kwargs={
            'store_name': store.name,
            'seller_name': user.full_name,
        },
        expiry_minutes=10,
        sms_purpose='store admin verification',
    )
    if not ok_send:
        return jsonify({'error': (fail or {}).get('error') or 'Failed to send OTP.'}), 500
    sync_plain_otp_record(rec, meta, otp_code)

    dest = meta.get('destination_masked') or login_id
    return jsonify({
        'success': True,
        'message': f'OTP sent to {dest}. Ask the admin for the 6-digit code.',
        'otp_id': rec.id,
        'otp_channel': channel,
        'destination_masked': dest,
    }), 201


@store_admin_bp.route('/api/seller/admins/resend-invitation', methods=['POST'])
def resend_store_admin_invite():
    ok, err = _owner_ok()
    if not ok:
        return err
    user = User.query.get(session['user_id'])
    store = _owner_store()
    if not store:
        return jsonify({'error': 'No active store found'}), 404
    data = request.get_json() or {}
    otp_id = data.get('otp_id')
    rec = StoreAdminOTP.query.filter_by(id=otp_id, store_id=store.id, is_verified=False).first()
    if not rec:
        return jsonify({'error': 'Invitation not found'}), 404

    from app.utils.otp_delivery import deliver_otp, sync_plain_otp_record
    from app.utils.email_helper import generate_otp_code, send_store_admin_otp_email

    new_otp = generate_otp_code()
    rec.verification_token = new_otp
    rec.expires_at = datetime.utcnow() + timedelta(minutes=10)
    payload = rec.admin_data or {}
    channel = payload.get('otp_channel') or 'email'
    db.session.commit()

    ok_send, fail, meta = deliver_otp(
        channel,
        otp_code=new_otp,
        email=rec.email,
        phone=payload.get('phone'),
        email_sender_fn=send_store_admin_otp_email,
        email_sender_kwargs={
            'store_name': store.name,
            'seller_name': user.full_name,
        },
        expiry_minutes=10,
        sms_purpose='store admin verification',
    )
    if not ok_send:
        return jsonify({'error': (fail or {}).get('error') or 'Failed to resend OTP'}), 500
    sync_plain_otp_record(rec, meta, new_otp)
    dest = meta.get('destination_masked') or rec.email
    return jsonify({'success': True, 'message': f'New OTP sent to {dest}', 'destination_masked': dest}), 200


@store_admin_bp.route('/api/seller/admins/verify-otp', methods=['POST'])
def verify_store_admin_otp():
    ok, err = _owner_ok()
    if not ok:
        return err
    store = _owner_store()
    if not store:
        return jsonify({'error': 'No active store found'}), 404
    data = request.get_json() or {}
    otp_id = data.get('otp_id')
    otp_code = (data.get('otp_code') or '').strip()
    if not otp_id or not otp_code:
        return jsonify({'error': 'OTP ID and code are required'}), 400

    rec = StoreAdminOTP.query.filter_by(id=otp_id, store_id=store.id, is_verified=False).first()
    if not rec:
        return jsonify({'error': 'Invitation not found'}), 404
    if rec.is_expired():
        return jsonify({'error': 'OTP has expired. Please resend a new one.'}), 400
    if rec.verification_token != otp_code:
        return jsonify({'error': 'Invalid OTP code. Please try again.'}), 400

    from app.utils.email_helper import generate_store_admin_password, send_store_admin_credentials_email
    from app.utils.phone_utils import display_login_id, is_synthetic_account_email, normalize_ph_mobile
    from app.utils.sms_helper import send_store_admin_credentials_sms

    payload = rec.admin_data or {}
    account_email = rec.email
    default_password = generate_store_admin_password()
    login_id = payload.get('login_id') or display_login_id(
        email=account_email, phone=payload.get('phone')
    )
    phone = normalize_ph_mobile(payload.get('phone'))

    user_account = User.query.filter_by(email=account_email).first()
    if not user_account:
        user_account = User(
            full_name=payload.get('full_name') or '',
            email=account_email,
            phone=phone,
            role='store_admin',
            status='active',
        )
        user_account.set_password(default_password)
        db.session.add(user_account)
        db.session.flush()
    else:
        if user_account.role not in ('store_admin',):
            return jsonify({'error': 'This contact is already registered as another account type.'}), 409
        user_account.set_password(default_password)
        user_account.status = 'active'
        user_account.full_name = payload.get('full_name') or user_account.full_name
        if phone:
            user_account.phone = phone

    existing = StoreAdmin.query.filter_by(user_id=user_account.id, store_id=store.id).first()
    if not existing:
        from app.utils.store_admin_perms import default_permissions
        db.session.add(StoreAdmin(
            user_id=user_account.id,
            store_id=store.id,
            is_active=True,
            is_archived=False,
            permissions=default_permissions(),
        ))

    rec.is_verified = True
    db.session.delete(rec)
    db.session.commit()

    credentials_channel = 'sms' if (
        is_synthetic_account_email(account_email) and payload.get('phone')
    ) else 'email'
    credentials_delivered = False
    if credentials_channel == 'sms':
        credentials_delivered = bool(send_store_admin_credentials_sms(
            phone=payload.get('phone'),
            full_name=payload.get('full_name') or '',
            default_password=default_password,
            store_name=store.name,
            login_id=login_id,
        ))
    else:
        credentials_delivered = bool(send_store_admin_credentials_email(
            recipient_email=account_email,
            full_name=payload.get('full_name') or '',
            default_password=default_password,
            store_name=store.name,
        ))

    return jsonify({
        'success': True,
        'message': 'Store admin account created.',
        'full_name': payload.get('full_name'),
        'login_id': login_id,
        'temporary_password': default_password,
        'credentials_channel': credentials_channel,
        'credentials_delivered': credentials_delivered,
    }), 200


@store_admin_bp.route('/api/seller/admins/cancel-invitation', methods=['POST'])
def cancel_store_admin_invite():
    ok, err = _owner_ok()
    if not ok:
        return err
    store = _owner_store()
    if not store:
        return jsonify({'error': 'No active store found'}), 404
    otp_id = (request.get_json() or {}).get('otp_id')
    rec = StoreAdminOTP.query.filter_by(id=otp_id, store_id=store.id, is_verified=False).first()
    if not rec:
        return jsonify({'error': 'Invitation not found'}), 404
    db.session.delete(rec)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Invitation cancelled'}), 200


@store_admin_bp.route('/api/seller/admins/<int:admin_id>', methods=['GET'])
def store_admin_detail(admin_id):
    ok, err = _owner_ok()
    if not ok:
        return err
    store = _owner_store()
    row = StoreAdmin.query.filter_by(id=admin_id, store_id=store.id).first() if store else None
    if not row:
        return jsonify({'error': 'Admin not found'}), 404
    return jsonify({'success': True, 'admin': row.to_dict()}), 200


@store_admin_bp.route('/api/seller/admins/<int:admin_id>', methods=['PUT'])
def update_store_admin(admin_id):
    ok, err = _owner_ok()
    if not ok:
        return err
    store = _owner_store()
    row = StoreAdmin.query.filter_by(id=admin_id, store_id=store.id).first() if store else None
    if not row:
        return jsonify({'error': 'Admin not found'}), 404
    data = request.get_json() or {}
    if 'is_active' in data:
        row.is_active = bool(data['is_active'])
        if row.is_active:
            row.is_archived = False
    if row.user and 'full_name' in data:
        row.user.full_name = data['full_name']
    if row.user and 'phone' in data:
        from app.utils.phone_utils import normalize_ph_mobile
        phone = (data.get('phone') or '').strip()
        row.user.phone = normalize_ph_mobile(phone) or phone or None
    row.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True, 'admin': row.to_dict()}), 200


@store_admin_bp.route('/api/seller/admins/<int:admin_id>/status', methods=['PUT'])
def store_admin_status(admin_id):
    return update_store_admin(admin_id)


@store_admin_bp.route('/api/seller/admins/<int:admin_id>/permissions', methods=['PUT'])
def update_store_admin_permissions(admin_id):
    ok, err = _owner_ok()
    if not ok:
        return err
    store = _owner_store()
    row = StoreAdmin.query.filter_by(id=admin_id, store_id=store.id).first() if store else None
    if not row:
        return jsonify({'error': 'Admin not found'}), 404
    from app.utils.store_admin_perms import normalize_permissions
    data = request.get_json() or {}
    row.permissions = normalize_permissions(data.get('permissions') or data)
    row.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True, 'admin': row.to_dict()}), 200


@store_admin_bp.route('/api/seller/admins/<int:admin_id>/reset-password', methods=['POST'])
def reset_store_admin_password(admin_id):
    ok, err = _owner_ok()
    if not ok:
        return err
    store = _owner_store()
    row = StoreAdmin.query.filter_by(id=admin_id, store_id=store.id).first() if store else None
    if not row or not row.user:
        return jsonify({'error': 'Admin not found'}), 404

    from app.utils.email_helper import generate_store_admin_password, send_store_admin_credentials_email
    from app.utils.phone_utils import display_login_id, is_synthetic_account_email
    from app.utils.sms_helper import send_store_admin_credentials_sms

    default_password = generate_store_admin_password()
    row.user.set_password(default_password)
    row.user.status = 'active'
    db.session.commit()
    login_id = display_login_id(email=row.user.email, phone=row.user.phone)
    credentials_channel = 'sms' if (
        is_synthetic_account_email(row.user.email) and row.user.phone
    ) else 'email'
    if credentials_channel == 'sms':
        send_store_admin_credentials_sms(
            phone=row.user.phone,
            full_name=row.user.full_name,
            default_password=default_password,
            store_name=store.name,
            login_id=login_id,
        )
    else:
        send_store_admin_credentials_email(
            recipient_email=row.user.email,
            full_name=row.user.full_name,
            default_password=default_password,
            store_name=store.name,
        )
    return jsonify({
        'success': True,
        'message': 'Temporary password reset. Share it with the admin.',
        'full_name': row.user.full_name,
        'login_id': login_id,
        'temporary_password': default_password,
        'credentials_channel': credentials_channel,
    }), 200


@store_admin_bp.route('/api/seller/admins/<int:admin_id>', methods=['DELETE'])
def archive_store_admin(admin_id):
    ok, err = _owner_ok()
    if not ok:
        return err
    store = _owner_store()
    row = StoreAdmin.query.filter_by(id=admin_id, store_id=store.id).first() if store else None
    if not row:
        return jsonify({'error': 'Admin not found'}), 404
    row.is_archived = True
    row.is_active = False
    if row.user:
        row.user.status = 'inactive'
    db.session.commit()
    return jsonify({'success': True, 'message': 'Admin archived', 'admin': row.to_dict()}), 200
