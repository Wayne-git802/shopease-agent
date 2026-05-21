"""
URL configuration for mysite project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from templates.views import (
    home, product_list, product_detail, cart,
    user_login, user_register, user_logout,
    order_list, profile, checkout, shop, shop_list
)

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Template pages
    path('', home, name='home'),
    path('products/', product_list, name='product_list'),
    path('products/<int:pk>/', product_detail, name='product_detail'),
    path('cart/', cart, name='cart'),
    
    # User pages
    path('users/login/', user_login, name='login'),
    path('users/register/', user_register, name='register'),
    path('users/logout/', user_logout, name='logout'),
    path('profile/', profile, name='profile'),
    
    # Order pages
    path('orders/', order_list, name='order_list'),
    path('orders/checkout/', checkout, name='checkout'),
    
    # Shop pages
    path('shops/', shop_list, name='shop_list'),
    path('shop/<int:shop_id>/', shop, name='shop'),
    
    # API endpoints
    path('api/users/', include('users.urls')),
    path('api/products/', include('products.urls')),
    path('api/orders/', include('orders.urls')),
    path('api/admin/', include('admin_api.urls')),
]

# Serve static files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
