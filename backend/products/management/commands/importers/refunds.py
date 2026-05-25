"""
Refund importer — RefundRequest.csv → Refund + RefundItem.

FK resolution via legacy_id:
- purchase_id → Order (legacy_id)
- Refund tied to Order's first OrderItem via RefundItem
"""

from orders.models import Order, OrderItem, Refund, RefundItem
from users.models import User
from .runtime import (
    ImporterRuntime, ErrorKind, read_csv, to_int, to_decimal, parse_legacy_id,
    BATCH_SIZE,
)


REFUND_STATUS_MAP = {
    'approve': 'approved',
    'approved': 'approved',
    'pending': 'pending',
    'reject': 'rejected',
    'rejected': 'rejected',
    'refunded': 'refunded',
}


def import_refunds(runtime: ImporterRuntime):
    runtime.log("Starting refund import...")

    # Build: order_id → first OrderItem, user_id
    first_items = {}
    for item in OrderItem.objects.select_related('product').order_by('id'):
        first_items.setdefault(item.order_id, item)

    order_users = dict(Order.objects.values_list('id', 'user_id'))

    rows = read_csv('RefundRequest.csv')
    refunds = []
    refund_item_specs = []  # (refund_legacy_id, order_id, order_item, row)
    skipped = 0

    for i, row in enumerate(rows):
        row_num = i + 2

        purchase_id = parse_legacy_id(row.get('purchase_id', ''))   # 'PR0000876' → 876
        refund_legacy = parse_legacy_id(row['refund_id'])             # 'RF0000001' → 1
        order = runtime.legacy_resolve(Order, purchase_id)
        if not order:
            runtime.error(ErrorKind.FK_MISSING, row_num,
                          f"Order legacy_id={purchase_id} not found")
            skipped += 1
            continue

        user_id = order_users.get(order.id, order.user_id)
        order_item = first_items.get(order.id)

        refund_amount = to_decimal(row.get('refund_money', '0'))
        refund_status = REFUND_STATUS_MAP.get(
            row.get('refund_status', 'pending'), 'pending')

        refunds.append(Refund(
            refund_no=str(refund_legacy),
            legacy_id=refund_legacy,
            order_id=order.id,
            user_id=user_id,
            reason=(row.get('refund_reason', '') or '')[:500],
            total_amount=refund_amount,
            status=refund_status,
        ))

        if order_item:
            refund_item_specs.append((refund_legacy, order.id, order_item, row, refund_amount))

    runtime.stats.skipped = skipped
    refund_created = runtime.bulk_create(refunds)

    # ── RefundItems ──
    if not runtime.dry_run:
        # Build legacy_id → refund.id map
        refund_id_map = {}
        for r in Refund.objects.filter(legacy_id__isnull=False):
            refund_id_map[r.legacy_id] = r.id

        rif_items = []
        for ref_legacy, order_id, order_item, row, amount in refund_item_specs:
            refund_id = refund_id_map.get(ref_legacy)
            if not refund_id:
                continue
            qty = max(1, min(order_item.quantity, to_int(row.get('refund_amount'), 1)))
            rif_items.append(RefundItem(
                refund_id=refund_id,
                order_item_id=order_item.id,
                quantity=qty,
                refund_amount=amount,
            ))
        if rif_items:
            RefundItem.objects.bulk_create(rif_items, batch_size=BATCH_SIZE)
            runtime.log(f"Created {len(rif_items)} refund items")

    runtime.finish()
