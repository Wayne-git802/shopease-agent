"""Translate legacy Chinese audit_log entries to English."""
from django.db import migrations


def translate_audit_logs(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        # ── Action field ──
        c.execute("UPDATE audit_logs SET action = 'Inventory Restocked' WHERE action = '补货入库'")
        c.execute("UPDATE audit_logs SET action = 'Inventory Deducted' WHERE action = '订单扣减'")
        c.execute("UPDATE audit_logs SET action = 'Order Created' WHERE action = '创建订单'")
        c.execute("UPDATE audit_logs SET action = 'Product Approved' WHERE action = 'APPROVE 商品'")
        c.execute("UPDATE audit_logs SET action = 'Shop Approved' WHERE action = 'APPROVE 店铺'")
        c.execute("UPDATE audit_logs SET action = 'Review Approved' WHERE action = 'APPROVE 评论'")
        c.execute("UPDATE audit_logs SET action = 'Refund Submitted' WHERE action = 'SUBMIT 退款'")

        # ── Description field ──
        # Pattern: {product} 库存 +{qty} → {product} stock +{qty}
        c.execute("UPDATE audit_logs SET description = REPLACE(description, '库存 +', 'stock +') WHERE description LIKE '%库存 +%'")
        c.execute("UPDATE audit_logs SET description = REPLACE(description, '库存 -', 'stock -') WHERE description LIKE '%库存 -%'")

        # Pattern: {user} 下单 #{order}，金额 ¥{amount}，状态：已支付
        c.execute("UPDATE audit_logs SET description = REPLACE(description, ' 下单 #', ' placed order #') WHERE description LIKE '% 下单 #%'")
        c.execute("UPDATE audit_logs SET description = REPLACE(description, '，金额 ¥', ', total ¥') WHERE description LIKE '%，金额 ¥%'")
        c.execute("UPDATE audit_logs SET description = REPLACE(description, '，状态：已支付', ', status: paid') WHERE description LIKE '%，状态：已支付%'")

        # Pattern: {user} 对 {type} #{id} 执行了 APPROVE 操作
        c.execute("UPDATE audit_logs SET description = REPLACE(description, ' 执行了 APPROVE 操作', '') WHERE description LIKE '% 执行了 APPROVE 操作%'")
        c.execute("UPDATE audit_logs SET description = REPLACE(description, ' 对 商品 #', ' approved Product #') WHERE description LIKE '% 对 商品 #%'")
        c.execute("UPDATE audit_logs SET description = REPLACE(description, ' 对 店铺 #', ' approved Shop #') WHERE description LIKE '% 对 店铺 #%'")
        c.execute("UPDATE audit_logs SET description = REPLACE(description, ' 对 评论 #', ' approved Review #') WHERE description LIKE '% 对 评论 #%'")
        c.execute("UPDATE audit_logs SET description = REPLACE(description, ' 对 退款 #', ' approved Refund #') WHERE description LIKE '% 对 退款 #%'")


class Migration(migrations.Migration):

    dependencies = [
        ('admin_api', '0005_merge_change_log_into_audit'),
    ]

    operations = [
        migrations.RunPython(translate_audit_logs, migrations.RunPython.noop),
    ]
