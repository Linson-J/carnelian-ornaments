# from django.shortcuts import render
#
# def admin_dashboard(request):
#     return render(request, 'adminpanel/dashboard.html')
#
# def admin_products(request):
#     return render(request, 'adminpanel/products.html')
#
# def add_product(request):
#     return render(request, 'adminpanel/add_product.html')
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from datetime import timedelta
import bcrypt

from .models import AdminUser, LoginAttempt, Product
from .decorators import admin_login_required

MAX_ATTEMPTS    = 5
LOCKOUT_MINUTES = 15

def _get_ip(request):
    x = request.META.get('HTTP_X_FORWARDED_FOR')
    return x.split(',')[0].strip() if x else request.META.get('REMOTE_ADDR')

def _is_locked(ip):
    cutoff = timezone.now() - timedelta(minutes=LOCKOUT_MINUTES)
    return LoginAttempt.objects.filter(
        ip_address=ip, success=False, attempted_at__gte=cutoff
    ).count() >= MAX_ATTEMPTS


@csrf_protect
@require_http_methods(['GET', 'POST'])
def admin_login(request):
    if request.session.get('admin_authenticated'):
        return redirect('admin_dashboard')   # uses name= from admin_urls.py

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        ip       = _get_ip(request)

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
                request.session['admin_id']   = user.id
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


@admin_login_required
def admin_dashboard(request):
    now   = timezone.now()
    since = now - timedelta(days=30)
    admin = AdminUser.objects.get(pk=request.session['admin_id'])

    success_logins  = LoginAttempt.objects.filter(success=True,  attempted_at__gte=since).count()
    failed_logins   = LoginAttempt.objects.filter(success=False, attempted_at__gte=since).count()
    recent_attempts = LoginAttempt.objects.order_by('-attempted_at')[:6]
    products        = Product.objects.all().order_by('-id')

    daily_attempts = []
    for i in range(6, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        count = LoginAttempt.objects.filter(
            attempted_at__gte=day_start,
            attempted_at__lt=day_start + timedelta(days=1)
        ).count()
        daily_attempts.append(count)

    mx = max(daily_attempts) if max(daily_attempts) > 0 else 1
    daily_pct = [round((c / mx) * 90) + 10 for c in daily_attempts]

    return render(request, 'adminpanel/dashboard.html', {
        'admin_name':      request.session.get('admin_name'),
        'last_login':      admin.last_login,
        'success_logins':  success_logins,
        'failed_logins':   failed_logins,
        'recent_attempts': recent_attempts,
        'daily_attempts':  daily_pct,
        'products':        products,
        'product_count':   products.count(),
    })


@admin_login_required
def admin_products(request):
    products = Product.objects.all().order_by('-id')
    return render(request, 'adminpanel/add_product.html', {'products': products})


@admin_login_required
def add_product(request):
    if request.method == 'POST':
        name        = request.POST.get('name', '').strip()
        price       = request.POST.get('price', 0)
        description = request.POST.get('description', '').strip()
        if name and price:
            Product.objects.create(name=name, price=price, description=description)
            messages.success(request, f'Product "{name}" added successfully.')
            return redirect('admin_products')
        messages.error(request, 'Name and price are required.')
    return render(request, 'adminpanel/add_product.html')