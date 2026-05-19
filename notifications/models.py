from django.conf import settings
from django.db import models


class NotificationPreference(models.Model):
    """
    Per-user opt-in/opt-out settings for each notification channel.
    Members can opt out of SMS at any time (roadmap spec).
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_prefs',
    )
    sms_enabled = models.BooleanField(default=True)
    push_enabled = models.BooleanField(default=True)
    in_app_enabled = models.BooleanField(default=True)
    # Marketing/nudge messages require explicit opt-in (GDPR-aligned)
    marketing_opted_in = models.BooleanField(default=False)

    # FCM/APNs device token — refreshed on each app login
    push_token = models.CharField(max_length=255, blank=True)
    push_token_updated_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"NotificationPrefs — {self.user.phone_number}"


class Notification(models.Model):
    """
    In-app notification centre — every notification sent is logged here
    regardless of channel, so users can read it in-app.
    """
    TYPE_CONTRIBUTION_REMINDER = 'CONTRIBUTION_REMINDER'
    TYPE_CONTRIBUTION_OVERDUE = 'CONTRIBUTION_OVERDUE'
    TYPE_CONTRIBUTION_CONFIRMED = 'CONTRIBUTION_CONFIRMED'
    TYPE_DISBURSEMENT_RECEIVED = 'DISBURSEMENT_RECEIVED'
    TYPE_WITHDRAWAL_VOTE = 'WITHDRAWAL_VOTE'
    TYPE_MEMBER_JOINED = 'MEMBER_JOINED'
    TYPE_BADGE_AWARDED = 'BADGE_AWARDED'
    TYPE_GENERAL = 'GENERAL'
    TYPE_CHOICES = [
        (TYPE_CONTRIBUTION_REMINDER, 'Contribution Reminder'),
        (TYPE_CONTRIBUTION_OVERDUE, 'Contribution Overdue'),
        (TYPE_CONTRIBUTION_CONFIRMED, 'Contribution Confirmed'),
        (TYPE_DISBURSEMENT_RECEIVED, 'Disbursement Received'),
        (TYPE_WITHDRAWAL_VOTE, 'Withdrawal Vote Required'),
        (TYPE_MEMBER_JOINED, 'Member Joined'),
        (TYPE_BADGE_AWARDED, 'Badge Awarded'),
        (TYPE_GENERAL, 'General'),
    ]

    CHANNEL_IN_APP = 'IN_APP'
    CHANNEL_SMS = 'SMS'
    CHANNEL_PUSH = 'PUSH'
    CHANNEL_CHOICES = [
        (CHANNEL_IN_APP, 'In-App'),
        (CHANNEL_SMS, 'SMS'),
        (CHANNEL_PUSH, 'Push'),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    notification_type = models.CharField(max_length=40, choices=TYPE_CHOICES)
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES, default=CHANNEL_IN_APP)
    title = models.CharField(max_length=100)
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # Optional metadata (group name, amount, etc.) — stored as JSON
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.notification_type}] → {self.recipient.phone_number}"