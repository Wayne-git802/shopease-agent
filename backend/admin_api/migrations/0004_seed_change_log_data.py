from django.db import migrations


def seed_change_log(apps, schema_editor):
    """从 inventory_transactions + orders + audit_logs 导入历史数据到 change_log"""
    import os
    if os.environ.get('DB_ENGINE', '').startswith('django.db.backends.sqlite3'):
        return  # skip on SQLite
    ChangeLog = apps.get_model('admin_api', 'ChangeLog')
    batch = []

    # ── inventory_transactions ──
    with schema_editor.connection.cursor() as c:
        c.execute('''
            SELECT it.transaction_id, it.change_type, it.quantity_change,
                   p.name, i.inventory_id,
                   COALESCE(o.order_no, ''), COALESCE(u.username, ''), it.created_at
            FROM inventory_transactions it
            JOIN inventory i ON i.inventory_id = it.inventory_id
            JOIN products p ON p.id = i.product_id
            LEFT JOIN orders o ON o.id = it.related_order_id
            LEFT JOIN users u ON u.id = o.user_id
            ORDER BY it.created_at ASC
        ''')
        for row in c.fetchall():
            txn_id, change_type, qty, name, inv_id, order_no, username, created_at = row
            if change_type == 'RESTOCK':
                action = '补货入库'
                desc = f'{name} 库存 +{qty}，订单 {order_no}' if order_no else f'{name} 库存 +{qty}'
            elif change_type == 'ORDER_DEDUCT':
                action = '订单扣减'
                desc = f'{name} 库存 -{abs(qty)}，订单 {order_no}' if order_no else f'{name} 库存 -{abs(qty)}'
            elif change_type == 'RETURN_RESTOCK':
                action = '退货回仓'
                desc = f'{name} 库存 +{qty}'
            elif change_type == 'REFUND_APPROVED':
                action = '退款退仓'
                desc = f'{name} 库存 +{qty}'
            else:
                action = change_type
                desc = f'{name} 变动 {qty}'
            batch.append(ChangeLog(
                table_name='inventory',
                record_id=str(inv_id),
                action=action,
                description=desc,
                created_at=created_at,
            ))
            if len(batch) >= 2000:
                ChangeLog.objects.bulk_create(batch)
                batch.clear()
        if batch:
            ChangeLog.objects.bulk_create(batch)
            batch.clear()

    # ── orders ──
    with schema_editor.connection.cursor() as c:
        c.execute('''
            SELECT o.id, o.order_no, o.status, o.total_amount,
                   COALESCE(u.username, ''), o.created_at
            FROM orders o
            LEFT JOIN users u ON u.id = o.user_id
            ORDER BY o.created_at ASC
        ''')
        for row in c.fetchall():
            oid, order_no, status, total, username, created_at = row
            status_cn = {'paid': '已支付', 'shipped': '已发货', 'completed': '已完成',
                         'cancelled': '已取消', 'refunded': '已退款'}.get(status, status)
            batch.append(ChangeLog(
                table_name='orders',
                record_id=order_no,
                action='创建订单' if status == 'paid' else f'订单{status_cn}',
                description=f'{username} 下单 #{order_no}，金额 ¥{float(total):.2f}，状态：{status_cn}',
                created_at=created_at,
            ))
            if len(batch) >= 2000:
                ChangeLog.objects.bulk_create(batch)
                batch.clear()
        if batch:
            ChangeLog.objects.bulk_create(batch)
            batch.clear()

    # ── audit_logs ──
    with schema_editor.connection.cursor() as c:
        c.execute('''
            SELECT al.id, al.action, al.table_name, al.record_id, al.detail,
                   COALESCE(u.username, ''), al.created_at
            FROM audit_logs al
            LEFT JOIN users u ON u.id = al.user_id
            ORDER BY al.created_at ASC
        ''')
        table_cn_map = {'users': '用户', 'shops': '店铺', 'products': '商品',
                        'reviews': '评论', 'refunds': '退款'}
        for row in c.fetchall():
            aid, action, table_name, record_id, detail, username, created_at = row
            table_cn = table_cn_map.get(table_name, table_name)
            batch.append(ChangeLog(
                table_name=table_name,
                record_id=str(record_id),
                action=f'{action} {table_cn}',
                description=f'{username} 对 {table_cn} #{record_id} 执行了 {action} 操作',
                created_at=created_at,
            ))
            if len(batch) >= 2000:
                ChangeLog.objects.bulk_create(batch)
                batch.clear()
        if batch:
            ChangeLog.objects.bulk_create(batch)
            batch.clear()


def reverse_seed(apps, schema_editor):
    ChangeLog = apps.get_model('admin_api', 'ChangeLog')
    ChangeLog.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('admin_api', '0003_add_change_log'),
    ]

    operations = [
        migrations.RunPython(seed_change_log, reverse_seed),
    ]
