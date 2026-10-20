"""
app/cost_helpers.py
Utility functions for calculating realistic, category-based cost prices and profit margins
for florist and gardening inventory items.
"""

def get_realistic_margin_rate(product_name='', category_path='', item_id=None):
    """
    Determine a realistic market gross margin percentage for a flower, plant, or garden product.
    Returns a float between 0.20 and 0.80 (e.g., 0.62 for 62% margin).
    """
    p_name = (product_name or '').lower()
    cat = (category_path or '').lower()

    # Deterministic organic variation (+/- 3%) based on item ID if provided
    var_pct = (((item_id or 1) * 17) % 7 - 3) * 0.01 if item_id else 0.0

    if any(k in p_name for k in ['money', 'ribbon', 'satin', 'artificial', 'handmade', 'shiny violet', 'crochet']) or \
       'money' in cat or 'artificial' in cat:
        base = 0.70
    elif any(k in p_name for k in ['soil', 'fertilizer', 'yaramila', 'yaravera', 'insecticide', 'cymbush', 'chemical', 'seedling tray', 'balde', 'floral foam']) or \
         any(k in cat for k in ['fertilizer', 'seedling', 'balde']):
        base = 0.26
    elif any(k in p_name for k in ['pot', 'wallpot', 'planter', 'robol', 'udalo']) or 'pots' in cat:
        base = 0.35
    elif any(k in p_name for k in ['wire', 'sprayer', 'pruning', 'shear']) or 'tools' in cat:
        base = 0.38
    elif any(k in p_name for k in ['candle', 'esperma', 'scented']) or 'candle' in cat:
        base = 0.42
    elif any(k in p_name for k in ['bonsai', 'fukienta', 'fig', 'poinsettia', 'swiss cheese', 'monstera', 'calathea', 'ficus', 'potted', 'plant']) or \
         'potted' in cat or 'bonsai' in cat:
        base = 0.52
    elif any(k in p_name for k in ['standee', 'wedding package', 'sympathy standee']) or \
         ('sympathy' in cat and 'standee' in p_name):
        base = 0.54
    elif any(k in p_name for k in ['arrangement', 'tambilina', 'basket']) or 'arrangement' in cat:
        base = 0.58
    elif ('fresh flowers' in cat or any(k in p_name for k in ['bundle', '1pc', 'stem', 'radus', 'aster', 'mum', 'rose'])) and 'bouquet' not in p_name:
        base = 0.50
    elif 'bouquet' in p_name or 'bouquet' in cat or 'valentines' in cat:
        base = 0.62
    else:
        base = 0.50

    return max(0.20, min(0.80, base + var_pct))


def calculate_realistic_cost(price, margin_rate=None, product_name='', category_path='', item_id=None):
    """
    Calculate a realistic wholesale / capital cost price based on retail price and product category.
    Rounds to clean commercial price points (e.g. nearest ₱0.50, ₱1, ₱5, or ₱50).
    """
    try:
        p = float(price or 0.0)
    except (ValueError, TypeError):
        return 0.0
    if p <= 0:
        return 0.0

    if margin_rate is None:
        margin_rate = get_realistic_margin_rate(product_name, category_path, item_id)

    raw_cost = p * (1.0 - margin_rate)
    if p < 50:
        cost = round(raw_cost * 2) / 2
    elif p < 250:
        cost = round(raw_cost)
    elif p < 1000:
        cost = round(raw_cost / 5.0) * 5.0
    else:
        cost = round(raw_cost / 50.0) * 50.0

    if cost >= p:
        cost = round(p * 0.85, 2)
    elif cost <= 0:
        cost = round(p * 0.30, 2)
    return round(cost, 2)
