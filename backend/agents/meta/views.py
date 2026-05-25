"""API views for MetaAgent."""
import uuid
import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from agents.permissions import IsAdminUser
from agents.meta.agent import MetaAgent
from agents.core.base_agent import AgentContext

logger = logging.getLogger(__name__)

@api_view(["GET"])
@permission_classes([IsAdminUser])
def weekly(request):
    """GET /api/agents/meta/weekly/?days=7"""
    days = int(request.query_params.get("days", 7))
    days = max(1, min(days, 90))  # clamp 1-90

    agent = MetaAgent()
    context = AgentContext(session_id=str(uuid.uuid4())[:12], trace_id=str(uuid.uuid4()))
    context.extra = {"days": days}
    result = agent.process("weekly", context)

    return Response(result.data, status=status.HTTP_200_OK)
