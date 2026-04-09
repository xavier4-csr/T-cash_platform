from django.shortcuts import render
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import User
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, OTPCode
from .sms_service import generate_otp, send_otp_sms



@api_view(['POST', 'GET'])
def login_user(request):
    # 1. If it's a browser hit (GET), just return a friendly message
    if request.method == 'GET':
        return Response({"message": "Please send a POST request with {'phone_number': '...'} to login."})
        
    # 2. Extract phone number
    phone = request.data.get("phone_number")

    # 3. Guard against empty phone numbers
    if not phone:
        return Response({"error": "phone_number is required"}, status=400)

    # 4. Proceed with login/registration
    user, created = User.objects.get_or_create(phone_number=phone)
    refresh = RefreshToken.for_user(user)
    
    return Response({
        "user": user.phone_number,
        "access_token": str(refresh.access_token),
        "refresh_token": str(refresh),
    })

@api_view(['POST'])
def request_otp(request):
    phone = request.data.get('phone_number')

    if not phone:
        return Response(
        {'error':'Phone number is required'},
        status=status.HTTP_400_BAD_REQUEST
        )
    
    OTPCode.objects.filter(
        phone_number=phone,
        is_used=False
    ).update(is_used=True)