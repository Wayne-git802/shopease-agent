"""
Template Views - Render HTML pages for the frontend
"""
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum, Count, Q
from django.http import JsonResponse

from products.models import Category, Product
from orders.models import Order


def home(request):
    """Home page with featured products"""
    featured_products = Product.objects.filter(is_active=True).select_related('category', 'seller')[:8]

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
    products = Product.objects.filter(is_active=True).select_related('category', 'seller')
    
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
                    'username': user.username
                })
            
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
        orders = Order.objects.filter(user=request.user).prefetch_related(
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
    """All shops list page"""
    from products.models import Shop, ShopFollow

    shops = Shop.objects.all().select_related('user').annotate(
        product_count=Count('products', filter=Q(products__is_active=True))
    )

    followed_shop_ids = set()
    if request.user.is_authenticated:
        followed_shop_ids = set(
            ShopFollow.objects.filter(user=request.user).values_list('shop_id', flat=True)
        )

    return render(request, 'shop_list.html', {
        'shops': shops,
        'total_shops': shops.count(),
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
    products = Product.objects.filter(shop=shop_obj, is_active=True).select_related('category')

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
