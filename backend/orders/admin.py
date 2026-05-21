from django.contrib import admin
from .models import Cart, Order, OrderItem, Refund, RefundItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'price', 'quantity')


class RefundItemInline(admin.TabularInline):
    model = RefundItem
    extra = 0
    readonly_fields = ('order_item', 'quantity', 'refund_amount')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_no', 'user', 'total_amount', 'status', 'receiver_name', 'buyer_deleted', 'created_at')
    list_filter = ('status', 'buyer_deleted', 'created_at')
    search_fields = ('order_no', 'user__username', 'receiver_name', 'receiver_phone')
    readonly_fields = ('order_no', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'product', 'price', 'quantity')
    search_fields = ('order__order_no', 'product__name')


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'product', 'quantity', 'updated_at')
    search_fields = ('user__username', 'product__name')


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ('refund_no', 'order', 'user', 'total_amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('refund_no', 'order__order_no', 'user__username')
    readonly_fields = ('refund_no', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    inlines = [RefundItemInline]


@admin.register(RefundItem)
class RefundItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'refund', 'order_item', 'quantity', 'refund_amount')
    search_fields = ('refund__refund_no',)
