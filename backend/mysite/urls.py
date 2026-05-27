"""
URL configuration for ShopEase Agent — Commerce + AI + Admin
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from views import (
    home, product_list, product_detail,
    cart, user_login, user_register, user_logout, profile,
    order_list, checkout, shop_list, shop,
    ai_workspace, ai_console, ai_runtime, ai_diff, ai_replay,
    admin_dashboard, admin_products, admin_sellers, admin_orders,
    admin_overview_api, admin_toggle_product,
)

urlpatterns = [
    path('admin/', admin.site.urls),

    # Home
    path('', home, name='home'),

    # Products
    path('products/', product_list, name='product_list'),
    path('products/<int:pk>/', product_detail, name='product_detail'),

    # Cart
    path('cart/', cart, name='cart'),

    # Auth
    path('users/login/', user_login, name='login'),
    path('users/register/', user_register, name='register'),
    path('users/logout/', user_logout, name='logout'),
    path('profile/', profile, name='profile'),

    # Orders
    path('orders/', order_list, name='order_list'),
    path('orders/checkout/', checkout, name='checkout'),

    # Shops
    path('shops/', shop_list, name='shop_list'),
    path('shop/<int:shop_id>/', shop, name='shop'),

    # AI Agent pages
    path('ai/workspace/', ai_workspace, name='ai_workspace'),
    path('ai/console/', ai_console, name='ai_console'),
    path('ai/runtime/', ai_runtime, name='ai_runtime'),
    path('ai/diff/', ai_diff, name='ai_diff'),
    path('ai/replay/', ai_replay, name='ai_replay'),

    # Admin management
    path('manage/', admin_dashboard, name='manage-dashboard'),
    path('manage/products/', admin_products, name='manage-products'),
    path('manage/sellers/', admin_sellers, name='manage-sellers'),
    path('manage/orders/', admin_orders, name='manage-orders'),
    path('manage/api/overview/', admin_overview_api, name='manage-overview-api'),
    path('manage/api/products/<int:pk>/toggle-status/', admin_toggle_product,
         name='manage-toggle-product'),

    # API endpoints
    path('api/users/', include('users.urls')),
    path('api/products/', include('products.urls')),
    path('api/orders/', include('orders.urls')),
    path('api/admin/', include('admin_api.urls')),
    path('api/agents/', include('agents.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
