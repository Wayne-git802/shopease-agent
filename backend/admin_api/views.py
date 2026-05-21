import json
from datetime import datetime, timedelta

from django.db import connection
from django.db.models import Count, Sum, Q, F, Avg
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import Order, OrderItem, Refund
from products.models import Category, Product, Shop, Inventory, Review, InventoryTransaction
from .models import AuditLog, write_audit
from .serializers import AuditLogSerializer, SQLDemoSerializer

User = get_user_model()


def check_admin(request):
    if not request.user.is_staff:
        return Response({'code': 1, 'msg': 'Admin permission required'}, status=status.HTTP_403_FORBIDDEN)
    return None


# ── Dashboard Stats ──────────────────────────────────────────

class AdminStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if (err := check_admin(request)):
            return err

        total_users = User.objects.count()
        total_sellers = User.objects.filter(shops__isnull=False).distinct().count()
        total_shops = Shop.objects.count()
        total_products = Product.objects.count()
        total_orders = Order.objects.count()
        total_revenue = Order.objects.aggregate(s=Sum('total_amount'))['s'] or 0
        total_categories = Category.objects.count()
        total_reviews = Review.objects.count()

        refund_count = Order.objects.filter(status='refunded').count()
        refund_rate = round(refund_count / total_orders * 100, 1) if total_orders else 0

        low_stock = Inventory.objects.filter(quantity__lt=10).count()

        # Top 5 selling products (raw SQL)
        with connection.cursor() as c:
            c.execute('''
                SELECT p.name, SUM(oi.quantity) AS sold
                FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                JOIN products p ON p.id = oi.product_id
                WHERE o.status NOT IN ('cancelled', 'refunded')
                GROUP BY p.id
                ORDER BY sold DESC
                LIMIT 5
            ''')
            top_products = [{'name': row[0], 'sold': row[1]} for row in c.fetchall()]

        # Monthly revenue (raw SQL)
        with connection.cursor() as c:
            c.execute('''
                SELECT DATE_FORMAT(created_at, '%Y-%m') AS month,
                       SUM(total_amount) AS revenue
                FROM orders
                WHERE status NOT IN ('cancelled', 'refunded')
                GROUP BY month
                ORDER BY month DESC
                LIMIT 6
            ''')
            monthly = [{'month': row[0], 'revenue': float(row[1])} for row in c.fetchall()]

        return Response({
            'code': 0,
            'data': {
                'total_users': total_users,
                'total_sellers': total_sellers,
                'total_shops': total_shops,
                'total_products': total_products,
                'total_orders': total_orders,
                'total_revenue': float(total_revenue),
                'total_categories': total_categories,
                'total_reviews': total_reviews,
                'refund_rate': refund_rate,
                'low_stock': low_stock,
                'top_products': top_products,
                'monthly_revenue': monthly,
            }
        })


# ── User Toggle (enable/disable) ──────────────────────────────

class AdminUserToggleView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, username):
        if (err := check_admin(request)):
            return err
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return Response({'code': 1, 'msg': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        user.is_active = not user.is_active
        user.save()
        new_status = 'active' if user.is_active else 'disabled'
        write_audit(request.user, 'User Toggled', 'users', username,
                    description=f'User {username} status changed to {new_status}',
                    old_value=str(not user.is_active),
                    new_value=str(user.is_active))
        return Response({'code': 0, 'data': {'username': username, 'status': new_status}})


# ── Shop Approval ────────────────────────────────────────────

class AdminShopApprovalView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, shop_id):
        if (err := check_admin(request)):
            return err
        try:
            shop = Shop.objects.get(shop_id=shop_id)
        except Shop.DoesNotExist:
            return Response({'code': 1, 'msg': 'Shop not found'}, status=status.HTTP_404_NOT_FOUND)

        status_val = request.data.get('status', 'approved')
        old_status = shop.status
        shop.status = status_val
        shop.save()
        write_audit(request.user, 'Shop Reviewed', 'shops', str(shop_id),
                    description=f'Shop {shop.shop_name} status: {old_status} → {status_val}',
                    old_value=old_status,
                    new_value=status_val)
        return Response({'code': 0, 'msg': 'ok', 'data': {'shop_id': shop_id, 'status': status_val}})


# ── Product Moderation ───────────────────────────────────────

class AdminProductModerateView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, product_id):
        if (err := check_admin(request)):
            return err
        try:
            product = Product.objects.get(pk=product_id)
        except Product.DoesNotExist:
            return Response({'code': 1, 'msg': 'Product not found'}, status=status.HTTP_404_NOT_FOUND)

        status_val = request.data.get('status', 'approved')
        old_active = product.is_active
        if status_val == 'off_shelf':
            product.is_active = False
            product.save()
        elif status_val == 'approved':
            product.is_active = True
            product.save()
        write_audit(request.user, 'Product Reviewed', 'products', str(product_id),
                    description=f'Product {product.name} {"listed" if product.is_active else "delisted"}',
                    old_value=f'is_active={old_active}',
                    new_value=f'is_active={product.is_active}')
        return Response({'code': 0, 'msg': 'ok'})


