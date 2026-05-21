from django.db.models import Count
from rest_framework import viewsets, generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated

from .models import Category, Inventory, InventoryChangeType, InventoryTransaction, Product, Review, Shop, ShopFollow
from .serializers import (
    CategorySerializer,
    InventorySerializer,
    ProductSerializer,
    ProductCreateSerializer,
    InventoryTransactionSerializer,
    ReviewSerializer,
    ShopSerializer,
)


class CategoryViewSet(viewsets.ModelViewSet):
    """
    分类管理接口
    GET /api/products/categories/ - 获取分类列表
    POST /api/products/categories/ - 创建分类
    GET /api/products/categories/{id}/ - 获取分类详情
    PUT /api/products/categories/{id}/ - 更新分类
    DELETE /api/products/categories/{id}/ - 删除分类
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    lookup_field = 'pk'

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return []
        return [IsAuthenticated()]

    def list(self, request, *args, **kwargs):
        # 只返回顶级分类（parent为空的）
        queryset = self.get_queryset().filter(parent__isnull=True)
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'code': 0,
            'msg': '获取成功',
            'data': serializer.data
        })

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({
            'code': 0,
            'msg': '获取成功',
            'data': serializer.data
        })

    def create(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return Response({'code': 1, 'msg': '只有管理员可以创建分类'}, status=status.HTTP_403_FORBIDDEN)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response({
            'code': 0,
            'msg': '创建成功',
            'data': serializer.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return Response({'code': 1, 'msg': 'Only admins can update categories.'}, status=status.HTTP_403_FORBIDDEN)
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response({
            'code': 0,
            'msg': 'updated',
            'data': serializer.data
        })

    def destroy(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return Response({'code': 1, 'msg': 'Only admins can delete categories.'}, status=status.HTTP_403_FORBIDDEN)
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({
            'code': 0,
            'msg': 'deleted'
        })


class ProductViewSet(viewsets.ModelViewSet):
    """
    商品管理接口
    GET /api/products/ - 获取商品列表
    POST /api/products/ - 发布商品（需登录）
    """
    queryset = Product.objects.all()
    lookup_field = 'pk'

    def get_serializer_class(self):
        if self.action == 'create':
            return ProductCreateSerializer
        return ProductSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return []
        else:
            return [IsAuthenticated()]

    def get_queryset(self):
        queryset = super().get_queryset().with_sales_data()

        if self.action in ('list', 'retrieve'):
            queryset = queryset.filter(is_active=True)

        # 分类筛选（一级分类自动包含子分类）
        category_id = self.request.query_params.get('category')
        if category_id:
            try:
                cat = Category.objects.get(pk=category_id)
                queryset = queryset.filter(category_id__in=cat.get_family_ids())
            except Category.DoesNotExist:
                pass
        # 关键词搜索 — MySQL FULLTEXT 索引加速
        keyword = self.request.query_params.get('search')
        if keyword:
            queryset = queryset.extra(
                where=['MATCH(name) AGAINST (%s IN BOOLEAN MODE)'],
                params=[keyword],
            )
        # 店铺筛选（支持逗号分隔多个店铺ID）
        shop_ids = self.request.query_params.get('shop')
        if shop_ids:
            ids = [int(x) for x in shop_ids.split(',') if x.strip().isdigit()]
            if ids:
                queryset = queryset.filter(shop_id__in=ids)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated = self.get_paginated_response(serializer.data)
            return Response({
                'code': 0,
                'msg': '获取成功',
                'data': serializer.data,
                'count': paginated.data['count'],
                'next': paginated.data.get('next'),
                'previous': paginated.data.get('previous'),
            })

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'code': 0,
            'msg': '获取成功',
            'data': serializer.data
        })

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({
            'code': 0,
            'msg': '获取成功',
            'data': serializer.data
        })

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        return Response({
            'code': 0,
            'msg': '商品发布成功',
            'data': ProductSerializer(product).data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        if not instance.is_editable_by(request.user):
            return Response({
                'code': 1,
                'msg': '只能编辑自己的商品'
            }, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response({
            'code': 0,
            'msg': '更新成功',
            'data': ProductSerializer(instance).data
        })

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # 检查是否为卖家本人
        if not instance.is_editable_by(request.user):
            return Response({
                'code': 1,
                'msg': 'You can only delete your own products.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        self.perform_destroy(instance)
        return Response({
            'code': 0,
            'msg': 'deleted'
        })


class ReviewCreateView(APIView):
    """提交商品评价"""
    permission_classes = [IsAuthenticated]

    def post(self, request, product_id):
        try:
            Product.objects.get(pk=product_id, is_active=True)
        except Product.DoesNotExist:
            return Response({'code': 1, 'msg': '商品不存在'}, status=status.HTTP_404_NOT_FOUND)

        data = {
            'product': product_id,
            'rating': request.data.get('rating'),
            'comment': request.data.get('comment', ''),
            'order_item_id': request.data.get('order_item_id') or None,
        }
        serializer = ReviewSerializer(data=data, context={'request': request})
        if not serializer.is_valid():
            return Response({'code': 1, 'msg': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        review = serializer.save()
        return Response({
            'code': 0,
            'msg': '评价成功',
            'data': ReviewSerializer(review).data
        }, status=status.HTTP_201_CREATED)


class InventoryTransactionListView(APIView):
    """Inventory transaction table scoped to the logged-in seller's store."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = min(int(request.query_params.get('limit', 500)), 2000)
        queryset = InventoryTransaction.objects.select_related(
            'inventory__product__shop',
            'related_order',
            'related_refund',
        )
        if not (request.user.is_staff or request.user.is_superuser):
            queryset = queryset.filter(inventory__product__shop__user=request.user)
        queryset = queryset.order_by('-created_at')[:limit]
        serializer = InventoryTransactionSerializer(queryset, many=True)
        return Response({
            'code': 0,
            'msg': 'success',
            'data': serializer.data
        })


