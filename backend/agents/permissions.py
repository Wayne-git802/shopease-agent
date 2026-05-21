"""Permission classes for AI Agent API endpoints.

Matches the permission matrix from ARCHITECTURE.md:
    POST  /api/agents/chat/              → authenticated only
    GET   /api/agents/chat/history/      → authenticated (own) / admin (all)
    GET   /api/agents/ops/health/        → admin only
    GET   /api/agents/ops/alerts/        → admin only
    GET   /api/agents/ops/report/        → admin only
    GET   /api/agents/recommend/for-you/ → authenticated
    GET   /api/agents/recommend/trending/→ anyone
    GET   /api/agents/meta/report/       → admin only

Usage in views:
    permission_classes = [IsAuthenticated]
    permission_classes = [IsAdminUser]
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]
"""

from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAdminUser(BasePermission):
    """Only admin users (is_staff=True or is_superuser=True)."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or request.user.is_superuser)
        )


class IsOwnerOrAdmin(BasePermission):
    """Object-level: allow if user owns the resource or is admin.

    Assumes the view has a `get_object()` that returns a model with a
    `user` field.  For list views, admins see all, others see none
    (use with a filtered queryset).
    """

    def has_permission(self, request, view):
        # Must be authenticated
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff or request.user.is_superuser:
            return True
        return getattr(obj, 'user', None) == request.user


class IsAdminOrReadOnly(BasePermission):
    """Admins can write; everyone else read-only.

    Useful for endpoints where data is public to view but
    only admins can modify.
    """

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or request.user.is_superuser)
        )


class IsAuthenticatedOrGuest(BasePermission):
    """Allow both authenticated users and anonymous guests.

    The view logic should differentiate based on request.user.is_authenticated.
    """

    def has_permission(self, request, view):
        return True  # everyone — view handles the rest


# ── Convenience mapping ─────────────────────────────────────────
# Maps each API endpoint to its permission class(es)

ENDPOINT_PERMISSIONS = {
    'chat':        [IsAuthenticatedOrGuest],   # view enforces login for actual chat
    'chat_history': [IsOwnerOrAdmin],
    'ops_health':  [IsAdminUser],
    'ops_alerts':  [IsAdminUser],
    'ops_report':  [IsAdminUser],
    'recommend_for_you': [IsAuthenticatedOrGuest],  # view enforces login
    'recommend_trending': [IsAuthenticatedOrGuest],  # public
    'meta_report': [IsAdminUser],
}
