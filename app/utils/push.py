"""Firebase Cloud Messaging (phone push) for order status and chat."""

from typing import Optional
import json
import logging
import os
import threading
import base64

import requests
from flask import current_app
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from sqlalchemy import event
from sqlalchemy.orm import Session, object_session

logger = logging.getLogger(__name__)

_FCM_SCOPE = 'https://www.googleapis.com/auth/firebase.messaging'
_ORDER_COPY = {
    'accepted': (
        'Order confirmed',
        'Your order has been confirmed.',
    ),
    'preparing': (
        'Order preparing',
        'Your order is preparing.',
    ),
    'done_preparing': (
        'Order ready',
        'Your order is done being prepared.',
    ),
    'on_delivery': (
        'Order in transit',
        'Your order is in transit.',
    ),
    'delivered': (
        'Order delivered',
        'Your order has been delivered.',
    ),
}


def _parse_service_account(raw):
    raw = (raw or '').strip().lstrip('\ufeff')
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ('"', "'"):
        inner = raw[1:-1].strip()
        if inner.startswith('{'):
            raw = inner.replace('\\n', '\n')
    if not raw:
        return None
    if os.path.isfile(raw):
        with open(raw, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    if raw.startswith('{'):
        return json.loads(raw)
    return None


def fcm_config_hint():
    """Safe diagnostic for why FCM credentials are missing. Never includes secrets."""
    b64 = os.environ.get('FCM_SERVICE_ACCOUNT_B64')
    raw = os.environ.get('FCM_SERVICE_ACCOUNT_JSON')
    alt = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    if b64 and str(b64).strip():
        try:
            decoded = base64.b64decode(str(b64).strip()).decode('utf-8')
            info = _parse_service_account(decoded)
            if info and info.get('private_key'):
                return 'ok'
            return 'b64_not_json'
        except Exception as exc:
            return 'b64_invalid:%s' % type(exc).__name__
    if raw is None or not str(raw).strip():
        if alt and str(alt).strip():
            try:
                _parse_service_account(alt)
                return 'using_google_application_credentials'
            except Exception as exc:
                return 'google_application_credentials_invalid:%s' % type(exc).__name__
        return 'env_missing'
    try:
        info = _parse_service_account(raw)
    except Exception as exc:
        return 'json_invalid:%s' % type(exc).__name__
    if not info:
        prefix = str(raw).strip()[:8]
        return 'not_json_prefix=%r_len=%s' % (prefix, len(str(raw).strip()))
    if not info.get('private_key') or not info.get('project_id'):
        return 'json_missing_fields'
    return 'ok'


def _service_account_info():
    b64 = (os.environ.get('FCM_SERVICE_ACCOUNT_B64') or '').strip()
    if b64:
        try:
            decoded = base64.b64decode(b64).decode('utf-8')
            info = _parse_service_account(decoded)
            if info:
                return info
        except Exception as exc:
            logger.warning('[FCM] FCM_SERVICE_ACCOUNT_B64 parse failed: %s', exc)
            print('[FCM] B64 parse failed:', exc, flush=True)
    for key in ('FCM_SERVICE_ACCOUNT_JSON', 'GOOGLE_APPLICATION_CREDENTIALS'):
        raw = os.environ.get(key)
        if not raw or not str(raw).strip():
            continue
        try:
            info = _parse_service_account(raw)
        except Exception as exc:
            logger.warning('[FCM] %s parse failed: %s', key, exc)
            print('[FCM]', key, 'parse failed:', exc, flush=True)
            continue
        if info:
            return info
    return None


def _access_token_and_project():
    info = _service_account_info()
    if not info:
        return None, None
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=[_FCM_SCOPE]
    )
    creds.refresh(Request())
    return creds.token, info.get('project_id')


def fcm_is_configured():
    try:
        return _service_account_info() is not None
    except Exception as exc:
        logger.warning('[FCM] service account JSON is invalid: %s', exc)
        return False


def send_fcm(token, title, body, data=None):
    """Send one FCM notification. Returns True on success."""
    token = (token or '').strip()
    if not token:
        logger.warning('[FCM] skip: empty device token')
        return False
    try:
        access, project_id = _access_token_and_project()
    except Exception as exc:
        logger.warning('[FCM] credentials error: %s', exc)
        print('[FCM] credentials error:', exc, flush=True)
        return False
    if not access or not project_id:
        logger.warning('[FCM] skip: FCM_SERVICE_ACCOUNT_JSON is missing or invalid')
        print('[FCM] skip: no service account configured', flush=True)
        return False

    payload_data = {str(k): str(v) for k, v in (data or {}).items() if v is not None}
    body_json = {
        'message': {
            'token': token,
            'notification': {'title': title[:120], 'body': (body or '')[:240]},
            'data': payload_data,
            'android': {
                'priority': 'HIGH',
                'notification': {
                    'channel_id': 'eflora_alerts',
                    'sound': 'default',
                    'notification_priority': 'PRIORITY_MAX',
                    'default_vibrate_timings': True,
                },
            },
            'apns': {
                'headers': {'apns-priority': '10'},
                'payload': {
                    'aps': {
                        'sound': 'default',
                        'badge': 1,
                        'content-available': 1,
                    },
                },
            },
        }
    }
    try:
        res = requests.post(
            f'https://fcm.googleapis.com/v1/projects/{project_id}/messages:send',
            headers={
                'Authorization': f'Bearer {access}',
                'Content-Type': 'application/json; charset=utf-8',
            },
            json=body_json,
            timeout=12,
        )
        if res.status_code >= 400:
            logger.warning('[FCM] send failed %s: %s', res.status_code, res.text[:400])
            print('[FCM] send failed', res.status_code, res.text[:400], flush=True)
            err = (res.text or '').upper()
            if any(x in err for x in ('UNREGISTERED', 'NOT_FOUND', 'INVALID_ARGUMENT')):
                return 'invalid_token'
            return False
        logger.info('[FCM] sent project=%s title=%s', project_id, title)
        print('[FCM] sent ok title=', title, flush=True)
        return True
    except Exception as exc:
        logger.warning('[FCM] request error: %s', exc)
        print('[FCM] request error:', exc, flush=True)
        return False


