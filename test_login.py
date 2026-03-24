import urllib.request
import json
import urllib.error

url = 'http://127.0.0.1:8000/api/users/login/'
data = {
    "phone_number": "+254700000000"
}
json_data = json.dumps(data).encode('utf-8')
headers = {'Content-Type': 'application/json'}

print(f"Testing POST request to {url}")
print(f"Sending payload: {data}")
print("-" * 50)

req = urllib.request.Request(url, data=json_data, headers=headers)

try:
    with urllib.request.urlopen(req) as response:
        result = response.read().decode('utf-8')
        print("SUCCESS! Endpoint returned:")
        
        # Pretty print the JSON
        parsed_json = json.loads(result)
        print(json.dumps(parsed_json, indent=4))
        
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code} - {e.reason}")
    print(e.read().decode('utf-8'))
except urllib.error.URLError as e:
    print(f"Connection Error: {e.reason}")
    print("Make sure your Django development server is running! (python manage.py runserver)")
