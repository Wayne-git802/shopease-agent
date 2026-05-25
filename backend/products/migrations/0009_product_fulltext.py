from django.db import migrations


def create_fulltext_if_mysql(apps, schema_editor):
    import os
    if os.environ.get('DB_ENGINE', '').startswith('django.db.backends.sqlite3'):
        return
    with schema_editor.connection.cursor() as c:
        c.execute(
            'CREATE FULLTEXT INDEX idx_product_name_ft '
            'ON products(name)'
        )


def drop_fulltext_if_mysql(apps, schema_editor):
    import os
    if os.environ.get('DB_ENGINE', '').startswith('django.db.backends.sqlite3'):
        return
    with schema_editor.connection.cursor() as c:
        c.execute('DROP INDEX idx_product_name_ft ON products')


class Migration(migrations.Migration):
    dependencies = [
        ('products', '0008_alter_review_unique_together'),
    ]

    operations = [
        migrations.RunPython(create_fulltext_if_mysql, drop_fulltext_if_mysql),
    ]
