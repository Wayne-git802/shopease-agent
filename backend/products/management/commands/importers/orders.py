"""
Order importer — PurchaseRecord.csv → Order + OrderItem.

Key features:
- Same purchase_id rows grouped into one Order
- assert_same: address, receiver_name, receiver_phone must match within group
- total_amount recalculated from sum(OrderItems), NOT trusted from CSV
- status = 'completed' (user confirmed)
- All FK resolved via legacy_id
"""

from collections import defaultdict
from decimal import Decimal

from orders.models import Order, OrderItem
from products.models import Product
from users.models import User
from .runtime import (
    ImporterRuntime, ErrorKind, read_csv, to_int, to_decimal,
    assert_same, parse_legacy_id, BATCH_SIZE,
)


def import_orders(runtime: ImporterRuntime):
    runtime.log("Starting order import...")

    rows = read_csv('PurchaseRecord.csv')

    # Group by purchase_id
    groups = defaultdict(list)
    for row in rows:
        groups[row['purchase_id']].append(row)
    runtime.log(f"Grouped into {len(groups)} orders from {len(rows)} records")

    order_count = 0
    item_count = 0
    skipped = 0

    for purchase_id, group in groups.items():
        if not group:
            continue

        # ── assert_same for address/receiver fields ──
        addr_map = {}
        name_map = {}
        phone_map = {}
        for row in group:
            addr = ', '.join([
                row.get('province', ''),
                row.get('city', ''),
                row.get('district', ''),
                row.get('street_name', ''),
                row.get('house_number', ''),
            ])
            addr_map[row.get('purchase_record_id', '?')] = addr
            name_map[row.get('purchase_record_id', '?')] = row.get('recipient_name', '')
            phone_map[row.get('purchase_record_id', '?')] = row.get('recipient_phone', '')

        assert_same('address', addr_map, 0, runtime)
        assert_same('receiver_name', name_map, 0, runtime)
        assert_same('receiver_phone', phone_map, 0, runtime)

        first = group[0]

        # Resolve user
        user = runtime.legacy_resolve(User, first['customer_id'], offset=300000)  # C00001 → 300001
        if not user:
            runtime.error(ErrorKind.FK_MISSING, 0,
                          f"User legacy_id={first['customer_id']} not found for order {purchase_id}")
            skipped += len(group)
            continue

        # Build address
        address = ', '.join([
            first.get('province', ''),
            first.get('city', ''),
            first.get('district', ''),
            first.get('street_name', ''),
            first.get('house_number', ''),
        ])[:255]

        # ── Create OrderItem objects first (to calculate total) ──
        order_items = []
        for row in group:
            product = runtime.legacy_resolve(Product, row['product_id'])
            if not product:
                runtime.error(ErrorKind.FK_MISSING, 0,
                              f"Product legacy_id={row['product_id']} not found")
                skipped += 1
                continue
            quantity = max(1, to_int(row['quantity'], 1))
            unit_price = to_decimal(row.get('total_price', '0'))
            if unit_price <= 0:
                unit_price = product.price  # fallback to product price
            order_items.append({
                'product': product,
                'quantity': quantity,
                'price': unit_price,
            })

        if not order_items:
            skipped += len(group)
            continue

        # Recalculate total (DON'T trust CSV)
        total = sum(Decimal(str(it['price'])) * it['quantity'] for it in order_items)

        if runtime.dry_run:
            order_count += 1
            item_count += len(order_items)
            continue

        # ── Create Order ──
        order = Order.objects.create(
            user_id=user.id,
            legacy_id=parse_legacy_id(purchase_id),  # 'PR0000876' → 876
            total_amount=total,
            status='completed',
            address=address,
            receiver_name=first.get('recipient_name', '')[:100],
            receiver_phone=first.get('recipient_phone', '')[:11],
        )

        # ── Create OrderItems ──
        items = []
        for it in order_items:
            items.append(OrderItem(
                order_id=order.id,
                product_id=it['product'].id,
                quantity=it['quantity'],
                price=it['price'],
            ))

        OrderItem.objects.bulk_create(items, batch_size=BATCH_SIZE)
        order_count += 1
        item_count += len(items)

    runtime.stats.imported = order_count
    runtime.stats.skipped = skipped
    runtime.log(f"Orders: {order_count}, Items: {item_count}, skipped rows: {skipped}")
    runtime.finish()
