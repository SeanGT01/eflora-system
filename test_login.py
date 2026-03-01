# test_login.py
import requests
import json

# Login with customer1
response = requests.post(
    'http://127.0.0.1:5000/api/v1/auth/login',
    json={'email': 'customer1@gmail.com', 'password': '123456'},
    headers={'Content-Type': 'application/json'}
)

print(f"Status: {response.status_code}")
print(f"Headers: {dict(response.headers)}")
print(f"Raw response text: {response.text}")

try:
    print(f"JSON response: {response.json()}")
except:
    print("Could not parse JSON response")