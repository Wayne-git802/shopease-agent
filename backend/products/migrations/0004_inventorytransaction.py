from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0002_initial'),
        ('products', '0003_shopfollow'),
    ]

    operations = [
        migrations.CreateModel(
            name='InventoryTransaction',
            fields=[
                ('transaction_id', models.AutoField(primary_key=True, serialize=False)),
                ('change_type', models.CharField(choices=[
                    ('RESTOCK', 'RESTOCK'),
                    ('ORDER_DEDUCT', 'ORDER_DEDUCT'),
                    ('ADJUSTMENT', 'ADJUSTMENT'),
                    ('REFUND_REQUESTED', 'REFUND_REQUESTED'),
                    ('REFUND_APPROVED', 'REFUND_APPROVED'),
                    ('RETURN_RESTOCK', 'RETURN_RESTOCK'),
                ], max_length=32)),
                ('quantity_change', models.IntegerField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('inventory', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='transactions', to='products.inventory')),
                ('related_order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='inventory_transactions', to='orders.order')),
                ('related_refund', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='inventory_transactions', to='orders.refund')),
            ],
            options={
                'db_table': 'inventory_transactions',
                'ordering': ['-created_at'],
            },
        ),
    ]
