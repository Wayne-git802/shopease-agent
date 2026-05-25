import re
from urllib.parse import quote


IMAGE_KEYWORDS = [
    # (keywords, query, emoji)
    (('air conditioner', 'split ac', 'inverter ac', 'cooling', 'ac'), 'air-conditioner', '❄️'),
    (('helmet', 'visor', 'motorbike', 'motorcycle'), 'motorcycle-helmet', '🪖'),
    (('steamer', 'garment', 'steam iron', 'iron'), 'garment-steamer', '👕'),
    (('water purifier', 'pureit', 'filter', 'purifier'), 'water-purifier', '💧'),
    (('fan', 'crompton', 'havells', 'ceiling fan'), 'electric-fan', '🌀'),
    (('heater', 'ptc', 'room heater'), 'room-heater', '🔥'),
    (('cook', 'kitchen', 'pressure cooker', 'pan', 'mixer', 'grinder',
      'inalsa', 'usha', 'morphy', 'hamilton beach', 'blender', 'toaster',
      'microwave', 'oven', 'induction'), 'kitchen-appliance', '🍳'),
    (('coffee', 'espresso', 'cappuccino', 'latte'), 'coffee-maker', '☕'),
    (('laptop', 'notebook', 'computer', 'desktop', 'pc', 'thinkpad', 'macbook'), 'laptop-computer', '💻'),
    (('phone', 'smartphone', 'mobile', 'iphone', 'samsung', 'oneplus'), 'smartphone', '📱'),
    (('headphone', 'earbud', 'speaker', 'bluetooth', 'earphone', 'audio'), 'headphones', '🎧'),
    (('watch', 'fitness tracker', 'smartwatch', 'wearable'), 'smart-watch', '⌚'),
    (('camera', 'lens', 'dslr', 'photography', 'canon', 'nikon', 'sony'), 'camera', '📷'),
    (('shoe', 'sneaker', 'sandal', 'boot', 'footwear', 'slipper'), 'shoes', '👟'),
    (('shirt', 'jacket', 'dress', 'jeans', 'clothing', 'tshirt', 't-shirt',
      'sweater', 'hoodie', 'trouser', 'coat', 'suit'), 'clothing', '👔'),
    (('bag', 'luggage', 'backpack', 'suitcase', 'wallet', 'purse', 'handbag'), 'luggage', '🎒'),
    (('beauty', 'cream', 'makeup', 'skin', 'shampoo', 'cosmetic', 'lipstick',
      'perfume', 'lotion', 'soap'), 'beauty-products', '💄'),
    (('pet', 'dog', 'cat', 'fish', 'bird', 'animal'), 'pet-supplies', '🐾'),
    (('grocery', 'food', 'cereal', 'snack', 'tea', 'beverage', 'drink',
      'chocolate', 'biscuit', 'noodle', 'rice', 'oil', 'spice'), 'grocery-products', '🛒'),
    (('book', 'novel', 'textbook', 'notebook', 'stationery', 'pen', 'pencil'), 'books', '📚'),
    (('toy', 'baby', 'doll', 'lego', 'puzzle', 'game'), 'toys', '🧸'),
    (('sports', 'fitness', 'yoga', 'gym', 'exercise', 'dumbbell',
      'treadmill', 'cycle'), 'fitness-equipment', '🏋️'),
    (('guitar', 'piano', 'music', 'instrument', 'drum', 'violin', 'keyboard'), 'musical-instrument', '🎵'),
    (('furniture', 'chair', 'table', 'sofa', 'bed', 'desk', 'shelf',
      'cabinet', 'wardrobe', 'mattress'), 'home-furniture', '🛋️'),
    (('industrial', 'tool', 'hardware', 'drill', 'screw', 'hammer',
      'wrench', 'pliers'), 'industrial-tools', '🔧'),
    (('garden', 'plant', 'flower', 'seed', 'fertilizer', 'pot', 'soil'), 'garden-tools', '🌿'),
    (('tv', 'television', 'monitor', 'display', 'screen'), 'television', '🖥️'),
    (('printer', 'scanner', 'cartridge', 'toner'), 'printer', '🖨️'),
    (('router', 'modem', 'networking', 'wifi'), 'networking', '📡'),
    (('drone', 'quadcopter'), 'drone', '🛸'),
    (('gaming', 'console', 'playstation', 'xbox', 'nintendo', 'controller'), 'gaming', '🎮'),
    (('bike', 'bicycle', 'cycling'), 'bicycle', '🚲'),
    (('car', 'automobile', 'vehicle'), 'car-accessories', '🚗'),
    (('jewelry', 'jewellery', 'necklace', 'ring', 'bracelet', 'earring'), 'jewelry', '💍'),
    (('medicine', 'health', 'vitamin', 'supplement', 'protein'), 'health-supplements', '💊'),
    (('light', 'lamp', 'bulb', 'lighting', 'led'), 'lighting', '💡'),
    (('battery', 'charger', 'power bank', 'cable', 'adapter'), 'accessories', '🔋'),
]


