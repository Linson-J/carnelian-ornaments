from datetime import timedelta

import bcrypt
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib.auth.models import User
from django.db.models import Sum, Q

from .forms import CarouselItemForm
from .decorators import admin_login_required
from .models import (
    AdminUser,
    CarouselItem,
    Category,
    CategoryTag,
    HomeSection,
    HomeTheme,
    LoginAttempt,
    NewsletterSubscription,
    Product,
    ProductImage,
    Favorite,
    DeliveryZone,
    DeliveryConfig,
    Order,
    OrderItem,
    OTPSettings,
    ContactMessage,
    Coupon,
    PopupBanner,
)
from .email_utils import send_order_status_email


MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _get_ip(request):
    x = request.META.get('HTTP_X_FORWARDED_FOR')
    return x.split(',')[0].strip() if x else request.META.get('REMOTE_ADDR', '0.0.0.0')


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
    admin = get_object_or_404(AdminUser, pk=request.session['admin_id'])

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

    # Dynamic Order Stats
    total_orders = Order.objects.count()
    sales_agg = Order.objects.exclude(status=Order.Status.CANCELLED).aggregate(total_sum=Sum('total'))
    total_sales = float(sales_agg['total_sum'] or 0.0)
    
    total_customers = User.objects.filter(is_superuser=False, is_staff=False).count()
    pending_orders = Order.objects.filter(status=Order.Status.PENDING).count()
    low_stock_products = Product.objects.filter(stock__lte=5).count()
    
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_rev_agg = Order.objects.filter(created_at__gte=month_start).exclude(status=Order.Status.CANCELLED).aggregate(total_sum=Sum('total'))
    revenue_this_month = float(monthly_rev_agg['total_sum'] or 0.0)
    
    db_recent_orders = Order.objects.order_by('-created_at')[:5]
    recent_orders = []
    for o in db_recent_orders:
        o.customer_name = o.full_name
        recent_orders.append(o)
        
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    order_statistics = {
        'today': Order.objects.filter(created_at__gte=today_start).count(),
        'this_week': Order.objects.filter(created_at__gte=week).count(),
        'this_month': Order.objects.filter(created_at__gte=month_start).count(),
    }
    
    top_selling_data = OrderItem.objects.values('product__name').annotate(sold=Sum('quantity')).order_by('-sold')[:5]
    top_selling = [{'name': item['product__name'], 'sold': item['sold']} for item in top_selling_data if item['product__name']]
    
    sales_chart = []
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_sum = Order.objects.filter(created_at__gte=day_start, created_at__lt=day_end).exclude(status=Order.Status.CANCELLED).aggregate(total_sum=Sum('total'))['total_sum'] or 0.0
        sales_chart.append({
            'label': day.strftime('%a'),
            'value': float(day_sum)
        })
        
    max_val = max(item['value'] for item in sales_chart) if sales_chart else 0
    if max_val > 0:
        for item in sales_chart:
            item['original_value'] = item['value']
            item['value'] = round((item['original_value'] / max_val) * 90) + 10

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
    categories = Category.objects.order_by('name')

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
    categories = Category.objects.filter(status=Category.Status.ACTIVE).order_by('name')
    return render(request, 'adminpanel/add_product.html', {
        'categories': categories,
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'products',
        'product_count': Product.objects.count(),
    })


