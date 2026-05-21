from django.urls import path
from .views import (
    # 购物车
    CartListView, CartAddView, CartUpdateView, CartDeleteView, CartClearView,
    # 订单
    OrderListView, OrderDetailView, OrderCreateView, OrderStatusUpdateView, DirectOrderCreateView, OrderDeleteView,
    # 退款
    RefundListView, RefundDetailView, RefundCreateView, RefundCancelView, RefundProcessView,
)

urlpatterns = [
    # ==================== 购物车 ====================
    path('cart/', CartListView.as_view(), name='cart-list'),           # GET 购物车列表
    path('cart/add/', CartAddView.as_view(), name='cart-add'),         # POST 添加购物车
    path('cart/<int:pk>/', CartUpdateView.as_view(), name='cart-update'),  # PUT 更新数量
    path('cart/<int:pk>/delete/', CartDeleteView.as_view(), name='cart-delete'),  # DELETE 删除
    path('cart/clear/', CartClearView.as_view(), name='cart-clear'),   # DELETE 清空购物车

    # ==================== 订单 ====================
    path('', OrderListView.as_view(), name='order-list'),              # GET 订单列表
    path('create/', OrderCreateView.as_view(), name='order-create'),   # POST 创建订单（从购物车）
    path('direct-create/', DirectOrderCreateView.as_view(), name='order-direct-create'),  # POST 直接购买
    path('<int:pk>/', OrderDetailView.as_view(), name='order-detail'), # GET 订单详情
    path('<int:pk>/status/', OrderStatusUpdateView.as_view(), name='order-status'),  # PUT 更新状态
    path('<int:pk>/delete/', OrderDeleteView.as_view(), name='order-delete'),  # DELETE 删除订单

    # ==================== 退款 ====================
    path('refunds/', RefundListView.as_view(), name='refund-list'),            # GET 退款列表
    path('refunds/create/', RefundCreateView.as_view(), name='refund-create'), # POST create refund
    path('refunds/<int:pk>/', RefundDetailView.as_view(), name='refund-detail'),  # GET 退款详情
    path('refunds/<int:pk>/cancel/', RefundCancelView.as_view(), name='refund-cancel'),  # PUT cancel refund
    path('refunds/<int:pk>/process/', RefundProcessView.as_view(), name='refund-process'),  # PUT 处理退款
]
