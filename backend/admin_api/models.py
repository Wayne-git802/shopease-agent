import json

from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class AuditLog(models.Model):
    """统一变更日志 — 记录所有关键数据库操作，作为 Change Feed 的数据源"""
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='audit_logs', verbose_name='触发用户'
    )
    action = models.CharField(max_length=50, verbose_name='操作类型')
    table_name = models.CharField(max_length=50, verbose_name='变更表')
    record_id = models.CharField(max_length=50, verbose_name='记录ID')
    description = models.TextField(default='', verbose_name='描述')
    old_value = models.TextField(blank=True, default='', verbose_name='变更前JSON')
    new_value = models.TextField(blank=True, default='', verbose_name='变更后JSON')
    detail = models.TextField(blank=True, default='', verbose_name='详情JSON')  # 保留兼容历史数据
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='操作时间')

    class Meta:
        db_table = 'audit_logs'
        verbose_name = '变更日志'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['table_name', 'created_at'], name='idx_alog_table_time'),
            models.Index(fields=['created_at'], name='idx_alog_time'),
        ]

    def __str__(self):
        return f'[{self.created_at}] {self.table_name}#{self.record_id} {self.action}'


def write_audit(user, action, table_name, record_id, description='',
                old_value='', new_value='', detail=None):
    """写入统一变更日志"""
    AuditLog.objects.create(
        user=user,
        action=action,
        table_name=table_name,
        record_id=str(record_id),
        description=description,
        old_value=old_value if isinstance(old_value, str) else json.dumps(old_value, ensure_ascii=False),
        new_value=new_value if isinstance(new_value, str) else json.dumps(new_value, ensure_ascii=False),
        detail=json.dumps(detail or {}, ensure_ascii=False),
    )
