import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.stdout.reconfigure(encoding='utf-8')

from app import create_app
import cloudinary.uploader

app = create_app()

artifacts_dir = r"C:\Users\seanm\.gemini\antigravity-ide\brain\d0bd21a1-0f44-42d0-a16d-ba7341f5137d"

images_to_upload = {
    # Rider Proofs
    "rider_garden": (os.path.join(artifacts_dir, "rider_delivery_garden_gate_1790806210038.jpg"), "e-flowers/delivery-proofs"),
    "rider_flower": (os.path.join(artifacts_dir, "rider_delivery_flower_handoff_1790806225343.jpg"), "e-flowers/delivery-proofs"),
    "rider_luxury": (os.path.join(artifacts_dir, "rider_delivery_luxury_rose_1790806240703.jpg"), "e-flowers/delivery-proofs"),
    
    # Seller Finished Product Prep Proofs (Fresh angles!)
    "seller_garden": (os.path.join(artifacts_dir, "seller_prep_garden_plants_1790806259659.jpg"), "e-flowers/seller-preps"),
    "seller_flower": (os.path.join(artifacts_dir, "seller_prep_flower_shop_1790806278946.jpg"), "e-flowers/seller-preps"),
    "seller_luxury": (os.path.join(artifacts_dir, "seller_prep_speaking_flowers_1790806298650.jpg"), "e-flowers/seller-preps"),
    
    # GCash Receipts matching exact amounts!
    "gcash_406_90": (os.path.join(artifacts_dir, "gcash_receipt_406_90_1790806318945.jpg"), "e-flowers/payments"),
    "gcash_836_16": (os.path.join(artifacts_dir, "gcash_receipt_836_16_1790806344842.jpg"), "e-flowers/payments"),
    "gcash_562_18": (os.path.join(artifacts_dir, "gcash_receipt_562_18_1790806363263.jpg"), "e-flowers/payments"),
    "gcash_314_64": (os.path.join(artifacts_dir, "gcash_receipt_314_64_1790806390952.jpg"), "e-flowers/payments"),
    "gcash_313_54": (os.path.join(artifacts_dir, "gcash_receipt_313_54_1790806416306.jpg"), "e-flowers/payments"),
    "gcash_570_00": (os.path.join(artifacts_dir, "gcash_receipt_570_00_1790806444169.jpg"), "e-flowers/payments"),
    "gcash_565_00": (os.path.join(artifacts_dir, "gcash_receipt_565_00_1790806470550.jpg"), "e-flowers/payments"),
    "gcash_880_00": (os.path.join(artifacts_dir, "gcash_receipt_880_00.jpg"), "e-flowers/payments"),
    "gcash_3320_00": (os.path.join(artifacts_dir, "gcash_receipt_3320_00.jpg"), "e-flowers/payments"),
}

uploaded_map_file = os.path.join(os.path.dirname(__file__), "uploaded_simulation_assets.json")

with app.app_context():
    uploaded_urls = {}
    if os.path.exists(uploaded_map_file):
        try:
            with open(uploaded_map_file, "r") as f:
                uploaded_urls = json.load(f)
        except Exception:
            pass

    for key, (path, folder) in images_to_upload.items():
        if key in uploaded_urls and uploaded_urls[key]:
            print(f"⏩ Already uploaded {key}: {uploaded_urls[key]}")
            continue
        print(f"Uploading {key} from {path}...")
        res = cloudinary.uploader.upload(path, folder=folder)
        url = res.get("secure_url") or res.get("url")
        print(f"✅ Uploaded {key} -> {url}")
        uploaded_urls[key] = url

    with open(uploaded_map_file, "w") as f:
        json.dump(uploaded_urls, f, indent=2)

print("🎉 All assets uploaded and saved to uploaded_simulation_assets.json")
