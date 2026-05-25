"""
Shop importer — OnlineStore.csv → Shop, resolved via User.legacy_id.
"""

from decimal import Decimal

from products.models import Shop
from .runtime import ImporterRuntime, ErrorKind, read_csv, parse_legacy_id, BATCH_SIZE


STATUS_MAP = {
    'active': 'approved',
    'approved': 'approved',
    'pending': 'pending',
    'rejected': 'rejected',
    'suspended': 'disabled',
    'closed': 'disabled',
    'disabled': 'disabled',
}


def import_shops(runtime: ImporterRuntime):
    runtime.log("Starting shop import...")

    rows = read_csv('OnlineStore.csv')
    shops = []
    skipped = 0

    for i, row in enumerate(rows):
        row_num = i + 2
        seller_id = runtime.legacy_resolve_id(
            Shop._meta.get_field('user').remote_field.model,
            row['seller_id'], offset=200000)  # S00001 → legacy_id=200001
        if not seller_id:
            runtime.error(ErrorKind.FK_MISSING, row_num, f"Seller legacy_id={row['seller_id']} not found")
            skipped += 1
            continue

        status = STATUS_MAP.get(row.get('status', 'active'), 'approved')
        shops.append(Shop(
            user_id=seller_id,
            shop_name=row['store_name'][:100],
            legacy_id=parse_legacy_id(row['store_id']),  # 'ST00792' → 792
            status=status,
            rating=Decimal('5.00'),
        ))

    runtime.stats.skipped = skipped
    runtime.bulk_create(shops)
    runtime.finish()
