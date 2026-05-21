"""DRF serializers for CustomerServiceAgent API."""

from rest_framework import serializers


class ChatRequestSerializer(serializers.Serializer):
    """POST /api/agents/chat/ — customer inquiry."""
    message = serializers.CharField(max_length=2000, required=True)
    session_id = serializers.CharField(max_length=64, required=False, default='')


class ChatResponseSerializer(serializers.Serializer):
    """Response from chat endpoint."""
    reply = serializers.CharField()
    tokens_used = serializers.IntegerField(default=0)
    cache_hit = serializers.BooleanField(default=False)
    session_id = serializers.CharField()
    trace_id = serializers.CharField()


class ChatHistorySerializer(serializers.Serializer):
    """GET /api/agents/chat/history/ — conversation history item."""
    id = serializers.IntegerField()
    role = serializers.CharField()
    content = serializers.CharField()
    created_at = serializers.DateTimeField()
