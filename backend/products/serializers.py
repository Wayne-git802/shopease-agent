from django.db.models import Sum, Avg
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Category, Product, Shop, Inventory, InventoryTransaction, Review
from .image_utils import product_image_url

User = get_user_model()


class CategorySerializer(serializers.ModelSerializer):
    """
    分类序列化器
    """
    parent_name = serializers.CharField(source='parent.name', read_only=True)
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ('id', 'name', 'parent', 'parent_name', 'slug', 'is_active', 'children', 'created_at')
        read_only_fields = ('id', 'created_at')

    def validate_parent(self, value):
        if value and value.parent is not None:
            raise serializers.ValidationError('只能创建二级分类，所选父分类已是子分类')
        return value

    def get_children(self, obj):
        children = obj.children.all()
        return CategorySimpleSerializer(children, many=True).data


class CategorySimpleSerializer(serializers.ModelSerializer):
    """
    简单分类序列化器（用于嵌套显示）
    """
    class Meta:
        model = Category
        fields = ('id', 'name', 'parent', 'slug', 'is_active')


class UserSimpleSerializer(serializers.ModelSerializer):
    """
    简单用户序列化器（用于嵌套显示卖家信息）
    """
    class Meta:
        model = User
        fields = ('id', 'username')


# ======================== Shop ========================

class ShopSerializer(serializers.ModelSerializer):
    """
    店铺序列化器
    """
    owner_username = serializers.CharField(source='user.username', read_only=True)
    product_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Shop
        fields = ('shop_id', 'user', 'owner_username', 'shop_name', 'description', 'status', 'rating', 'product_count', 'created_at')
        read_only_fields = ('shop_id', 'user', 'rating', 'created_at', 'status', 'product_count')

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class ShopSimpleSerializer(serializers.ModelSerializer):
    """
    简单店铺序列化器（用于嵌套）
    """
    class Meta:
        model = Shop
        fields = ('shop_id', 'shop_name', 'status', 'rating')


# ======================== Inventory ========================

class InventorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Inventory
        fields = ('inventory_id', 'product', 'quantity', 'updated_at')
        read_only_fields = ('inventory_id', 'updated_at')


class InventoryTransactionSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(source='inventory.product_id', read_only=True)
    product_name = serializers.CharField(source='inventory.product.name', read_only=True)
    store_id = serializers.IntegerField(source='inventory.product.shop_id', read_only=True)
    store_name = serializers.CharField(source='inventory.product.shop.shop_name', read_only=True)
    related_order_id = serializers.IntegerField(read_only=True)
    related_refund_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = InventoryTransaction
        fields = (
            'transaction_id',
            'inventory',
            'product_id',
            'product_name',
            'store_id',
            'store_name',
            'change_type',
            'quantity_change',
            'related_order_id',
            'related_refund_id',
            'created_at',
        )
        read_only_fields = ('transaction_id', 'created_at')


# ======================== Review ========================

class ReviewSerializer(serializers.ModelSerializer):
    """
    评论序列化器
    """
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = Review
        fields = ('review_id', 'product', 'user', 'username', 'order_item',
                  'rating', 'comment', 'status', 'like_count', 'created_at')
        read_only_fields = ('review_id', 'user', 'like_count', 'created_at', 'status')

    def validate_order_item_id(self, value):
        if value and Review.objects.filter(
            user=self.context['request'].user, order_item_id=value
        ).exists():
            raise serializers.ValidationError('该订单项已评价过')
        return value

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


# ======================== Product ========================

class ProductSerializer(serializers.ModelSerializer):
    """
    商品序列化器（列表/详情）
    """
    category_name = serializers.SerializerMethodField()
    seller_name = serializers.CharField(source='seller.username', read_only=True)
    shop_name = serializers.CharField(source='shop.shop_name', read_only=True)
    image = serializers.SerializerMethodField()
    sold_count = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()
    good_rate = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            'id', 'name', 'description', 'price', 'stock', 'image',
            'category', 'category_name', 'seller', 'seller_name',
            'shop', 'shop_name', 'is_active', 'sold_count',
            'review_count', 'average_rating', 'good_rate',
            'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'seller', 'created_at', 'updated_at')

    def get_image(self, obj):
        return product_image_url(obj)

    def get_category_name(self, obj):
        request = self.context.get('request')
        params = getattr(request, 'query_params', getattr(request, 'GET', {})) if request else {}
        selected_id = params.get('category') if params else None
        if selected_id and str(selected_id).isdigit():
            try:
                selected = Category.objects.get(pk=int(selected_id))
                if obj.category_id in selected.get_family_ids():
                    return selected.name
            except Category.DoesNotExist:
                pass
        return obj.category.name if obj.category else None

    def get_sold_count(self, obj):
        from orders.models import OrderItem
        if hasattr(obj, '_sold_count'):
            return obj._sold_count or 0
        return OrderItem.objects.filter(
            product=obj
        ).exclude(
            order__status__in=['cancelled', 'pending']
        ).aggregate(s=Sum('quantity'))['s'] or 0

    def get_review_count(self, obj):
        if hasattr(obj, '_review_count'):
            return obj._review_count or 0
        return Review.objects.filter(product=obj).count()

    def get_average_rating(self, obj):
        if hasattr(obj, '_average_rating'):
            val = obj._average_rating
            return round(val, 1) if val else None
        avg = Review.objects.filter(product=obj).aggregate(a=Avg('rating'))['a']
        return round(avg, 1) if avg else None

    def get_good_rate(self, obj):
        total = self.get_review_count(obj)
        if total == 0:
            return None
        if hasattr(obj, '_good_count'):
            return round(obj._good_count / total * 100, 1)
        good = Review.objects.filter(product=obj, rating__gte=4).count()
        return round(good / total * 100, 1)


class ProductCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = (
            'name', 'description', 'price', 'image',
            'category', 'shop', 'is_active'
        )

    def create(self, validated_data):
        validated_data['seller'] = self.context['request'].user
        product = super().create(validated_data)
        Inventory.objects.get_or_create(product=product, defaults={'quantity': 0})
        return product

