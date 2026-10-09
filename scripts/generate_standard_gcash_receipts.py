import os
from PIL import Image, ImageDraw, ImageFont

template_path = r'C:\Users\seanm\.gemini\antigravity-ide\brain\d0bd21a1-0f44-42d0-a16d-ba7341f5137d\.user_uploaded\media_1790807623481.jpg'
out_dir = r'C:\Users\seanm\OneDrive\Desktop\eflowers-system\scripts\generated_gcash_receipts'
os.makedirs(out_dir, exist_ok=True)

font_name = ImageFont.truetype('segoeuib.ttf', 20)
font_phone = ImageFont.truetype('segoeuib.ttf', 16)
font_amt = ImageFont.truetype('segoeuib.ttf', 20)
font_tot = ImageFont.truetype('segoeuib.ttf', 30)
font_ref_lbl = ImageFont.truetype('segoeui.ttf', 13)
font_ref_num = ImageFont.truetype('segoeuib.ttf', 13)
font_date = ImageFont.truetype('segoeui.ttf', 12)

# Orders metadata matching exact totals, with subtle size variations around 237x461
orders_meta = [
    {
        'order_id': 808, 'amount_str': '406.90', 'tot_str': '₱406.90',
        'name': 'PR•••••••S R.', 'phone': '+63 917 842 1904',
        'ref': '9045283185633', 'date': 'Sep 22, 2026 09:15 AM',
        'size': (237, 461), 'quality': 95
    },
    {
        'order_id': 809, 'amount_str': '836.16', 'tot_str': '₱836.16',
        'name': 'PR••••••S B.', 'phone': '+63 956 718 7071',
        'ref': '9045812938471', 'date': 'Sep 23, 2026 10:30 AM',
        'size': (235, 457), 'quality': 94
    },
    {
        'order_id': 810, 'amount_str': '562.18', 'tot_str': '₱562.18',
        'name': 'EL••••A R.', 'phone': '+63 928 412 8839',
        'ref': '9046182947102', 'date': 'Sep 24, 2026 11:20 AM',
        'size': (240, 466), 'quality': 95
    },
    {
        'order_id': 811, 'amount_str': '505.00', 'tot_str': '₱505.00',
        'name': 'RO•••••A S.', 'phone': '+63 908 619 4421',
        'ref': '9046529183740', 'date': 'Sep 25, 2026 01:45 PM',
        'size': (237, 461), 'quality': 95
    },
    {
        'order_id': 812, 'amount_str': '314.64', 'tot_str': '₱314.64',
        'name': 'PR•••••••S G.', 'phone': '+63 915 329 8812',
        'ref': '9046918273645', 'date': 'Sep 26, 2026 02:10 PM',
        'size': (238, 463), 'quality': 95
    },
    {
        'order_id': 813, 'amount_str': '313.54', 'tot_str': '₱313.54',
        'name': 'RA••••S B.', 'phone': '+63 927 503 1184',
        'ref': '9047281940283', 'date': 'Sep 27, 2026 03:30 PM',
        'size': (234, 455), 'quality': 94
    },
    {
        'order_id': 814, 'amount_str': '570.00', 'tot_str': '₱570.00',
        'name': 'AK• C••P', 'phone': '+63 919 440 2819',
        'ref': '9047619284710', 'date': 'Sep 25, 2026 09:40 AM',
        'size': (236, 459), 'quality': 95
    },
    {
        'order_id': 815, 'amount_str': '565.00', 'tot_str': '₱565.00',
        'name': 'AK• M••••••••E', 'phone': '+63 939 882 1045',
        'ref': '9048029184719', 'date': 'Sep 26, 2026 10:15 AM',
        'size': (241, 468), 'quality': 94
    },
    {
        'order_id': 816, 'amount_str': '880.00', 'tot_str': '₱880.00',
        'name': 'JU••••A C.', 'phone': '+63 956 312 9901',
        'ref': '9048391827401', 'date': 'Sep 27, 2026 01:20 PM',
        'size': (235, 458), 'quality': 95
    },
    {
        'order_id': 817, 'amount_str': '625.00', 'tot_str': '₱625.00',
        'name': 'MA••••A D.', 'phone': '+63 917 620 4813',
        'ref': '9048719284719', 'date': 'Sep 28, 2026 02:50 PM',
        'size': (239, 465), 'quality': 93
    },
    {
        'order_id': 818, 'amount_str': '3,320.00', 'tot_str': '₱3,320.00',
        'name': 'SP••••••G F.', 'phone': '+63 920 918 3350',
        'ref': '9049182739401', 'date': 'Sep 28, 2026 11:10 AM',
        'size': (237, 461), 'quality': 95
    }
]

