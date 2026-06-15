from django.urls import path
from .views import (
    notification_list,
    mark_read,
    notification_preferences,
    register_push_token,
)

urlpatterns = [
    # In-app notification centre
    path('', notification_list, name='notification-list'),
    path('mark-read/', mark_read, name='mark-read'),

    # User notification preferences (SMS / push opt-in/out)
    path('preferences/', notification_preferences, name='notification-preferences'),

    # Register FCM/APNs token on each login
    path('push-token/', register_push_token, name='register-push-token'),
]