# ─── Edit Product ─────────────────────────────────────────────
@admin_login_required
def edit_product(request, pk):
    product = get_object_or_404(Product.objects.select_related('category'), pk=pk)
    categories = Category.objects.filter(status=Category.Status.ACTIVE).order_by('name')
    if product.category_id and product.category.status != Category.Status.ACTIVE:
        categories = Category.objects.filter(pk=product.category_id) | categories

    if request.method == 'POST':
        product.name = request.POST.get('name', product.name).strip()
        product.description = request.POST.get('description', product.description).strip()
        product.price = request.POST.get('price', product.price)
        product.discount_price = request.POST.get('discount_price') or None
        product.category_id = request.POST.get('category') or None
        product.stock = request.POST.get('stock', product.stock)
        product.status = request.POST.get('status', product.status)

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
def admin_categories(request):
    CategoryTag.ensure_defaults()
    categories = Category.objects.prefetch_related('products', 'tags').order_by('name')
    tags = CategoryTag.objects.prefetch_related('categories').order_by('name')
    status = request.GET.get('status')
    search = request.GET.get('search')
    if status:
        categories = categories.filter(status=status)
    if search:
        categories = categories.filter(name__icontains=search)

    return render(request, 'adminpanel/categories.html', {
        'categories': categories,
        'category_tags': tags,
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'categories',
        'category_count': Category.objects.count(),
        'product_count': Product.objects.count(),
        'filter_status': status or '',
        'filter_search': search or '',
    })


# Delete Product
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
    form = CarouselItemForm(request.POST or None, request.FILES or None, instance=item)
    if request.method == 'POST' and form.is_valid():
        updated = form.save()
        if request.FILES.get('image') and old_image and old_image.name != updated.image.name:
            old_image.delete(save=False)
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


@admin_login_required
@require_http_methods(['GET', 'POST'])
def admin_settings(request):
    otp_settings = OTPSettings.current()
    theme = HomeTheme.current()

    if request.method == 'POST':
        # Check if JSON request
        if 'application/json' in (request.content_type or ''):
            import json
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({'success': False, 'message': 'Invalid JSON data.'}, status=400)
            
            company_name = data.get('company_name', '').strip() or 'Carmelian'
            sender_email = data.get('sender_email', '').strip()
            smtp_host_user = data.get('smtp_host_user', '').strip()
            smtp_host_password = data.get('smtp_host_password', '').strip()
            try:
                otp_length = int(data.get('otp_length', 6))
                otp_expiry_minutes = int(data.get('otp_expiry_minutes', 5))
                resend_cooldown_seconds = int(data.get('resend_cooldown_seconds', 60))
            except (ValueError, TypeError):
                return JsonResponse({'success': False, 'message': 'Invalid numbers for OTP configuration.'}, status=400)

            if not sender_email or '@' not in sender_email:
                return JsonResponse({'success': False, 'message': 'Please enter a valid sender email address.'}, status=400)

            if otp_length not in [4, 6, 8]:
                return JsonResponse({'success': False, 'message': 'OTP length must be 4, 6, or 8 digits.'}, status=400)

            if otp_expiry_minutes < 1 or otp_expiry_minutes > 60:
                return JsonResponse({'success': False, 'message': 'OTP expiry must be between 1 and 60 minutes.'}, status=400)

            if resend_cooldown_seconds < 10 or resend_cooldown_seconds > 600:
                return JsonResponse({'success': False, 'message': 'Resend cooldown must be between 10 and 600 seconds.'}, status=400)

            otp_settings.company_name = company_name
            otp_settings.sender_email = sender_email
            if smtp_host_user:
                otp_settings.smtp_host_user = smtp_host_user
            if smtp_host_password:
                otp_settings.smtp_host_password = smtp_host_password
            otp_settings.otp_length = otp_length
            otp_settings.otp_expiry_minutes = otp_expiry_minutes
            otp_settings.resend_cooldown_seconds = resend_cooldown_seconds
            otp_settings.save()

            return JsonResponse({
                'success': True,
                'message': 'OTP & SMTP settings updated successfully!',
                'otp_settings': {
                    'company_name': otp_settings.company_name,
                    'sender_email': otp_settings.sender_email,
                    'smtp_host_user': otp_settings.smtp_host_user,
                    'smtp_host_password': otp_settings.smtp_host_password,
                    'otp_length': otp_settings.otp_length,
                    'otp_expiry_minutes': otp_settings.otp_expiry_minutes,
                    'resend_cooldown_seconds': otp_settings.resend_cooldown_seconds,
                }
            })
        else:
            company_name = request.POST.get('company_name', '').strip() or 'Carmelian'
            sender_email = request.POST.get('sender_email', '').strip()
            smtp_host_user = request.POST.get('smtp_host_user', '').strip()
            smtp_host_password = request.POST.get('smtp_host_password', '').strip()
            try:
                otp_length = int(request.POST.get('otp_length', 6))
                otp_expiry_minutes = int(request.POST.get('otp_expiry_minutes', 5))
                resend_cooldown_seconds = int(request.POST.get('resend_cooldown_seconds', 60))
            except (ValueError, TypeError):
                messages.error(request, 'Please enter valid numeric values for OTP settings.')
                return redirect('admin_settings')

            if not sender_email or '@' not in sender_email:
                messages.error(request, 'Please enter a valid sender email address.')
                return redirect('admin_settings')

            if otp_length not in [4, 6, 8]:
                messages.error(request, 'OTP length must be 4, 6, or 8 digits.')
                return redirect('admin_settings')

            otp_settings.company_name = company_name
            otp_settings.sender_email = sender_email
            if smtp_host_user:
                otp_settings.smtp_host_user = smtp_host_user
            if smtp_host_password:
                otp_settings.smtp_host_password = smtp_host_password
            otp_settings.otp_length = otp_length
            otp_settings.otp_expiry_minutes = otp_expiry_minutes
            otp_settings.resend_cooldown_seconds = resend_cooldown_seconds
            otp_settings.save()

            messages.success(request, 'OTP & Security Settings updated successfully.')
            return redirect('admin_settings')

    return render(request, 'adminpanel/settings.html', {
        'theme': theme,
        'otp_settings': otp_settings,
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'settings',
    })