def send_to_user_id(user_id, title, body, data=None):
    from app.extensions import db
    from app.models import User

    if not user_id:
        logger.warning('[FCM] skip: no user_id')
        return False
    user = User.query.get(user_id)
    if not user:
        logger.warning('[FCM] skip: user %s not found', user_id)
        return False
    if not (user.fcm_token or '').strip():
        logger.warning('[FCM] skip: user %s has no device token', user_id)
        print('[FCM] skip: user', user_id, 'has no device token', flush=True)
        return False
    result = send_fcm(user.fcm_token, title, body, data)
    if result == 'invalid_token':
        logger.warning('[FCM] clearing invalid token for user %s', user_id)
        user.fcm_token = None
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        return False
    if result is True:
        print('[FCM] delivered to user', user_id, 'title=', title, flush=True)
    return result is True


def queue_push(session, job: dict):
    if session is None:
        return
    session.info.setdefault('eflora_fcm', []).append(job)


def queue_order_status_push(order, new_status: str, previous_status: Optional[str] = None):
    if not order:
        return
    statuses = []
    if new_status == 'preparing' and previous_status not in ('accepted', 'preparing'):
        statuses.append('accepted')
        statuses.append('preparing')
    elif new_status in _ORDER_COPY:
        statuses.append(new_status)
    try:
        sess = object_session(order)
        for status in statuses:
            queue_push(sess, {
                'kind': 'order',
                'order_id': order.id,
                'customer_id': order.customer_id,
                'status': status,
            })
        if new_status == 'done_preparing' and not order.rider_id and order.store_id:
            queue_push(sess, {
                'kind': 'rider_ready',
                'order_id': order.id,
                'store_id': order.store_id,
            })
    except Exception:
        logger.debug('queue_order_status_push failed', exc_info=True)


def queue_chat_push(convo, sender, preview_text: str):
    if not convo or not sender:
        return
    other_id = convo.seller_id if sender.id == convo.customer_id else convo.customer_id
    if not other_id or other_id == sender.id:
        return
    name = (sender.full_name or 'Someone').strip() or 'Someone'
    snippet = (preview_text or '').strip() or 'sent a message'
    if len(snippet) > 80:
        snippet = snippet[:77] + '…'
    try:
        sess = object_session(convo)
        queue_push(sess, {
            'kind': 'chat',
            'user_id': other_id,
            'conversation_id': convo.id,
            'title': 'New message',
            'body': f'You received a new message from {name}: {snippet}',
        })
    except Exception:
        logger.debug('queue_chat_push failed', exc_info=True)


def _deliver_jobs(app, jobs):
    with app.app_context():
        for job in jobs:
            try:
                kind = job.get('kind')
                if kind == 'order':
                    status = job.get('status')
                    copy = _ORDER_COPY.get(status)
                    if not copy:
                        continue
                    title, body = copy
                    send_to_user_id(
                        job.get('customer_id'),
                        title,
                        body,
                        {
                            'type': 'order_status',
                            'order_id': job.get('order_id'),
                            'status': status,
                        },
                    )
                elif kind == 'rider_ready':
                    from app.models import Rider
                    store_id = job.get('store_id')
                    order_id = job.get('order_id')
                    if not store_id:
                        continue
                    riders = Rider.query.filter_by(
                        store_id=store_id,
                        is_active=True,
                        is_archived=False,
                    ).all()
                    title = 'New delivery ready'
                    body = (
                        f'Order #{order_id} is ready for delivery.'
                        if order_id
                        else 'A new order is ready for delivery.'
                    )
                    for rider in riders:
                        send_to_user_id(
                            rider.user_id,
                            title,
                            body,
                            {
                                'type': 'rider_order_ready',
                                'order_id': order_id,
                                'store_id': store_id,
                            },
                        )
                elif kind == 'chat':
                    send_to_user_id(
                        job.get('user_id'),
                        job.get('title') or 'New message',
                        job.get('body') or 'You received a new message.',
                        {
                            'type': 'chat',
                            'conversation_id': job.get('conversation_id'),
                        },
                    )
            except Exception:
                logger.exception('FCM job failed: %s', job)


_listeners_registered = False


def register_push_listeners():
    global _listeners_registered
    if _listeners_registered:
        return
    _listeners_registered = True

    @event.listens_for(Session, 'after_commit')
    def _after_commit(session):
        jobs = session.info.pop('eflora_fcm', None)
        if not jobs:
            return
        try:
            app = current_app._get_current_object()
        except RuntimeError:
            return
        print('[FCM] queued', len(jobs), 'job(s)', flush=True)
        threading.Thread(
            target=_deliver_jobs,
            args=(app, list(jobs)),
            daemon=True,
        ).start()
