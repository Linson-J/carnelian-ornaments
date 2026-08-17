from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_POST
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.utils import timezone
from datetime import timedelta
import json
import random
import re

from .forms import NewsletterSubscriptionForm
from .models import CarouselItem, Category, CategoryTag, Product, PasswordResetOTP, Favorite
from .decorators import login_required_ajax


def home(request):
    carousel_items = CarouselItem.objects.filter(is_active=True).select_related('product')
    return render(request, 'shop/home.html', {'carousel_items': carousel_items})


def shop_all(request):
    return render(request, 'shop/shop.html')


def categories_all(request):
    categories = (
        Category.objects.filter(status=Category.Status.ACTIVE)
        .prefetch_related('tags')
        .order_by('name')
    )
    tags = CategoryTag.objects.filter(is_active=True, categories__status=Category.Status.ACTIVE).distinct()
    return render(request, 'shop/categories.html', {
        'categories': categories,
        'tags': tags,
    })


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.select_related('category').prefetch_related('images'),
        slug=slug,
    )
    cart_qty = 0
    if request.user.is_authenticated:
        cart = request.session.get('cart', {})
        if isinstance(cart, dict):
            try:
                cart_qty = int(cart.get(str(product.id), 0))
            except (ValueError, TypeError):
                cart_qty = 0
                
    return render(request, 'shop/product_detail.html', {
        'product': product,
        'cart_qty': cart_qty
    })


@require_POST
def newsletter_subscribe(request):
    form = NewsletterSubscriptionForm(request.POST)
    if form.is_valid():
        form.save()
        return JsonResponse({
            'success': True,
            'message': 'Thanks for subscribing. You are on the list.',
        }, status=201)

    error = form.errors.get('email', ['Enter a valid email address.'])[0]
    return JsonResponse({
        'success': False,
        'message': error,
        'errors': form.errors,
    }, status=400)


# --- AJAX Authentication Views ---

@require_POST
def ajax_login(request):
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip()
        password = data.get('password', '')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON request.'}, status=400)

    if not email or not password:
        return JsonResponse({'success': False, 'message': 'Email and password are required.'}, status=400)

    user = authenticate(request, username=email, password=password)
    if user is not None:
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return JsonResponse({'success': True, 'message': 'Logged in successfully.'})
    else:
        return JsonResponse({'success': False, 'message': 'Invalid email or password.'}, status=400)


