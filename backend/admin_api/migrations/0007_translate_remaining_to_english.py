"""Translate remaining Chinese audit_log entries to English (second pass)."""
from django.db import migrations


def translate_remaining(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        # ADJUSTMENT: {product} 变动 {qty} → {product} adjusted {qty}
        c.execute("UPDATE audit_logs SET description = REPLACE(description, ' 变动 ', ' adjusted ') WHERE description LIKE '% 变动 %'")

        # Refund Submitted: remove leftover 执行了 SUBMIT 操作
        c.execute("UPDATE audit_logs SET description = REPLACE(description, ' 执行了 SUBMIT 操作', '') WHERE description LIKE '% 执行了 SUBMIT 操作%'")
        # Fix wrong 'approved Refund' → 'submitted refund' for SUBMIT entries
        c.execute("UPDATE audit_logs SET description = REPLACE(description, ' approved Refund #', ' submitted refund #') WHERE action = 'Refund Submitted'")

        # CREATE categories → Category Created
        c.execute("UPDATE audit_logs SET action = 'Category Created' WHERE action = 'CREATE categories'")
        c.execute("UPDATE audit_logs SET description = REPLACE(description, ' 对 categories #', ' created category #') WHERE description LIKE '% 对 categories #%'")
        c.execute("UPDATE audit_logs SET description = REPLACE(description, ' 执行了 CREATE 操作', '') WHERE description LIKE '% 执行了 CREATE 操作%'")

        # Remaining fullwidth punctuation
        c.execute("UPDATE audit_logs SET description = REPLACE(description, '，', ',') WHERE description LIKE BINARY '%\\uff0c%'")
        c.execute("UPDATE audit_logs SET description = REPLACE(description, '（', '(') WHERE description LIKE BINARY '%\\uff08%'")
        c.execute("UPDATE audit_logs SET description = REPLACE(description, '）', ')') WHERE description LIKE BINARY '%\\uff09%'")


class Migration(migrations.Migration):

    dependencies = [
        ('admin_api', '0006_translate_audit_logs_to_english'),
    ]

    operations = [
        migrations.RunPython(translate_remaining, migrations.RunPython.noop),
    ]
