from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0010_inventorytransaction_idx_inv_txn_type_time_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='inventory',
            old_name='stock_quantity',
            new_name='quantity',
        ),
        migrations.RemoveField(
            model_name='inventory',
            name='reserved_quantity',
        ),
        migrations.RemoveField(
            model_name='inventory',
            name='sold_quantity',
        ),
        migrations.RemoveField(
            model_name='product',
            name='stock',
        ),
    ]
