"""URL configuration for AI Agent API endpoints.

Mount at: /api/agents/
"""

from django.urls import path
from agents.customer_service import views as cs_views
from agents.ops import views as ops_views

urlpatterns = [
    # Customer Service (Phase 2)
    path('chat/', cs_views.chat, name='agent-chat'),
    path('chat/history/', cs_views.chat_history, name='agent-chat-history'),
    # AI entry (LangGraph)
    path('ai/', cs_views.ai_entry, name='agent-ai-entry'),
    path('ai/feedback/', cs_views.feedback, name='agent-ai-feedback'),
    # Phase A: Evaluation tracking
    path('eval/track/', cs_views.eval_track, name='agent-eval-track'),

    # Agent Console (observability)
    path('console/traces/', cs_views.traces_list, name='console-traces-list'),
    path('console/traces/<str:session_id>/', cs_views.traces_detail, name='console-traces-detail'),
    path('console/health/', cs_views.health, name='console-health'),

    # Ops (Phase 3)
    path('ops/health/', ops_views.health, name='agent-ops-health'),
    path('ops/alerts/', ops_views.alerts, name='agent-ops-alerts'),
    path('ops/report/', ops_views.report, name='agent-ops-report'),
]
