"""URL configuration for AI Agent API endpoints.

Mount at: /api/agents/
"""

from django.urls import path
from agents.api import views as api_views
from agents.ops import views as ops_views

urlpatterns = [
    # Customer Service (Phase 2)
    path('chat/', api_views.chat, name='agent-chat'),
    path('chat/history/', api_views.chat_history, name='agent-chat-history'),
    # AI entry (LangGraph)
    path('ai/', api_views.ai_entry, name='agent-ai-entry'),
    path('ai/feedback/', api_views.feedback, name='agent-ai-feedback'),
    # Session management
    path('sessions/', api_views.session_list, name='agent-session-list'),
    path('sessions/create/', api_views.session_create, name='agent-session-create'),
    path('sessions/<str:session_id>/', api_views.session_detail, name='agent-session-detail'),
    path('sessions/<str:session_id>/messages/', api_views.session_messages, name='agent-session-messages'),
    path('sessions/<str:session_id>/delete/', api_views.session_delete, name='agent-session-delete'),
    # Phase A: Evaluation tracking
    path('eval/track/', api_views.eval_track, name='agent-eval-track'),

    # Agent Console (observability)
    path('console/traces/', api_views.traces_list, name='console-traces-list'),
    path('console/traces/<str:session_id>/', api_views.traces_detail, name='console-traces-detail'),
    path('console/health/', api_views.health, name='console-health'),

    # Ops (Phase 3)
    path('ops/health/', ops_views.health, name='agent-ops-health'),
    path('ops/alerts/', ops_views.alerts, name='agent-ops-alerts'),
    path('ops/report/', ops_views.report, name='agent-ops-report'),
]
