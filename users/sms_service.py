import africastalking
import random
import logging
from decouple import config

logger = logging.getLogger(__name__)

AT_USERNAME = config('AT_USERNAME', default='')
AT_API_KEY = config('AT_API_KEY', default='')

# Bypass Africa's Talking initialization if using dummy/invalid sandbox credentials
if AT_USERNAME and AT_API_KEY and AT_API_KEY != 'dummy_at_api_key':
    africastalking.initialize(
        username=AT_USERNAME,
        api_key=AT_API_KEY,
    )
    sms = africastalking.SMS
else:
    sms = None

def generate_otp():
    return str(random.randint(100000, 999999))


def send_otp_sms(phone_number, otp_code):
    message = f"Your T-Cash verification code is: {otp_code}. Valid for 10 minutes. Do not share this code."
    
    if not sms:
        logger.warning(f"Mock SMS to {phone_number}: {message}")
        return True, "Mock SMS sent (AT credentials not configured)"
        
    try:
        response = sms.send(message, [phone_number])
        return True, response
    except Exception as e:
        return False, str(e)