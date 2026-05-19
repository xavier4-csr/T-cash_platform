from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification, NotificationPreference
from .service import update_push_token


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def notification_list(request):
    """Return the authenticated user's in-app notifications (most recent 50)."""
    notifications = Notification.objects.filter(
        recipient=request.user,
        channel=Notification.CHANNEL_IN_APP,
    )[:50]

    data = [
        {
            'id': n.id,
            'type': n.notification_type,
            'title': n.title,
            'body': n.body,
            'is_read': n.is_read,
            'metadata': n.metadata,
            'created_at': n.created_at,
        }
        for n in notifications
    ]
    unread_count = Notification.objects.filter(
        recipient=request.user, channel=Notification.CHANNEL_IN_APP, is_read=False
    ).count()

    return Response({'unread_count': unread_count, 'notifications': data})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_read(request):
    """
    Mark notifications as read.
    Body: { "notification_ids": [1, 2, 3] }  — or omit to mark ALL as read.
    """
    ids = request.data.get('notification_ids')
    qs = Notification.objects.filter(recipient=request.user, is_read=False)

    if ids:
        qs = qs.filter(id__in=ids)

    updated = qs.update(is_read=True)
    return Response({'marked_read': updated})


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def notification_preferences(request):
    """
    GET  → return current notification preferences.
    PATCH → update sms_enabled, push_enabled, marketing_opted_in.
    """
    prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)

    if request.method == 'GET':
        return Response({
            'sms_enabled': prefs.sms_enabled,
            'push_enabled': prefs.push_enabled,
            'in_app_enabled': prefs.in_app_enabled,
            'marketing_opted_in': prefs.marketing_opted_in,
        })

    allowed_fields = ['sms_enabled', 'push_enabled', 'in_app_enabled', 'marketing_opted_in']
    for field in allowed_fields:
        if field in request.data:
            setattr(prefs, field, request.data[field])

    prefs.save()
    return Response({'message': 'Preferences updated.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def register_push_token(request):
    """
    Called on each app login to refresh the FCM/APNs device token.
    Body: { "token": "<FCM or APNs token>" }
    """
    token = request.data.get('token', '').strip()
    if not token:
        return Response({'error': 'token is required.'}, status=status.HTTP_400_BAD_REQUEST)

    update_push_token(request.user, token)
    return Response({'message': 'Push token registered.'})