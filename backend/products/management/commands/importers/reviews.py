"""
Review importer — Review.csv → Review.

FK resolution via legacy_id:
- purchase_id → Order (then find first OrderItem for product, find user)
"""

from products.models import Review
from orders.models import Order, OrderItem
from users.models import User
from .runtime import (
    ImporterRuntime, ErrorKind, read_csv, csv_exists,
    clamp, parse_legacy_id, BATCH_SIZE,
)


REVIEW_STATUS_MAP = {
    'visible': 'visible',
    'pending': 'hidden',
    'rejected': 'deleted',
    'removed': 'deleted',
    'deleted': 'deleted',
    'hidden': 'hidden',
    'reported': 'reported',
}


def import_reviews(runtime: ImporterRuntime):
    runtime.log("Starting review import...")

    # Build lookup: order_id → first OrderItem
    first_items = {}
    for item in OrderItem.objects.select_related('product').order_by('id'):
        first_items.setdefault(item.order_id, item)

    # Build order → user lookup
    order_users = dict(Order.objects.values_list('id', 'user_id'))

    filename = 'Review.csv' if csv_exists('Review.csv') else 'Review_Final.csv'
    rows = read_csv(filename)

    reviews = []
    skipped = 0

    for i, row in enumerate(rows):
        row_num = i + 2

        purchase_id = parse_legacy_id(row.get('purchase_id', ''))  # 'PR0000876' → 876

        order = runtime.legacy_resolve(Order, purchase_id)
        if not order:
            runtime.error(ErrorKind.FK_MISSING, row_num,
                          f"Order legacy_id={purchase_id} not found")
            skipped += 1
            continue

        order_item = first_items.get(order.id)
        user_id = order_users.get(order.id)
        if not order_item or not user_id:
            skipped += 1
            continue

        rating = clamp(row.get('rating', 5), 1, 5)
        status = REVIEW_STATUS_MAP.get(row.get('status', 'visible'), 'visible')

        reviews.append(Review(
            legacy_id=parse_legacy_id(row['review_id']),  # 'RV0000001' → 1
            product_id=order_item.product_id,
            user_id=user_id,
            order_item_id=order_item.id,
            rating=rating,
            comment=(row.get('comment') or '')[:1000],
            status=status,
        ))

    runtime.stats.skipped = skipped
    runtime.bulk_create(reviews)
    runtime.finish()
