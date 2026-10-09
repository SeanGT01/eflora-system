import os
import sys
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

print('Re-uploading zoomed GCash receipts to Cloudinary...')

for oid in order_ids:
    gcash_file = os.path.join(GCASH_DIR, f'gcash_receipt_{oid}.jpg')
    
    # Upload to Cloudinary with unique versioned public ID
    resp = cloudinary.uploader.upload(
        gcash_file,
        folder='simulation_proofs',
        public_id=f'gcash_clean_card_{oid}',
        overwrite=True
    )
    url = resp['secure_url']
    pid = resp['public_id']
    print(f'Order #{oid}: uploaded {url}')
    
    # Update orders table in Postgres
    cur.execute('''
        UPDATE orders
        SET payment_proof_url = %s,
            payment_proof = %s,
            payment_proof_public_id = %s
        WHERE id = %s
    ''', (url, pid, pid, oid))

conn.commit()
conn.close()

print('\nSuccessfully updated all 11 orders in database with zoomed GCash receipts!')
