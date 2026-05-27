"""API views for CustomerServiceAgent.

Endpoints:
    POST   /api/agents/chat/             — Send a customer inquiry
    GET    /api/agents/chat/history/     — Get conversation history
    GET    /api/agents/chat/stream/      — SSE streaming chat (Phase 2b)
"""

import uuid
import logging

from django.http import StreamingHttpResponse
from django.db import models
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from agents.models import ConversationSession, AgentConversation
from agents.permissions import IsAuthenticatedOrGuest, IsOwnerOrAdmin
from agents.api.agent import CustomerServiceAgent
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


@api_view(['POST'])
@permission_classes([IsAuthenticatedOrGuest])
def ai_entry(request):
    """Unified AI entry point — all AI requests go through LangGraph."""
    from .serializers import ChatRequestSerializer
    import uuid as _uuid

    serializer = ChatRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    query = serializer.validated_data['message']
    session_id = serializer.validated_data.get('session_id') or str(_uuid.uuid4())[:12]
    query_type = request.data.get('query_type', '')
    product_id = str(request.data.get('product_id', ''))
    user_id = request.user.id if request.user.is_authenticated else None

    from agents.graph.orchestrator import run as run_graph

    history = request.data.get('history', [])

    # ── Persist user message (immediate) ──
    if request.user.is_authenticated:
        try:
            AgentConversation.objects.create(
                user=request.user,
                agent_type='workspace',
                session_id=session_id,
                role='user',
                content=query,
            )
        except Exception:
            pass

    assistant_reply = ''
    assistant_blocks = []
    try:
        result = run_graph(query=query, user_id=user_id, session_id=session_id,
                          query_type=query_type, product_id=product_id,
                          history=history)
        assistant_reply = result.get('reply', '')
        assistant_blocks = result.get('blocks', [])
    except Exception as e:
        assistant_reply = f'AI service error: {e}'
        return Response({'error': str(e), 'reply': assistant_reply},
                       status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        # ── Persist assistant message (guaranteed) ──
        if request.user.is_authenticated and assistant_reply:
            try:
                AgentConversation.objects.create(
                    user=request.user,
                    agent_type='workspace',
                    session_id=session_id,
                    role='assistant',
                    content=assistant_reply,
                    metadata={'blocks': assistant_blocks},
                )
                ConversationSession.objects.filter(
                    session_id=session_id, user=request.user,
                ).update(last_message_at=timezone.now())
                cs = ConversationSession.objects.filter(
                    session_id=session_id, user=request.user,
                ).first()
                if cs and not cs.title:
                    cs.title = query[:50]
                    cs.save(update_fields=['title'])
            except Exception:
                pass

    return Response({
        'ui_state': result.get('ui_state', 'done'),
        'message': result.get('message', ''),
        'blocks': result.get('blocks', []),
        'reply': result.get('reply', ''),
        'intent': result.get('intent', ''),
        'agent_type': result.get('agent_type', 'commerce'),
        'confidence': result.get('confidence', 0.0),
        'ranked_items': result.get('ranked_items', []),
        'tool_results': result.get('tool_results', {}),
        'session_id': session_id,
        'query_type': query_type,
        'runtime': result.get('runtime'),
        'explain': result.get('explain'),
        'retrieval': result.get('retrieval'),
        'show_budget_hint': result.get('show_budget_hint', False),
        'show_clarify_hint': result.get('show_clarify_hint', False),
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticatedOrGuest])
def eval_track(request):
    """Record an evaluation event (impression/click/dismiss/etc)."""
    from agents.models import EvaluationEvent
    import uuid as _uuid

    session_id = request.data.get('session_id') or str(_uuid.uuid4())[:12]
    query_type = request.data.get('query_type', '')
    event_type = request.data.get('event_type', '')
    product_id = request.data.get('product_id') or None
    duration_ms = request.data.get('duration_ms') or None
    outcome_type = request.data.get('outcome_type', '')
    success = request.data.get('success', False)

    if not event_type:
        return Response({'error': 'event_type required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        EvaluationEvent.objects.create(
            session_id=session_id,
            query_type=query_type,
            event_type=event_type,
            product_id=product_id,
            duration_ms=duration_ms,
            outcome_type=outcome_type,
            success=success,
            metadata=request.data.get('metadata', {}),
        )

        # Phase B-0: classify signal and persist StandardizedSignal
        try:
            from agents.graph.feedback.signal_classifier import classify_and_create
            classify_and_create(
                event={
                    "event_type": event_type,
                    "session_id": session_id,
                    "product_id": product_id,
                    "category": request.data.get("category", ""),
                    "metadata": request.data.get("metadata", {}),
                },
                user_id=request.user.id if request.user.is_authenticated else None,
            )
        except Exception:
            pass  # signal persistence is non-critical

        # Phase B-3: feed outcome back to routing tuner
        try:
            from agents.graph.routing.tuner import update_outcome
            update_outcome(session_id, outcome_type or event_type)
        except Exception:
            pass

        return Response({'status': 'ok'}, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticatedOrGuest])
def feedback(request):
    """Record user feedback on AI recommendations."""
    product_id = request.data.get('product_id')
    action = request.data.get('action', 'click')
    category = request.data.get('category', '')
    product_name = request.data.get('product_name', '')

    if not product_id:
        return Response({'error': 'product_id required'}, status=status.HTTP_400_BAD_REQUEST)

    from products.models import Product
    try:
        Product.objects.filter(id=product_id).update(
            popularity_score=models.F('popularity_score') + 1
        )
    except Exception:
        pass

    return Response({'status': 'ok'}, status=status.HTTP_200_OK)


# ═══════════════════════════════════════════════════════════════
# Session Management API
# ═══════════════════════════════════════════════════════════════

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def session_list(request):
    sessions = ConversationSession.objects.none()
    if request.user.is_authenticated:
        sessions = ConversationSession.objects.filter(
            user=request.user,
        ).order_by('-last_message_at')
    data = [{
        'session_id': s.session_id,
        'title': s.title,
        'last_message_at': s.last_message_at,
        'created_at': s.created_at,
    } for s in sessions]
    return Response(data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def session_create(request):
    title = request.data.get('title', '')
    session_id = uuid.uuid4().hex
    ConversationSession.objects.create(
        session_id=session_id,
        user=request.user,
        title=title,
    )
    return Response({'session_id': session_id, 'title': title}, status=status.HTTP_201_CREATED)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def session_detail(request, session_id):
    title = request.data.get('title', '')
    updated = ConversationSession.objects.filter(
        session_id=session_id, user=request.user,
    ).update(title=title)
    if not updated:
        return Response({'error': 'not found'}, status=status.HTTP_404_NOT_FOUND)
    return Response({'ok': True}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def session_messages(request, session_id):
    qs = AgentConversation.objects.filter(
        session_id=session_id, user=request.user,
    ).order_by('created_at')
    data = [{
        'role': m.role,
        'content': m.content,
        'metadata': m.metadata or {},
        'created_at': m.created_at,
    } for m in qs]
    return Response(data, status=status.HTTP_200_OK)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def session_delete(request, session_id):
    ConversationSession.objects.filter(
        session_id=session_id, user=request.user,
    ).delete()
    AgentConversation.objects.filter(
        session_id=session_id, user=request.user,
    ).delete()
    return Response({'ok': True}, status=status.HTTP_200_OK)


# ═══════════════════════════════════════════════════════════════
# Agent Console API — observability endpoints
# ═══════════════════════════════════════════════════════════════

@api_view(['GET'])
@permission_classes([IsAuthenticatedOrGuest])
def traces_list(request):
    """List recent session traces for the Agent Console."""
    from agents.models import SessionTrace
    from datetime import timedelta
    from django.utils import timezone

    limit = min(int(request.GET.get('limit', 20)), 50)
    qs = SessionTrace.objects.order_by('-created_at')[:limit]
    results = []
    for t in qs:
        # Count block events
        blocks = {}
        for e in (t.events or []):
            b = e.get('block', '')
            blocks[b] = blocks.get(b, 0) + 1
        results.append({
            'session_id': t.session_id,
            'query': t.query[:80],
            'intent': t.intent,
            'confidence': round(t.routing_conf, 2),
            'total_ms': t.total_ms,
            'blocks': blocks,
            'created_at': t.created_at.isoformat(),
        })
    return Response({'traces': results, 'count': len(results)})


@api_view(['GET'])
@permission_classes([IsAuthenticatedOrGuest])
def traces_detail(request, session_id):
    """Get full trace detail including phases, events, and ranking changes."""
    from agents.models import SessionTrace
    from django.shortcuts import get_object_or_404

    t = get_object_or_404(SessionTrace, session_id=session_id)
    return Response({
        'session_id': t.session_id,
        'query': t.query,
        'intent': t.intent,
        'confidence': round(t.routing_conf, 2),
        'total_ms': t.total_ms,
        'phases': t.phases,
        'events': t.events,
        'ranked_before': t.ranked_before[:10],
        'ranked_after': t.ranked_after[:10],
        'signals_applied': t.signals_applied,
        'reply': t.reply[:300],
        'created_at': t.created_at.isoformat(),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticatedOrGuest])
def health(request):
    """Aggregated runtime health for the Agent Console Layer 1."""
    from agents.models import SessionTrace
    from datetime import timedelta
    from django.utils import timezone

    cutoff = timezone.now() - timedelta(hours=24)
    recent = SessionTrace.objects.filter(created_at__gte=cutoff)
    total = recent.count()
    if total == 0:
        return Response({
            'avg_latency_ms': 0,
            'routing_quality': 0,
            'fast_ratio': 0,
            'total_sessions_24h': 0,
            'p95_latency_ms': 0,
            'ranking_lift_avg': 0,
            'ranked_session_count': 0,
            'clarify_rate': 0,
            'clarify_count': 0,
            'fallback_rate': 0,
            'fallback_count': 0,
        })

    avg_latency = sum(t.total_ms for t in recent) / total

    # P95 latency
    latencies = sorted([t.total_ms for t in recent])
    p95_idx = int(len(latencies) * 0.95)
    p95_latency = latencies[p95_idx] if latencies else 0

    # Routing Quality: sessions with engagement (have ranked_after changes)
    engaged = 0
    rank_deltas = []
    ranked_session_ids = set()
    for t in recent:
        if t.events:
            for e in t.events:
                if e.get('block') == 'ranking' and e.get('payload', {}).get('changes'):
                    engaged += 1
                    ranked_session_ids.add(t.session_id)
                    for ch in e['payload']['changes']:
                        if 'delta' in ch:
                            rank_deltas.append(ch['delta'])
                    break
    routing_quality = round(engaged / total, 3) if total > 0 else 0
    avg_rank_shift = round(sum(rank_deltas) / len(rank_deltas), 1) if rank_deltas else 0
    ranked_session_count = len(ranked_session_ids)

    # Fast ratio from events
    fast_count = 0
    for t in recent:
        if t.events:
            for e in t.events:
                if e.get('block') == 'routing' and e.get('payload', {}).get('method') == 'fast':
                    fast_count += 1
                    break
    fast_ratio = round(fast_count / total, 3) if total > 0 else 0

    # Clarify and fallback counts → rates
    clarify_count = recent.filter(intent='clarify').count()
    fallback_count = recent.filter(models.Q(intent='') | models.Q(intent='fallback')).count()
    clarify_rate = round(clarify_count / total, 3) if total > 0 else 0
    fallback_rate = round(fallback_count / total, 3) if total > 0 else 0

    return Response({
        'avg_latency_ms': round(avg_latency),
        'routing_quality': routing_quality,
        'fast_ratio': fast_ratio,
        'total_sessions_24h': total,
        'p95_latency_ms': p95_latency,
        'ranking_lift_avg': avg_rank_shift,
        'ranked_session_count': ranked_session_count,
        'clarify_rate': clarify_rate,
        'clarify_count': clarify_count,
        'fallback_rate': fallback_rate,
        'fallback_count': fallback_count,
    })
