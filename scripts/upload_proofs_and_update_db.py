import os
import sys
import json
import psycopg2
from urllib.parse import urlparse
import cloudinary
import cloudinary.uploader

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.config import Config

# Setup Cloudinary
cloudinary.config(
    cloud_name=Config.CLOUDINARY_CLOUD_NAME,
    api_key=Config.CLOUDINARY_API_KEY,
    api_secret=Config.CLOUDINARY_API_SECRET
)

PROOFS_DIR = r'C:\Users\seanm\OneDrive\Desktop\eflowers-system\scripts\generated_order_proofs'
GCASH_DIR = r'C:\Users\seanm\OneDrive\Desktop\eflowers-system\scripts\generated_gcash_receipts'

# Connect to database
db_url = Config.SQLALCHEMY_DATABASE_URI
parsed = urlparse(db_url.replace('postgresql+psycopg2://', 'postgresql://'))
conn = psycopg2.connect(
    dbname=parsed.path[1:],
    user=parsed.username,
    password=parsed.password,
    host=parsed.hostname,
    port=parsed.port or 5432
)
cur = conn.cursor()

order_ids = list(range(808, 819))
uploaded_map = {}

print('Starting Cloudinary upload and database update for orders 808 to 818...')

for oid in order_ids:
    seller_file = os.path.join(PROOFS_DIR, f'seller_prep_order_{oid}.jpg')
    rider_file = os.path.join(PROOFS_DIR, f'rider_delivery_order_{oid}.jpg')
    gcash_file = os.path.join(GCASH_DIR, f'gcash_receipt_{oid}.jpg')
    
    print(f'\n--- Processing Order #{oid} ---')
    
    # 1. Upload Seller Prep Proof
    seller_resp = cloudinary.uploader.upload(
        seller_file,
        folder='simulation_proofs',
        public_id=f'seller_prep_matching_{oid}',
        overwrite=True
    )
    seller_url = seller_resp['secure_url']
    seller_pid = seller_resp['public_id']
    print(f'Seller prep URL: {seller_url}')
    
    # 2. Upload Rider Delivery Proof
    rider_resp = cloudinary.uploader.upload(
        rider_file,
        folder='simulation_proofs',
        public_id=f'rider_delivery_matching_{oid}',
        overwrite=True
    )
    rider_url = rider_resp['secure_url']
    rider_pid = rider_resp['public_id']
    print(f'Rider delivery URL: {rider_url}')
    
    # 3. Upload GCash Receipt
    gcash_resp = cloudinary.uploader.upload(
        gcash_file,
        folder='simulation_proofs',
        public_id=f'gcash_template_receipt_{oid}',
        overwrite=True
    )
    gcash_url = gcash_resp['secure_url']
    gcash_pid = gcash_resp['public_id']
    print(f'GCash receipt URL: {gcash_url}')
    
    uploaded_map[oid] = {
        'seller_url': seller_url,
        'seller_public_id': seller_pid,
        'rider_url': rider_url,
        'rider_public_id': rider_pid,
        'gcash_url': gcash_url,
        'gcash_public_id': gcash_pid
    }
    
    # Update orders table in Postgres
    # Check payment method first
    cur.execute('SELECT payment_method FROM orders WHERE id = %s', (oid,))
    pmethod = cur.fetchone()[0]
    
    if pmethod == 'gcash':
        cur.execute('''
            UPDATE orders
            SET done_preparing_proof_url = %s,
                done_preparing_proof = %s,
                done_preparing_proof_public_id = %s,
                delivery_proof_url = %s,
                delivery_proof = %s,
                delivery_proof_public_id = %s,
                payment_proof_url = %s,
                payment_proof = %s,
                payment_proof_public_id = %s
            WHERE id = %s
        ''', (
            seller_url, seller_pid, seller_pid,
            rider_url, rider_pid, rider_pid,
            gcash_url, gcash_pid, gcash_pid,
            oid
        ))
    else:
        # COD order (keeps payment_proof_url as is, or optionally set receipt)
        # We also set payment_proof_url so even if viewed in admin/seller modal, it shows the receipt
        cur.execute('''
            UPDATE orders
            SET done_preparing_proof_url = %s,
                done_preparing_proof = %s,
                done_preparing_proof_public_id = %s,
                delivery_proof_url = %s,
                delivery_proof = %s,
                delivery_proof_public_id = %s,
                payment_proof_url = %s,
                payment_proof = %s,
                payment_proof_public_id = %s
            WHERE id = %s
        ''', (
            seller_url, seller_pid, seller_pid,
            rider_url, rider_pid, rider_pid,
            gcash_url, gcash_pid, gcash_pid,
            oid
        ))

conn.commit()
conn.close()

# Save mapping to json file
with open(r'C:\Users\seanm\OneDrive\Desktop\eflowers-system\scripts\uploaded_matching_proofs.json', 'w') as f:
    json.dump(uploaded_map, f, indent=2)

print('\nSuccessfully updated all 11 orders with Cloudinary proofs and database entries!')
