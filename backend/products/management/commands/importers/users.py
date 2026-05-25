"""
User importer — Admin → Seller → Customer + address/phone.

Adds legacy_id to User model for FK resolution.
Passwords hashed with Django-compatible PBKDF2.
"""

import base64
import hashlib
import os as _os
from collections import defaultdict

from users.models import User
from .runtime import (
    ImporterRuntime, ErrorKind, read_csv, to_int, to_decimal, parse_legacy_id,
    BATCH_SIZE,
)


def fast_password_hash(raw_password: str) -> str:
    """Django-compatible PBKDF2-SHA256 hash."""
    algo = 'pbkdf2_sha256'
    iterations = 1000
    salt = _os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac(
        'sha256', raw_password.encode(), salt.encode(), iterations, dklen=32)
    return f'{algo}${iterations}${salt}${base64.b64encode(dk).decode().strip()}'


def _load_multi_map(filename, key_field, value_field_or_func):
    result = defaultdict(list)
    from .runtime import csv_exists as _csv_exists
    if not _csv_exists(filename):
        return result
    from .runtime import read_csv as _read_csv
    for row in _read_csv(filename):
        value = (value_field_or_func(row) if callable(value_field_or_func)
                 else row.get(value_field_or_func, ''))
        result[row[key_field]].append(value)
    return result


def _format_address(row: dict) -> str:
    parts = [
        row.get('province', ''),
        row.get('city', ''),
        row.get('district', ''),
        row.get('street_name', ''),
        row.get('home_number', ''),
    ]
    return ', '.join(p for p in parts if p)


def import_users(runtime: ImporterRuntime):
    runtime.log("Starting user import...")

    # Keep admin and wayne (existing superusers)
    preserved = set(User.objects.filter(
        username__in=['admin', 'wayne']
    ).values_list('username', flat=True))

    phones_cust = _load_multi_map('Customer_phone.csv', 'customer_id', 'phone')
    addresses = _load_multi_map('Customer_address.csv', 'customer_id', _format_address)

    all_users = []

    # ── Customers ──
    for row in read_csv('Customer.csv'):
        legacy_id = parse_legacy_id(row['customer_id']) + 300000  # C00001 → 300001
        username = row['customer_id'].lower()
        if username in preserved:
            continue
        all_users.append(User(
            username=username,
            display_name=row['customer_name'][:50],
            password=fast_password_hash(row['password']),
            phone=(phones_cust.get(row['customer_id'], [''])[0])[:11],
            address=(addresses.get(row['customer_id'], [''])[0])[:255],
            legacy_id=legacy_id,
            is_active=True,
        ))

    # ── Sellers ──
    phones_seller = _load_multi_map('Seller_phone.csv', 'seller_id', 'phone')
    for row in read_csv('Seller.csv'):
        legacy_id = parse_legacy_id(row['seller_id']) + 200000  # S00001 → 200001
        username = row['seller_id'].lower()
        if username in preserved:
            continue
        status = row.get('status', 'active')
        all_users.append(User(
            username=username,
            display_name=row['seller_name'][:50],
            password=fast_password_hash(row['password']),
            phone=(phones_seller.get(row['seller_id'], [''])[0])[:11],
            legacy_id=legacy_id,
            is_active=status not in {'disabled', 'closed', 'suspended'},
        ))

    # ── Admins ──
    phones_admin = _load_multi_map('Admin_phone.csv', 'admin_id', 'phone')
    for row in read_csv('Admin.csv'):
        legacy_id = parse_legacy_id(row['admin_id']) + 100000  # A00001 → 100001
        username = row['admin_id'].lower()
        if username in preserved:
            continue
        all_users.append(User(
            username=username,
            display_name=row['admin_name'][:50],
            password=fast_password_hash(row['password']),
            phone=(phones_admin.get(row['admin_id'], [''])[0])[:11],
            legacy_id=legacy_id,
            is_staff=True,
            is_active=True,
        ))

    runtime.log(f"Built {len(all_users)} user objects, bulk creating...")
    runtime.bulk_create(all_users)
    runtime.finish()
