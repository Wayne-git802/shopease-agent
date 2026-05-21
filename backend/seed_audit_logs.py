import json
import sys
from datetime import datetime, timedelta

# Add current dir to path
sys.path.insert(0, '.')

import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')
django.setup()

from admin_api.models import AuditLog
from users.models import User

user = User.objects.first()
if not user:
    print("No users. Run seed_data.py first.")
    sys.exit(1)

AuditLog.objects.all().delete()

now = datetime.now()
entries = [
    ('LOGIN', 'users', 'admin', {'role': 'admin'}, 120),
    ('UPDATE', 'users.status', 'seller_alice', {'old': 'active', 'new': 'disabled'}, 115),
    ('UPDATE', 'users.status', 'seller_alice', {'old': 'disabled', 'new': 'active'}, 113),
    ('UPDATE', 'shops.status', '3', {'old': 'pending', 'new': 'approved'}, 110),
    ('UPDATE', 'products.status', '7', {'old': 'pending', 'new': 'approved'}, 105),
    ('UPDATE', 'products.status', '12', {'old': 'pending', 'new': 'off_shelf'}, 100),
    ('UPDATE', 'reviews.status', '15', {'old': 'reported', 'new': 'hidden'}, 90),
    ('INSERT', 'categories', '8', {'name': 'Electronics', 'slug': 'electronics'}, 85),
    ('UPDATE', 'categories', '5', {'old_name': 'Home', 'new_name': 'Home & Living'}, 80),
    ('DELETE', 'reviews.status', '22', {'old': 'visible', 'new': 'deleted'}, 75),
    ('UPDATE', 'shops.status', '1', {'old': 'approved', 'new': 'disabled'}, 60),
    ('INSERT', 'orders', 'ORD20260504120000A1B2', {'total': 299.00, 'status': 'paid'}, 50),
    ('UPDATE', 'orders.status', 'ORD20260503150000E5F6', {'old': 'paid', 'new': 'shipped'}, 45),
    ('UPDATE', 'inventory.restock', '5', {'product': 'Wireless Mouse', 'added': 50}, 40),
    ('UPDATE', 'refunds.status', 'REF20260504090000X1Y2', {'old': 'pending', 'new': 'approved', 'remark': 'refund approved'}, 30),
    ('LOGOUT', 'users', 'admin', {}, 5),
]

for action, table, record_id, detail, offset_min in entries:
    AuditLog.objects.create(
        user=user,
        action=action,
        table_name=table,
        record_id=str(record_id),
        detail=json.dumps(detail, ensure_ascii=False),
        created_at=now - timedelta(minutes=offset_min),
    )

print(f"Created {len(entries)} audit log entries. Total: {AuditLog.objects.count()}")