@admin_login_required
def admin_home_sections(request):
    HomeSection.ensure_defaults()
    return render(request, 'adminpanel/home_sections.html', {
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'home_sections',
        'section_count': HomeSection.objects.count(),
    })


@admin_login_required
def admin_subscriptions(request):
    search = request.GET.get('search', '').strip()
    subscriptions = NewsletterSubscription.objects.all()
    if search:
        subscriptions = subscriptions.filter(email__icontains=search)
    return render(request, 'adminpanel/subscriptions.html', {
        'subscriptions': subscriptions,
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'subscriptions',
        'subscription_count': NewsletterSubscription.objects.count(),
        'filter_search': search,
    })


@admin_login_required
@require_POST
def delete_subscription(request, pk):
    subscription = get_object_or_404(NewsletterSubscription, pk=pk)
    email = subscription.email
    subscription.delete()
    messages.success(request, f'Subscription for {email} deleted.')
    return redirect('admin_subscriptions')


@admin_login_required
def admin_customers(request):
    from django.contrib.auth.models import User
    from django.db.models import Count

    search = request.GET.get('search', '').strip()
    customers = User.objects.filter(is_superuser=False, is_staff=False).annotate(
        favorites_count=Count('favorites')
    ).order_by('-date_joined')

    if search:
        customers = customers.filter(email__icontains=search)

    return render(request, 'adminpanel/customers.html', {
        'customers': customers,
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'customers',
        'customer_count': customers.count(),
        'filter_search': search,
    })


@admin_login_required
@require_POST
def delete_customer(request, pk):
    from django.contrib.auth.models import User
    customer = get_object_or_404(User, pk=pk, is_superuser=False, is_staff=False)
    email = customer.email
    customer.delete()
    messages.success(request, f'Customer account for {email} has been deleted.')
    return redirect('admin_customers')


# ─── Delivery Settings & Zones Views ──────────────────────────

