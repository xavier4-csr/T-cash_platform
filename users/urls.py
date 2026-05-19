from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    logout_user,
    profile,
    request_otp,
    setup_pin,
    verify_otp,
    verify_pin,
)

urlpatterns = [
    # --- Authentication flow ---
    path('request-otp/', request_otp, name='request-otp'),   # Step 1: send OTP
    path('verify-otp/', verify_otp, name='verify-otp'),       # Step 2: verify + get tokens

    # --- Token management ---
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('logout/', logout_user, name='logout'),

    # --- Profile & KYC ---
    path('profile/', profile, name='profile'),

    # --- PIN (used by payments module) ---
    path('setup-pin/', setup_pin, name='setup-pin'),
    path('verify-pin/', verify_pin, name='verify-pin'),
]