import render
from django.shortcuts  import render, redirect, get_object_or_404
from django.views.decorators.csrf  import csrf_protect
from django.views.decorators.http  import require_http_methods, require_POST
from .decorators  import admin_login_required


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


# ─── Login / Logout ──────────────────────────────────────────
@csrf_protect
@require_http_methods(['GET', 'POST'])
def admin_login(request):
    if request.session.get('admin_authenticated'):
        return redirect('admin_dashboard')
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


# ─── Dashboard ───────────────────────────────────────────────
@admin_login_required
def admin_dashboard(request):
    now   = timezone.now()
    since = now - timedelta(days=30)
    week  = now - timedelta(days=7)
    admin = AdminUser.objects.get(pk=request.session['admin_id'])

    # Login stats
    success_logins  = LoginAttempt.objects.filter(success=True,  attempted_at__gte=since).count()
    failed_logins   = LoginAttempt.objects.filter(success=False, attempted_at__gte=since).count()
    recent_attempts = LoginAttempt.objects.order_by('-attempted_at')[:6]

    # Bar chart: last 7 days
    daily_attempts = []
    week_labels    = []
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        count = LoginAttempt.objects.filter(
            attempted_at__gte=day_start,
            attempted_at__lt=day_start + timedelta(days=1)
        ).count()
        daily_attempts.append(count)
        week_labels.append(day.strftime('%a'))          # Mon, Tue...

    mx = max(daily_attempts) if max(daily_attempts) > 0 else 1
    daily_pct = [round((c / mx) * 90) + 10 for c in daily_attempts]

    # Products
    products       = Product.objects.select_related('category').prefetch_related('images').order_by('-created_at')[:10]
    product_count  = Product.objects.count()
    new_this_week  = Product.objects.filter(created_at__gte=week).count()

    return render(request, 'adminpanel/dashboard.html', {
        'admin_name':      request.session.get('admin_name'),
        'last_login':      admin.last_login,
        'success_logins':  success_logins,
        'failed_logins':   failed_logins,
        'recent_attempts': recent_attempts,
        'daily_attempts':  daily_pct,
        'week_labels':     week_labels,
        'products':        products,
        'product_count':   product_count,
        'new_this_week':   new_this_week,
    })


# ─── Product List ─────────────────────────────────────────────
@admin_login_required
def admin_products(request):
    products   = Product.objects.select_related('category').prefetch_related('images').order_by('-created_at')
    categories = Category.objects.all()

    # Filter
    cat    = request.GET.get('category')
    status = request.GET.get('status')
    search = request.GET.get('search')
    if cat:    products = products.filter(category__id=cat)
    if status: products = products.filter(status=status)
    if search: products = products.filter(name__icontains=search)

    return render(request, 'adminpanel/products.html', {
        'products':   products,
        'categories': categories,
        'admin_name': request.session.get('admin_name'),
    })


# ─── Add Product ─────────────────────────────────────────────
@admin_login_required
def add_product(request):
    categories = Category.objects.all()
    if request.method == 'POST':
        name           = request.POST.get('name', '').strip()
        description    = request.POST.get('description', '').strip()
        price          = request.POST.get('price')
        discount_price = request.POST.get('discount_price') or None
        category_id    = request.POST.get('category') or None
        stock          = request.POST.get('stock', 0)
        status         = request.POST.get('status', 'available')
        colors_raw     = request.POST.get('colors', '')
        offer          = request.POST.get('offer', '').strip()
        images         = request.FILES.getlist('images')

        # Basic validation
        errors = {}
        if not name:   errors['name']  = 'Name is required'
        if not price:  errors['price'] = 'Price is required'
        if not images: errors['images'] = 'At least one image is required'

        if errors:
            return render(request, 'adminpanel/add_product.html', {
                'errors': errors, 'categories': categories,
                'admin_name': request.session.get('admin_name'),
            })

        # Parse colors — "red, blue, black" → ["red","blue","black"]
        colors = [c.strip() for c in colors_raw.split(',') if c.strip()]

        product = Product.objects.create(
            name=name, description=description,
            price=price, discount_price=discount_price,
            category_id=category_id, stock=stock,
            status=status, colors=colors, offer=offer,
        )

        for i, img in enumerate(images):
            ProductImage.objects.create(
                product=product, image=img,
                is_primary=(i == 0), order=i
            )

        return redirect(f"{{% url 'admin_products' %}}?msg=Product+added+successfully&type=success")

    return render(request, 'adminpanel/add_product.html', {
        'categories': categories,
        'admin_name': request.session.get('admin_name'),
    })