# ── Review Moderation ────────────────────────────────────────

class AdminReviewListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if (err := check_admin(request)):
            return err

        status_filter = request.query_params.get('status', '')
        qs = Review.objects.select_related('user', 'product').order_by('-created_at')
        if status_filter:
            qs = qs.filter(status=status_filter)

        data = []
        for r in qs[:500]:
            data.append({
                'review_id': r.review_id,
                'product_id': r.product_id,
                'product_name': r.product.name,
                'username': r.user.username,
                'rating': r.rating,
                'comment': r.comment or '',
                'status': r.status,
                'like_count': r.like_count,
                'created_at': r.created_at.isoformat(),
            })

        return Response({'code': 0, 'data': data})


class AdminReviewModerateView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, review_id):
        if (err := check_admin(request)):
            return err
        try:
            review = Review.objects.get(review_id=review_id)
        except Review.DoesNotExist:
            return Response({'code': 1, 'msg': 'Review not found'}, status=status.HTTP_404_NOT_FOUND)

        status_val = request.data.get('status', 'visible')
        old_status = review.status
        review.status = status_val
        review.save()
        write_audit(request.user, 'Review Moderated', 'reviews', str(review_id),
                    description=f'Review #{review_id} status: {old_status} → {status_val}',
                    old_value=old_status,
                    new_value=status_val)
        return Response({'code': 0, 'msg': 'ok'})


# ── SQL Demo Queries ─────────────────────────────────────────

