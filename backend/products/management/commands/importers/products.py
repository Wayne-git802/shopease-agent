"""
Product & Inventory importer — Product.csv + Inventory.csv.

Uses Belongs_to.csv + leaf category resolution, the same as the existing import.
"""
from collections import defaultdict

from products.models import Product, Inventory, Category
from users.models import User
from .runtime import (
    ImporterRuntime, ErrorKind, read_csv, csv_exists,
    to_int, to_decimal, parse_legacy_id, BATCH_SIZE,
)


def _load_product_categories():
    """Resolve leaf category per product from Belongs_to + Parent_of."""
    if not csv_exists('Belongs_to.csv'):
        return {}

    # Children are leaf categories
    children = set()
    if csv_exists('Parent_of.csv'):
        for row in read_csv('Parent_of.csv'):
            children.add(row['child_category_id'])  # e.g. 'CAT0021'

    product_cats = defaultdict(list)
    for row in read_csv('Belongs_to.csv'):
        cat_id = row['category_id']  # e.g. 'CAT0001'
        product_cats[row['product_id']].append(cat_id)

    leaf_by_product = {}
    for pid, cat_ids in product_cats.items():
        leaf = next((cid for cid in cat_ids if cid in children), None)
        leaf_by_product[pid] = leaf or cat_ids[0]

    return leaf_by_product


def _cat_to_legacy_id(cat_id: str) -> int:
    """Convert 'CAT0001' → legacy_id=1."""
    return int(cat_id.replace('CAT', '').lstrip('0') or '0')


def _is_product_active(status: str) -> bool:
    return status in {'active', 'approved', 'pending'}


def import_products(runtime: ImporterRuntime):
    runtime.log("Starting product import...")

    leaf_by_product = _load_product_categories()
    if leaf_by_product:
        runtime.log(f"Loaded {len(leaf_by_product)} product→category mappings")
    else:
        runtime.log("No Belongs_to.csv — all products will have null category")

    rows = read_csv('Product.csv')
    products = []
    skipped = 0

    for i, row in enumerate(rows):
        row_num = i + 2
        store_id = row['store_id']

        # Resolve shop via legacy_id
        from products.models import Shop
        shop = runtime.legacy_resolve(Shop, store_id)
        if not shop:
            runtime.error(ErrorKind.FK_MISSING, row_num,
                          f"Shop legacy_id={store_id} not found")
            skipped += 1
            continue

        # Category — resolve via legacy_id from Belongs_to
        cat_id = leaf_by_product.get(row['product_id']) if leaf_by_product else None
        category = runtime.legacy_resolve(Category, _cat_to_legacy_id(cat_id)) if cat_id else None

        products.append(Product(
            name=row['product_name'][:200],
            legacy_id=parse_legacy_id(row['product_id']),  # 'P0000001' → 1
            price=to_decimal(row['unit_price']),
            category_id=category.id if category else None,
            seller_id=shop.user_id,
            shop_id=shop.shop_id,
            is_active=_is_product_active(row.get('status', 'active')),
        ))

    runtime.stats.skipped = skipped
    runtime.bulk_create(products)
    runtime.finish()

    # ── Inventory ──
    import_inventory(runtime)


def import_inventory(runtime: ImporterRuntime):
    runtime.log("Starting inventory import...")

    rows = read_csv('Inventory.csv')
    inv_objs = []
    skipped = 0

    for i, row in enumerate(rows):
        row_num = i + 2
        product = runtime.legacy_resolve(Product, row['product_id'])
        if not product:
            runtime.error(ErrorKind.FK_MISSING, row_num,
                          f"Product legacy_id={row['product_id']} not found")
            skipped += 1
            continue

        inv_objs.append(Inventory(
            product_id=product.id,
            quantity=max(0, to_int(row['quantity'])),
        ))

    # Accumulate stats into same runtime
    runtime.stats.imported += len(inv_objs) if not runtime.dry_run else len(inv_objs)
    runtime.stats.skipped += skipped
    runtime.bulk_create(inv_objs)
    runtime.log(f"  Inventory: {len(inv_objs)} records")
