"""
Template Views - Render HTML pages for the frontend
"""
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum, Count, Q, Avg
from django.http import JsonResponse
from django.contrib.auth import get_user_model

from products.models import Category, Product, ProductStatus, Shop, ShopStatus
from orders.models import Order, Cart, OrderItem, OrderStatus

User = get_user_model()


def home(request):
    """Home page with AI-powered featured products."""
    from agents.commerce.engine import RecommendEngine
    from agents.commerce.strategy_router import route

    strategy, reason = route(request.user)
    engine = RecommendEngine()

    try:
        scored = engine.get_scored(
            user_id=request.user.id if request.user.is_authenticated else None,
            strategy=strategy,
            limit=8,
        )
        featured_products = [p for p, _score, _exp in scored]
        # Attach explain dicts to products for template rendering
        for (p, score, explain), idx in zip(scored, range(len(featured_products))):
            p.ai_score = round(score, 2)
            p.ai_explain = explain
            p.ai_rank = idx + 1
    except Exception:
        # Graceful fallback: raw popular products
        featured_products = Product.objects.filter(is_active=True).select_related(
            'category', 'seller', 'inventory'
        )[:8]
        strategy = "fallback"
        reason = "fusion_error"

    # Get categories with product count (计算子分类中的商品)
    categories = Category.objects.filter(parent__isnull=True).annotate(
        products_count=Count('children__products', filter=Q(children__products__is_active=True))
    )
    category_data = []
    for cat in categories:
        category_data.append({
            'id': cat.id,
            'name': cat.name,
            'products_count': cat.products_count
        })
    
    return render(request, 'home.html', {
        'featured_products': featured_products,
        'categories': category_data
    })


def product_list(request):
    """Product listing page with filtering, sorting, search and pagination"""
    products = Product.objects.filter(is_active=True).select_related('category', 'seller', 'inventory')
    
    # Filter by category
    selected_category = request.GET.get('category')
    if selected_category:
        selected_category = int(selected_category)
        # Check if this is a top-level category
        cat = Category.objects.filter(pk=selected_category, parent__isnull=True).first()
        if cat:
            # Get all subcategory IDs
            sub_ids = cat.children.values_list('id', flat=True)
            products = products.filter(category_id__in=list(sub_ids))
        else:
            products = products.filter(category_id=selected_category)
    
    # Search keyword
    search_query = request.GET.get('search', '')
    if search_query:
        products = products.filter(Q(name__icontains=search_query) | Q(description__icontains=search_query))
    
    # Sorting
    sort_by = request.GET.get('sort', 'default')
    if sort_by == 'price_asc':
        products = products.order_by('price')
    elif sort_by == 'price_desc':
        products = products.order_by('-price')
    else:
        products = products.order_by('-id')  # default: newest first
    
    # Pagination
    paginator = Paginator(products, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get all categories for sidebar
    categories = Category.objects.filter(parent__isnull=True).prefetch_related('children')
    
    return render(request, 'products/product_list.html', {
        'products': page_obj,
        'categories': categories,
        'selected_category': int(selected_category) if selected_category else None,
        'search_query': search_query,
        'sort_by': sort_by,
    })


def product_detail(request, pk):
    """Product detail page"""
    from products.models import Review
    from orders.models import OrderItem
    from django.db.models import Sum
    try:
        product = Product.objects.select_related('category', 'seller', 'shop').get(pk=pk, is_active=True)
    except Product.DoesNotExist:
        return redirect('product_list')

    shop = product.shop

    total_sold = OrderItem.objects.filter(
        product=product
    ).exclude(
        order__status__in=['cancelled', 'pending']
    ).aggregate(sold=Sum('quantity'))['sold'] or 0

    reviews = Review.objects.filter(product=product).select_related('user').order_by('-created_at')[:20]

    avg_rating = None
    review_count = Review.objects.filter(product=product).count()
    if review_count > 0:
        from django.db.models import Avg
        avg_rating = Review.objects.filter(product=product).aggregate(avg=Avg('rating'))['avg']
        avg_rating = round(avg_rating, 1)

    return render(request, 'products/product_detail.html', {
        'product': product,
        'total_sold': total_sold,
        'shop': shop,
        'reviews': reviews,
        'review_count': review_count,
        'avg_rating': avg_rating,
    })


def cart(request):
    """Shopping cart page"""
    return render(request, 'cart.html')


def user_login(request):
    """User login page"""
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('manage-dashboard')
        return redirect('home')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            
            # 如果是 AJAX 请求，返回 JSON
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'username': user.username,
                    'is_staff': user.is_staff
                })
            
            if user.is_staff:
                return redirect('manage-dashboard')
            return redirect('home')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid username or password'
                }, status=400)
            
            return render(request, 'users/login.html', {
                'error': 'Invalid username or password'
            })
    
    return render(request, 'users/login.html')