@require_POST
def ajax_signup(request):
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip()
        password = data.get('password', '')
        confirm_password = data.get('confirm_password', '')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON request.'}, status=400)

    if not email or not password or not confirm_password:
        return JsonResponse({'success': False, 'message': 'All fields are required.'}, status=400)

    # Basic validations
    if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
        return JsonResponse({'success': False, 'message': 'Please enter a valid email address.'}, status=400)

    if len(password) < 8:
        return JsonResponse({'success': False, 'message': 'Password must be at least 8 characters long.'}, status=400)

    if password != confirm_password:
        return JsonResponse({'success': False, 'message': 'Passwords do not match.'}, status=400)

    if User.objects.filter(username=email).exists() or User.objects.filter(email=email).exists():
        return JsonResponse({'success': False, 'message': 'An account with this email already exists.'}, status=400)

    try:
        user = User.objects.create_user(username=email, email=email)
        user.set_password(password)
        user.save()
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return JsonResponse({'success': True, 'message': 'Account created and logged in successfully.'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Signup failed: {str(e)}'}, status=500)


@require_POST
def ajax_logout(request):
    logout(request)
    return JsonResponse({'success': True, 'message': 'Logged out successfully.'})


# --- OTP Forgot Password Views ---

@require_POST
def request_otp(request):
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip()
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON request.'}, status=400)

    if not email:
        return JsonResponse({'success': False, 'message': 'Email is required.'}, status=400)

    user = User.objects.filter(email=email).first()
    if not user:
        return JsonResponse({'success': False, 'message': 'No account found with this email address.'}, status=400)

    # Rate limiting: max 1 OTP request per 30 seconds per email/IP
    now = timezone.now()
    cooldown_time = now - timedelta(seconds=30)
    ip = request.META.get('REMOTE_ADDR')

    if PasswordResetOTP.objects.filter(user=user, created_at__gte=cooldown_time).exists():
        return JsonResponse({'success': False, 'message': 'Please wait 30 seconds before requesting another OTP.'}, status=429)

    if ip and PasswordResetOTP.objects.filter(ip_address=ip, created_at__gte=cooldown_time).exists():
        return JsonResponse({'success': False, 'message': 'Too many OTP requests. Please wait 30 seconds.'}, status=429)

    # Generate 4-digit OTP
    otp_code = str(random.randint(1000, 9999))
    expires_at = now + timedelta(minutes=5)

    PasswordResetOTP.objects.create(
        user=user,
        otp_code=otp_code,
        ip_address=ip,
        expires_at=expires_at
    )

    # Send email
    try:
        send_mail(
            subject='Your Password Reset OTP',
            message=f'Your OTP is {otp_code}. It expires in 5 minutes.',
            from_email=None,
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Failed to send OTP email: {str(e)}'}, status=500)

    from django.conf import settings
    resp_data = {'success': True, 'message': 'OTP has been sent to your email.'}
    if settings.DEBUG:
        resp_data['debug_otp'] = otp_code
    return JsonResponse(resp_data)


@require_POST
def verify_otp(request):
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip()
        otp_code = data.get('otp_code', '').strip()
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON request.'}, status=400)

    if not email or not otp_code:
        return JsonResponse({'success': False, 'message': 'Email and OTP are required.'}, status=400)

    now = timezone.now()
    otp_record = PasswordResetOTP.objects.filter(
        user__email=email,
        otp_code=otp_code,
        is_used=False,
        expires_at__gt=now
    ).first()

    if not otp_record:
        return JsonResponse({'success': False, 'message': 'Invalid or expired OTP.'}, status=400)

    otp_record.is_used = True
    otp_record.save()

    return JsonResponse({'success': True, 'message': 'OTP verified successfully. Please enter your new password.'})


@require_POST
def reset_password(request):
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip()
        otp_code = data.get('otp_code', '').strip()
        password = data.get('password', '')
        confirm_password = data.get('confirm_password', '')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON request.'}, status=400)

    if not email or not otp_code or not password or not confirm_password:
        return JsonResponse({'success': False, 'message': 'All fields are required.'}, status=400)

    if len(password) < 8:
        return JsonResponse({'success': False, 'message': 'Password must be at least 8 characters long.'}, status=400)

    if password != confirm_password:
        return JsonResponse({'success': False, 'message': 'Passwords do not match.'}, status=400)

    now = timezone.now()
    five_mins_ago = now - timedelta(minutes=5)
    otp_record = PasswordResetOTP.objects.filter(
        user__email=email,
        otp_code=otp_code,
        is_used=True,
        created_at__gte=five_mins_ago
    ).first()

    if not otp_record:
        return JsonResponse({'success': False, 'message': 'Session expired or invalid OTP verification. Please try again.'}, status=400)

    user = otp_record.user
    user.set_password(password)
    user.save()

    # Clear all OTPs for this user
    PasswordResetOTP.objects.filter(user=user).delete()

    return JsonResponse({'success': True, 'message': 'Password reset successful. You can now login.'})


# --- AJAX protected e-commerce actions ---

@require_POST
@login_required_ajax
def add_to_cart(request):
    try:
        data = json.loads(request.body)
        product_id = data.get('product_id')
    except (json.JSONDecodeError, AttributeError, ValueError):
        product_id = request.POST.get('product_id')

    product = get_object_or_404(Product, id=product_id)
    cart = request.session.get('cart', {})
    product_id_str = str(product.id)
    cart[product_id_str] = cart.get(product_id_str, 0) + 1
    request.session['cart'] = cart

    return JsonResponse({
        'success': True,
        'message': f'Added {product.name} to cart!',
        'cart_count': sum(cart.values())
    })


@require_POST
@login_required_ajax
def add_to_wishlist(request):
    try:
        data = json.loads(request.body)
        product_id = data.get('product_id')
    except (json.JSONDecodeError, AttributeError, ValueError):
        product_id = request.POST.get('product_id')

    product = get_object_or_404(Product, id=product_id)
    favorite, created = Favorite.objects.get_or_create(user=request.user, product=product)
    
    if created:
        message = f'Added {product.name} to wishlist!'
    else:
        message = f'{product.name} is already in wishlist!'

    wishlist_count = Favorite.objects.filter(user=request.user).count()
    return JsonResponse({
        'success': True,
        'message': message,
        'wishlist_count': wishlist_count
    })


@require_POST
@login_required_ajax
def buy_now(request):
    try:
        data = json.loads(request.body)
        product_id = data.get('product_id')
    except (json.JSONDecodeError, AttributeError, ValueError):
        product_id = request.POST.get('product_id')

    product = get_object_or_404(Product, id=product_id)
    return JsonResponse({
        'success': True,
        'message': f'Proceeding to checkout with {product.name}!',
        'checkout_url': '/checkout/'
    })


def wishlist_page(request):
    if not request.user.is_authenticated:
        return render(request, 'shop/wishlist.html', {'is_auth': False})
    
    favorites = Favorite.objects.filter(user=request.user).select_related('product').prefetch_related('product__images')
    return render(request, 'shop/wishlist.html', {
        'favorites': favorites,
        'is_auth': True
    })


@require_POST
@login_required_ajax
def remove_from_wishlist(request):
    try:
        data = json.loads(request.body)
        product_id = data.get('product_id')
    except (json.JSONDecodeError, AttributeError, ValueError):
        product_id = request.POST.get('product_id')

    favorite = get_object_or_404(Favorite, user=request.user, product_id=product_id)
    favorite.delete()
    
    wishlist_count = Favorite.objects.filter(user=request.user).count()
    return JsonResponse({
        'success': True,
        'message': 'Removed item from wishlist.',
        'wishlist_count': wishlist_count
    })


def cart_page(request):
    if not request.user.is_authenticated:
        return render(request, 'shop/cart.html', {'is_auth': False})
    
    cart = request.session.get('cart', {})
    cart_items = []
    subtotal = 0.0
    original_total = 0.0
    
    # Clean up cart session if any invalid keys are present
    valid_cart = {}
    if isinstance(cart, dict):
        for prod_id, qty in list(cart.items()):
            try:
                prod_id_int = int(prod_id)
                if qty <= 0:
                    continue
                product = Product.objects.filter(id=prod_id_int).first()
                if product:
                    valid_cart[str(product.id)] = qty
                    price = float(product.discount_price if product.discount_price else product.price)
                    orig_price = float(product.price)
                    item_subtotal = price * qty
                    item_original = orig_price * qty
                    subtotal += item_subtotal
                    original_total += item_original
                    
                    # Fetch primary image or first image
                    primary_image = product.images.filter(is_primary=True).first()
                    if not primary_image:
                        primary_image = product.images.first()
                    
                    cart_items.append({
                        'product': product,
                        'quantity': qty,
                        'subtotal': item_subtotal,
                        'image': primary_image,
                    })
            except ValueError:
                continue
            
    # Update cleaned cart back to session if changed
    request.session['cart'] = valid_cart
        
    discount = original_total - subtotal
    # Shipping rules: Free shipping if subtotal >= Rs. 2000, otherwise Rs. 150. Free if empty.
    shipping = 0.0 if (subtotal >= 2000.0 or subtotal == 0) else 150.0
    grand_total = subtotal + shipping
    
    return render(request, 'shop/cart.html', {
        'cart_items': cart_items,
        'subtotal': subtotal,
        'original_total': original_total,
        'discount': discount,
        'shipping': shipping,
        'grand_total': grand_total,
        'is_auth': True
    })


@require_POST
@login_required_ajax
def update_cart_quantity(request):
    try:
        data = json.loads(request.body)
        product_id = str(data.get('product_id'))
        quantity = int(data.get('quantity'))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({'success': False, 'message': 'Invalid input data.'}, status=400)
        
    if quantity <= 0:
        return JsonResponse({'success': False, 'message': 'Quantity must be at least 1.'}, status=400)
        
    product = get_object_or_404(Product, id=product_id)
    
    # Check inventory
    if product.stock < quantity:
        return JsonResponse({
            'success': False, 
            'message': f'Only {product.stock} items available in stock.'
        }, status=400)
        
    cart = request.session.get('cart', {})
    cart[product_id] = quantity
    request.session['cart'] = cart
    
    # Calculate new totals
    subtotal = 0.0
    original_total = 0.0
    item_subtotal = 0.0
    for prod_id, qty in cart.items():
        prod = Product.objects.filter(id=int(prod_id)).first()
        if prod:
            price = float(prod.discount_price if prod.discount_price else prod.price)
            orig_price = float(prod.price)
            subtotal += price * qty
            original_total += orig_price * qty
            if prod_id == product_id:
                item_subtotal = price * qty
                
    discount = original_total - subtotal
    shipping = 0.0 if (subtotal >= 2000.0 or subtotal == 0) else 150.0
    grand_total = subtotal + shipping
    cart_count = sum(cart.values())
    
    return JsonResponse({
        'success': True,
        'message': 'Quantity updated.',
        'item_subtotal': item_subtotal,
        'cart_count': cart_count,
        'subtotal': subtotal,
        'discount': discount,
        'shipping': shipping,
        'grand_total': grand_total
    })


@require_POST
@login_required_ajax
def remove_from_cart(request):
    try:
        data = json.loads(request.body)
        product_id = str(data.get('product_id'))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({'success': False, 'message': 'Invalid input data.'}, status=400)
        
    cart = request.session.get('cart', {})
    if product_id in cart:
        del cart[product_id]
        request.session['cart'] = cart
        
    # Calculate new totals
    subtotal = 0.0
    original_total = 0.0
    for prod_id, qty in cart.items():
        prod = Product.objects.filter(id=int(prod_id)).first()
        if prod:
            price = float(prod.discount_price if prod.discount_price else prod.price)
            orig_price = float(prod.price)
            subtotal += price * qty
            original_total += orig_price * qty
            
    discount = original_total - subtotal
    shipping = 0.0 if (subtotal >= 2000.0 or subtotal == 0) else 150.0
    grand_total = subtotal + shipping
    cart_count = sum(cart.values())
    
    return JsonResponse({
        'success': True,
        'message': 'Item removed from cart.',
        'cart_count': cart_count,
        'subtotal': subtotal,
        'discount': discount,
        'shipping': shipping,
        'grand_total': grand_total
    })
