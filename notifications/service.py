"""
Centralised notification dispatcher.
All modules call send_notification() — it respects user preferences,
routes to the correct channel(s), and always logs to the in-app centre.

SMS rule: never include raw monetary amounts (fraud interception risk).
"""
import logging

import africastalking
import requests
from decouple import config
from django.utils import timezone

from .models import Notification, NotificationPreference

logger = logging.getLogger(__name__)

# Initialise Africa's Talking SDK once at module level
africastalking.initialize(
    username=config('AT_USERNAME', default='sandbox'),
    api_key=config('AT_API_KEY', default=''),
)
_sms = africastalking.SMS


def send_notification(
    user,
    notification_type: str,
    title: str,
    body: str,
    sms_body: str = None,          # SMS-safe version (no amounts)
    metadata: dict = None,
    channels: list = None,         # defaults to ['IN_APP', 'SMS', 'PUSH']
):
    """
    Dispatch a notification to a user across requested channels.
    Always creates an in-app Notification record regardless of channel failures.

    Args:
        user:              User instance.
        notification_type: One of Notification.TYPE_* constants.
        title:             Short notification title.
        body:              Full body text (for in-app / push).
        sms_body:          SMS-safe version — must not include amounts.
                           Falls back to title if omitted.
        metadata:          Optional dict attached to in-app record.
        channels:          List of channel strings. Default: all enabled channels.
    """
    if channels is None:
        channels = [Notification.CHANNEL_IN_APP, Notification.CHANNEL_SMS, Notification.CHANNEL_PUSH]

    metadata = metadata or {}

    # Fetch or create preference record
    prefs, _ = NotificationPreference.objects.get_or_create(user=user)

    # Always log in-app
    Notification.objects.create(
        recipient=user,
        notification_type=notification_type,
        channel=Notification.CHANNEL_IN_APP,
        title=title,
        body=body,
        metadata=metadata,
    )

    # SMS
    if Notification.CHANNEL_SMS in channels and prefs.sms_enabled:
        safe_text = sms_body or title   # use SMS-safe version — no amounts
        _send_sms(user.phone_number, safe_text)

    # Push
    if Notification.CHANNEL_PUSH in channels and prefs.push_enabled and prefs.push_token:
        _send_push(prefs.push_token, title, body)


def _send_sms(phone_number: str, message: str):
    try:
        _sms.send(message, [phone_number])
    except Exception as exc:
        logger.exception("SMS send failed to %s: %s", phone_number, exc)


def _send_push(token: str, title: str, body: str):
    """Send FCM push notification."""
    fcm_key = config('FCM_SERVER_KEY', default='')
    if not fcm_key:
        logger.warning("FCM_SERVER_KEY not configured — push skipped.")
        return

    try:
        response = requests.post(
            'https://fcm.googleapis.com/fcm/send',
            json={
                'to': token,
                'notification': {'title': title, 'body': body},
                'priority': 'high',
            },
            headers={
                'Authorization': f'key={fcm_key}',
                'Content-Type': 'application/json',
            },
            timeout=5,
        )
        if response.status_code != 200:
            logger.warning("FCM push failed: %s", response.text)
    except Exception as exc:
        logger.exception("FCM push exception: %s", exc)


def update_push_token(user, token: str):
    """Refresh FCM/APNs token on each app login."""
    prefs, _ = NotificationPreference.objects.get_or_create(user=user)
    prefs.push_token = token
    prefs.push_token_updated_at = timezone.now()
    prefs.save(update_fields=['push_token', 'push_token_updated_at'])