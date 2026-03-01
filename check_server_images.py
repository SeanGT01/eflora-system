# check_server_images.py
import requests
import os

base_url = "http://192.168.1.9:5000"
image_filenames = [
    "p3_1_008392_c059e330.png",
    "p4_1_008377_8f751b4b.png", 
    "p5_1_008348_61d580a4.png"
]

print("\n=== CHECKING IMAGES ON SERVER ===\n")

for filename in image_filenames:
    # Check full-size image
    full_url = f"{base_url}/static/uploads/products/{filename}"
    response = requests.get(full_url)
    print(f"📸 {filename}")
    print(f"   Full-size URL: {full_url}")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print(f"   ✅ Full-size image exists ({len(response.content)} bytes)")
    else:
        print(f"   ❌ Full-size image not found")
    
    # Check resized endpoint
    resized_url = f"{base_url}/api/product-image/{filename}?w=300&h=300"
    response = requests.get(resized_url)
    print(f"   Resized URL: {resized_url}")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print(f"   ✅ Resized image works")
    else:
        print(f"   ❌ Resized image failed")
    print()