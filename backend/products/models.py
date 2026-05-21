from django.db import models
from django.db.models import Count, OuterRef, Q, Subquery, Sum, Avg, IntegerField
from django.db.models.functions import Coalesce
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator

User = get_user_model()


class Category(models.Model):
    """
    商品分类模型
    支持二级分类（父分类 -> 子分类）
    """
    name = models.CharField(max_length=100, verbose_name='分类名称')
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='父分类'
    )
    slug = models.SlugField(max_length=100, unique=True, verbose_name='URL别名')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'categories'
        verbose_name = '商品分类'
        verbose_name_plural = verbose_name
        ordering = ['name']

    def get_family_ids(self):
        """返回自身及所有子分类的 ID。二级分类只返回自己。"""
        ids = [self.id]
        if self.parent is None:
            ids.extend(
                Category.objects.filter(parent=self).values_list('id', flat=True)
            )
        return ids

    def __str__(self):
        return self.name


class ShopStatus:
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    DISABLED = 'disabled'

    CHOICES = [
        (PENDING, '待审核'),
        (APPROVED, '已通过'),
        (REJECTED, '已拒绝'),
        (DISABLED, '已禁用'),
    ]


class Shop(models.Model):
    """
    店铺模型
    """
    shop_id = models.AutoField(primary_key=True, verbose_name='店铺ID')
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='shops',
        verbose_name='店铺拥有者'
    )
    shop_name = models.CharField(max_length=100, verbose_name='店铺名称')
    description = models.TextField(blank=True, null=True, verbose_name='店铺简介')
    status = models.CharField(
        max_length=20,
        choices=ShopStatus.CHOICES,
        default=ShopStatus.APPROVED,
        verbose_name='店铺状态'
    )
    rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=5.00,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        verbose_name='店铺评分'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'shops'
        verbose_name = '店铺'
        verbose_name_plural = verbose_name

    def is_editable_by(self, user):
        return user.is_staff or self.user_id == user.id

    def __str__(self):
        return self.shop_name


class ProductQuerySet(models.QuerySet):
    def with_sales_data(self):
        from orders.models import OrderItem
        sold_sq = OrderItem.objects.filter(
            product=OuterRef('pk')
        ).exclude(
            order__status__in=['cancelled', 'pending']
        ).values('product').annotate(s=Sum('quantity')).values('s')
        return self.annotate(
            _review_count=Count('reviews', distinct=True),
            _average_rating=Coalesce(Avg('reviews__rating'), None),
            _good_count=Count('reviews', distinct=True, filter=Q(reviews__rating__gte=4)),
            _sold_count=Coalesce(Subquery(sold_sq, output_field=IntegerField()), 0),
        )


class Product(models.Model):
    """
    商品模型
    """
    objects = ProductQuerySet.as_manager()

    name = models.CharField(max_length=200, verbose_name='商品名称')
    description = models.TextField(blank=True, null=True, verbose_name='商品描述')
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='价格')
    image = models.URLField(blank=True, null=True, verbose_name='商品图片')
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
        verbose_name='分类'
    )
    seller = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='products',
        verbose_name='卖家'
    )
    shop = models.ForeignKey(
        Shop,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
        verbose_name='所属店铺'
    )
    is_active = models.BooleanField(default=True, verbose_name='是否上架')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    @property
    def stock(self):
        """从 Inventory 表读取库存"""
        try:
            return self.inventory.quantity
        except Inventory.DoesNotExist:
            return 0

    class Meta:
        db_table = 'products'
        verbose_name = '商品'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['price'], name='idx_product_price'),
            models.Index(fields=['category', 'is_active'], name='idx_product_cat_active'),
        ]

    def is_editable_by(self, user):
        return user.is_staff or self.seller_id == user.id

    def __str__(self):
        return self.name