def generate_receipts():
    for meta in orders_meta:
        im = Image.open(template_path).copy()
        draw = ImageDraw.Draw(im)
        
        # 1. Recipient Name
        draw.rectangle((45, 212, 425, 246), fill=(255, 255, 255))
        name_text = meta['name']
        name_bbox = draw.textbbox((0, 0), name_text, font=font_name)
        name_w = name_bbox[2] - name_bbox[0]
        draw.text(((471 - name_w) // 2, 218), name_text, fill=(0, 39, 123), font=font_name)
        
        # 2. Phone pill
        draw.rectangle((120, 250, 350, 286), fill=(255, 255, 255))
        phone_text = meta['phone']
        phone_bbox = draw.textbbox((0, 0), phone_text, font=font_phone)
        phone_w = phone_bbox[2] - phone_bbox[0]
        pill_x0 = (471 - phone_w) // 2 - 14
        pill_x1 = (471 + phone_w) // 2 + 14
        draw.rounded_rectangle((pill_x0, 252, pill_x1, 282), radius=15, fill=(227, 246, 255))
        draw.text(((471 - phone_w) // 2, 257), phone_text, fill=(8, 36, 95), font=font_phone)
        
        # 3. Amount
        draw.rectangle((280, 385, 435, 420), fill=(255, 255, 255))
        amt_text = meta['amount_str']
        amt_bbox = draw.textbbox((0, 0), amt_text, font=font_amt)
        amt_w = amt_bbox[2] - amt_bbox[0]
        draw.text((422 - amt_w, 390), amt_text, fill=(7, 26, 54), font=font_amt)
        
        # 4. Total Amount Sent
        draw.rectangle((240, 465, 435, 520), fill=(255, 255, 255))
        tot_text = meta['tot_str']
        tot_bbox = draw.textbbox((0, 0), tot_text, font=font_tot)
        tot_w = tot_bbox[2] - tot_bbox[0]
        draw.text((422 - tot_w, 473), tot_text, fill=(6, 39, 73), font=font_tot)
        
        # 5. Ref No & Date
        draw.rectangle((35, 540, 435, 575), fill=(245, 248, 255))
        draw.text((46, 548), 'Ref No. ', fill=(113, 130, 155), font=font_ref_lbl)
        ref_lbl_bbox = draw.textbbox((0, 0), 'Ref No. ', font=font_ref_lbl)
        draw.text((46 + (ref_lbl_bbox[2] - ref_lbl_bbox[0]), 548), meta['ref'], fill=(15, 37, 66), font=font_ref_num)
        
        date_text = meta['date']
        date_bbox = draw.textbbox((0, 0), date_text, font=font_date)
        date_w = date_bbox[2] - date_bbox[0]
        draw.text((422 - date_w, 550), date_text, fill=(113, 130, 155), font=font_date)
        
        # 6. Crop top part (removing status bar and 'Express Send'), cropping exactly like user template
        cropped = im.crop((0, 118, 471, 1010))
        
        # 7. Resize to target dimensions
        final_receipt = cropped.resize(meta['size'], Image.Resampling.LANCZOS)
            
        out_file = os.path.join(out_dir, f"gcash_receipt_{meta['order_id']}.jpg")
        final_receipt.save(out_file, 'JPEG', quality=meta['quality'])
        print(f"Order {meta['order_id']}: saved receipt at {final_receipt.size}, quality={meta['quality']}")

if __name__ == '__main__':
    generate_receipts()
