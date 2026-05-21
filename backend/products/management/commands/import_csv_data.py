"""
Import the CSV files in data(1)/ into the runnable SQLite database.

Usage:
    python manage.py import_csv_data --clear
"""
import base64
import csv
import hashlib
import json
import os
import re
from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import connection, transaction


BATCH_SIZE = 5000

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = _HERE
for _ in range(4):
    _BACKEND_DIR = os.path.dirname(_BACKEND_DIR)
DATA_DIR = r'C:\Users\admin\Desktop\ShopEase\data_new'


def read_csv(filename):
    path = os.path.join(DATA_DIR, filename)
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def csv_exists(filename):
    return os.path.exists(os.path.join(DATA_DIR, filename))


def fast_password_hash(raw_password):
    algo = 'pbkdf2_sha256'
    iterations = 1000
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac('sha256', raw_password.encode(), salt.encode(), iterations, dklen=32)
    return f'{algo}${iterations}${salt}${base64.b64encode(dk).decode().strip()}'


def slugify(value):
    slug = re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')
    return slug or 'category'


def clamp(value, low, high):
    return max(low, min(high, value))


def to_int(value, default=0):
    try:
        return int(Decimal(str(value or default)))
    except Exception:
        return default


def to_decimal(value, default='0'):
    try:
        return Decimal(str(value or default))
    except Exception:
        return Decimal(default)


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='Clear existing imported data before import')

    @transaction.atomic
    def handle(self, *args, **options):
        if options['clear']:
            self._clear_all()

        user_map = self._import_users()
        category_map = self._import_categories()
        shop_map, store_seller_map = self._import_shops(user_map)
        product_map = self._import_products(shop_map, store_seller_map, category_map)
        inventory_map = self._import_inventory(product_map)
        order_map = self._import_orders(user_map, product_map)
        self._import_carts(user_map, product_map)
        refund_map = self._import_refunds(order_map)
        review_map = self._import_reviews(order_map)
        self._import_inventory_transactions(inventory_map)
        self._import_audit_logs(user_map, shop_map, product_map, category_map, refund_map, review_map)

        self.stdout.write(self.style.SUCCESS('All CSV data imported successfully.'))

    @staticmethod
    def _chunk(items, size=BATCH_SIZE):
        batch = []
        for item in items:
            batch.append(item)
            if len(batch) >= size:
                yield batch
                batch = []
        if batch:
            yield batch

    @staticmethod
    def _clear_all():
        from admin_api.models import AuditLog
        from orders.models import Cart, RefundItem, Refund, OrderItem, Order
        from products.models import Review, InventoryTransaction, Inventory, Product, ShopFollow, Shop, Category
        from users.models import User

        preserved = list(User.objects.filter(username__in=['admin', 'wayne']).values())

        for model in [
            AuditLog, RefundItem, Refund, OrderItem, Order, Cart, Review,
            InventoryTransaction, Inventory, Product, ShopFollow, Shop, Category,
        ]:
            model.objects.all().delete()
        User.objects.exclude(username__in=['admin', 'wayne']).delete()

        tables = [
            'audit_logs', 'refund_items', 'refunds', 'order_items', 'orders',
            'carts', 'reviews', 'inventory_transactions', 'inventory',
            'products', 'shop_follows', 'shops', 'categories',
        ]
        with connection.cursor() as cursor:
            if connection.vendor == 'sqlite':
                for table in tables:
                    cursor.execute("DELETE FROM sqlite_sequence WHERE name = %s", [table])
            elif connection.vendor == 'mysql':
                for table in tables:
                    cursor.execute(f'ALTER TABLE {table} AUTO_INCREMENT = 1')

        for u in preserved:
            User.objects.get_or_create(
                username=u['username'],
                defaults=u,
            )
        return preserved

    @staticmethod
    def _load_multi_map(filename, key_field, value_field_or_func):
        result = defaultdict(list)
        if not csv_exists(filename):
            return result
        for row in read_csv(filename):
            value = value_field_or_func(row) if callable(value_field_or_func) else row.get(value_field_or_func, '')
            result[row[key_field]].append(value)
        return result

    @staticmethod
    def _format_address(row):
        parts = [
            row.get('province', ''),
            row.get('city', ''),
            row.get('district', ''),
            row.get('street_name', ''),
            row.get('home_number', ''),
        ]
        return ', '.join(part for part in parts if part)

    def _import_users(self):
        from users.models import User

        users = []
        external_usernames = {}

        # admin and wayne are preserved from clearing — don't recreate
        existing = set(User.objects.filter(username__in=['admin', 'wayne']).values_list('username', flat=True))
        for u in existing:
            external_usernames[u] = u

        phones = self._load_multi_map('Customer_phone.csv', 'customer_id', 'phone')
        addresses = self._load_multi_map('Customer_address.csv', 'customer_id', self._format_address)
        for row in read_csv('Customer.csv'):
            username = row['customer_id'].lower()
            users.append(User(
                username=username,
                display_name=row['customer_name'][:50],
                password=fast_password_hash(row['password']),
                phone=(phones.get(row['customer_id'], [''])[0])[:11],
                address=(addresses.get(row['customer_id'], [''])[0])[:255],
                is_active=True,
            ))
            external_usernames[row['customer_id']] = username

        phones = self._load_multi_map('Seller_phone.csv', 'seller_id', 'phone')
        for row in read_csv('Seller.csv'):
            username = row['seller_id'].lower()
            users.append(User(
                username=username,
                display_name=row['seller_name'][:50],
                password=fast_password_hash(row['password']),
                phone=(phones.get(row['seller_id'], [''])[0])[:11],
                is_active=row.get('status', 'active') not in {'disabled', 'closed', 'suspended'},
            ))
            external_usernames[row['seller_id']] = username

        phones = self._load_multi_map('Admin_phone.csv', 'admin_id', 'phone')
        for row in read_csv('Admin.csv'):
            username = row['admin_id'].lower()
            users.append(User(
                username=username,
                display_name=row['admin_name'][:50],
                password=fast_password_hash(row['password']),
                phone=(phones.get(row['admin_id'], [''])[0])[:11],
                is_staff=True,
                is_active=True,
            ))
            external_usernames[row['admin_id']] = username

        User.objects.bulk_create(users, batch_size=BATCH_SIZE)
        db_users = User.objects.in_bulk(external_usernames.values(), field_name='username')
        user_map = {
            external_id: db_users[username].id
            for external_id, username in external_usernames.items()
            if username in db_users
        }
        self.stdout.write(f'Imported {len(user_map)} users, including default admin')
        return user_map

    def _import_categories(self):
        from products.models import Category

        rows = read_csv('Category.csv')
        category_objs = []
        slug_by_external = {}
        for row in rows:
            slug = f"{slugify(row['category_name'])}-{row['category_id'].lower()}"
            slug_by_external[row['category_id']] = slug
            category_objs.append(Category(
                name=row['category_name'][:100],
                slug=slug,
                is_active=True,
            ))

        Category.objects.bulk_create(category_objs, batch_size=BATCH_SIZE)
        slug_to_id = dict(Category.objects.values_list('slug', 'id'))
        category_map = {
            external_id: slug_to_id[slug]
            for external_id, slug in slug_by_external.items()
            if slug in slug_to_id
        }

        updates = []
        for row in read_csv('Parent_of.csv'):
            child_id = category_map.get(row['child_category_id'])
            parent_id = category_map.get(row['father_category_id'])
            if child_id and parent_id:
                updates.append(Category(id=child_id, parent_id=parent_id))
        if updates:
            Category.objects.bulk_update(updates, ['parent_id'], batch_size=BATCH_SIZE)

        self.stdout.write(f'Imported {len(category_map)} categories and {len(updates)} parent links')
        return category_map

    @staticmethod
    def _normalize_shop_status(status):
        return {
            'active': 'approved',
            'approved': 'approved',
            'pending': 'pending',
            'rejected': 'rejected',
            'suspended': 'disabled',
            'closed': 'disabled',
            'disabled': 'disabled',
        }.get(status, 'approved')

    def _import_shops(self, user_map):
        from products.models import Shop

        stores = read_csv('OnlineStore.csv')
        shop_objs = []
        store_name_by_id = {}
        store_seller_map = {}
        for row in stores:
            seller_id = user_map.get(row['seller_id'])
            if not seller_id:
                continue
            store_name_by_id[row['store_id']] = row['store_name']
            store_seller_map[row['store_id']] = seller_id
            shop_objs.append(Shop(
                user_id=seller_id,
                shop_name=row['store_name'][:100],
                status=self._normalize_shop_status(row.get('status', 'active')),
                rating=Decimal('5.00'),
            ))

        Shop.objects.bulk_create(shop_objs, batch_size=BATCH_SIZE)
        name_to_id = dict(Shop.objects.values_list('shop_name', 'shop_id'))
        shop_map = {
            store_id: name_to_id[name]
            for store_id, name in store_name_by_id.items()
            if name in name_to_id
        }
        self.stdout.write(f'Imported {len(shop_map)} shops')
        return shop_map, store_seller_map

    def _load_product_categories(self):
        children = {row['child_category_id'] for row in read_csv('Parent_of.csv')}
        product_categories = defaultdict(list)
        for row in read_csv('Belongs_to.csv'):
            product_categories[row['product_id']].append(row['category_id'])

        leaf_by_product = {}
        for product_id, category_ids in product_categories.items():
            leaf = next((cid for cid in category_ids if cid in children), None)
            leaf_by_product[product_id] = leaf or category_ids[0]
        return leaf_by_product

    @staticmethod
    def _is_product_active(status):
        return status in {'active', 'approved', 'pending'}

    def _import_products(self, shop_map, store_seller_map, category_map):
        from products.models import Product

        leaf_by_product = self._load_product_categories()
        product_objs = []
        name_by_external = {}
        skipped = 0

        for row in read_csv('Product.csv'):
            shop_id = shop_map.get(row['store_id'])
            seller_id = store_seller_map.get(row['store_id'])
            if not shop_id or not seller_id:
                skipped += 1
                continue
            category_id = category_map.get(leaf_by_product.get(row['product_id']))
            product_objs.append(Product(
                name=row['product_name'][:200],
                price=to_decimal(row['unit_price']),
                category_id=category_id,
                seller_id=seller_id,
                shop_id=shop_id,
                is_active=self._is_product_active(row.get('status', 'active')),
            ))
            name_by_external[row['product_id']] = row['product_name'][:200]

        Product.objects.bulk_create(product_objs, batch_size=BATCH_SIZE)
        name_to_id = dict(Product.objects.values_list('name', 'id'))
        product_map = {
            external_id: name_to_id[name]
            for external_id, name in name_by_external.items()
            if name in name_to_id
        }
        self.stdout.write(f'Imported {len(product_map)} products ({skipped} skipped)')
        return product_map

    def _import_inventory(self, product_map):
        from products.models import Inventory, Product

        inventory_objs = []
        inventory_product_by_external = {}
        for row in read_csv('Inventory.csv'):
            product_id = product_map.get(row['product_id'])
            if not product_id:
                continue
            quantity = max(0, to_int(row['quantity']))
            inventory_objs.append(Inventory(
                product_id=product_id,
                quantity=quantity,
            ))
            inventory_product_by_external[row['inventory_id']] = product_id

        Inventory.objects.bulk_create(inventory_objs, batch_size=BATCH_SIZE)
        product_to_inventory = dict(Inventory.objects.values_list('product_id', 'inventory_id'))
        inventory_map = {
            external_id: product_to_inventory[product_id]
            for external_id, product_id in inventory_product_by_external.items()
            if product_id in product_to_inventory
        }
        self.stdout.write(f'Imported {len(inventory_map)} inventory records')
        return inventory_map

    def _import_orders(self, user_map, product_map):
        from orders.models import Order, OrderItem

        groups = defaultdict(list)
        for row in read_csv('PurchaseRecord.csv'):
            groups[row['purchase_id']].append(row)

        order_map = {}
        order_items = []
        skipped = 0
        for purchase_id, group in groups.items():
            first = group[0]
            user_id = user_map.get(first['customer_id'])
            if not user_id:
                skipped += len(group)
                continue
            total = sum(to_decimal(row['total_price']) for row in group)
            address = ', '.join([
                first.get('province', ''),
                first.get('city', ''),
                first.get('district', ''),
                first.get('street_name', ''),
                first.get('house_number', ''),
            ])[:255]
            order = Order.objects.create(
                user_id=user_id,
                total_amount=total,
                status='paid',
                address=address,
                receiver_name=first.get('recipient_name', '')[:100],
                receiver_phone=first.get('recipient_phone', '')[:11],
            )
            order_map[purchase_id] = order.id

            for row in group:
                product_id = product_map.get(row['product_id'])
                quantity = max(1, to_int(row['quantity'], 1))
                if not product_id:
                    skipped += 1
                    continue
                order_items.append(OrderItem(
                    order_id=order.id,
                    product_id=product_id,
                    quantity=quantity,
                    price=to_decimal(row['total_price']) / Decimal(quantity),
                ))

        OrderItem.objects.bulk_create(order_items, batch_size=BATCH_SIZE)
        self.stdout.write(f'Imported {len(order_map)} orders and {len(order_items)} order items ({skipped} skipped)')
        return order_map

    def _import_carts(self, user_map, product_map):
        from orders.models import Cart

        cart_owner = {row['cart_id']: row['customer_id'] for row in read_csv('Cart.csv')}
        carts = []
        skipped = 0
        seen = set()
        for row in read_csv('CartItem.csv'):
            user_id = user_map.get(cart_owner.get(row['cart_id']))
            product_id = product_map.get(row['product_id'])
            pair = (user_id, product_id)
            if not user_id or not product_id or pair in seen:
                skipped += 1
                continue
            seen.add(pair)
            carts.append(Cart(
                user_id=user_id,
                product_id=product_id,
                quantity=max(1, to_int(row['quantity'], 1)),
            ))

        Cart.objects.bulk_create(carts, batch_size=BATCH_SIZE)
        self.stdout.write(f'Imported {len(carts)} cart items ({skipped} skipped)')

    @staticmethod
    def _normalize_refund_status(status):
        return {
            'approve': 'approved',
            'approved': 'approved',
            'pending': 'pending',
            'reject': 'rejected',
            'rejected': 'rejected',
            'refunded': 'refunded',
        }.get(status, 'pending')

    def _import_refunds(self, order_map):
        from orders.models import Order, OrderItem, Refund, RefundItem

        order_user_map = dict(Order.objects.values_list('id', 'user_id'))
        first_order_item = {}
        for item in OrderItem.objects.order_by('id'):
            first_order_item.setdefault(item.order_id, item)

        refunds = []
        refund_external_by_no = {}
        refund_item_specs = []
        for row in read_csv('RefundRequest.csv'):
            order_id = order_map.get(row['purchase_id'])
            if not order_id:
                continue
            refund_no = row['refund_id']
            refunds.append(Refund(
                refund_no=refund_no,
                order_id=order_id,
                user_id=order_user_map[order_id],
                reason=row.get('refund_reason', '')[:500],
                total_amount=to_decimal(row.get('refund_money')),
                status=self._normalize_refund_status(row.get('refund_status', 'pending')),
            ))
            refund_external_by_no[refund_no] = row['refund_id']
            refund_item_specs.append((refund_no, order_id, row))

        Refund.objects.bulk_create(refunds, batch_size=BATCH_SIZE)
        refund_no_to_id = dict(Refund.objects.values_list('refund_no', 'id'))
        refund_map = {
            external_id: refund_no_to_id[refund_no]
            for refund_no, external_id in refund_external_by_no.items()
            if refund_no in refund_no_to_id
        }

        refund_items = []
        for refund_no, order_id, row in refund_item_specs:
            order_item = first_order_item.get(order_id)
            refund_id = refund_no_to_id.get(refund_no)
            if not order_item or not refund_id:
                continue
            refund_items.append(RefundItem(
                refund_id=refund_id,
                order_item_id=order_item.id,
                quantity=max(1, min(order_item.quantity, to_int(row.get('refund_amount'), 1))),
                refund_amount=to_decimal(row.get('refund_money')),
            ))
        RefundItem.objects.bulk_create(refund_items, batch_size=BATCH_SIZE)
        self.stdout.write(f'Imported {len(refund_map)} refunds and {len(refund_items)} refund items')
        return refund_map

    @staticmethod
    def _normalize_review_status(status):
        return {
            'visible': 'visible',
            'pending': 'hidden',
            'rejected': 'deleted',
            'removed': 'deleted',
            'deleted': 'deleted',
            'hidden': 'hidden',
            'reported': 'reported',
        }.get(status, 'visible')

    def _import_reviews(self, order_map):
        from orders.models import Order, OrderItem
        from products.models import Review

        order_user_map = dict(Order.objects.values_list('id', 'user_id'))
        first_order_item = {}
        for item in OrderItem.objects.order_by('id'):
            first_order_item.setdefault(item.order_id, item)

        review_file = 'Review.csv' if csv_exists('Review.csv') else 'Review_Final.csv'
        reviews = []
        external_ids = []
        skipped = 0
        for row in read_csv(review_file):
            order_id = order_map.get(row['purchase_id'])
            order_item = first_order_item.get(order_id)
            user_id = order_user_map.get(order_id)
            if not order_id or not order_item or not user_id:
                skipped += 1
                continue
            rating = clamp(round(float(row.get('rating') or 5)), 1, 5)
            reviews.append(Review(
                product_id=order_item.product_id,
                user_id=user_id,
                order_item_id=order_item.id,
                rating=rating,
                comment=(row.get('comment') or '')[:1000],
                status=self._normalize_review_status(row.get('status', 'visible')),
            ))
            external_ids.append(row['review_id'])

        Review.objects.bulk_create(reviews, batch_size=BATCH_SIZE)
        created_ids = list(Review.objects.order_by('review_id').values_list('review_id', flat=True))
        review_map = dict(zip(external_ids, created_ids))
        self.stdout.write(f'Imported {len(review_map)} reviews ({skipped} skipped)')
        return review_map

    @staticmethod
    def _normalize_inventory_change(change_type):
        return {
            'restock': 'RESTOCK',
            'order_deduct': 'ORDER_DEDUCT',
            'adjustment': 'ADJUSTMENT',
            'return_restock': 'RETURN_RESTOCK',
            'refund_requested': 'REFUND_REQUESTED',
            'refund_approved': 'REFUND_APPROVED',
        }.get(change_type, change_type.upper())

    def _import_inventory_transactions(self, inventory_map):
        if not csv_exists('InventoryTransaction.csv'):
            return

        from products.models import InventoryTransaction

        transactions = []
        skipped = 0
        for row in read_csv('InventoryTransaction.csv'):
            inventory_id = inventory_map.get(row['inventory_id'])
            if not inventory_id:
                skipped += 1
                continue
            transactions.append(InventoryTransaction(
                inventory_id=inventory_id,
                change_type=self._normalize_inventory_change(row.get('change_type', 'ADJUSTMENT')),
                quantity_change=to_int(row.get('quantity_change')),
            ))

        InventoryTransaction.objects.bulk_create(transactions, batch_size=BATCH_SIZE)
        self.stdout.write(f'Imported {len(transactions)} inventory transactions ({skipped} skipped)')

    def _import_audit_logs(self, user_map, shop_map, product_map, category_map, refund_map, review_map):
        from admin_api.models import AuditLog

        logs = []

        def add(user_external_id, action, table_name, record_id, detail=None):
            logs.append(AuditLog(
                user_id=user_map.get(user_external_id),
                action=(action or 'UPDATE').upper()[:20],
                table_name=table_name[:50],
                record_id=str(record_id)[:50],
                detail=json.dumps(detail or {}, ensure_ascii=False),
            ))

        if csv_exists('Store_audit.csv'):
            for row in read_csv('Store_audit.csv'):
                add(row.get('admin_id'), row.get('action_type'), 'shops', shop_map.get(row.get('store_id'), row.get('store_id')), {
                    'external_store_id': row.get('store_id'),
                    'reason': row.get('reason', ''),
                })

        if csv_exists('Product_moderation.csv'):
            for row in read_csv('Product_moderation.csv'):
                add(row.get('admin_id'), row.get('action_type'), 'products', product_map.get(row.get('product_id'), row.get('product_id')), {
                    'external_product_id': row.get('product_id'),
                    'reason': row.get('reason', ''),
                })

        if csv_exists('Review_moderation.csv'):
            for row in read_csv('Review_moderation.csv'):
                add(row.get('admin_id'), row.get('action_type'), 'reviews', review_map.get(row.get('review_id'), row.get('review_id')), {
                    'external_review_id': row.get('review_id'),
                    'external_purchase_id': row.get('purchase_id'),
                })

        if csv_exists('Category_action.csv'):
            for row in read_csv('Category_action.csv'):
                add(row.get('admin_id'), row.get('action_type'), 'categories', category_map.get(row.get('category_id'), row.get('category_id')), {
                    'external_category_id': row.get('category_id'),
                    'old': row.get('old_value', ''),
                    'new': row.get('new_value', ''),
                })

        if csv_exists('refundAction.csv'):
            for row in read_csv('refundAction.csv'):
                actor = row.get('actor_admin_id') or row.get('actor_seller_id') or row.get('actor_customer_id')
                add(actor, row.get('action_type'), 'refunds', refund_map.get(row.get('refund_id'), row.get('refund_id')), {
                    'external_refund_id': row.get('refund_id'),
                    'actor_customer_id': row.get('actor_customer_id'),
                    'actor_seller_id': row.get('actor_seller_id'),
                    'actor_admin_id': row.get('actor_admin_id'),
                })

        if logs:
            AuditLog.objects.bulk_create(logs, batch_size=BATCH_SIZE)
        self.stdout.write(f'Imported {len(logs)} audit log records')
