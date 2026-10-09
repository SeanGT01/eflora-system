import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import urllib.request
import psycopg2
from urllib.parse import urlparse
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import cloudinary
import cloudinary.uploader
from app.config import Config

# Setup Cloudinary
cloudinary.config(
    cloud_name=Config.CLOUDINARY_CLOUD_NAME,
    api_key=Config.CLOUDINARY_API_KEY,
    api_secret=Config.CLOUDINARY_API_SECRET
)

PROOFS_DIR = r'C:\Users\seanm\OneDrive\Desktop\eflowers-system\scripts\generated_order_proofs'
os.makedirs(PROOFS_DIR, exist_ok=True)

# Order metadata and product sources
ORDERS_DATA = [
    {
        'id': 808,
        'store_id': 21,
        'store_name': 'Princess Rasec Botanical Garden',
        'items': ['product_samples/808_soil.jpg', 'product_samples/808_pots.jpg'],
        'address': 'Block 4 Lot 12, Villa Zaragosa, Brgy. Silangan, Calauan, Laguna',
        'rider': 'Eduardo "Eddie" Santos',
        'time_str': '2026-09-22 11:10 AM PHT'
    },
    {
        'id': 809,
        'store_id': 21,
        'store_name': 'Princess Rasec Botanical Garden',
        'items': ['product_samples/809_bonsai.jpg', 'product_samples/809_cocopeat.jpg'],
        'address': '78 J. Rizal St., Poblacion, Luisiana, Laguna',
        'rider': 'Eduardo "Eddie" Santos',
        'time_str': '2026-09-23 12:25 PM PHT'
    },
    {
        'id': 810,
        'store_id': 21,
        'store_name': 'Princess Rasec Botanical Garden',
        'items': ['product_samples/810_pots.jpg', 'product_samples/810_yaramila.jpg'],
        'address': 'Unit 2B, Greenhills Subd., San Pablo City, Laguna',
        'rider': 'Eduardo "Eddie" Santos',
        'time_str': '2026-09-24 01:15 PM PHT'
    },
    {
        'id': 811,
        'store_id': 21,
        'store_name': 'Princess Rasec Botanical Garden',
        'items': ['product_samples/808_soil.jpg', 'product_samples/811_fertilizer.jpg'],
        'address': 'Zone 3, Barangay Dayap, Calauan, Laguna',
        'rider': 'Eduardo "Eddie" Santos',
        'time_str': '2026-09-25 03:40 PM PHT'
    },
    {
        'id': 812,
        'store_id': 21,
        'store_name': 'Princess Rasec Botanical Garden',
        'items': ['product_samples/812_shears.jpg', 'product_samples/812_sprayer.jpg'],
        'address': '15 Mabini St., Brgy. Sto. Domingo, Bay, Laguna',
        'rider': 'Eduardo "Eddie" Santos',
        'time_str': '2026-09-26 04:05 PM PHT'
    },
    {
        'id': 813,
        'store_id': 21,
        'store_name': 'Princess Rasec Botanical Garden',
        'items': ['product_samples/813_seedling.jpg', 'product_samples/813_soil.jpg'],
        'address': 'Sitio Ilaya, Brgy. San Buenaventura, Luisiana, Laguna',
        'rider': 'Eduardo "Eddie" Santos',
        'time_str': '2026-09-27 05:25 PM PHT'
    },
    {
        'id': 814,
        'store_id': 18,
        'store_name': 'AKS Coop Flowershop',
        'items': ['product_samples/814_roses.jpg'],
        'address': 'Purok 5, Brgy. Kanluran Kabubuhayan, Nagcarlan, Laguna',
        'rider': 'Lito Dela Torre',
        'time_str': '2026-09-25 03:35 PM PHT'
    },
    {
        'id': 815,
        'store_id': 18,
        'store_name': 'AKS Coop Flowershop',
        'items': ['product_samples/815_sunflower.jpg'],
        'address': 'Lot 8, Palm Grove Estate, Los Baños, Laguna',
        'rider': 'Lito Dela Torre',
        'time_str': '2026-09-26 04:10 PM PHT'
    },
    {
        'id': 816,
        'store_id': 18,
        'store_name': 'AKS Coop Flowershop',
        'items': ['product_samples/816_blue.jpg'],
        'address': 'Barangay Lamot 1, Calauan, Laguna',
        'rider': 'Lito Dela Torre',
        'time_str': '2026-09-27 03:15 PM PHT'
    },
    {
        'id': 817,
        'store_id': 18,
        'store_name': 'AKS Coop Flowershop',
        'items': ['product_samples/817_money.jpg'],
        'address': '22 Bonifacio St., Pila, Laguna',
        'rider': 'Lito Dela Torre',
        'time_str': '2026-09-28 04:45 PM PHT'
    },
    {
        'id': 818,
        'store_id': 22,
        'store_name': 'Speaking Flowers',
        'items': ['product_samples/818_premium.jpg'],
        'address': 'Barangay San Diego, San Pablo City, Laguna',
        'rider': 'Ramil "Mac" Hernandez',
        'time_str': '2026-09-28 01:05 PM PHT'
    }
]

