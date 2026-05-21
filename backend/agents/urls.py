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

    # Ops (Phase 3)
    path('ops/health/', ops_views.health, name='agent-ops-health'),
    path('ops/alerts/', ops_views.alerts, name='agent-ops-alerts'),
    path('ops/report/', ops_views.report, name='agent-ops-report'),

    # Future (Phase 4-5):
    # path('recommend/for-you/', rec_views.for_you, name='agent-recommend-for-you'),
    # path('recommend/trending/', rec_views.trending, name='agent-recommend-trending'),
    # path('meta/report/', meta_views.report, name='agent-meta-report'),
]
