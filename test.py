import requests

url = "http://localhost:8000/api/users/request-otp/"
data = {"phone_number": "+254700000000"}

try:
    response = requests.post(url, json=data)
    print("Status Code:", response.status_code)
    print("Response text:", response.text)
except Exception as e:
    print("Error:", e)