def compose_base_product_image(item_paths):
    if len(item_paths) == 1:
        return Image.open(item_paths[0]).convert('RGB')
    
    # 2 items side by side
    im1 = Image.open(item_paths[0]).convert('RGB')
    im2 = Image.open(item_paths[1]).convert('RGB')
    
    target_h = 750
    w1 = int(im1.width * (target_h / im1.height))
    im1_r = im1.resize((w1, target_h), Image.Resampling.LANCZOS)
    
    w2 = int(im2.width * (target_h / im2.height))
    im2_r = im2.resize((w2, target_h), Image.Resampling.LANCZOS)
    
    total_w = w1 + w2 + 8
    canvas = Image.new('RGB', (total_w, target_h), (245, 245, 248))
    canvas.paste(im1_r, (0, 0))
    canvas.paste(im2_r, (w1 + 8, 0))
    return canvas

def make_seller_prep_image(base_img, order_id, store_name, out_path):
    w, h = base_img.size
    
    # Distinct angle: 3D perspective / affine tilt so it's clearly shot from a different angle
    skew_x = 0.04
    skew_y = -0.03
    matrix = (1, skew_x, -skew_x * h * 0.5, skew_y, 1, -skew_y * w * 0.5)
    transformed = base_img.transform(base_img.size, Image.Transform.AFFINE, matrix, Image.Resampling.BICUBIC)
    
    # Zoom/crop center 88%
    crop_w, crop_h = int(w * 0.06), int(h * 0.06)
    transformed = transformed.crop((crop_w, crop_h, w - crop_w, h - crop_h))
    
    # Warmer store lighting
    transformed = ImageEnhance.Color(transformed).enhance(1.06)
    transformed = ImageEnhance.Brightness(transformed).enhance(1.02)
    transformed = ImageEnhance.Contrast(transformed).enhance(1.04)
    
    # Seller readiness badge
    badge_img = Image.new('RGBA', transformed.size, (0, 0, 0, 0))
    bdraw = ImageDraw.Draw(badge_img)
    font_title = ImageFont.truetype('segoeuib.ttf', 16)
    font_sub = ImageFont.truetype('segoeui.ttf', 13)
    
    bdraw.rounded_rectangle((20, 20, 370, 78), radius=8, fill=(15, 23, 42, 220))
    bdraw.text((32, 28), f'{store_name.upper()} • READY', fill=(255, 255, 255), font=font_title)
    bdraw.text((32, 50), f'Order #{order_id} — Inspected & Packed for Dispatch', fill=(203, 213, 225), font=font_sub)
    
    final_img = Image.alpha_composite(transformed.convert('RGBA'), badge_img).convert('RGB')
    final_img.save(out_path, 'JPEG', quality=94)

def make_rider_delivery_image(base_img, order_id, address, rider_name, time_str, out_path):
    w, h = base_img.size
    
    # Handheld delivery camera tilt
    rotated = base_img.rotate(2.8, resample=Image.Resampling.BICUBIC, expand=True)
    rw, rh = rotated.size
    crop_w, crop_h = int(rw * 0.05), int(rh * 0.05)
    cropped = rotated.crop((crop_w, crop_h, rw - crop_w, rh - crop_h))
    
    # Natural daylight contrast
    cropped = ImageEnhance.Contrast(cropped).enhance(1.07)
    cropped = ImageEnhance.Color(cropped).enhance(1.05)
    
    cw, ch = cropped.size
    hud_h = 105
    hud_img = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
    hdraw = ImageDraw.Draw(hud_img)
    
    # Dark bottom banner with green POD accent line
    hdraw.rectangle((0, ch - hud_h, cw, ch), fill=(15, 23, 42, 230))
    hdraw.rectangle((0, ch - hud_h, cw, ch - hud_h + 3), fill=(34, 197, 94, 255))
    
    font_title = ImageFont.truetype('segoeuib.ttf', 17)
    font_body = ImageFont.truetype('segoeui.ttf', 13)
    
    hdraw.text((20, ch - hud_h + 14), f'✔ DELIVERED — ORDER #{order_id}', fill=(74, 222, 128, 255), font=font_title)
    addr_disp = address if len(address) < 55 else address[:52] + '...'
    hdraw.text((20, ch - hud_h + 42), f'📍 {addr_disp}', fill=(241, 245, 249, 255), font=font_body)
    hdraw.text((20, ch - hud_h + 68), f'🕒 {time_str}  •  Courier: {rider_name}', fill=(148, 163, 184, 255), font=font_body)
    
    final_img = Image.alpha_composite(cropped.convert('RGBA'), hud_img).convert('RGB')
    final_img.save(out_path, 'JPEG', quality=93)

def generate_all_proofs():
    print('Generating seller and rider proofs for all 11 orders...')
    for order in ORDERS_DATA:
        oid = order['id']
        base_img = compose_base_product_image(order['items'])
        
        seller_path = os.path.join(PROOFS_DIR, f'seller_prep_order_{oid}.jpg')
        rider_path = os.path.join(PROOFS_DIR, f'rider_delivery_order_{oid}.jpg')
        
        make_seller_prep_image(base_img, oid, order['store_name'], seller_path)
        make_rider_delivery_image(base_img, oid, order['address'], order['rider'], order['time_str'], rider_path)
        print(f'Done Order #{oid}: seller prep & rider proof generated.')

if __name__ == '__main__':
    generate_all_proofs()
