from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_POST
from datetime import timedelta
import bcrypt

from .forms import CarouselItemForm
from .models import AdminUser, LoginAttempt, Product, ProductImage, Category, CarouselItem
from .decorators import admin_login_required


MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _get_ip(request):
    x = request.META.get('HTTP_X_FORWARDED_FOR')
    return x.split(',')[0].strip() if x else request.META.get('REMOTE_ADDR')


def _is_locked(ip):
    cutoff = timezone.now() - timedelta(minutes=LOCKOUT_MINUTES)
    return LoginAttempt.objects.filter(
        ip_address=ip, success=False, attempted_at__gte=cutoff
    ).count() >= MAX_ATTEMPTS


# ─── Login / Logout ──────────────────────────────────────────
@csrf_protect
@require_http_methods(['GET', 'POST'])
def admin_login(request):
    if request.session.get('admin_authenticated'):
        return redirect('admin_dashboard')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        ip = _get_ip(request)
        if _is_locked(ip):
            messages.error(request, 'Too many attempts. Wait 15 minutes.')
            return render(request, 'adminpanel/admin_login.html', {'locked': True})
        try:
            user = AdminUser.objects.get(username=username, is_active=True)
            if bcrypt.checkpw(password.encode(), user.password.encode()):
                user.last_login = timezone.now()
                user.save(update_fields=['last_login'])
                LoginAttempt.objects.create(username=username, ip_address=ip, success=True)
                request.session['admin_authenticated'] = True
                request.session['admin_id'] = user.id
                request.session['admin_name'] = user.username
                request.session.set_expiry(3600)
                return redirect('admin_dashboard')
        except AdminUser.DoesNotExist:
            pass
        LoginAttempt.objects.create(username=username, ip_address=ip, success=False)
        messages.error(request, 'Invalid username or password.')
    return render(request, 'adminpanel/admin_login.html')


def admin_logout(request):
    request.session.flush()
    return redirect('admin_login')


# ─── Dashboard ───────────────────────────────────────────────
@admin_login_required
def admin_dashboard(request):
    now = timezone.now()
    since = now - timedelta(days=30)
    week = now - timedelta(days=7)
    admin = AdminUser.objects.get(pk=request.session['admin_id'])

    success_logins = LoginAttempt.objects.filter(success=True, attempted_at__gte=since).count()
    failed_logins = LoginAttempt.objects.filter(success=False, attempted_at__gte=since).count()
    recent_attempts = LoginAttempt.objects.order_by('-attempted_at')[:6]

    daily_attempts = []
    week_labels = []
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        count = LoginAttempt.objects.filter(
            attempted_at__gte=day_start,
            attempted_at__lt=day_start + timedelta(days=1)
        ).count()
        daily_attempts.append(count)
        week_labels.append(day.strftime('%a'))

    mx = max(daily_attempts) if max(daily_attempts) > 0 else 1
    daily_pct = [round((c / mx) * 90) + 10 for c in daily_attempts]

    products = Product.objects.select_related('category').prefetch_related('images').order_by('-created_at')[:10]
    product_count = Product.objects.count()
    new_this_week = Product.objects.filter(created_at__gte=week).count()

    # Dashboard metrics placeholders (orders/customers/sales not implemented yet)
    total_sales = 0
    total_orders = 0
    total_customers = 0
    pending_orders = 0
    low_stock_products = Product.objects.filter(stock__lte=5).count()
    revenue_this_month = 0.0

    # Chart / widget data placeholders
    sales_chart = []           # e.g. list of {label, value}
    order_statistics = {}      # e.g. {'today':0,'this_week':0}
    top_selling = []           # list of product summaries
    recent_orders = []         # list of recent order dicts

    return render(request, 'adminpanel/dashboard.html', {
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'dashboard',
        'last_login': admin.last_login,
        'success_logins': success_logins,
        'failed_logins': failed_logins,
        'recent_attempts': recent_attempts,
        'daily_attempts': daily_pct,
        'week_labels': week_labels,
        'products': products,
        'product_count': product_count,
        'new_this_week': new_this_week,
        'total_sales': total_sales,
        'total_orders': total_orders,
        'total_customers': total_customers,
        'pending_orders': pending_orders,
        'low_stock_products': low_stock_products,
        'revenue_this_month': revenue_this_month,
        'sales_chart': sales_chart,
        'order_statistics': order_statistics,
        'top_selling': top_selling,
        'recent_orders': recent_orders,
    })


# ─── Product List ─────────────────────────────────────────────
@admin_login_required
def admin_products(request):
    products = Product.objects.select_related('category').prefetch_related('images').order_by('-created_at')
    categories = Category.objects.all()

    cat = request.GET.get('category')
    status = request.GET.get('status')
    search = request.GET.get('search')
    if cat:
        products = products.filter(category__id=cat)
    if status:
        products = products.filter(status=status)
    if search:
        products = products.filter(name__icontains=search)

    return render(request, 'adminpanel/products.html', {
        'products': products,
        'categories': categories,
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'products',
        'product_count': Product.objects.count(),
        'filter_category': cat or '',
        'filter_status': status or '',
        'filter_search': search or '',
    })