class Inventory(models.Model):
    """
    商品库存模型 — 唯一库存数据源
    """
    inventory_id = models.AutoField(primary_key=True, verbose_name='库存ID')
    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name='inventory',
        verbose_name='商品'
    )
    quantity = models.PositiveIntegerField(default=0, verbose_name='库存数量')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'inventory'
        verbose_name = '商品库存'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'{self.product.name} 库存: {self.quantity}'

    def can_be_managed_by(self, user):
        return user.is_staff or self.product.seller_id == user.id

    def restock(self, quantity):
        if quantity <= 0:
            raise ValueError('补货数量必须大于0')
        self.quantity += quantity
        self.save()
        InventoryTransaction.objects.create(
            inventory=self,
            change_type=InventoryChangeType.RESTOCK,
            quantity_change=quantity,
        )

    @classmethod
    def restock_with_lock(cls, product_id, quantity):
        """补货 + select_for_update 行锁，防止并发丢失更新"""
        from django.db import transaction
        with transaction.atomic():
            inv = cls.objects.select_for_update().get(product_id=product_id)
            old_qty = inv.quantity
            inv.quantity += quantity
            inv.save()
            InventoryTransaction.objects.create(
                inventory=inv,
                change_type=InventoryChangeType.RESTOCK,
                quantity_change=quantity,
            )
            from admin_api.models import write_audit
            write_audit(
                user=None,
                action='Inventory Restocked',
                table_name='inventory',
                record_id=str(inv.inventory_id),
                description=f'{inv.product.name} stock +{quantity} ({old_qty} → {inv.quantity})',
                old_value=str(old_qty),
                new_value=str(inv.quantity),
            )
            return inv


class InventoryChangeType:
    RESTOCK = 'RESTOCK'
    ORDER_DEDUCT = 'ORDER_DEDUCT'
    ADJUSTMENT = 'ADJUSTMENT'
    REFUND_REQUESTED = 'REFUND_REQUESTED'
    REFUND_APPROVED = 'REFUND_APPROVED'
    RETURN_RESTOCK = 'RETURN_RESTOCK'

    CHOICES = [
        (RESTOCK, 'RESTOCK'),
        (ORDER_DEDUCT, 'ORDER_DEDUCT'),
        (ADJUSTMENT, 'ADJUSTMENT'),
        (REFUND_REQUESTED, 'REFUND_REQUESTED'),
        (REFUND_APPROVED, 'REFUND_APPROVED'),
        (RETURN_RESTOCK, 'RETURN_RESTOCK'),
    ]


class InventoryTransaction(models.Model):
    """
    Inventory change ledger. The Inventory table remains unchanged; every stock
    movement writes one row here for traceability.
    """
    transaction_id = models.AutoField(primary_key=True)
    inventory = models.ForeignKey(
        Inventory,
        on_delete=models.CASCADE,
        related_name='transactions',
    )
    change_type = models.CharField(max_length=32, choices=InventoryChangeType.CHOICES)
    quantity_change = models.IntegerField()
    related_order = models.ForeignKey(
        'orders.Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventory_transactions',
    )
    related_refund = models.ForeignKey(
        'orders.Refund',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventory_transactions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['change_type', 'created_at'], name='idx_inv_txn_type_time'),
        ]

    def __str__(self):
        return f'{self.transaction_id} {self.change_type} {self.quantity_change}'


class ShopFollow(models.Model):
    """店铺关注模型"""
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='followed_shops',
        verbose_name='用户'
    )
    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name='followers',
        verbose_name='店铺'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='关注时间')

    class Meta:
        db_table = 'shop_follows'
        verbose_name = '店铺关注'
        verbose_name_plural = verbose_name
        unique_together = ['user', 'shop']
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} follows {self.shop.shop_name}'


class ReviewStatus:
    VISIBLE = 'visible'
    HIDDEN = 'hidden'
    DELETED = 'deleted'
    REPORTED = 'reported'

    CHOICES = [
        (VISIBLE, '可见'),
        (HIDDEN, '隐藏'),
        (DELETED, '已删除'),
        (REPORTED, '被举报'),
    ]


class Review(models.Model):
    """
    商品评论模型
    """
    review_id = models.AutoField(primary_key=True, verbose_name='评论ID')
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='reviews',
        verbose_name='商品'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='reviews',
        verbose_name='用户'
    )
    order_item = models.ForeignKey(
        'orders.OrderItem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='review',
        verbose_name='对应订单项'
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name='评分'
    )
    comment = models.TextField(blank=True, null=True, verbose_name='评论内容')
    status = models.CharField(
        max_length=20,
        choices=ReviewStatus.CHOICES,
        default=ReviewStatus.HIDDEN,
        verbose_name='审核状态'
    )
    like_count = models.PositiveIntegerField(default=0, verbose_name='点赞数量')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='评论时间')

    class Meta:
        db_table = 'reviews'
        verbose_name = '商品评论'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status'], name='idx_review_status'),
            models.Index(fields=['created_at'], name='idx_review_created'),
        ]
        # 每个订单项只能评论一次

    def __str__(self):
        return f'{self.user.username} 评论 {self.product.name} ({self.rating}星)'