# ─── Edit Product ─────────────────────────────────────────────
@admin_login_required
def edit_product(request, pk):
    product    = get_object_or_404(Product, pk=pk)
    categories = Category.objects.all()

    if request.method == 'POST':
        product.name           = request.POST.get('name', product.name).strip()
        product.description    = request.POST.get('description', product.description).strip()
        product.price          = request.POST.get('price', product.price)
        product.discount_price = request.POST.get('discount_price') or None
        product.category_id    = request.POST.get('category') or None
        product.stock          = request.POST.get('stock', product.stock)
        product.status         = request.POST.get('status', product.status)
        product.offer          = request.POST.get('offer', '').strip()

        colors_raw   = request.POST.get('colors', '')
        product.colors = [c.strip() for c in colors_raw.split(',') if c.strip()]

        product.save()

        # Add new images if uploaded
        new_images = request.FILES.getlist('images')
        existing   = product.images.count()
        for i, img in enumerate(new_images):
            ProductImage.objects.create(
                product=product, image=img,
                is_primary=False, order=existing + i
            )

        # Delete selected images
        delete_ids = request.POST.getlist('delete_images')
        for img_id in delete_ids:
            try:
                img = ProductImage.objects.get(pk=img_id, product=product)
                img.image.delete(save=False)
                img.delete()
            except ProductImage.DoesNotExist:
                pass

        # Set primary image
        primary_id = request.POST.get('primary_image')
        if primary_id:
            try:
                pi = ProductImage.objects.get(pk=primary_id, product=product)
                pi.is_primary = True
                pi.save()
            except ProductImage.DoesNotExist:
                pass

        return redirect(f"/admin-panel/products/?msg=Product+updated&type=success")

    return render(request, 'adminpanel/edit_product.html', {
        'product':    product,
        'categories': categories,
        'colors_str': ', '.join(product.colors) if product.colors else '',
        'admin_name': request.session.get('admin_name'),
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
def admin_login_logs(request):
    logs = LoginAttempt.objects.order_by('-attempted_at')[:100]
    return render(request, 'admin_login_logs.html', {
        'logs':       logs,
        'admin_name': request.session.get('admin_name'),
    });from django.shortcuts  import render, redirect, get_object_or_404
from django.contrib    import messages
from django.utils      import timezone
from django.views.decorators.csrf  import csrf_protect
from django.views.decorators.http  import require_http_methods, require_POST
from datetime import timedelta
import bcrypt

from .models      import AdminUser, LoginAttempt, Product, ProductImage, Category
from .decorators  import admin_login_required


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


# ─── Login / Logout ──────────────────────────────────────────
@csrf_protect
@require_http_methods(['GET', 'POST'])
def admin_login(request):
    if request.session.get('admin_authenticated'):
        return redirect('admin_dashboard')
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


# ─── Dashboard ───────────────────────────────────────────────
@admin_login_required
def admin_dashboard(request):
    now   = timezone.now()
    since = now - timedelta(days=30)
    week  = now - timedelta(days=7)
    admin = AdminUser.objects.get(pk=request.session['admin_id'])

    # Login stats
    success_logins  = LoginAttempt.objects.filter(success=True,  attempted_at__gte=since).count()
    failed_logins   = LoginAttempt.objects.filter(success=False, attempted_at__gte=since).count()
    recent_attempts = LoginAttempt.objects.order_by('-attempted_at')[:6]

    # Bar chart: last 7 days
    daily_attempts = []
    week_labels    = []
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        count = LoginAttempt.objects.filter(
            attempted_at__gte=day_start,
            attempted_at__lt=day_start + timedelta(days=1)
        ).count()
        daily_attempts.append(count)
        week_labels.append(day.strftime('%a'))          # Mon, Tue...

    mx = max(daily_attempts) if max(daily_attempts) > 0 else 1
    daily_pct = [round((c / mx) * 90) + 10 for c in daily_attempts]

    # Products
    products       = Product.objects.select_related('category').prefetch_related('images').order_by('-created_at')[:10]
    product_count  = Product.objects.count()
    new_this_week  = Product.objects.filter(created_at__gte=week).count()

    return render(request, 'adminpanel/dashboard.html', {
        'admin_name':      request.session.get('admin_name'),
        'last_login':      admin.last_login,
        'success_logins':  success_logins,
        'failed_logins':   failed_logins,
        'recent_attempts': recent_attempts,
        'daily_attempts':  daily_pct,
        'week_labels':     week_labels,
        'products':        products,
        'product_count':   product_count,
        'new_this_week':   new_this_week,
    })


# ─── Product List ─────────────────────────────────────────────
@admin_login_required
def admin_products(request):
    products   = Product.objects.select_related('category').prefetch_related('images').order_by('-created_at')
    categories = Category.objects.all()

    # Filter
    cat    = request.GET.get('category')
    status = request.GET.get('status')
    search = request.GET.get('search')
    if cat:    products = products.filter(category__id=cat)
    if status: products = products.filter(status=status)
    if search: products = products.filter(name__icontains=search)

    return render(request, 'adminpanel/product.html', {
        'products':   products,
        'categories': categories,
        'admin_name': request.session.get('admin_name'),
    })


# ─── Add Product ─────────────────────────────────────────────
@admin_login_required
def add_product(request):
    categories = Category.objects.all()
    if request.method == 'POST':
        name           = request.POST.get('name', '').strip()
        description    = request.POST.get('description', '').strip()
        price          = request.POST.get('price')
        discount_price = request.POST.get('discount_price') or None
        category_id    = request.POST.get('category') or None
        stock          = request.POST.get('stock', 0)
        status         = request.POST.get('status', 'available')
        colors_raw     = request.POST.get('colors', '')
        offer          = request.POST.get('offer', '').strip()
        images         = request.FILES.getlist('images')

        # Basic validation
        errors = {}
        if not name:   errors['name']  = 'Name is required'
        if not price:  errors['price'] = 'Price is required'
        if not images: errors['images'] = 'At least one image is required'

        if errors:
            return render(request, 'adminpanel/add_product.html', {
                'errors': errors, 'categories': categories,
                'admin_name': request.session.get('admin_name'),
            })

        # Parse colors — "red, blue, black" → ["red","blue","black"]
        colors = [c.strip() for c in colors_raw.split(',') if c.strip()]

        product = Product.objects.create(
            name=name, description=description,
            price=price, discount_price=discount_price,
            category_id=category_id, stock=stock,
            status=status, colors=colors, offer=offer,
        )

        for i, img in enumerate(images):
            ProductImage.objects.create(
                product=product, image=img,
                is_primary=(i == 0), order=i
            )

        return redirect(f"{{% url 'admin_products' %}}?msg=Product+added+successfully&type=success")

    return render(request, 'adminpanel/add_product.html', {
        'categories': categories,
        'admin_name': request.session.get('admin_name'),
    })


# ─── Edit Product ─────────────────────────────────────────────
@admin_login_required
def edit_product(request, pk):
    product    = get_object_or_404(Product, pk=pk)
    categories = Category.objects.all()

    if request.method == 'POST':
        product.name           = request.POST.get('name', product.name).strip()
        product.description    = request.POST.get('description', product.description).strip()
        product.price          = request.POST.get('price', product.price)
        product.discount_price = request.POST.get('discount_price') or None
        product.category_id    = request.POST.get('category') or None
        product.stock          = request.POST.get('stock', product.stock)
        product.status         = request.POST.get('status', product.status)
        product.offer          = request.POST.get('offer', '').strip()

        colors_raw   = request.POST.get('colors', '')
        product.colors = [c.strip() for c in colors_raw.split(',') if c.strip()]

        product.save()

        # Add new images if uploaded
        new_images = request.FILES.getlist('images')
        existing   = product.images.count()
        for i, img in enumerate(new_images):
            ProductImage.objects.create(
                product=product, image=img,
                is_primary=False, order=existing + i
            )

        # Delete selected images
        delete_ids = request.POST.getlist('delete_images')
        for img_id in delete_ids:
            try:
                img = ProductImage.objects.get(pk=img_id, product=product)
                img.image.delete(save=False)
                img.delete()
            except ProductImage.DoesNotExist:
                pass

        # Set primary image
        primary_id = request.POST.get('primary_image')
        if primary_id:
            try:
                pi = ProductImage.objects.get(pk=primary_id, product=product)
                pi.is_primary = True
                pi.save()
            except ProductImage.DoesNotExist:
                pass

        return redirect(f"/admin-panel/products/?msg=Product+updated&type=success")

    return render(request, 'adminpanel/edit_product.html', {
        'product':    product,
        'categories': categories,
        'colors_str': ', '.join(product.colors) if product.colors else '',
        'admin_name': request.session.get('admin_name'),
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
def admin_login_logs(request):
    logs = LoginAttempt.objects.order_by('-attempted_at')[:100]
    return render(request, 'adminpanel/admin_login_logs.html', {
        'logs':       logs,
        'admin_name': request.session.get('admin_name'),
    })