# ─── Add Product ─────────────────────────────────────────────
@admin_login_required
def add_product(request):
    categories = Category.objects.all()
    return render(request, 'adminpanel/add_product.html', {
        'categories': categories,
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'products',
        'product_count': Product.objects.count(),
    })


# ─── Edit Product ─────────────────────────────────────────────
@admin_login_required
def edit_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    categories = Category.objects.all()

    if request.method == 'POST':
        product.name = request.POST.get('name', product.name).strip()
        product.description = request.POST.get('description', product.description).strip()
        product.price = request.POST.get('price', product.price)
        product.discount_price = request.POST.get('discount_price') or None
        product.category_id = request.POST.get('category') or None
        product.stock = request.POST.get('stock', product.stock)
        product.status = request.POST.get('status', product.status)
        product.offer = request.POST.get('offer', '').strip()

        colors_raw = request.POST.get('colors', '')
        product.colors = [c.strip() for c in colors_raw.split(',') if c.strip()]

        product.save()

        new_images = request.FILES.getlist('images')
        existing = product.images.count()
        for i, img in enumerate(new_images):
            ProductImage.objects.create(
                product=product, image=img,
                is_primary=False, order=existing + i
            )

        delete_ids = request.POST.getlist('delete_images')
        for img_id in delete_ids:
            try:
                img = ProductImage.objects.get(pk=img_id, product=product)
                img.image.delete(save=False)
                img.delete()
            except ProductImage.DoesNotExist:
                pass

        primary_id = request.POST.get('primary_image')
        if primary_id:
            try:
                pi = ProductImage.objects.get(pk=primary_id, product=product)
                pi.is_primary = True
                pi.save()
            except ProductImage.DoesNotExist:
                pass

        return redirect('/admin-panel/products/?msg=Product+updated&type=success')

    return render(request, 'adminpanel/edit_product.html', {
        'product': product,
        'categories': categories,
        'colors_str': ', '.join(product.colors) if product.colors else '',
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'products',
        'product_count': Product.objects.count(),
    })


# ─── Delete Product ───────────────────────────────────────────
@admin_login_required
@require_POST
def delete_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    for img in product.images.all():
        img.image.delete(save=False)
    product.delete()
    return redirect('/admin-panel/products/?msg=Product+deleted&type=success')


# ─── Login Logs ───────────────────────────────────────────────
@admin_login_required
def admin_carousel(request):
    items = CarouselItem.objects.select_related('product')
    return render(request, 'adminpanel/carousel_items.html', {
        'items': items,
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'carousel',
        'carousel_count': items.count(),
    })


@admin_login_required
@require_http_methods(['GET', 'POST'])
def add_carousel_item(request):
    form = CarouselItemForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Carousel item created.')
        return redirect('admin_carousel')
    return render(request, 'adminpanel/carousel_form.html', {
        'form': form,
        'form_title': 'Add carousel item',
        'submit_text': 'Add item',
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'carousel',
    })


@admin_login_required
@require_http_methods(['GET', 'POST'])
def edit_carousel_item(request, pk):
    item = get_object_or_404(CarouselItem, pk=pk)
    old_image = item.image
    old_mobile_image = item.mobile_image
    form = CarouselItemForm(request.POST or None, request.FILES or None, instance=item)
    if request.method == 'POST' and form.is_valid():
        updated = form.save()
        if request.FILES.get('image') and old_image and old_image.name != updated.image.name:
            old_image.delete(save=False)
        if request.FILES.get('mobile_image') and old_mobile_image and old_mobile_image.name != getattr(updated.mobile_image, 'name', None):
            old_mobile_image.delete(save=False)
        messages.success(request, 'Carousel item updated.')
        return redirect('admin_carousel')
    return render(request, 'adminpanel/carousel_form.html', {
        'form': form,
        'item': item,
        'form_title': 'Edit carousel item',
        'submit_text': 'Save changes',
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'carousel',
    })


@admin_login_required
@require_POST
def delete_carousel_item(request, pk):
    item = get_object_or_404(CarouselItem, pk=pk)
    if item.image:
        item.image.delete(save=False)
    if item.mobile_image:
        item.mobile_image.delete(save=False)
    item.delete()
    messages.success(request, 'Carousel item deleted.')
    return redirect('admin_carousel')


@admin_login_required
def admin_login_logs(request):
    logs = LoginAttempt.objects.order_by('-attempted_at')[:100]
    return render(request, 'adminpanel/admin_login_logs.html', {
        'logs': logs,
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'login_logs',
    })
