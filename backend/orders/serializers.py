from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.transaction import atomic

from .models import (
    Cart, Order, OrderItem, Refund, RefundItem, OrderStatus, RefundStatus,
    create_inventory_transaction,
)
from products.models import Product, Inventory, InventoryChangeType
from products.image_utils import product_image_url

User = get_user_model()


# ==================== 购物车 ====================

class CartSerializer(serializers.ModelSerializer):
    """购物车序列化器"""
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_price = serializers.DecimalField(source='product.price', max_digits=10,
                                               decimal_places=2, read_only=True)
    product_image = serializers.SerializerMethodField()
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ('id', 'product', 'product_name', 'product_price',
                  'product_image', 'quantity', 'total_price', 'created_at')
        read_only_fields = ('id', 'created_at')

    def get_total_price(self, obj):
        return str(obj.total_price)

    def get_product_image(self, obj):
        return product_image_url(obj.product)


class CartAddSerializer(serializers.Serializer):
    """添加购物车"""
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)

    def validate_product_id(self, value):
        try:
            product = Product.objects.get(id=value, is_active=True)
        except Product.DoesNotExist:
            raise serializers.ValidationError('商品不存在或已下架')
        inventory, _ = Inventory.objects.get_or_create(product=product, defaults={'quantity': 0})
        if inventory.quantity <= 0:
            raise serializers.ValidationError('This product is out of stock.')
        return value

    def validate(self, attrs):
        product = Product.objects.get(id=attrs['product_id'])
        inventory, _ = Inventory.objects.get_or_create(product=product, defaults={'quantity': 0})
        if attrs['quantity'] > inventory.quantity:
            raise serializers.ValidationError(f'Only {inventory.quantity} item(s) are available.')
        return attrs


class CartUpdateSerializer(serializers.Serializer):
    """更新购物车数量"""
    quantity = serializers.IntegerField(min_value=1)


# ==================== 订单项 ====================

class OrderItemSerializer(serializers.ModelSerializer):
    """订单项序列化器"""
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_image = serializers.SerializerMethodField()
    total_price = serializers.SerializerMethodField()
    shop_name = serializers.SerializerMethodField()
    shop_id = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ('id', 'product', 'product_name', 'product_image',
                  'price', 'quantity', 'total_price', 'shop_name', 'shop_id')

    def get_total_price(self, obj):
        return str(obj.total_price)

    def get_product_image(self, obj):
        return product_image_url(obj.product)

    def get_shop_name(self, obj):
        if obj.product.shop:
            return obj.product.shop.shop_name
        return ''

    def get_shop_id(self, obj):
        if obj.product.shop:
            return obj.product.shop.shop_id
        return None


# ==================== 订单 ====================

class OrderSerializer(serializers.ModelSerializer):
    """订单序列化器"""
    items = OrderItemSerializer(many=True, read_only=True)
    status_text = serializers.SerializerMethodField()
    pending_refund_id = serializers.SerializerMethodField()
    pending_refund_status = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ('id', 'order_no', 'total_amount', 'status', 'status_text',
                  'address', 'receiver_name', 'receiver_phone', 'remark',
                  'items', 'pending_refund_id', 'pending_refund_status',
                  'created_at', 'updated_at')
        read_only_fields = ('id', 'order_no', 'total_amount', 'created_at', 'updated_at')

    def get_pending_refund_id(self, obj):
        refund = obj.refunds.filter(status='pending').first()
        return refund.id if refund else None

    def get_pending_refund_status(self, obj):
        refund = obj.refunds.filter(status='pending').first()
        return refund.status if refund else None

    def get_status_text(self, obj):
        return {
            'paid': 'Paid',
            'shipped': 'Shipped',
            'completed': 'Completed',
            'cancelled': 'Cancelled',
            'refunded': 'Refunded',
        }.get(obj.status, obj.status.title())


class OrderCreateSerializer(serializers.Serializer):
    """Create order from cart (or explicit item list)."""
    address = serializers.CharField(max_length=255)
    receiver_name = serializers.CharField(max_length=100)
    receiver_phone = serializers.CharField(max_length=11)
    remark = serializers.CharField(required=False, allow_blank=True, default='')
    items = serializers.ListField(required=False, default=[])

    def create(self, validated_data):
        try:
            return Order.create_from_cart(
                user=self.context['request'].user,
                address=validated_data['address'],
                receiver_name=validated_data['receiver_name'],
                receiver_phone=validated_data['receiver_phone'],
                remark=validated_data.get('remark', ''),
                items=validated_data.get('items') or None,
            )
        except DjangoValidationError as e:
            raise serializers.ValidationError(str(e))