SQL_DEMOS = [
    {
        'title': '1. Sales Revenue by Category (Multi-table JOIN + GROUP BY + ORDER BY)',
        'description': 'Join categories -> products -> order_items -> orders, '
                       'aggregate revenue by category for completed orders, sorted descending.',
        'sql': '''SELECT c.name           AS category,
       COUNT(DISTINCT o.id) AS order_count,
       SUM(oi.price * oi.quantity) AS revenue
FROM categories c
JOIN products p    ON p.category_id = c.id
JOIN order_items oi ON oi.product_id = p.id
JOIN orders o      ON o.id = oi.order_id
WHERE o.status NOT IN ('cancelled', 'refunded')
GROUP BY c.id
ORDER BY revenue DESC''',
    },
    {
        'title': '2. Top Spenders (JOIN + Aggregate SUM/COUNT)',
        'description': 'Total spending and order count per user, filtered to users who have placed orders.',
        'sql': '''SELECT u.username,
       COUNT(DISTINCT o.id) AS order_count,
       SUM(o.total_amount)  AS total_spent
FROM users u
JOIN orders o ON o.user_id = u.id
WHERE o.status NOT IN ('cancelled', 'refunded')
GROUP BY u.id
HAVING SUM(o.total_amount) > 0
ORDER BY total_spent DESC
LIMIT 10''',
    },
    {
        'title': '3. Low Stock Alert (Subquery + HAVING)',
        'description': 'Products with stock under 10 units, with their shop rating.',
        'sql': '''SELECT p.name           AS product,
       inv.quantity     AS remaining,
       s.shop_name      AS shop,
       s.rating         AS shop_rating
FROM products p
JOIN inventory inv ON inv.product_id = p.id
LEFT JOIN shops s ON s.shop_id = p.shop_id
WHERE inv.quantity < 10 AND p.is_active = 1
ORDER BY inv.quantity ASC''',
    },
    {
        'title': '4. Monthly Sales Trend (DATE_FORMAT + GROUP BY)',
        'description': 'Monthly sales aggregation using DATE_FORMAT, showing recent 6 months trend.',
        'sql': '''SELECT DATE_FORMAT(o.created_at, '%Y-%m') AS month,
       COUNT(DISTINCT o.id)       AS orders,
       SUM(o.total_amount)        AS revenue,
       ROUND(AVG(o.total_amount), 2) AS avg_order_value
FROM orders o
WHERE o.status NOT IN ('cancelled', 'refunded')
GROUP BY month
ORDER BY month DESC
LIMIT 6''',
    },
    {
        'title': '5. Seller Sales Summary (Multi-level JOIN + Aggregation)',
        'description': 'Sales volume and revenue per seller per shop.',
        'sql': '''SELECT u.display_name          AS seller,
       s.shop_name              AS shop,
       COUNT(DISTINCT o.id)     AS orders,
       SUM(oi.quantity)         AS items_sold,
       SUM(oi.price * oi.quantity) AS revenue
FROM users u
JOIN shops s       ON s.user_id = u.id
JOIN products p    ON p.shop_id = s.shop_id
JOIN order_items oi ON oi.product_id = p.id
JOIN orders o      ON o.id = oi.order_id
WHERE o.status NOT IN ('cancelled', 'refunded')
GROUP BY u.id, s.shop_id
ORDER BY revenue DESC''',
    },
    {
        'title': '6. Inventory Movement Audit (Transaction Log)',
        'description': 'Recent inventory transactions with change type and related order number.',
        'sql': '''SELECT it.transaction_id,
       p.name          AS product,
       it.change_type,
       it.quantity_change,
       COALESCE(o.order_no, '--') AS order_no,
       it.created_at
FROM inventory_transactions it
JOIN inventory i   ON i.inventory_id = it.inventory_id
JOIN products p    ON p.id = i.product_id
LEFT JOIN orders o ON o.id = it.related_order_id
ORDER BY it.created_at DESC
LIMIT 20''',
    },
]


class SQLDemoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if (err := check_admin(request)):
            return err

        results = []
        for demo in SQL_DEMOS:
            try:
                with connection.cursor() as c:
                    c.execute(demo['sql'])
                    columns = [col[0] for col in c.description] if c.description else []
                    rows = c.fetchall()
                    results.append({
                        'title': demo['title'],
                        'description': demo['description'],
                        'sql': demo['sql'].strip(),
                        'columns': columns,
                        'rows': [list(row) for row in rows],
                    })
            except Exception as e:
                results.append({
                    'title': demo['title'],
                    'description': demo['description'],
                    'sql': demo['sql'].strip(),
                    'columns': [],
                    'rows': [],
                    'error': str(e),
                })

        return Response({'code': 0, 'data': results})


# ── Audit Log ────────────────────────────────────────────────

class AuditLogListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if (err := check_admin(request)):
            return err
        logs = AuditLog.objects.select_related('user')[:200]
        return Response({
            'code': 0,
            'data': AuditLogSerializer(logs, many=True).data
        })

    def post(self, request):
        action = request.data.get('action', '')
        table_name = request.data.get('table', '')
        record_id = request.data.get('recordId', '')
        old_value = request.data.get('oldValue', '')
        new_value = request.data.get('newValue', '')
        detail = json.dumps({'old': old_value, 'new': new_value}, ensure_ascii=False)

        AuditLog.objects.create(
            user=request.user,
            action=action,
            table_name=table_name,
            record_id=str(record_id),
            detail=detail,
        )
        return Response({'code': 0, 'msg': 'ok'}, status=status.HTTP_201_CREATED)


# ── Admin Order List ──────────────────────────────────────────

class AdminOrderListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if (err := check_admin(request)):
            return err

        status_filter = request.query_params.get('status', '')
        search = request.query_params.get('search', '')

        qs = Order.objects.select_related('user').prefetch_related('items__product', 'refunds')
        if status_filter:
            qs = qs.filter(status=status_filter)
        if search:
            qs = qs.filter(order_no__icontains=search)

        qs = qs.order_by('-created_at')[:200]

        data = []
        for order in qs:
            data.append({
                'id': order.id,
                'order_no': order.order_no,
                'username': order.user.username,
                'total_amount': float(order.total_amount),
                'status': order.status,
                'status_text': order.get_status_display(),
                'receiver_name': order.receiver_name,
                'receiver_phone': order.receiver_phone,
                'address': order.address,
                'items': [{
                    'product_name': item.product.name,
                    'price': float(item.price),
                    'quantity': item.quantity,
                } for item in order.items.all()],
                'created_at': order.created_at.isoformat(),
            })

        # Aggregate stats
        stats = {
            'total': qs.count() if status_filter else Order.objects.count(),
            'by_status': {},
        }
        for s in ['paid', 'shipped', 'completed', 'cancelled', 'refunded']:
            stats['by_status'][s] = Order.objects.filter(status=s).count()
        total_revenue = Order.objects.aggregate(s=Sum('total_amount'))['s'] or 0
        stats['total_revenue'] = float(total_revenue)

        return Response({'code': 0, 'data': {'orders': data, 'stats': stats}})


# ── Database Explorer ──────────────────────────────────────────

DB_WHITELIST = {
    'users', 'shops', 'products', 'categories', 'inventory',
    'inventory_transactions', 'orders', 'order_items', 'carts',
    'refunds', 'reviews', 'shop_follows', 'audit_logs',
}


class DatabaseTablesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if (err := check_admin(request)):
            return err

        with connection.cursor() as c:
            c.execute('SELECT DATABASE()')
            db_name = c.fetchone()[0]

            c.execute('''
                SELECT TABLE_NAME, TABLE_ROWS, CREATE_TIME, TABLE_COMMENT
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
            ''', [db_name])
            tables = []
            for row in c.fetchall():
                name = row[0]
                if name not in DB_WHITELIST:
                    continue
                c.execute('''
                    SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY, COLUMN_DEFAULT, EXTRA
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                    ORDER BY ORDINAL_POSITION
                ''', [db_name, name])
                columns = [
                    {'name': col[0], 'type': col[1], 'nullable': col[2] == 'YES',
                     'key': col[3] or '', 'default': str(col[4]) if col[4] is not None else None,
                     'extra': col[5]}
                    for col in c.fetchall()
                ]
                tables.append({
                    'name': name,
                    'row_count': row[1] or 0,
                    'created_at': row[2].isoformat() if row[2] else '',
                    'comment': row[3] or '',
                    'columns': columns,
                })

        return Response({'code': 0, 'data': tables})


class DatabaseTableView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if (err := check_admin(request)):
            return err

        table = request.query_params.get('table', '')
        if table not in DB_WHITELIST:
            return Response({'code': 1, 'msg': 'Table not allowed'}, status=status.HTTP_400_BAD_REQUEST)

        page = int(request.query_params.get('page', 1))
        size = min(int(request.query_params.get('size', 50)), 200)

        with connection.cursor() as c:
            # Count
            c.execute(f'SELECT COUNT(*) FROM `{table}`')
            total = c.fetchone()[0]

            # Columns
            c.execute('''
                SELECT COLUMN_NAME FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
            ''', [table])
            columns = [col[0] for col in c.fetchall()]

            # Rows
            offset = (page - 1) * size
            c.execute(f'SELECT * FROM `{table}` LIMIT %s OFFSET %s', [size, offset])
            rows = [list(row) for row in c.fetchall()]

        return Response({
            'code': 0,
            'data': {
                'table': table,
                'columns': columns,
                'rows': rows,
                'total': total,
                'page': page,
                'size': size,
            }
        })


class ChangeFeedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if (err := check_admin(request)):
            return err

        since = request.query_params.get('since', '')
        limit = min(int(request.query_params.get('limit', 30)), 100)

        qs = AuditLog.objects.select_related('user').order_by('-created_at')
        if since:
            qs = qs.filter(created_at__gt=since)
        qs = qs[:limit]

        feeds = []
        for log in qs:
            feeds.append({
                'id': str(log.id),
                'table': log.table_name,
                'action': log.action,
                'description': log.description,
                'time': log.created_at.isoformat(),
            })

        return Response({'code': 0, 'data': feeds})