@admin_login_required
@require_http_methods(['GET', 'POST'])
def admin_delivery(request):
    config = DeliveryConfig.current()
    zones = DeliveryZone.objects.all()
    
    if request.method == 'POST':
        config.fee_type = request.POST.get('fee_type', config.fee_type)
        try:
            config.base_fee = float(request.POST.get('base_fee', config.base_fee))
            config.free_threshold = float(request.POST.get('free_threshold', config.free_threshold))
        except ValueError:
            messages.error(request, 'Please enter valid numbers for fee values.')
            return redirect('admin_delivery')
            
        config.save()
        messages.success(request, 'Delivery configuration updated successfully.')
        return redirect('admin_delivery')
        
    return render(request, 'adminpanel/delivery.html', {
        'config': config,
        'zones': zones,
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'delivery',
    })


@admin_login_required
@require_POST
def add_delivery_zone(request):
    country = request.POST.get('country', 'India').strip()
    state = request.POST.get('state', '').strip()
    city = request.POST.get('city', '').strip()
    county = request.POST.get('county', '').strip()
    
    try:
        delivery_fee = float(request.POST.get('delivery_fee', 150.00))
    except ValueError:
        delivery_fee = 150.00
        
    if not state:
        messages.error(request, 'State field is required to add a delivery zone.')
        return redirect('admin_delivery')
        
    DeliveryZone.objects.create(
        country=country,
        state=state,
        city=city,
        county=county,
        delivery_fee=delivery_fee,
        is_active=True
    )
    messages.success(request, f'Delivery zone for {state} added successfully.')
    return redirect('admin_delivery')


@admin_login_required
@require_POST
def delete_delivery_zone(request, pk):
    zone = get_object_or_404(DeliveryZone, pk=pk)
    details = str(zone)
    zone.delete()
    messages.success(request, f'Delivery zone [{details}] deleted successfully.')
    return redirect('admin_delivery')


# ─── Order Management Views ───────────────────────────────────

@admin_login_required
def admin_orders(request):
    orders = Order.objects.prefetch_related('items', 'items__product', 'items__product__images').order_by('-created_at')
    
    status_filter = request.GET.get('status', '').strip()
    if status_filter:
        orders = orders.filter(status=status_filter)
        
    search_query = request.GET.get('search', '').strip()
    if search_query:
        if search_query.isdigit():
            orders = orders.filter(id=search_query)
        else:
            orders = orders.filter(full_name__icontains=search_query)

    return render(request, 'adminpanel/orders.html', {
        'orders': orders,
        'status_filter': status_filter,
        'search_query': search_query,
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'orders',
        'order_count': Order.objects.count(),
        'choices': Order.Status.choices,
    })


@admin_login_required
@require_POST
def update_order_status(request, pk):
    order = get_object_or_404(Order, pk=pk)
    new_status = request.POST.get('status', '').strip()
    old_status = order.status
    
    # Once an order is cancelled, disallow status updates
    if order.status == Order.Status.CANCELLED:
        messages.warning(request, f"Order #{order.id} is already cancelled and cannot be changed.")
        return redirect('admin_orders')

    if new_status in dict(Order.Status.choices):
        if new_status != old_status:
            order.status = new_status
            if new_status == Order.Status.DELIVERED and not order.delivered_at:
                order.delivered_at = timezone.now()
            elif new_status == Order.Status.CANCELLED:
                if not order.cancelled_at:
                    order.cancelled_at = timezone.now()
                order.cancel_requested = True
                # Restore stock if cancelled by admin
                for item in order.items.all():
                    if item.product:
                        item.product.stock += item.quantity
                        if item.product.status == Product.Status.OUT_OF_STOCK and item.product.stock > 0:
                            item.product.status = Product.Status.AVAILABLE
                        item.product.save()
            elif new_status in [Order.Status.RETURN_REQUESTED, Order.Status.RETURNED]:
                if not order.returned_at:
                    order.returned_at = timezone.now()
                order.return_requested = True
            order.save()

            # Trigger transactional status email notification
            status_event_map = {
                Order.Status.SHIPPED: 'shipped',
                Order.Status.DELIVERED: 'delivered',
                Order.Status.CANCELLED: 'cancelled',
                Order.Status.RETURN_REQUESTED: 'replacement_requested',
                Order.Status.RETURNED: 'replacement_completed',
            }
            event_type = status_event_map.get(new_status)
            if event_type:
                send_order_status_email(order, event_type)

            messages.success(request, f"Order #{order.id} status updated to '{order.get_status_display()}'.")
        else:
            messages.info(request, f"Order #{order.id} status is already '{order.get_status_display()}'.")
    else:
        messages.error(request, "Invalid status transition selected.")
        
    return redirect('admin_orders')