# Extended palette — 12 color pairs for more variety
PALETTE = [
    ('0f766e', 'ccfbf1'),   # teal
    ('2563eb', 'dbeafe'),   # blue
    ('7c3aed', 'ede9fe'),   # purple
    ('ea580c', 'ffedd5'),   # orange
    ('be123c', 'ffe4e6'),   # rose
    ('047857', 'd1fae5'),   # emerald
    ('b45309', 'fef3c7'),   # amber
    ('1d4ed8', 'eff6ff'),   # royal blue
    ('6d28d9', 'f5f3ff'),   # violet
    ('db2777', 'fce7f3'),   # pink
    ('0e7490', 'ecfeff'),   # cyan
    ('65a30d', 'ecfccb'),   # lime
]


def _slug(value):
    cleaned = re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')
    return cleaned or 'product'


def product_image_url(product):
    if getattr(product, 'image', None):
        return product.image

    category = getattr(product, 'category', None)
    category_name = getattr(category, 'name', '') if category else ''
    text = f'{getattr(product, "name", "")} {category_name}'.lower()

    query = ''
    emoji = '📦'  # default
    for keywords, image_query, icon in IMAGE_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            query = image_query
            emoji = icon
            break

    if not query:
        query = _slug(category_name or getattr(product, 'name', '')).split('-')[0]
        # pick emoji from first letter if no match
        emoji = '🛍️'

    label = query.replace('-', ' ').title()

    lock = int(getattr(product, 'id', None) or getattr(product, 'pk', None) or 1)
    ink, bg = PALETTE[lock % len(PALETTE)]

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500" viewBox="0 0 500 500">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#{bg}"/>
      <stop offset="100%" stop-color="#{ink}" stop-opacity="0.12"/>
    </linearGradient>
  </defs>
  <rect width="500" height="500" rx="36" fill="url(#g)"/>
  <circle cx="390" cy="108" r="74" fill="#ffffff" opacity="0.55"/>
  <circle cx="118" cy="396" r="96" fill="#ffffff" opacity="0.40"/>
  <circle cx="420" cy="440" r="48" fill="#ffffff" opacity="0.30"/>
  <rect x="76" y="108" width="348" height="284" rx="32" fill="#ffffff" opacity="0.90"/>
  <rect x="104" y="140" width="292" height="152" rx="18" fill="#{ink}" opacity="0.08"/>
  <text x="250" y="248" text-anchor="middle" font-family="Apple Color Emoji, Segoe UI Emoji, Noto Color Emoji, sans-serif" font-size="80">{emoji}</text>
  <text x="250" y="344" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="26" font-weight="700" fill="#{ink}" letter-spacing="1">{label}</text>
</svg>'''
    return f'data:image/svg+xml;charset=UTF-8,{quote(svg)}'
