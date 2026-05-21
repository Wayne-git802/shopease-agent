from django.urls import path
from .views import (
    CategoryViewSet,
    ProductViewSet,
    InventoryListView,
    InventoryRestockView,
    InventoryTransactionListView,
    ReviewCreateView,
    ReviewListView,
    ShopFollowView,
    ShopListView,
    ShopDetailView,
)

# Category 路由
category_list = CategoryViewSet.as_view({
    'get': 'list',
    'post': 'create'
})
category_detail = CategoryViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'delete': 'destroy'
})

# Product 路由
product_list = ProductViewSet.as_view({
    'get': 'list',
    'post': 'create'
})
product_detail = ProductViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
    'delete': 'destroy',
})

urlpatterns = [
    # Category API
    path('categories/', category_list, name='category-list'),
    path('categories/<int:pk>/', category_detail, name='category-detail'),

    # Product API
    path('', product_list, name='product-list'),
    path('inventory-transactions/', InventoryTransactionListView.as_view(), name='inventory-transaction-list'),
    path('inventory/', InventoryListView.as_view(), name='inventory-list'),
    path('inventory/<int:product_id>/restock/', InventoryRestockView.as_view(), name='inventory-restock'),
    path('<int:pk>/', product_detail, name='product-detail'),
    path('<int:product_id>/reviews/', ReviewListView.as_view(), name='review-list'),
    path('<int:product_id>/reviews/create/', ReviewCreateView.as_view(), name='review-create'),
    path('shops/', ShopListView.as_view(), name='shop-list'),
    path('shops/<int:pk>/', ShopDetailView.as_view(), name='shop-detail'),
    path('shops/<int:pk>/follow/', ShopFollowView.as_view(), name='shop-follow'),
]