class OrderStatusUpdateSerializer(serializers.Serializer):
    """更新订单状态"""
    status = serializers.ChoiceField(choices=OrderStatus.CHOICES)


class DirectOrderCreateSerializer(serializers.Serializer):
    """Direct purchase (buy now)."""
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)
    address = serializers.CharField(max_length=255)
    receiver_name = serializers.CharField(max_length=100)
    receiver_phone = serializers.CharField(max_length=11)
    remark = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_product_id(self, value):
        if not Product.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError('Product not found or unavailable.')
        return value

    def create(self, validated_data):
        try:
            return Order.create_direct(
                user=self.context['request'].user,
                product_id=validated_data['product_id'],
                quantity=validated_data['quantity'],
                address=validated_data['address'],
                receiver_name=validated_data['receiver_name'],
                receiver_phone=validated_data['receiver_phone'],
                remark=validated_data.get('remark', ''),
            )
        except DjangoValidationError as e:
            raise serializers.ValidationError(str(e))


# ==================== 退款 ====================

class RefundItemSerializer(serializers.ModelSerializer):
    """退款项序列化器"""
    product_name = serializers.CharField(source='order_item.product.name', read_only=True)

    class Meta:
        model = RefundItem
        fields = ('id', 'order_item', 'product_name', 'quantity', 'refund_amount')


class RefundSerializer(serializers.ModelSerializer):
    """退款序列化器"""
    items = RefundItemSerializer(many=True, read_only=True)
    status_text = serializers.SerializerMethodField()
    order_no = serializers.CharField(source='order.order_no', read_only=True)

    class Meta:
        model = Refund
        fields = ('id', 'refund_no', 'order', 'order_no', 'reason', 'total_amount',
                  'status', 'status_text', 'admin_remark', 'items',
                  'created_at', 'updated_at')
        read_only_fields = ('id', 'refund_no', 'total_amount', 'created_at', 'updated_at')

    def get_status_text(self, obj):
        return {
            'pending': 'Pending',
            'approved': 'Approved',
            'rejected': 'Rejected',
            'refunded': 'Refunded',
        }.get(obj.status, obj.status.title())


class RefundCreateSerializer(serializers.Serializer):
    """创建退款申请 — 退整个订单"""
    order_id = serializers.IntegerField()
    reason = serializers.CharField()

    def validate_order_id(self, value):
        user = self.context['request'].user
        try:
            order = Order.objects.get(id=value, user=user)
        except Order.DoesNotExist:
            raise serializers.ValidationError('Order not found.')

        if order.status == OrderStatus.CANCELLED:
            raise serializers.ValidationError('This order cannot be refunded in its current status.')

        if order.status == OrderStatus.REFUNDED:
            raise serializers.ValidationError('This order has already been refunded.')

        if Refund.objects.filter(order=order).exclude(status=RefundStatus.REJECTED).exists():
            raise serializers.ValidationError('This order already has a refund request in progress.')

        return value

    @atomic
    def create(self, validated_data):
        user = self.context['request'].user
        order = Order.objects.get(id=validated_data['order_id'])

        total_amount = sum(item.total_price for item in order.items.all())

        refund = Refund.objects.create(
            order=order,
            user=user,
            reason=validated_data['reason'],
            total_amount=total_amount,
            status=RefundStatus.PENDING,
        )

        for item in order.items.all():
            RefundItem.objects.create(
                refund=refund,
                order_item=item,
                quantity=item.quantity,
                refund_amount=item.total_price,
            )
            create_inventory_transaction(
                item.product,
                InventoryChangeType.REFUND_REQUESTED,
                item.quantity,
                refund=refund,
            )

        return refund


class RefundItemCreateSerializer(serializers.Serializer):
    """退款项数据"""
    order_item_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class RefundProcessSerializer(serializers.Serializer):
    """处理退款（管理员审批）—— 只做参数校验，业务逻辑在 Refund 模型中"""
    status = serializers.ChoiceField(choices=[RefundStatus.APPROVED, RefundStatus.REJECTED])
    admin_remark = serializers.CharField(required=False, allow_blank=True, default='')

    def update(self, instance, validated_data):
        new_status = validated_data['status']
        remark = validated_data.get('admin_remark', '')
        user = self.context['request'].user

        if new_status == RefundStatus.APPROVED:
            instance.approve(remark, processed_by=user)
        else:
            instance.reject(remark, processed_by=user)

        return instance
