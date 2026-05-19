from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, OTPCode
from .sms_service import generate_otp, send_otp_sms

@api_view(['POST'])
def request_otp(request):
    phone = request.data.get('phone_number')
    if not phone:
        return Response({'error': 'phone_number is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Rate limit: max 3 OTP requests per phone per 10 minutes
    if OTPCode.recent_request_count(phone) >= 3:
        return Response(
            {'error': 'Too many OTP requests. Please wait 10 minutes before trying again.'},
            status=status.HTTP_429_TOO_MANY_REQUESTS
        )
    
    user, _ = User.objects.get_or_create(phone_number=phone)
    if user.is_otp_locked():
        return Response({'error': 'Account locked due to too many failed attempts'}, status=status.HTTP_403_FORBIDDEN)
        
    OTPCode.objects.filter(phone_number=phone, is_used=False).update(is_used=True)
    
    otp = generate_otp()
    OTPCode.objects.create(phone_number=phone, code=otp)
    
    # We send the OTP. In dev, we can return the OTP in the response for easy testing
    # but in production we'd only rely on `send_otp_sms`
    success, msg_or_error = send_otp_sms(phone, otp)
    
    response_data = {"message": f"OTP sent to {phone}"}
    if settings.DEBUG:
        response_data["developer_note"] = f"Dev Code: {otp} | SMS Status: {msg_or_error}"
    return Response(response_data, status=status.HTTP_200_OK)

@api_view(['POST'])
def verify_otp(request):
    phone = request.data.get('phone_number')
    code = request.data.get('code')
    
    if not phone or not code:
        return Response({'error': 'phone_number and code are required'}, status=status.HTTP_400_BAD_REQUEST)
        
    user, created = User.objects.get_or_create(phone_number=phone)
    
    if user.is_otp_locked():
        return Response({'error': 'Account locked'}, status=status.HTTP_403_FORBIDDEN)
        
    otp_record = OTPCode.objects.filter(phone_number=phone, code=code, is_used=False).order_by('-created_at').first()
    
    if otp_record and otp_record.is_valid():
        otp_record.is_used = True
        otp_record.save()
        user.reset_otp_failures()
        
        refresh = RefreshToken.for_user(user)
        return Response({
            "message": "Login successful",
            "access_token": str(refresh.access_token),
            "refresh_token": str(refresh),
            "user_id": user.id,
            "kyc_tier": user.kyc_tier
        }, status=status.HTTP_200_OK)
    else:
        user.record_otp_failure()
        return Response({'error': 'Invalid or expired OTP'}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_user(request):
    try:
        refresh_token = request.data.get("refresh_token")
        if not refresh_token:
            return Response({"error": "refresh_token is required to logout"}, status=status.HTTP_400_BAD_REQUEST)
        token = RefreshToken(refresh_token)
        token.blacklist()
        return Response({"message": "Successfully logged out"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def profile(request):
    user = request.user
    if request.method == 'GET':
        return Response({
            "phone_number": user.phone_number,
            "kyc_tier": user.kyc_tier,
            "id_number": user.id_number,
            "pin_set": bool(user.pin)
        })
    elif request.method == 'PUT':
        user.id_number = request.data.get('id_number', user.id_number)
        user.save()
        return Response({"message": "Profile updated successfully"})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def setup_pin(request):
    pin = request.data.get('pin')
    if not pin or len(str(pin)) != 4 or not str(pin).isdigit():
        return Response({"error": "A 4-digit numeric PIN is required"}, status=status.HTTP_400_BAD_REQUEST)
    
    request.user.set_pin(str(pin))
    return Response({"message": "PIN setup successfully"})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_pin(request):
    from django.contrib.auth.hashers import check_password
    pin = request.data.get('pin')
    
    if not request.user.pin:
         return Response({"error": "PIN not set up yet"}, status=status.HTTP_400_BAD_REQUEST)
         
    if check_password(str(pin), request.user.pin):
        return Response({"message": "PIN verified"})
    return Response({"error": "Invalid PIN"}, status=status.HTTP_400_BAD_REQUEST)