def user_register(request):
    """User registration page"""
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        display_name = request.POST.get('display_name', '')
        email = request.POST.get('email')
        password = request.POST.get('password')
        password_confirm = request.POST.get('password_confirm')
        phone = request.POST.get('phone', '')
        address = request.POST.get('address', '')
        
        # Validation
        if password != password_confirm:
            return render(request, 'users/register.html', {
                'error': 'Passwords do not match'
            })
        
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        if User.objects.filter(username=username).exists():
            return render(request, 'users/register.html', {
                'error': 'Username already exists'
            })
        
        # 如果没有提供显示名，使用用户名
        if not display_name:
            display_name = username
        
        # Create user
        user = User.objects.create_user(
            username=username,
            display_name=display_name,
            email=email,
            password=password,
            phone=phone,
            address=address
        )
        
        # Don't auto-login — redirect to login page so user gets JWT tokens
        return redirect('/users/login/?registered=1')
    
    return render(request, 'users/register.html')


@login_required
def user_logout(request):
    """User logout"""
    logout(request)
    # 清除 localStorage 中的 JWT token
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    return redirect('home')


def order_list(request):
    """User order list page"""
    # 如果用户已登录，显示后端订单
    reviewed_item_ids = set()
    if request.user.is_authenticated:
        orders = Order.objects.filter(user=request.user, buyer_deleted=False).prefetch_related(
            'items__product__shop'
        ).order_by('-created_at')
        # 获取用户已评价的订单项ID
        from products.models import Review
        reviewed_item_ids = set(
            Review.objects.filter(user=request.user).values_list('order_item_id', flat=True)
        )
    else:
        orders = []

    return render(request, 'orders/order_list.html', {
        'orders': orders,
        'reviewed_item_ids': reviewed_item_ids,
    })


def checkout(request):
    """Checkout page"""
    return render(request, 'orders/checkout.html')


def shop_list(request):
    """All shops list page with pagination (3×4 grid)"""
    from products.models import ShopFollow, Shop

    shops_qs = Shop.objects.all().select_related('user').annotate(
        product_count=Count('products', filter=Q(products__is_active=True))
    ).order_by('-rating', '-created_at')

    total_shops = shops_qs.count()

    followed_shop_ids = set()
    if request.user.is_authenticated:
        followed_shop_ids = set(
            ShopFollow.objects.filter(user=request.user).values_list('shop_id', flat=True)
        )

    paginator = Paginator(shops_qs, 12)  # 3 columns × 4 rows
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'shop_list.html', {
        'shops': page_obj,
        'total_shops': total_shops,
        'followed_shop_ids': followed_shop_ids,
    })


