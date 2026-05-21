from django.core.exceptions import ValidationError
from django.db import models
from django.db.transaction import atomic
from django.contrib.auth import get_user_model
from products.models import Product, Inventory, InventoryChangeType, InventoryTransaction

User = get_user_model()


def create_inventory_transaction(product, change_type, quantity_change, order=None, refund=None):
    inventory, _ = Inventory.objects.get_or_create(
        product=product,
        defaults={'quantity': 0},
    )
    InventoryTransaction.objects.create(
        inventory=inventory,
        change_type=change_type,
        quantity_change=quantity_change,
        related_order=order,
        related_refund=refund,
    )


class OrderStatus:
    """Order status constants."""
    PAID = 'paid'
    SHIPPED = 'shipped'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'
    REFUNDED = 'refunded'

    CHOICES = [
        (PAID, 'Paid'),
        (SHIPPED, 'Shipped'),
        (COMPLETED, 'Completed'),
        (CANCELLED, 'Cancelled'),
        (REFUNDED, 'Refunded'),
    ]


class RefundStatus:
    """Refund status constants."""
    PENDING = 'pending'            # 待处理
    APPROVED = 'approved'          # 已通过
    REJECTED = 'rejected'          # 已拒绝
    REFUNDED = 'refunded'

    CHOICES = [
        (PENDING, 'Pending'),
        (APPROVED, 'Approved'),
        (REJECTED, 'Rejected'),
        (REFUNDED, 'Refunded'),
    ]


