from django.contrib import admin
from .models import Category, Product, Shop, Inventory, InventoryTransaction, Review


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ('shop_id', 'shop_name', 'user', 'rating', 'created_at')
    search_fields = ('shop_name', 'user__username')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'price', 'shop', 'seller', 'is_active', 'created_at')
    list_filter = ('is_active', 'category', 'created_at')
    search_fields = ('name', 'seller__username', 'shop__shop_name')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'parent', 'slug')
    search_fields = ('name',)


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ('inventory_id', 'product', 'quantity', 'updated_at')
    search_fields = ('product__name',)


@admin.register(InventoryTransaction)
class InventoryTransactionAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'inventory', 'change_type', 'quantity_change',
                    'related_order', 'related_refund', 'created_at')
    list_filter = ('change_type', 'created_at', 'related_order', 'related_refund')
    search_fields = ('inventory__product__name', 'related_order__order_no', 'related_refund__refund_no')


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('review_id', 'product', 'user', 'rating', 'like_count', 'created_at')
    list_filter = ('rating',)
    search_fields = ('product__name', 'user__username')