@admin_login_required
def admin_reviews(request):
    from .models import Review
    search = request.GET.get('search', '').strip()
    reviews = Review.objects.select_related('user', 'product').order_by('-created_at')
    
    if search:
        reviews = reviews.filter(
            Q(product__name__icontains=search) | 
            Q(user__email__icontains=search) |
            Q(comment__icontains=search)
        )
        
    return render(request, 'adminpanel/reviews.html', {
        'reviews': reviews,
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'reviews',
        'filter_search': search,
    })


@admin_login_required
@require_POST
def delete_review(request, pk):
    from .models import Review
    review = get_object_or_404(Review, pk=pk)
    product_name = review.product.name
    user_email = review.user.email
    review.delete()
    messages.success(request, f'Review by {user_email} on {product_name} deleted successfully.')
    return redirect('admin_reviews')


# ─── Contact Messages Views ───────────────────────────────────

@admin_login_required
def admin_messages(request):
    search = request.GET.get('search', '').strip()
    contact_messages = ContactMessage.objects.all().order_by('-created_at')

    if search:
        contact_messages = contact_messages.filter(
            Q(name__icontains=search) |
            Q(email__icontains=search) |
            Q(subject__icontains=search) |
            Q(message__icontains=search)
        )

    unread_count = ContactMessage.objects.filter(is_read=False).count()

    return render(request, 'adminpanel/messages.html', {
        'contact_messages': contact_messages,
        'unread_count': unread_count,
        'message_count': ContactMessage.objects.count(),
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'messages',
        'filter_search': search,
    })


@admin_login_required
@require_POST
def delete_message(request, pk):
    msg = get_object_or_404(ContactMessage, pk=pk)
    sender_name = msg.name
    msg.delete()
    messages.success(request, f'Message from {sender_name} deleted successfully.')
    return redirect('admin_messages')


@admin_login_required
@require_POST
def toggle_message_read(request, pk):
    msg = get_object_or_404(ContactMessage, pk=pk)
    msg.is_read = not msg.is_read
    msg.save(update_fields=['is_read'])
    status_str = "marked as read" if msg.is_read else "marked as unread"
    messages.success(request, f'Message from {msg.name} {status_str}.')
    return redirect('admin_messages')


# ─── Coupon Management Views ─────────────────────────────────

@admin_login_required
def admin_coupons(request):
    search = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip()
    
    coupons = Coupon.objects.all().order_by('-created_at')
    
    if search:
        coupons = coupons.filter(code__icontains=search)
        
    now = timezone.now()
    if status_filter == 'active':
        coupons = coupons.filter(is_active=True, valid_from__lte=now, valid_until__gte=now)
    elif status_filter == 'scheduled':
        coupons = coupons.filter(is_active=True, valid_from__gt=now)
    elif status_filter == 'inactive':
        coupons = coupons.filter(Q(is_active=False) | Q(valid_until__lt=now))
    elif status_filter == 'expired':
        coupons = coupons.filter(valid_until__lt=now)

    total_coupons = Coupon.objects.count()
    active_coupons = Coupon.objects.filter(is_active=True, valid_from__lte=now, valid_until__gte=now).count()
    expired_coupons = Coupon.objects.filter(valid_until__lt=now).count()

    return render(request, 'adminpanel/coupons.html', {
        'coupons': coupons,
        'total_coupons': total_coupons,
        'active_coupons': active_coupons,
        'expired_coupons': expired_coupons,
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'coupons',
        'filter_search': search,
        'status_filter': status_filter,
    })


