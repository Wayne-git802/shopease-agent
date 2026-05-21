"""API views for CustomerServiceAgent.

Endpoints:
    POST   /api/agents/chat/             — Send a customer inquiry
    GET    /api/agents/chat/history/     — Get conversation history
    GET    /api/agents/chat/stream/      — SSE streaming chat (Phase 2b)
"""

import uuid
import logging

from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from agents.permissions import IsAuthenticatedOrGuest, IsOwnerOrAdmin
from agents.customer_service.agent import CustomerServiceAgent
from agents.core.base_agent import AgentContext

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([IsAuthenticatedOrGuest])
def chat(request):
    """Handle a customer inquiry.

    Authenticated users get personalized responses with order access.
    Guests get generic product info and policy answers only.
    """
    from .serializers import ChatRequestSerializer, ChatResponseSerializer

    serializer = ChatRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    message = serializer.validated_data['message']
    session_id = serializer.validated_data.get('session_id') or str(uuid.uuid4())[:12]
    trace_id = str(uuid.uuid4())

    user_id = request.user.id if request.user.is_authenticated else None

    agent = CustomerServiceAgent()
    context = AgentContext(
        user_id=user_id,
        session_id=session_id,
        trace_id=trace_id,
    )
    result = agent.process(message, context)

    response_data = {
        'reply': result.text,
        'tokens_used': result.tokens_used,
        'cache_hit': result.cache_hit,
        'session_id': session_id,
        'trace_id': trace_id,
    }

    # Flush agent logs to DB
    agent.logger.flush_to_db()

    resp_serializer = ChatResponseSerializer(data=response_data)
    resp_serializer.is_valid(raise_exception=True)

    return Response(resp_serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsOwnerOrAdmin])
def chat_history(request):
    """Get conversation history for the current user (or all for admins)."""
    from agents.models import AgentConversation
    from .serializers import ChatHistorySerializer

    user_id = request.user.id if request.user.is_authenticated else None
    if not user_id:
        return Response([], status=status.HTTP_200_OK)

    session_id = request.query_params.get('session_id', '')

    qs = AgentConversation.objects.filter(
        user_id=user_id,
        agent_type='customer_service',
    )
    if session_id:
        qs = qs.filter(session_id=session_id)

    qs = qs.order_by('-created_at')[:50]
    data = [{
        'id': m.id,
        'role': m.role,
        'content': m.content,
        'created_at': m.created_at,
    } for m in qs]

    return Response(data, status=status.HTTP_200_OK)
