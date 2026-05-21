"""API views for OpsAgent.

Endpoints:
    GET  /api/agents/ops/health/  — system health status
    GET  /api/agents/ops/alerts/  — query alerts (filter by severity)
    GET  /api/agents/ops/report/  — daily operations digest
"""

import uuid
import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from agents.permissions import IsAdminUser
from agents.ops.agent import OpsAgent
from agents.core.base_agent import AgentContext

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def health(request):
    """Run all monitors and return system health status."""
    agent = OpsAgent()
    context = AgentContext(
        session_id=str(uuid.uuid4())[:12],
        trace_id=str(uuid.uuid4()),
    )
    result = agent.process('health', context)
    agent.logger.flush_to_db()

    data = result.data or {}
    data['status'] = data.get('status', result.status)
    data['timestamp'] = data.get('timestamp', '')
    return Response(data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def alerts(request):
    """Query recent unresolved alerts."""
    from agents.ops.alerts import get_alerts

    severity = request.query_params.get('severity', None)
    resolved_str = request.query_params.get('resolved', None)
    resolved = None
    if resolved_str is not None:
        resolved = resolved_str.lower() in ('true', '1', 'yes')

    alerts_data = get_alerts(severity=severity, resolved=resolved)

    return Response({
        'total': len(alerts_data),
        'alerts': alerts_data,
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def report(request):
    """Generate a daily operations digest."""
    agent = OpsAgent()
    context = AgentContext(
        session_id=str(uuid.uuid4())[:12],
        trace_id=str(uuid.uuid4()),
    )
    result = agent.process('report', context)
    agent.logger.flush_to_db()

    return Response({
        'digest': result.text,
    }, status=status.HTTP_200_OK)