@admin_login_required
@require_http_methods(['GET', 'POST'])
def add_coupon(request):
    now = timezone.now()
    if request.method == 'POST':
        code = request.POST.get('code', '').strip().upper()
        discount_type = request.POST.get('discount_type', Coupon.DiscountType.PERCENTAGE)
        
        try:
            discount_value = float(request.POST.get('discount_value', 0))
            min_purchase = float(request.POST.get('min_purchase', 0.0))
        except ValueError:
            messages.error(request, 'Please enter valid numeric values for discount and minimum purchase.')
            return redirect('add_coupon')

        max_discount_raw = request.POST.get('max_discount', '').strip()
        max_discount = float(max_discount_raw) if max_discount_raw else None

        usage_limit_raw = request.POST.get('usage_limit', '').strip()
        usage_limit = int(usage_limit_raw) if usage_limit_raw else None

        valid_from_raw = request.POST.get('valid_from', '').strip()
        days_to_expire_raw = request.POST.get('days_to_expire', '').strip()
        valid_until_raw = request.POST.get('valid_until', '').strip()
        
        if not code:
            messages.error(request, 'Coupon code is required.')
            return redirect('add_coupon')

        if Coupon.objects.filter(code__iexact=code).exists():
            messages.error(request, f"Coupon code '{code}' already exists. Please choose a unique code.")
            return redirect('add_coupon')

        # Parse valid_from (Start Date)
        if valid_from_raw:
            try:
                from django.utils.dateparse import parse_datetime
                parsed_from = parse_datetime(valid_from_raw)
                if not parsed_from:
                    from datetime import datetime
                    parsed_from = timezone.make_aware(datetime.strptime(valid_from_raw, '%Y-%m-%d'))
                valid_from = parsed_from
            except Exception:
                valid_from = now
        else:
            valid_from = now

        # Compute valid_until (Expiry Date)
        if days_to_expire_raw and days_to_expire_raw.isdigit():
            valid_until = valid_from + timedelta(days=int(days_to_expire_raw))
        elif valid_until_raw:
            try:
                from django.utils.dateparse import parse_datetime
                parsed_until = parse_datetime(valid_until_raw)
                if not parsed_until:
                    from datetime import datetime
                    parsed_until = timezone.make_aware(datetime.strptime(valid_until_raw, '%Y-%m-%d'))
                valid_until = parsed_until
            except Exception:
                valid_until = valid_from + timedelta(days=30)
        else:
            valid_until = valid_from + timedelta(days=30)

        is_active = request.POST.get('is_active') == 'on' or request.POST.get('is_active') == '1'

        Coupon.objects.create(
            code=code,
            discount_type=discount_type,
            discount_value=discount_value,
            min_purchase=min_purchase,
            max_discount=max_discount,
            valid_from=valid_from,
            valid_until=valid_until,
            usage_limit=usage_limit,
            is_active=is_active,
        )

        messages.success(request, f"Coupon code '{code}' created successfully!")
        return redirect('admin_coupons')

    return render(request, 'adminpanel/coupon_form.html', {
        'form_title': 'Add New Coupon',
        'submit_text': 'Create Coupon',
        'discount_types': Coupon.DiscountType.choices,
        'valid_from_formatted': now.strftime('%Y-%m-%dT%H:%M'),
        'valid_until_formatted': (now + timedelta(days=7)).strftime('%Y-%m-%dT%H:%M'),
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'coupons',
    })