class ShopFollowView(APIView):
    """Follow / Unfollow shop"""
    permission_classes = []

    def post(self, request, pk):
        from rest_framework_simplejwt.authentication import JWTAuthentication
        try:
            auth = JWTAuthentication().authenticate(request)
            user = auth[0] if auth else None
        except Exception:
            user = None

        if not user or not user.is_authenticated:
            return Response({
                'code': 1,
                'msg': 'Please login first'
            }, status=status.HTTP_401_UNAUTHORIZED)

        try:
            shop = Shop.objects.get(pk=pk)
        except Shop.DoesNotExist:
            return Response({
                'code': 1,
                'msg': 'Shop not found'
            }, status=status.HTTP_404_NOT_FOUND)

        follow, created = ShopFollow.objects.get_or_create(user=user, shop=shop)
        if not created:
            follow.delete()
            return Response({
                'code': 0,
                'msg': 'Unfollowed successfully',
                'data': {'is_followed': False}
            })

        return Response({
            'code': 0,
            'msg': 'Followed successfully',
            'data': {'is_followed': True}
        }, status=status.HTTP_201_CREATED)


class ShopListView(APIView):
    """店铺列表 / 创建店铺"""
    permission_classes = []

    def get(self, request):
        shops = Shop.objects.annotate(product_count=Count('products')).all().select_related('user')
        serializer = ShopSerializer(shops, many=True)
        return Response({
            'code': 0,
            'msg': '获取成功',
            'data': serializer.data,
        })

    def post(self, request):
        if not request.user.is_authenticated:
            return Response({'code': 1, 'msg': '请先登录'}, status=status.HTTP_401_UNAUTHORIZED)

        serializer = ShopSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        shop = serializer.save()
        return Response({
            'code': 0,
            'msg': '店铺创建成功',
            'data': ShopSerializer(shop).data,
        }, status=status.HTTP_201_CREATED)


class ShopDetailView(APIView):
    """店铺详情 / 更新店铺"""
    permission_classes = []

    def get(self, request, pk):
        try:
            shop = Shop.objects.annotate(product_count=Count('products')).select_related('user').get(pk=pk)
        except Shop.DoesNotExist:
            return Response({'code': 1, 'msg': '店铺不存在'}, status=status.HTTP_404_NOT_FOUND)

        serializer = ShopSerializer(shop)
        return Response({
            'code': 0,
            'msg': '获取成功',
            'data': serializer.data,
        })

    def put(self, request, pk):
        if not request.user.is_authenticated:
            return Response({'code': 1, 'msg': '请先登录'}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            shop = Shop.objects.get(pk=pk)
        except Shop.DoesNotExist:
            return Response({'code': 1, 'msg': '店铺不存在'}, status=status.HTTP_404_NOT_FOUND)

        if not shop.is_editable_by(request.user):
            return Response({'code': 1, 'msg': '只能编辑自己的店铺'}, status=status.HTTP_403_FORBIDDEN)

        serializer = ShopSerializer(shop, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        shop = serializer.save()
        return Response({
            'code': 0,
            'msg': '更新成功',
            'data': ShopSerializer(shop).data,
        })


class InventoryListView(APIView):
    """卖家查看自己商品的库存"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        inventories = Inventory.objects.filter(
            product__seller=request.user
        ).select_related('product')
        serializer = InventorySerializer(inventories, many=True)
        return Response({
            'code': 0,
            'msg': '获取成功',
            'data': serializer.data,
        })


class InventoryRestockView(APIView):
    """卖家补货 — select_for_update 防止并发补货丢失更新"""
    permission_classes = [IsAuthenticated]

    def post(self, request, product_id):
        try:
            inventory = Inventory.objects.select_related('product').get(product_id=product_id)
        except Inventory.DoesNotExist:
            return Response({'code': 1, 'msg': '库存记录不存在'}, status=status.HTTP_404_NOT_FOUND)

        if not inventory.can_be_managed_by(request.user):
            return Response({'code': 1, 'msg': '只能补货自己的商品'}, status=status.HTTP_403_FORBIDDEN)

        try:
            quantity = int(request.data.get('quantity', 0))
            inventory = Inventory.restock_with_lock(product_id, quantity)
        except (TypeError, ValueError) as e:
            return Response({'code': 1, 'msg': str(e) or 'Quantity must be an integer'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'code': 0,
            'msg': 'Restock successful',
            'data': InventorySerializer(inventory).data,
        })


class ReviewListView(APIView):
    """获取商品评论列表（仅已审核通过的）"""
    permission_classes = []

    def get(self, request, product_id):
        reviews = Review.objects.filter(
            product_id=product_id, status='visible'
        ).select_related('user').order_by('-created_at')
        serializer = ReviewSerializer(reviews, many=True)
        return Response({
            'code': 0,
            'msg': '获取成功',
            'data': serializer.data,
        })
