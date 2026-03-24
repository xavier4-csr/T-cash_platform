from test_login import response
import africastalking
import random
from decouple import config

africastalking.initialize(
    username=config('AT_USERNAME'),
    api_key=config('AT_API_KEY'),
)

sms = africastalking.sms

def generate_otp():
    return str(random.randint(100000, 999999))

def send_otp_sms(phone_number, otp_code):
    try:
        message = f"Your T-Cash verification code is: {otp_code}. Valid for 5 minutes. Do not share this code"
        respomse = sms.send(message, [phone_number])
        return True, response
    except Exception as e:
        return False, str(e)
        