class Cart(models.Model):
    """
    购物车模型
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='carts',
        verbose_name='用户'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='carts',
        verbose_name='商品'
    )
    quantity = models.PositiveIntegerField(default=1, verbose_name='数量')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='添加时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'carts'
        verbose_name = '购物车'
        verbose_name_plural = verbose_name
        unique_together = ['user', 'product']  # 同一用户同一商品只能有一条记录

    def __str__(self):
        return f'{self.user.username} - {self.product.name} x {self.quantity}'

    @property
    def total_price(self):
        """计算总价"""
        return self.product.price * self.quantity


class OrderQuerySet(models.QuerySet):
    def visible_to(self, user):
        """用户可见的订单：买家自己的 + 卖家店铺的"""
        from products.models import Shop
        q = models.Q(user=user, buyer_deleted=False)
        shop_ids = Shop.objects.filter(user=user).values_list('shop_id', flat=True)
        if shop_ids:
            q |= models.Q(items__product__shop_id__in=shop_ids)
        return self.filter(q).distinct()


class Order(models.Model):
    """
    订单模型
    """
    objects = OrderQuerySet.as_manager()

    order_no = models.CharField(max_length=32, unique=True, verbose_name='订单号')
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='orders',
        verbose_name='用户'
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='订单总金额')
    status = models.CharField(max_length=20, choices=OrderStatus.CHOICES, 
                              default=OrderStatus.PAID, verbose_name='订单状态')
    address = models.CharField(max_length=255, verbose_name='收货地址')
    receiver_name = models.CharField(max_length=100, verbose_name='收货人姓名')
    receiver_phone = models.CharField(max_length=11, verbose_name='收货人电话')
    remark = models.TextField(blank=True, null=True, verbose_name='订单备注')
    buyer_deleted = models.BooleanField(default=False, verbose_name='买家已删除')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'orders'
        verbose_name = '订单'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status'], name='idx_order_status'),
            models.Index(fields=['created_at'], name='idx_order_created'),
            models.Index(fields=['user', 'status'], name='idx_order_user_status'),
        ]

    def __str__(self):
        return f'订单 {self.order_no}'

    def save(self, *args, **kwargs):
        if not self.order_no:
            import uuid
            import time
            self.order_no = f'{time.strftime("%Y%m%d%H%M%S")}{uuid.uuid4().hex[:8].upper()}'
        super().save(*args, **kwargs)

    # ── 状态机规则（唯一的数据源） ──
    TRANSITIONS = {
        'paid': {
            'shipped': {'who': 'seller'},
            'cancelled': {'who': 'buyer'},
        },
        'shipped': {
            'completed': {'who': 'buyer'},
        },
    }

    def is_final(self):
        """终态订单不允许任何状态变更"""
        return self.status in [OrderStatus.COMPLETED, OrderStatus.REFUNDED, OrderStatus.CANCELLED]

    def is_sold_by(self, user):
        """检查用户是否是该订单中任一商品的店铺卖家"""
        from products.models import Shop
        shop_ids = self.items.values_list('product__shop_id', flat=True)
        return Shop.objects.filter(shop_id__in=shop_ids, user=user).exists()

    def can_transition_to(self, new_status, user):
        """
        检查用户是否有权将订单转到目标状态。
        返回 (ok: bool, message: str)
        """
        if self.is_final():
            return False, 'Completed, cancelled, or refunded orders cannot be updated.'

        available = self.TRANSITIONS.get(self.status, {})
        if new_status not in available:
            return False, f'Cannot change status from {self.status} to {new_status}.'

        who = available[new_status]['who']

        if who == 'seller':
            if user.is_staff:
                return True, ''
            if not self.is_sold_by(user):
                return False, 'Only the seller for this shop can perform this action.'

        elif who == 'buyer':
            if self.user_id != user.id:
                return False, 'Only the buyer can perform this action.'

        return True, ''

    @classmethod
    @atomic
    def create_direct(cls, user, product_id, quantity, address, receiver_name,
                      receiver_phone, remark=''):
        """Direct purchase (buy now). Locks inventory row to prevent overselling."""
        from admin_api.models import write_audit

        product = Product.objects.select_related('inventory').get(
            id=product_id, is_active=True)
        inventory = Inventory.objects.select_for_update().get(product=product)

        if inventory.quantity < quantity:
            raise ValidationError(
                f'{product.name} only has {inventory.quantity} in stock.')

        total = product.price * quantity

        order = cls.objects.create(
            user=user, total_amount=total, status=OrderStatus.PAID,
            address=address, receiver_name=receiver_name,
            receiver_phone=receiver_phone, remark=remark,
        )

        write_audit(
            user=user, action='Order Created', table_name='orders',
            record_id=order.order_no,
            description=f'{user.username} placed order #{order.order_no}, total ¥{float(total):.2f}',
            new_value=f'status=paid, amount={float(total)}',
        )

        OrderItem.objects.create(
            order=order, product=product, price=product.price, quantity=quantity)

        old_qty = inventory.quantity
        inventory.quantity -= quantity
        inventory.save()

        create_inventory_transaction(
            product, InventoryChangeType.ORDER_DEDUCT, -quantity, order=order)

        write_audit(
            user=user, action='Inventory Deducted', table_name='inventory',
            record_id=str(inventory.inventory_id),
            description=f'{product.name} stock -{quantity} ({old_qty} → {inventory.quantity}), order {order.order_no}',
            old_value=str(old_qty), new_value=str(inventory.quantity),
        )

        return order

    @classmethod
    @atomic
    def create_from_cart(cls, user, address, receiver_name, receiver_phone,
                         remark='', items=None):
        """Create order from cart or from an explicit item list.

        Args:
            items: Optional list of dicts like [{'product_id': 1, 'quantity': 2}].
                   When None, reads from the user's cart and clears it.
        """
        from admin_api.models import write_audit

        if items:
            product_ids = [it['product_id'] for it in items]
            products = Product.objects.filter(
                id__in=product_ids, is_active=True).select_related('inventory')
            product_map = {p.id: p for p in products}

            for item in items:
                if item['product_id'] not in product_map:
                    raise ValidationError(
                        f'Product {item["product_id"]} not found or unavailable.')

            inv_map = {
                inv.product_id: inv
                for inv in Inventory.objects.select_for_update().filter(
                    product_id__in=product_ids)
            }

            order_items_data = []
            for item in items:
                product = product_map[item['product_id']]
                inventory = inv_map.get(product.id)
                if not inventory:
                    inventory, _ = Inventory.objects.get_or_create(
                        product=product, defaults={'quantity': 0})
                    inv_map[product.id] = inventory
                qty = item.get('quantity', 1)
                if inventory.quantity < qty:
                    raise ValidationError(
                        f'{product.name} only has {inventory.quantity} in stock.')
                order_items_data.append(
                    {'product': product, 'price': product.price, 'quantity': qty})
        else:
            carts = Cart.objects.filter(
                user=user).select_related('product__inventory')
            if not carts.exists():
                raise ValidationError('Cart is empty.')

            product_ids = [c.product_id for c in carts]
            inv_map = {
                inv.product_id: inv
                for inv in Inventory.objects.select_for_update().filter(
                    product_id__in=product_ids)
            }

            order_items_data = []
            for cart in carts:
                inventory = inv_map.get(cart.product_id)
                if not inventory or inventory.quantity < cart.quantity:
                    stock = inventory.quantity if inventory else 0
                    raise ValidationError(
                        f'{cart.product.name} only has {stock} in stock.')
                order_items_data.append(
                    {'product': cart.product, 'price': cart.product.price,
                     'quantity': cart.quantity})

        if not order_items_data:
            raise ValidationError('No items to order.')

        total = sum(d['price'] * d['quantity'] for d in order_items_data)

        order = cls.objects.create(
            user=user, total_amount=total, status=OrderStatus.PAID,
            address=address, receiver_name=receiver_name,
            receiver_phone=receiver_phone, remark=remark,
        )

        write_audit(
            user=user, action='Order Created', table_name='orders',
            record_id=order.order_no,
            description=f'{user.username} placed order #{order.order_no}, total ¥{float(total):.2f}',
            new_value=f'status=paid, amount={float(total)}',
        )

        for d in order_items_data:
            product = d['product']
            qty = d['quantity']
            OrderItem.objects.create(
                order=order, product=product, price=d['price'], quantity=qty)

            inventory = inv_map[product.id]
            old_qty = inventory.quantity
            inventory.quantity -= qty
            inventory.save()

            create_inventory_transaction(
                product, InventoryChangeType.ORDER_DEDUCT, -qty, order=order)

            write_audit(
                user=user, action='Inventory Deducted', table_name='inventory',
                record_id=str(inventory.inventory_id),
                description=f'{product.name} stock -{qty} ({old_qty} → {inventory.quantity}), order {order.order_no}',
                old_value=str(old_qty), new_value=str(inventory.quantity),
            )

        if not items:
            Cart.objects.filter(user=user).delete()

        return order


class OrderItem(models.Model):
    """
    订单项模型
    """
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='订单'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='order_items',
        verbose_name='商品'
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='商品单价')
    quantity = models.PositiveIntegerField(default=1, verbose_name='购买数量')

    class Meta:
        db_table = 'order_items'
        verbose_name = '订单项'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'{self.order.order_no} - {self.product.name}'

    @property
    def total_price(self):
        """计算该项总价"""
        return self.price * self.quantity


class RefundQuerySet(models.QuerySet):
    def visible_to(self, user):
        """用户可见的退款：买家自己的 + 卖家店铺的"""
        from products.models import Shop
        q = models.Q(user=user)
        shop_ids = Shop.objects.filter(user=user).values_list('shop_id', flat=True)
        if shop_ids:
            q |= models.Q(order__items__product__shop_id__in=shop_ids)
        return self.filter(q).distinct()


class Refund(models.Model):
    """
    退款模型
    """
    objects = RefundQuerySet.as_manager()

    refund_no = models.CharField(max_length=32, unique=True, verbose_name='退款单号')
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='refunds',
        verbose_name='关联订单'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='refunds',
        verbose_name='申请人'
    )
    reason = models.TextField(verbose_name='Refund reason')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='退款金额')
    status = models.CharField(max_length=20, choices=RefundStatus.CHOICES,
                              default=RefundStatus.PENDING, verbose_name='退款状态')
    admin_remark = models.TextField(blank=True, null=True, verbose_name='管理员备注')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='申请时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'refunds'
        verbose_name = '退款'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status'], name='idx_refund_status'),
            models.Index(fields=['created_at'], name='idx_refund_created'),
        ]

    def __str__(self):
        return f'退款单 {self.refund_no}'

    def save(self, *args, **kwargs):
        if not self.refund_no:
            import uuid
            import time
            self.refund_no = f'REF{time.strftime("%Y%m%d%H%M%S")}{uuid.uuid4().hex[:8].upper()}'
        super().save(*args, **kwargs)

    def approve(self, remark='', processed_by=None):
        self.status = RefundStatus.APPROVED
        self.admin_remark = remark
        self.save()

        self.order.status = OrderStatus.REFUNDED
        self.order.save()

        for refund_item in self.items.all():
            product = refund_item.order_item.product
            inventory = Inventory.objects.select_for_update().get(product=product)
            old_qty = inventory.quantity
            inventory.quantity += refund_item.quantity
            inventory.save()
            create_inventory_transaction(
                product,
                InventoryChangeType.RETURN_RESTOCK,
                refund_item.quantity,
                order=self.order,
                refund=self,
            )

        from admin_api.models import write_audit
        write_audit(
            user=processed_by,
            action='Refund Approved',
            table_name='refunds',
            record_id=self.refund_no,
            description=f'Refund #{self.refund_no} approved, order {self.order.order_no} → refunded, ¥{float(self.total_amount):.2f}',
            old_value='pending',
            new_value='approved',
        )

    def reject(self, remark='', processed_by=None):
        """拒绝退款"""
        self.status = RefundStatus.REJECTED
        self.admin_remark = remark
        self.save()

        from admin_api.models import write_audit
        write_audit(
            user=processed_by,
            action='Refund Rejected',
            table_name='refunds',
            record_id=self.refund_no,
            description=f'Refund #{self.refund_no} rejected ({remark}), order {self.order.order_no}',
            old_value='pending',
            new_value='rejected',
        )

    def can_be_processed_by(self, user):
        """检查用户是否有权处理此退款（管理员或订单商品的店铺卖家）"""
        if user.is_staff:
            return True
        from products.models import Shop
        shop_ids = self.order.items.values_list('product__shop_id', flat=True)
        return Shop.objects.filter(shop_id__in=shop_ids, user=user).exists()

    def cancel(self, user):
        """Cancel a pending refund request owned by the current customer."""
        if self.user_id != user.id:
            raise PermissionError('You can only cancel your own refund request.')
        if self.status != RefundStatus.PENDING:
            raise ValueError('Only pending refunds can be cancelled.')
        self.status = RefundStatus.REJECTED
        self.admin_remark = 'Refund cancelled by customer'
        self.save()


class RefundItem(models.Model):
    """
    退款项模型
    """
    refund = models.ForeignKey(
        Refund,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='退款单'
    )
    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.CASCADE,
        related_name='refund_items',
        verbose_name='订单项'
    )
    quantity = models.PositiveIntegerField(default=1, verbose_name='退款数量')
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='退款金额')

    class Meta:
        db_table = 'refund_items'
        verbose_name = '退款项'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'{self.refund.refund_no} - {self.order_item.product.name}'
