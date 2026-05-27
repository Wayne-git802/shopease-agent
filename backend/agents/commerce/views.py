"""API views for RecommendAgent."""
import uuid
import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from agents.commerce.agent import RecommendAgent
from agents.core.base_agent import AgentContext

logger = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([AllowAny])
def popular(request):
    """GET /api/agents/recommend/popular/?limit=10"""
    limit = int(request.query_params.get("limit", 10))
    agent = RecommendAgent()
    context = AgentContext(session_id=str(uuid.uuid4())[:12], trace_id=str(uuid.uuid4()))
    context.extra = {"limit": limit}
    result = agent.process("popular", context)
    return Response(result.data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def similar(request, product_id: int):
    """GET /api/agents/recommend/similar/<product_id>/?limit=5"""
    limit = int(request.query_params.get("limit", 5))
    agent = RecommendAgent()
    context = AgentContext(session_id=str(uuid.uuid4())[:12], trace_id=str(uuid.uuid4()))
    context.extra = {"product_id": product_id, "limit": limit}
    result = agent.process("similar", context)
    return Response(result.data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def for_you(request):
    """GET /api/agents/recommend/for-you/?limit=10"""
    limit = int(request.query_params.get("limit", 10))
    agent = RecommendAgent()
    context = AgentContext(user_id=request.user.id, session_id=str(uuid.uuid4())[:12], trace_id=str(uuid.uuid4()))
    context.extra = {"limit": limit}
    result = agent.process("for-you", context)
    return Response(result.data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([AllowAny])
def trending(request):
    """GET /api/agents/recommend/trending/?limit=10"""
    limit = int(request.query_params.get("limit", 10))
    agent = RecommendAgent()
    context = AgentContext(session_id=str(uuid.uuid4())[:12], trace_id=str(uuid.uuid4()))
    context.extra = {"limit": limit}
    result = agent.process("trending", context)
    return Response(result.data, status=status.HTTP_200_OK)