@admin_login_required
@require_http_methods(['GET', 'POST'])
def edit_coupon(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)

    if request.method == 'POST':
        code = request.POST.get('code', '').strip().upper()
        discount_type = request.POST.get('discount_type', coupon.discount_type)
        
        try:
            discount_value = float(request.POST.get('discount_value', coupon.discount_value))
            min_purchase = float(request.POST.get('min_purchase', coupon.min_purchase))
        except ValueError:
            messages.error(request, 'Please enter valid numeric values.')
            return redirect('edit_coupon', pk=pk)

        max_discount_raw = request.POST.get('max_discount', '').strip()
        max_discount = float(max_discount_raw) if max_discount_raw else None

        usage_limit_raw = request.POST.get('usage_limit', '').strip()
        usage_limit = int(usage_limit_raw) if usage_limit_raw else None

        valid_from_raw = request.POST.get('valid_from', '').strip()
        days_to_expire_raw = request.POST.get('days_to_expire', '').strip()
        valid_until_raw = request.POST.get('valid_until', '').strip()

        if not code:
            messages.error(request, 'Coupon code cannot be empty.')
            return redirect('edit_coupon', pk=pk)

        if Coupon.objects.filter(code__iexact=code).exclude(pk=pk).exists():
            messages.error(request, f"Coupon code '{code}' is already used by another coupon.")
            return redirect('edit_coupon', pk=pk)

        coupon.code = code
        coupon.discount_type = discount_type
        coupon.discount_value = discount_value
        coupon.min_purchase = min_purchase
        coupon.max_discount = max_discount
        coupon.usage_limit = usage_limit
        coupon.is_active = request.POST.get('is_active') == 'on' or request.POST.get('is_active') == '1'

        if valid_from_raw:
            try:
                from django.utils.dateparse import parse_datetime
                parsed_from = parse_datetime(valid_from_raw)
                if parsed_from:
                    coupon.valid_from = parsed_from
            except Exception:
                pass

        if days_to_expire_raw and days_to_expire_raw.isdigit():
            coupon.valid_until = coupon.valid_from + timedelta(days=int(days_to_expire_raw))
        elif valid_until_raw:
            try:
                from django.utils.dateparse import parse_datetime
                parsed = parse_datetime(valid_until_raw)
                if parsed:
                    coupon.valid_until = parsed
            except Exception:
                pass

        coupon.save()
        messages.success(request, f"Coupon '{coupon.code}' updated successfully!")
        return redirect('admin_coupons')

    return render(request, 'adminpanel/coupon_form.html', {
        'coupon': coupon,
        'form_title': f"Edit Coupon: {coupon.code}",
        'submit_text': 'Save Changes',
        'discount_types': Coupon.DiscountType.choices,
        'valid_from_formatted': coupon.valid_from.strftime('%Y-%m-%dT%H:%M') if coupon.valid_from else '',
        'valid_until_formatted': coupon.valid_until.strftime('%Y-%m-%dT%H:%M') if coupon.valid_until else '',
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'coupons',
    })


@admin_login_required
@require_POST
def delete_coupon(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)
    code = coupon.code
    coupon.delete()
    messages.success(request, f"Coupon '{code}' deleted successfully.")
    return redirect('admin_coupons')


@admin_login_required
@require_POST
def toggle_coupon(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)
    coupon.is_active = not coupon.is_active
    coupon.save(update_fields=['is_active'])
    status_str = "activated" if coupon.is_active else "deactivated"
    messages.success(request, f"Coupon '{coupon.code}' {status_str}.")
    return redirect('admin_coupons')


# ─── Popup Banner Management Views ────────────────────────────

@admin_login_required
def admin_popups(request):
    search = request.GET.get('search', '').strip()
    popups = PopupBanner.objects.all().order_by('-created_at')

    if search:
        popups = popups.filter(Q(title__icontains=search) | Q(subtitle__icontains=search))

    popup_count = PopupBanner.objects.count()
    active_popup_count = PopupBanner.objects.filter(is_active=True).count()

    return render(request, 'adminpanel/popups.html', {
        'popups': popups,
        'popup_count': popup_count,
        'active_popup_count': active_popup_count,
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'popups',
        'filter_search': search,
    })


