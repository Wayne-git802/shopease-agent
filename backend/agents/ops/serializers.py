"""DRF serializers for OpsAgent API."""

from rest_framework import serializers


class HealthSerializer(serializers.Serializer):
    """GET /api/agents/ops/health/ — system health status."""
    status = serializers.CharField()
    timestamp = serializers.DateTimeField()
    critical_count = serializers.IntegerField()
    warning_count = serializers.IntegerField()
    total_findings = serializers.IntegerField()
    findings = serializers.ListField(child=serializers.DictField())


class AlertSerializer(serializers.Serializer):
    """Alert item in responses."""
    id = serializers.IntegerField()
    title = serializers.CharField()
    description = serializers.CharField()
    severity = serializers.CharField()
    source = serializers.CharField()
    resolved = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class AlertListSerializer(serializers.Serializer):
    """GET /api/agents/ops/alerts/ — list of alerts."""
    total = serializers.IntegerField()
    alerts = AlertSerializer(many=True)


class ReportSerializer(serializers.Serializer):
    """GET /api/agents/ops/report/ — daily digest."""
    digest = serializers.CharField()
