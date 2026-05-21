from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Cart, Order, Refund, OrderStatus
from .serializers import (
    CartSerializer,
    CartAddSerializer,
    CartUpdateSerializer,
    DirectOrderCreateSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    OrderStatusUpdateSerializer,
    RefundCreateSerializer,
    RefundProcessSerializer,
    RefundSerializer,
)


class CartListView(generics.ListAPIView):
    serializer_class = CartSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Cart.objects.filter(user=self.request.user).select_related('product')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        total = sum(item.total_price for item in queryset)
        return Response({
            'code': 0,
            'msg': 'success',
            'data': {
                'items': serializer.data,
                'total_count': queryset.count(),
                'total_price': str(total),
            },
        })


class CartAddView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CartAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product_id = serializer.validated_data['product_id']
        quantity = serializer.validated_data['quantity']

        from products.models import Product, Inventory
        product = Product.objects.get(id=product_id)
        inventory, _ = Inventory.objects.get_or_create(product=product, defaults={'quantity': 0})
        cart_item, created = Cart.objects.get_or_create(
            user=request.user,
            product_id=product_id,
            defaults={'quantity': quantity},
        )
        if not created:
            if cart_item.quantity + quantity > inventory.quantity:
                return Response({
                    'code': 1,
                    'msg': f'Only {inventory.quantity} item(s) are available.',
                }, status=status.HTTP_400_BAD_REQUEST)
            cart_item.quantity += quantity
            cart_item.save()

        return Response({
            'code': 0,
            'msg': 'added' if created else 'quantity updated',
            'data': CartSerializer(cart_item).data,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class CartUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        serializer = CartUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            cart_item = Cart.objects.get(pk=pk, user=request.user)
        except Cart.DoesNotExist:
            return Response({'code': 1, 'msg': 'cart item not found'}, status=status.HTTP_404_NOT_FOUND)

        quantity = serializer.validated_data['quantity']
        inventory, _ = Inventory.objects.get_or_create(product=cart_item.product, defaults={'quantity': 0})
        if quantity > inventory.quantity:
            return Response({
                'code': 1,
                'msg': f'Only {inventory.quantity} item(s) are available.',
            }, status=status.HTTP_400_BAD_REQUEST)

        cart_item.quantity = quantity
        cart_item.save()
        return Response({'code': 0, 'msg': 'success', 'data': CartSerializer(cart_item).data})


class CartDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        Cart.objects.filter(pk=pk, user=request.user).delete()
        return Response({'code': 0, 'msg': 'deleted'})


class CartClearView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request):
        Cart.objects.filter(user=request.user).delete()
        return Response({'code': 0, 'msg': 'cart cleared'})


class OrderListView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.visible_to(self.request.user).prefetch_related('items__product', 'refunds')

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response({'code': 0, 'msg': 'success', 'data': serializer.data})


class OrderDetailView(generics.RetrieveAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.visible_to(self.request.user).prefetch_related('items__product', 'refunds')

    def retrieve(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object())
        return Response({'code': 0, 'msg': 'success', 'data': serializer.data})


class OrderCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data, context={'request': request})
        try:
            serializer.is_valid(raise_exception=True)
            order = serializer.save()
        except serializers.ValidationError as exc:
            return Response({'code': 1, 'msg': exc.detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'code': 0,
            'msg': 'order created',
            'data': OrderSerializer(order).data,
        }, status=status.HTTP_201_CREATED)


class DirectOrderCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = DirectOrderCreateSerializer(data=request.data, context={'request': request})
        try:
            serializer.is_valid(raise_exception=True)
            order = serializer.save()
        except serializers.ValidationError as exc:
            return Response({'code': 1, 'msg': exc.detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'code': 0,
            'msg': 'order created',
            'data': OrderSerializer(order).data,
        }, status=status.HTTP_201_CREATED)


class OrderStatusUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        serializer = OrderStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data['status']

        try:
            order = Order.objects.get(pk=pk)
        except Order.DoesNotExist:
            return Response({'code': 1, 'msg': 'order not found'}, status=status.HTTP_404_NOT_FOUND)

        ok, msg = order.can_transition_to(new_status, request.user)
        if not ok:
            return Response({'code': 1, 'msg': msg}, status=status.HTTP_403_FORBIDDEN)

        order.status = new_status
        order.save()
        return Response({'code': 0, 'msg': 'success', 'data': OrderSerializer(order).data})


class OrderDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        updated = Order.objects.filter(pk=pk, user=request.user).update(buyer_deleted=True)
        if not updated:
            return Response({'code': 1, 'msg': 'order not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'code': 0, 'msg': 'deleted'})


class RefundListView(generics.ListAPIView):
    serializer_class = RefundSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Refund.objects.visible_to(self.request.user).select_related('order', 'user').prefetch_related('items__order_item__product')

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response({'code': 0, 'msg': 'success', 'data': serializer.data})


class RefundDetailView(generics.RetrieveAPIView):
    serializer_class = RefundSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Refund.objects.visible_to(self.request.user).select_related('order', 'user').prefetch_related('items__order_item__product')


class RefundCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = RefundCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        refund = serializer.save()
        return Response({'code': 0, 'msg': 'refund created', 'data': RefundSerializer(refund).data})


class RefundCancelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        try:
            refund = Refund.objects.get(pk=pk, user=request.user)
        except Refund.DoesNotExist:
            return Response({'code': 1, 'msg': 'refund not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            refund.cancel(request.user)
        except (PermissionError, ValueError) as e:
            return Response({'code': 1, 'msg': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'code': 0, 'msg': 'refund cancelled', 'data': RefundSerializer(refund).data})


class RefundProcessView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        try:
            refund = Refund.objects.select_related('order').get(pk=pk)
        except Refund.DoesNotExist:
            return Response({'code': 1, 'msg': 'refund not found'}, status=status.HTTP_404_NOT_FOUND)

        if not refund.can_be_processed_by(request.user):
            return Response({'code': 1, 'msg': '无权处理该退款'}, status=status.HTTP_403_FORBIDDEN)

        serializer = RefundProcessSerializer(refund, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        refund = serializer.save()
        return Response({'code': 0, 'msg': 'success', 'data': RefundSerializer(refund).data})