@admin_login_required
@require_http_methods(['GET', 'POST'])
def add_popup(request):
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        subtitle = request.POST.get('subtitle', '').strip()
        button_text = request.POST.get('button_text', 'Shop Now').strip() or 'Shop Now'
        link_url = request.POST.get('link_url', '/shop/').strip() or '/shop/'
        
        try:
            display_delay = int(request.POST.get('display_delay', 1))
        except (ValueError, TypeError):
            display_delay = 1

        frequency = request.POST.get('frequency', PopupBanner.DisplayFrequency.ONCE_PER_SESSION)
        is_active = request.POST.get('is_active') == 'on' or request.POST.get('is_active') == '1'
        image = request.FILES.get('image')

        if not image:
            messages.error(request, 'Popup image is required.')
            return redirect('add_popup')

        PopupBanner.objects.create(
            title=title,
            subtitle=subtitle,
            image=image,
            button_text=button_text,
            link_url=link_url,
            display_delay=display_delay,
            frequency=frequency,
            is_active=is_active,
        )

        messages.success(request, 'Popup Banner created successfully!')
        return redirect('admin_popups')

    categories = Category.objects.filter(status=Category.Status.ACTIVE).order_by('name')
    products = Product.objects.filter(status=Product.Status.AVAILABLE).order_by('name')

    return render(request, 'adminpanel/popup_form.html', {
        'form_title': 'Add New Popup Banner',
        'submit_text': 'Create Popup Banner',
        'frequencies': PopupBanner.DisplayFrequency.choices,
        'categories': categories,
        'products': products,
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'popups',
    })


@admin_login_required
@require_http_methods(['GET', 'POST'])
def edit_popup(request, pk):
    popup = get_object_or_404(PopupBanner, pk=pk)

    if request.method == 'POST':
        popup.title = request.POST.get('title', '').strip()
        popup.subtitle = request.POST.get('subtitle', '').strip()
        popup.button_text = request.POST.get('button_text', 'Shop Now').strip() or 'Shop Now'
        popup.link_url = request.POST.get('link_url', '/shop/').strip() or '/shop/'

        try:
            popup.display_delay = int(request.POST.get('display_delay', popup.display_delay))
        except (ValueError, TypeError):
            pass

        popup.frequency = request.POST.get('frequency', popup.frequency)
        popup.is_active = request.POST.get('is_active') == 'on' or request.POST.get('is_active') == '1'

        new_image = request.FILES.get('image')
        if new_image:
            if popup.image:
                popup.image.delete(save=False)
            popup.image = new_image

        popup.save()
        messages.success(request, f"Popup Banner '{popup}' updated successfully!")
        return redirect('admin_popups')

    categories = Category.objects.filter(status=Category.Status.ACTIVE).order_by('name')
    products = Product.objects.filter(status=Product.Status.AVAILABLE).order_by('name')

    return render(request, 'adminpanel/popup_form.html', {
        'popup': popup,
        'form_title': f"Edit Popup Banner #{popup.id}",
        'submit_text': 'Save Changes',
        'frequencies': PopupBanner.DisplayFrequency.choices,
        'categories': categories,
        'products': products,
        'admin_name': request.session.get('admin_name'),
        'active_nav': 'popups',
    })


@admin_login_required
@require_POST
def delete_popup(request, pk):
    popup = get_object_or_404(PopupBanner, pk=pk)
    if popup.image:
        popup.image.delete(save=False)
    popup.delete()
    messages.success(request, 'Popup Banner deleted successfully.')
    return redirect('admin_popups')


@admin_login_required
@require_POST
def toggle_popup(request, pk):
    popup = get_object_or_404(PopupBanner, pk=pk)
    popup.is_active = not popup.is_active
    popup.save(update_fields=['is_active'])
    status_str = "activated" if popup.is_active else "deactivated"
    messages.success(request, f"Popup Banner {status_str}.")
    return redirect('admin_popups')




