import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def migrate_change_log_data(apps, schema_editor):
    """用原始 SQL 将 change_log 数据迁移到 audit_logs"""
    import os
    if os.environ.get('DB_ENGINE', '').startswith('django.db.backends.sqlite3'):
        return  # skip on SQLite
    with schema_editor.connection.cursor() as c:
        c.execute('SELECT COUNT(*) FROM change_log')
        count = c.fetchone()[0]
        if count == 0:
            return

        batch_size = 2000
        offset = 0
        while offset < count:
            c.execute('''
                INSERT INTO audit_logs (action, table_name, record_id,
                    description, old_value, new_value, detail, created_at)
                SELECT action, table_name, record_id,
                       description, old_value, new_value, '', created_at
                FROM change_log
                ORDER BY created_at ASC
                LIMIT %s OFFSET %s
            ''', [batch_size, offset])
            offset += batch_size


class Migration(migrations.Migration):

    dependencies = [
        ('admin_api', '0004_seed_change_log_data'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Schema changes were already applied to the DB.
        # Use state_operations to sync Django's migration state without
        # touching the database.
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterModelOptions(
                    name='auditlog',
                    options={'ordering': ['-created_at'], 'verbose_name': '变更日志',
                             'verbose_name_plural': '变更日志'},
                ),
                migrations.RemoveIndex(
                    model_name='auditlog',
                    name='idx_audit_action_time',
                ),
                migrations.RemoveIndex(
                    model_name='auditlog',
                    name='idx_audit_table',
                ),
                migrations.AddField(
                    model_name='auditlog',
                    name='description',
                    field=models.TextField(default='', verbose_name='描述'),
                ),
                migrations.AddField(
                    model_name='auditlog',
                    name='new_value',
                    field=models.TextField(blank=True, default='', verbose_name='变更后JSON'),
                ),
                migrations.AddField(
                    model_name='auditlog',
                    name='old_value',
                    field=models.TextField(blank=True, default='', verbose_name='变更前JSON'),
                ),
                migrations.AlterField(
                    model_name='auditlog',
                    name='action',
                    field=models.CharField(max_length=50, verbose_name='操作类型'),
                ),
                migrations.AlterField(
                    model_name='auditlog',
                    name='table_name',
                    field=models.CharField(max_length=50, verbose_name='变更表'),
                ),
                migrations.AlterField(
                    model_name='auditlog',
                    name='user',
                    field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                                           related_name='audit_logs', to=settings.AUTH_USER_MODEL,
                                           verbose_name='触发用户'),
                ),
                migrations.AddIndex(
                    model_name='auditlog',
                    index=models.Index(fields=['table_name', 'created_at'], name='idx_alog_table_time'),
                ),
                migrations.AddIndex(
                    model_name='auditlog',
                    index=models.Index(fields=['created_at'], name='idx_alog_time'),
                ),
            ],
        ),
        # Data migration — actually copies change_log rows into audit_logs
        migrations.RunPython(migrate_change_log_data, migrations.RunPython.noop),
        # Delete change_log table (user FK was already dropped from DB)
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.DeleteModel(name='ChangeLog'),
            ],
            state_operations=[
                migrations.RemoveField(
                    model_name='changelog',
                    name='user',
                ),
                migrations.DeleteModel(name='ChangeLog'),
            ],
        ),
    ]
