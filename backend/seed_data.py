import os
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')

import django
django.setup()

from users.models import User
from products.models import Category, Inventory, Product, Shop


def user(username, password, email, display_name, *, staff=False, superuser=False):
    obj, created = User.objects.get_or_create(
        username=username,
        defaults={'email': email, 'display_name': display_name, 'is_staff': staff, 'is_superuser': superuser},
    )
    changed = False
    if created or not obj.has_usable_password():
        obj.set_password(password)
        changed = True
    for field, value in {
        'email': email,
        'display_name': display_name,
        'is_staff': staff,
        'is_superuser': superuser,
        'is_active': True,
    }.items():
        if getattr(obj, field) != value:
            setattr(obj, field, value)
            changed = True
    if changed:
        obj.save()
    return obj


def category(name, slug, parent=None):
    obj, _ = Category.objects.get_or_create(slug=slug, defaults={'name': name, 'parent': parent})
    if obj.name != name or obj.parent != parent:
        obj.name = name
        obj.parent = parent
        obj.save()
    return obj


def shop(owner, name, description):
    obj, _ = Shop.objects.get_or_create(
        user=owner,
        defaults={'shop_name': name, 'description': description, 'rating': Decimal('4.8')},
    )
    obj.shop_name = name
    obj.description = description
    obj.save()
    return obj


def product(name, cat, seller, store, price, stock, image):
    obj, _ = Product.objects.get_or_create(
        name=name,
        defaults={
            'description': f'{name} for ShopEase inventory demo.',
            'price': Decimal(str(price)),
            'stock': stock,
            'image': image,
            'category': cat,
            'seller': seller,
            'shop': store,
            'is_active': True,
        },
    )
    obj.description = f'{name} for ShopEase inventory demo.'
    obj.price = Decimal(str(price))
    obj.image = image
    obj.category = cat
    obj.seller = seller
    obj.shop = store
    obj.is_active = True
    obj.save()
    Inventory.objects.update_or_create(
        product=obj,
        defaults={'quantity': stock},
    )
    return obj


admin = user('admin', 'admin123', 'admin@shopease.local', 'Admin', staff=True, superuser=True)
customer = user('customer01', 'customer123', 'customer01@shopease.local', 'Customer One')
alice = user('seller_alice', 'seller123', 'alice@shopease.local', 'Alice')
charlie = user('seller_charlie', 'seller123', 'charlie@shopease.local', 'Charlie')
diana = user('seller_diana', 'seller123', 'diana@shopease.local', 'Diana')

electronics = category('Electronics', 'electronics')
home = category('Home & Living', 'home-living')
books = category('Books', 'books')
audio = category('Audio', 'audio', electronics)
wearables = category('Wearables', 'wearables', electronics)
kitchen = category('Kitchen', 'kitchen', home)
programming = category('Programming', 'programming', books)

alice_shop = shop(alice, "Alice's Electronics", 'Smart devices, headphones, and wearables.')
charlie_shop = shop(charlie, "Charlie's Home & Living", 'Kitchen and home products.')
diana_shop = shop(diana, "Diana's Book Nook", 'Books for study and personal growth.')

product(
    'Wireless Bluetooth Headphones',
    audio,
    alice,
    alice_shop,
    '79.99',
    50,
    'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=800',
)
product(
    'Smart Watch Pro',
    wearables,
    alice,
    alice_shop,
    '299.99',
    20,
    'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=800',
)
product(
    'Coffee Maker Deluxe',
    kitchen,
    charlie,
    charlie_shop,
    '149.99',
    20,
    'https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=800',
)
product(
    'Python Mastery Guide',
    programming,
    diana,
    diana_shop,
    '49.99',
    35,
    'https://images.unsplash.com/photo-1512820790803-83ca734da794?w=800',
)

print('Demo data is ready.')
print('Admin: admin / admin123')
print('Customer: customer01 / customer123')
print('Sellers: seller_alice, seller_charlie, seller_diana / seller123')
