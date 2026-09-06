"""Firebase Cloud Messaging (phone push) for order status and chat."""

from typing import Optional
import json
import logging
import os
import threading

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
    'on_delivery': (
        'Order in transit',
        'Your order is in transit.',
    ),
    'delivered': (
        'Order delivered',
        'Your order has been delivered.',
    ),
}


def _service_account_info():
    raw = (os.environ.get('FCM_SERVICE_ACCOUNT_JSON') or '').strip()
    if not raw:
        path = (os.environ.get('GOOGLE_APPLICATION_CREDENTIALS') or '').strip()
        if path and os.path.isfile(path):
            with open(path, 'r', encoding='utf-8') as fh:
                return json.load(fh)
        return None
    if raw.startswith('{'):
        return json.loads(raw)
    if os.path.isfile(raw):
        with open(raw, 'r', encoding='utf-8') as fh:
            return json.load(fh)
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


def send_fcm(token, title, body, data=None):
    """Send one FCM notification. Returns True on success."""
    token = (token or '').strip()
    if not token:
        return False
    try:
        access, project_id = _access_token_and_project()
    except Exception as exc:
        logger.warning('FCM credentials error: %s', exc)
        return False
    if not access or not project_id:
        logger.debug('FCM skipped: no service account configured')
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
                'Content-Type': 'application/json; charset=UTF-8',
            },
            json=body_json,
            timeout=12,
        )
        if res.status_code >= 400:
            logger.warning('FCM send failed %s: %s', res.status_code, res.text[:400])
            err = (res.text or '').upper()
            if any(x in err for x in ('UNREGISTERED', 'NOT_FOUND', 'INVALID_ARGUMENT')):
                return 'invalid_token'
            return False
        return True
    except Exception as exc:
        logger.warning('FCM request error: %s', exc)
        return False


def send_to_user_id(user_id, title, body, data=None):
    from app.extensions import db
    from app.models import User

    if not user_id:
        return
    user = User.query.get(user_id)
    if not user or not (user.fcm_token or '').strip():
        return
    result = send_fcm(user.fcm_token, title, body, data)
    if result == 'invalid_token':
        user.fcm_token = None
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()


def queue_push(session, job: dict):
    if session is None:
        return
    session.info.setdefault('eflora_fcm', []).append(job)


def queue_order_status_push(order, new_status: str, previous_status: Optional[str] = None):
    statuses = []
    if new_status == 'preparing' and previous_status not in ('accepted', 'preparing'):
        statuses.append('accepted')
        statuses.append('preparing')
    elif new_status in _ORDER_COPY:
        statuses.append(new_status)
    if not order or not statuses:
        return
    try:
        sess = object_session(order)
        for status in statuses:
            queue_push(sess, {
                'kind': 'order',
                'order_id': order.id,
                'customer_id': order.customer_id,
                'status': status,
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
        threading.Thread(
            target=_deliver_jobs,
            args=(app, list(jobs)),
            daemon=True,
        ).start()
