# Generated manually for recent_order_ids

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0015_pending_reference'),
    ]

    operations = [
        migrations.AddField(
            model_name='sessionstate',
            name='recent_order_ids',
            field=models.JSONField(default=list),
        ),
    ]
