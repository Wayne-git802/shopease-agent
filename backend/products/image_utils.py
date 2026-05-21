import re
from urllib.parse import quote


IMAGE_KEYWORDS = [
    (('air conditioner', 'split ac', 'inverter ac', 'cooling'), 'air-conditioner'),
    (('helmet', 'visor', 'motorbike'), 'motorcycle-helmet'),
    (('steamer', 'garment', 'steam iron', 'iron'), 'garment-steamer'),
    (('water purifier', 'pureit', 'filter'), 'water-purifier'),
    (('fan', 'crompton', 'havells'), 'electric-fan'),
    (('heater', 'ptc'), 'room-heater'),
    (('cook', 'kitchen', 'pressure cooker', 'pan', 'mixer', 'grinder', 'inalsa', 'usha', 'morphy', 'hamilton beach'), 'kitchen-appliance'),
    (('coffee', 'espresso'), 'coffee-maker'),
    (('laptop', 'notebook', 'computer'), 'laptop-computer'),
    (('phone', 'smartphone', 'mobile'), 'smartphone'),
    (('headphone', 'earbud', 'speaker', 'bluetooth'), 'headphones'),
    (('watch', 'fitness tracker'), 'smart-watch'),
    (('camera', 'lens'), 'camera'),
    (('shoe', 'sneaker', 'sandal', 'boot'), 'shoes'),
    (('shirt', 'jacket', 'dress', 'jeans', 'clothing'), 'clothing'),
    (('bag', 'luggage', 'backpack', 'suitcase'), 'luggage'),
    (('beauty', 'cream', 'makeup', 'skin', 'shampoo'), 'beauty-products'),
    (('pet', 'dog', 'cat'), 'pet-supplies'),
    (('grocery', 'food', 'cereal', 'snack', 'tea'), 'grocery-products'),
    (('book', 'novel'), 'books'),
    (('toy', 'baby'), 'toys'),
    (('sports', 'fitness', 'yoga', 'gym'), 'fitness-equipment'),
    (('guitar', 'piano', 'music', 'instrument'), 'musical-instrument'),
    (('furniture', 'chair', 'table', 'sofa', 'bed'), 'home-furniture'),
    (('industrial', 'tool', 'hardware'), 'industrial-tools'),
    (('garden', 'plant'), 'garden-tools'),
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
    for keywords, image_query in IMAGE_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            query = image_query
            break
    if not query:
        query = _slug(category_name or getattr(product, 'name', '')).split('-')[0]

    label = query.replace('-', ' ').title()
    palette = [
        ('0f766e', 'ccfbf1'),
        ('2563eb', 'dbeafe'),
        ('7c3aed', 'ede9fe'),
        ('ea580c', 'ffedd5'),
        ('be123c', 'ffe4e6'),
        ('047857', 'd1fae5'),
    ]
    lock = int(getattr(product, 'id', None) or getattr(product, 'pk', None) or 1)
    ink, bg = palette[lock % len(palette)]
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500" viewBox="0 0 500 500">
  <rect width="500" height="500" rx="36" fill="#{bg}"/>
  <circle cx="390" cy="108" r="74" fill="#ffffff" opacity="0.62"/>
  <circle cx="118" cy="396" r="96" fill="#ffffff" opacity="0.48"/>
  <rect x="96" y="126" width="308" height="214" rx="28" fill="#ffffff" opacity="0.86"/>
  <rect x="132" y="164" width="236" height="106" rx="16" fill="#{ink}" opacity="0.18"/>
  <path d="M164 306h172" stroke="#{ink}" stroke-width="18" stroke-linecap="round" opacity="0.68"/>
  <text x="250" y="402" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="34" font-weight="700" fill="#{ink}">{label}</text>
</svg>'''
    return f'data:image/svg+xml;charset=UTF-8,{quote(svg)}'