def shop(request, shop_id):
    """Shop/store page showing all products from a seller"""
    from products.models import Shop, Product, ShopFollow
    from django.core.paginator import Paginator

    try:
        shop_obj = Shop.objects.get(pk=shop_id)
    except Shop.DoesNotExist:
        return redirect('home')

    # 获取该店铺的所有商品
    products = Product.objects.filter(shop=shop_obj, is_active=True).select_related('category', 'inventory')

    # 分页
    paginator = Paginator(products, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # 获取店铺统计
    total_products = products.count()

    is_followed = False
    if request.user.is_authenticated:
        is_followed = ShopFollow.objects.filter(user=request.user, shop=shop_obj).exists()

    return render(request, 'shop.html', {
        'shop': shop_obj,
        'products': page_obj,
        'total_products': total_products,
        'is_followed': is_followed,
    })


@login_required
def profile(request):
    """User profile page"""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    success = False
    
    if request.method == 'POST':
        user = request.user
        user.email = request.POST.get('email', user.email)
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.phone = request.POST.get('phone', user.phone)
        user.address = request.POST.get('address', user.address)
        
        new_password = request.POST.get('new_password')
        if new_password:
            user.set_password(new_password)
        
        user.save()
        success = True
    
    # Order statistics
    orders = Order.objects.filter(user=request.user)
    order_stats = {
        'total': orders.count(),
        'completed': orders.filter(status='completed').count(),
        'total_spent': orders.aggregate(total=Sum('total_amount'))['total'] or 0
    }
    
    return render(request, 'users/profile.html', {
        'success': success,
        'order_stats': order_stats
    })


# ═══════════════════════════════════════════════════════════════════
# AI Agent Pages
# ═══════════════════════════════════════════════════════════════════

def ai_workspace(request):
    """AI workspace — unified entry for all AI interactions."""
    return render(request, 'ai/workspace.html')


# ═══════════════════════════════════════════════════════════════════
# Admin-Only Access Guard
# ═══════════════════════════════════════════════════════════════════

def _staff_required(view_func):
    """Decorator: redirect to login if not authenticated, 403 if not staff."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('/users/login/?next=' + request.path)
        if not request.user.is_staff:
            return render(request, 'admin/403.html', status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


@_staff_required
def ai_console(request):
    """Agent Console — runtime observability (admin only)."""
    return render(request, 'ai/console.html')


@_staff_required
def ai_runtime(request):
    """AI Runtime Dashboard (admin only)."""
    from agents.models import EvaluationEvent

    total = EvaluationEvent.objects.filter(event_type='impression').count()
    fallback_count = EvaluationEvent.objects.filter(event_type='fallback').count()
    clarify_trigger = EvaluationEvent.objects.filter(event_type='clarify_ask').count()
    clarify_success = EvaluationEvent.objects.filter(event_type='clarify_answer').count()
    avg_latency = EvaluationEvent.objects.filter(
        event_type='impression'
    ).aggregate(avg=Avg('duration_ms'))['avg'] or 0

    recent = EvaluationEvent.objects.filter(event_type='impression').order_by('-created_at')[:50]
    intents = EvaluationEvent.objects.filter(
        event_type='impression'
    ).values('query_type').annotate(count=Count('id')).order_by('-count')
    intent_total = sum(i['count'] for i in intents) or 1

    return render(request, 'ai/runtime.html', {
        'total_requests': total,
        'fallback_rate': round(fallback_count / max(total, 1) * 100, 1),
        'clarify_trigger_rate': round(clarify_trigger / max(total, 1) * 100, 1),
        'clarify_success_rate': round(clarify_success / max(clarify_trigger, 1) * 100, 1),
        'avg_latency_ms': int(avg_latency),
        'recent_events': recent,
        'intents': intents,
        'intent_total': intent_total,
    })


@_staff_required
def ai_diff(request):
    """Recommendation Diff View (admin only)."""
    from agents.models import SessionTrace

    user_id = request.user.id if request.user.is_authenticated else None
    traces = SessionTrace.objects.filter(
        user_id=user_id
    ).order_by('-created_at')[:20] if user_id else []

    first_trace = SessionTrace.objects.filter(
        user_id=user_id
    ).order_by('created_at').first() if user_id else None
    last_trace = SessionTrace.objects.filter(
        user_id=user_id
    ).order_by('-created_at').first() if user_id else None

    return render(request, 'ai/diff.html', {
        'traces': traces, 'first_trace': first_trace, 'last_trace': last_trace,
    })


@_staff_required
def ai_replay(request):
    """Session Replay panel (admin only)."""
    from agents.models import SessionTrace

    user_id = request.user.id if request.user.is_authenticated else None
    traces = (SessionTrace.objects.filter(user_id=user_id).order_by('-created_at')[:50]
              if user_id else SessionTrace.objects.order_by('-created_at')[:20])

    trace_id = request.GET.get('id', '')
    selected = None
    if trace_id:
        try:
            selected = SessionTrace.objects.get(session_id=trace_id)
        except SessionTrace.DoesNotExist:
            pass
    if not selected and traces:
        selected = traces[0]

    return render(request, 'ai/replay.html', {'traces': traces, 'selected': selected})


# ═══════════════════════════════════════════════════════════════════
# Admin Management
# ═══════════════════════════════════════════════════════════════════

@_staff_required
def admin_dashboard(request):
    return render(request, 'admin/dashboard.html')


@_staff_required
def admin_products(request):
    from django.core.paginator import Paginator
    status_filter = request.GET.get('status', '')
    qs = Product.objects.select_related('category', 'seller', 'shop').all().order_by('-id')
    if status_filter:
        qs = qs.filter(status=status_filter)
    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'admin/products.html', {
        'products': page_obj, 'status_filter': status_filter,
        'status_choices': ProductStatus.CHOICES,
    })


@_staff_required
def admin_sellers(request):
    from django.core.paginator import Paginator
    qs = Shop.objects.select_related('user').annotate(
        product_count=Count('products')
    ).all().order_by('-created_at')
    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'admin/sellers.html', {
        'sellers': page_obj, 'shop_status_choices': ShopStatus.CHOICES,
    })


@_staff_required
def admin_orders(request):
    from django.core.paginator import Paginator
    qs = Order.objects.select_related('user').prefetch_related(
        'items__product__shop'
    ).order_by('-created_at')
    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'admin/orders.html', {'orders': page_obj})


@_staff_required
def admin_overview_api(request):
    from datetime import timedelta
    from django.utils import timezone

    thirty_days_ago = timezone.now() - timedelta(days=30)
    total_orders = Order.objects.filter(created_at__gte=thirty_days_ago).count()
    active_sellers = Shop.objects.filter(status=ShopStatus.APPROVED).count()
    pending_products = Product.objects.filter(status=ProductStatus.PENDING).count()
    total_users = User.objects.count()
    pending_shops = Shop.objects.filter(status=ShopStatus.PENDING).count()

    recent_orders = Order.objects.select_related('user').prefetch_related(
        'items__product__shop'
    ).order_by('-created_at')[:10]

    recent_orders_data = []
    for o in recent_orders:
        seller_name = ''
        items = list(o.items.all())
        if items and items[0].product.shop:
            seller_name = items[0].product.shop.shop_name
        recent_orders_data.append({
            'order_no': o.order_no,
            'buyer': o.user.display_name or o.user.username,
            'seller': seller_name,
            'amount': float(o.total_amount),
            'status': o.get_status_display(),
            'created_at': o.created_at.strftime('%Y-%m-%d %H:%M'),
        })

    health = {'p95_latency': 0, 'avg_latency': 0, 'routing_quality': 0, 'fast_ratio': 0}
    try:
        from agents.models import EvaluationEvent
        import math
        latencies = list(
            EvaluationEvent.objects.filter(event_type='impression')
            .values_list('duration_ms', flat=True).order_by('duration_ms'))
        if latencies:
            n = len(latencies)
            health['avg_latency'] = round(sum(latencies) / n, 1)
            p95_idx = int(math.ceil(0.95 * n)) - 1
            health['p95_latency'] = latencies[p95_idx] if p95_idx < n else latencies[-1]
            total_imp = EvaluationEvent.objects.filter(event_type='impression').count()
            fb = EvaluationEvent.objects.filter(event_type='fallback').count()
            health['routing_quality'] = round((1 - fb / max(total_imp, 1)) * 100, 1)
            fast_count = sum(1 for l in latencies if l < 2000)
            health['fast_ratio'] = round(fast_count / n * 100, 1) if n else 0
    except Exception:
        pass

    return JsonResponse({
        'total_orders': total_orders, 'active_sellers': active_sellers,
        'pending_products': pending_products, 'total_users': total_users,
        'pending_shops': pending_shops, 'recent_orders': recent_orders_data,
        'health': health,
    })


@_staff_required
def admin_toggle_product(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        product = Product.objects.get(pk=pk)
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Product not found'}, status=404)
    if product.status == ProductStatus.SUSPENDED:
        product.status = ProductStatus.AVAILABLE
        product.is_active = True
    else:
        product.status = ProductStatus.SUSPENDED
        product.is_active = False
    product.save()
    return JsonResponse({
        'success': True, 'product_id': product.id,
        'new_status': product.get_status_display(),
    })
