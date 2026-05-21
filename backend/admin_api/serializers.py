from rest_framework import serializers
from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = AuditLog
        fields = ['id', 'user', 'user_name', 'action', 'table_name',
                  'record_id', 'description', 'old_value', 'new_value',
                  'detail', 'created_at']


class SQLDemoSerializer(serializers.Serializer):
    title = serializers.CharField()
    description = serializers.CharField()
    sql = serializers.CharField()
    columns = serializers.ListField(child=serializers.CharField())
    rows = serializers.ListField(child=serializers.ListField())
