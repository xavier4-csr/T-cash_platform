from django.contrib import admin
from .models import Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'notification_type', 'channel', 'title', 'is_read', 'created_at']
    list_filter = ['notification_type', 'channel', 'is_read']
    search_fields = ['recipient__phone_number', 'title']
    readonly_fields = ['created_at']


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ['user', 'sms_enabled', 'push_enabled', 'in_app_enabled', 'marketing_opted_in']
    search_fields = ['user__phone_number']