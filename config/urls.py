"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),

    # Authentication & user management
    path('api/users/', include('users.urls')),

    # Groups (chama/savings circle management)
    path('api/groups/', include('groups.urls')),

    # Contributions (member payment records)
    path('api/contributions/', include('contributions.urls')),

    # Payments (M-Pesa integration)
    path('api/payments/', include('payments.urls')),

    # Notifications
    path('api/notifications/', include('notifications.urls')),
]
