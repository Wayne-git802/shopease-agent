"""
Cart importer — Cart.csv + CartItem.csv → Cart.

Uses legacy_id FK resolution (no id_map needed).
"""

from orders.models import Cart
from products.models import Product
from users.models import User
from .runtime import ImporterRuntime, ErrorKind, read_csv, to_int, BATCH_SIZE


def import_carts(runtime: ImporterRuntime):
    runtime.log("Starting cart import...")

    # Build cart ownership map
    cart_owner = {}
    for row in read_csv('Cart.csv'):
        cart_owner[row['cart_id']] = row['customer_id']

    rows = read_csv('CartItem.csv')
    carts = []
    skipped = 0
    seen = set()

    for i, row in enumerate(rows):
        row_num = i + 2

        customer_legacy = cart_owner.get(row['cart_id'])
        if not customer_legacy:
            runtime.error(ErrorKind.FK_MISSING, row_num,
                          f"Cart {row['cart_id']} has no owner")
            skipped += 1
            continue

        user = runtime.legacy_resolve(User, customer_legacy, offset=300000)  # C00001 → 300001
        product = runtime.legacy_resolve(Product, row['product_id'])
        if not user or not product:
            runtime.error(ErrorKind.FK_MISSING, row_num,
                          f"User({customer_legacy}) or Product({row['product_id']}) not found")
            skipped += 1
            continue

        pair = (user.id, product.id)
        if pair in seen:
            skipped += 1
            continue
        seen.add(pair)

        carts.append(Cart(
            user_id=user.id,
            product_id=product.id,
            quantity=max(1, to_int(row['quantity'], 1)),
        ))

    runtime.stats.skipped = skipped
    runtime.bulk_create(carts)
    runtime.finish()
