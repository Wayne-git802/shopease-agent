from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('products', '0008_alter_review_unique_together'),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                'CREATE FULLTEXT INDEX idx_product_name_ft '
                'ON products(name)'
            ),
            reverse_sql=(
                'DROP INDEX idx_product_name_ft ON products'
            ),
        ),
    ]
