from django.urls import path
from .views import (
    AdminStatsView,
    AdminUserToggleView,
    AdminShopApprovalView,
    AdminProductModerateView,
    AdminReviewListView,
    AdminReviewModerateView,
    SQLDemoView,
    AuditLogListView,
    AdminOrderListView,
    DatabaseTablesView,
    DatabaseTableView,
    ChangeFeedView,
)

urlpatterns = [
    path('stats/', AdminStatsView.as_view(), name='admin-stats'),
    path('users/<str:username>/toggle/', AdminUserToggleView.as_view(), name='admin-user-toggle'),
    path('shops/<int:shop_id>/approve/', AdminShopApprovalView.as_view(), name='admin-shop-approve'),
    path('products/<int:product_id>/moderate/', AdminProductModerateView.as_view(), name='admin-product-moderate'),
    path('reviews/', AdminReviewListView.as_view(), name='admin-review-list'),
    path('reviews/<int:review_id>/moderate/', AdminReviewModerateView.as_view(), name='admin-review-moderate'),
    path('sql-demo/', SQLDemoView.as_view(), name='admin-sql-demo'),
    path('audit-logs/', AuditLogListView.as_view(), name='admin-audit-logs'),
    path('orders/', AdminOrderListView.as_view(), name='admin-orders'),
    path('db-tables/', DatabaseTablesView.as_view(), name='admin-db-tables'),
    path('db-table/', DatabaseTableView.as_view(), name='admin-db-table'),
    path('change-feed/', ChangeFeedView.as_view(), name='admin-change-feed'),
]
