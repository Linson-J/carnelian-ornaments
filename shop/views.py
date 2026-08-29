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
import string

from .forms import NewsletterSubscriptionForm
from .models import CarouselItem, Category, CategoryTag, Product, PasswordResetOTP, Favorite, DeliveryZone, DeliveryConfig, Order, OrderItem, UserProfile, Review, OTPSettings
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
    is_favorited = False
    if request.user.is_authenticated:
        cart = request.session.get('cart', {})
        if isinstance(cart, dict):
            try:
                cart_qty = int(cart.get(str(product.id), 0))
            except (ValueError, TypeError):
                cart_qty = 0
        is_favorited = Favorite.objects.filter(user=request.user, product=product).exists()

    reviews = product.reviews.select_related('user').order_by('-created_at')
                
    return render(request, 'shop/product_detail.html', {
        'product': product,
        'cart_qty': cart_qty,
        'is_favorited': is_favorited,
        'reviews': reviews,
    })


@require_POST
@login_required_ajax
def add_product_review(request, slug):
    try:
        data = json.loads(request.body)
        rating = int(data.get('rating', 5))
        comment = data.get('comment', '').strip()
    except (json.JSONDecodeError, AttributeError, ValueError):
        rating = int(request.POST.get('rating', 5))
        comment = request.POST.get('comment', '').strip()

    product = get_object_or_404(Product, slug=slug)

    # Validate rating
    if rating < 1 or rating > 5:
        return JsonResponse({
            'success': False,
            'message': 'Rating must be between 1 and 5 stars.'
        }, status=400)

    # Check if user already reviewed
    review, created = Review.objects.get_or_create(
        user=request.user,
        product=product,
        defaults={'rating': rating, 'comment': comment}
    )

    if not created:
        review.rating = rating
        review.comment = comment
        review.save()
        message = 'Your review has been updated!'
    else:
        message = 'Your review has been added successfully!'

    return JsonResponse({
        'success': True,
        'message': message,
        'average_rating': product.average_rating,
        'review_count': product.review_count
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


def login_redirect_view(request):
    next_url = request.GET.get('next', '/')
    if request.user.is_authenticated:
        return redirect(next_url)
    return redirect(f'/?login_required=1&next={next_url}')


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


def validate_strong_unique_password(password, user=None):
    """
    Enforces strong and unique password requirements:
    1. Minimum 8 characters.
    2. Must contain at least one uppercase letter (A-Z).
    3. Must contain at least one lowercase letter (a-z).
    4. Must contain at least one numeric digit (0-9).
    5. Must contain at least one special character (e.g. @, #, $, %, !).
    6. Uniqueness: Cannot be identical to current/previous password.
    """
    if not password:
        return False, "Password cannot be empty."
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter (A-Z)."
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter (a-z)."
    if not re.search(r'\d', password):
        return False, "Password must contain at least one numeric digit (0-9)."
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]', password):
        return False, "Password must contain at least one special character (e.g. @, #, $, %, !)."

    if user and user.check_password(password):
        return False, "New password cannot be the same as your current/previous password. Please choose a unique password."

    return True, ""


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

    if password != confirm_password:
        return JsonResponse({'success': False, 'message': 'Passwords do not match.'}, status=400)

    # Strong password validation
    is_valid_pw, pw_msg = validate_strong_unique_password(password)
    if not is_valid_pw:
        return JsonResponse({'success': False, 'message': pw_msg}, status=400)

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

    otp_config = OTPSettings.current()
    now = timezone.now()
    cooldown_time = now - timedelta(seconds=otp_config.resend_cooldown_seconds)
    ip = request.META.get('REMOTE_ADDR')

    # Rate limiting based on admin configured cooldown
    recent_otp = PasswordResetOTP.objects.filter(user=user, created_at__gte=cooldown_time).order_by('-created_at').first()
    if recent_otp:
        elapsed = (now - recent_otp.created_at).total_seconds()
        remaining = max(1, int(otp_config.resend_cooldown_seconds - elapsed))
        return JsonResponse({
            'success': False, 
            'message': f'Please wait {remaining} seconds before requesting another OTP.',
            'remaining_cooldown': remaining
        }, status=429)

    # Invalidate previous unused OTPs for this user
    PasswordResetOTP.objects.filter(user=user, is_used=False).update(is_used=True)

    # Generate OTP code based on admin configured length (4, 6, or 8 digits)
    otp_code = ''.join(random.choices(string.digits, k=otp_config.otp_length))
    expires_at = now + timedelta(minutes=otp_config.otp_expiry_minutes)

    PasswordResetOTP.objects.create(
        user=user,
        otp_code=otp_code,
        ip_address=ip,
        expires_at=expires_at
    )

    # Render HTML email with company name and rich layout
    from django.conf import settings
    from django.core.mail import get_connection, EmailMultiAlternatives
    from django.template.loader import render_to_string

    company = otp_config.company_name or 'Carmelian'
    smtp_user = (otp_config.smtp_host_user or getattr(settings, 'EMAIL_HOST_USER', '')).strip()
    smtp_pass = (otp_config.smtp_host_password or getattr(settings, 'EMAIL_HOST_PASSWORD', '')).strip()
    sender_addr = smtp_user if smtp_user else (otp_config.sender_email or 'webmaster@localhost')
    formatted_from = f"{company} Security <{sender_addr}>"

    subject = f"{company} - Your Password Reset Code: {otp_code}"
    text_content = (
        f"Hello,\n\n"
        f"Your {company} verification code to reset your password is: {otp_code}\n\n"
        f"This code will expire in {otp_config.otp_expiry_minutes} minutes.\n"
        f"If you did not request a password reset, please ignore this email."
    )

    html_content = render_to_string('emails/otp_email.html', {
        'company_name': company,
        'otp_code': otp_code,
        'expiry_minutes': otp_config.otp_expiry_minutes,
    })

    try:
        if smtp_user and smtp_pass:
            connection = get_connection(
                backend='django.core.mail.backends.smtp.EmailBackend',
                host=getattr(settings, 'EMAIL_HOST', 'smtp.gmail.com'),
                port=getattr(settings, 'EMAIL_PORT', 587),
                username=smtp_user,
                password=smtp_pass,
                use_tls=getattr(settings, 'EMAIL_USE_TLS', True),
            )
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=formatted_from,
                to=[email],
                connection=connection,
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send(fail_silently=False)
        else:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=formatted_from,
                to=[email],
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send(fail_silently=False)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send OTP email to {email}: {e}")
        return JsonResponse({'success': False, 'message': f'Failed to send email to {email}: {str(e)}'}, status=500)

    return JsonResponse({
        'success': True,
        'message': f'A {otp_config.otp_length}-digit OTP code has been sent to your email.',
        'otp_length': otp_config.otp_length,
        'expiry_minutes': otp_config.otp_expiry_minutes,
        'cooldown_seconds': otp_config.resend_cooldown_seconds,
    })


@require_POST
def verify_otp(request):
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip()
        otp_code = data.get('otp_code', '').strip()
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid JSON request.'}, status=400)

    if not email or not otp_code:
        return JsonResponse({'success': False, 'message': 'Email and OTP code are required.'}, status=400)

    otp_config = OTPSettings.current()
    if len(otp_code) != otp_config.otp_length:
        return JsonResponse({'success': False, 'message': f'Please enter a valid {otp_config.otp_length}-digit OTP code.'}, status=400)

    now = timezone.now()
    otp_record = PasswordResetOTP.objects.filter(
        user__email=email,
        otp_code=otp_code,
        is_used=False
    ).order_by('-created_at').first()

    if not otp_record:
        return JsonResponse({'success': False, 'message': 'Invalid OTP code. Please check and try again.'}, status=400)

    if otp_record.expires_at <= now:
        otp_record.is_used = True
        otp_record.save()
        return JsonResponse({'success': False, 'message': 'This OTP code has expired. Please request a new code.'}, status=400)

    otp_record.is_used = True
    otp_record.save()

    return JsonResponse({'success': True, 'message': 'OTP code verified successfully. Please set your new password.'})


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

    if password != confirm_password:
        return JsonResponse({'success': False, 'message': 'Passwords do not match.'}, status=400)

    otp_config = OTPSettings.current()
    now = timezone.now()
    cutoff_time = now - timedelta(minutes=otp_config.otp_expiry_minutes + 15)

    otp_record = PasswordResetOTP.objects.filter(
        user__email=email,
        otp_code=otp_code,
        is_used=True,
        created_at__gte=cutoff_time
    ).first()

    if not otp_record:
        return JsonResponse({'success': False, 'message': 'Verification session expired or invalid. Please request a new OTP.'}, status=400)

    user = otp_record.user

    # Validate strong and unique password (cannot reuse previous password)
    is_valid_pw, pw_msg = validate_strong_unique_password(password, user=user)
    if not is_valid_pw:
        return JsonResponse({'success': False, 'message': pw_msg}, status=400)

    user.set_password(password)
    user.save()

    # Clear all OTPs for this user
    PasswordResetOTP.objects.filter(user=user).delete()

    return JsonResponse({'success': True, 'message': 'Password reset successful. You can now log in.'})


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
        is_favorited = True
    else:
        favorite.delete()
        message = f'Removed {product.name} from wishlist!'
        is_favorited = False

    wishlist_count = Favorite.objects.filter(user=request.user).count()
    return JsonResponse({
        'success': True,
        'message': message,
        'wishlist_count': wishlist_count,
        'is_favorited': is_favorited
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


# ─── Checkout & Shipping Views ────────────────────────────────

import math

def _haversine_distance(lat1, lon1, lat2, lon2):
    """Calculates distance in kilometers between two coordinates."""
    try:
        degrees_to_radians = math.pi / 180.0
        phi1 = float(lat1) * degrees_to_radians
        phi2 = float(lat2) * degrees_to_radians
        theta1 = float(lon1) * degrees_to_radians
        theta2 = float(lon2) * degrees_to_radians
        
        cos = (math.sin(phi1) * math.sin(phi2) +
               math.cos(phi1) * math.cos(phi2) * math.cos(theta1 - theta2))
        cos = max(-1.0, min(1.0, cos))
        arc = math.acos(cos)
        return arc * 6371.0
    except Exception:
        return 0.0


def checkout_page(request):
    if not request.user.is_authenticated:
        return redirect('/?login_required=1')
        
    cart = request.session.get('cart', {})
    if not cart:
        return redirect('cart_page')
        
    subtotal = 0.0
    original_total = 0.0
    cart_items = []
    
    for prod_id, qty in cart.items():
        prod = Product.objects.filter(id=int(prod_id)).first()
        if prod:
            price = float(prod.discount_price if prod.discount_price else prod.price)
            orig_price = float(prod.price)
            subtotal += price * qty
            original_total += orig_price * qty
            cart_items.append({
                'product': prod,
                'quantity': qty,
                'total_price': price * qty
            })
            
    discount = original_total - subtotal
    config = DeliveryConfig.current()
    
    # Calculate a default delivery fee based on flat rules
    if config.fee_type == DeliveryConfig.FeeType.THRESHOLD and subtotal >= float(config.free_threshold):
        default_shipping = 0.0
    else:
        default_shipping = float(config.base_fee)
        
    grand_total = subtotal + default_shipping
    
    profile = None
    if request.user.is_authenticated:
        profile = UserProfile.objects.filter(user=request.user).first()
        
    return render(request, 'shop/checkout.html', {
        'cart_items': cart_items,
        'subtotal': subtotal,
        'discount': discount,
        'default_shipping': default_shipping,
        'grand_total': grand_total,
        'config': config,
        'profile': profile,
    })


@require_POST
def verify_checkout_address(request):
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'message': 'Authentication required.'}, status=401)
        
    try:
        data = json.loads(request.body)
        country = data.get('country', 'India').strip()
        state = data.get('state', '').strip()
        city = data.get('city', '').strip()
        county = data.get('county', '').strip()
        subtotal = float(data.get('subtotal', 0.0))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({'success': False, 'message': 'Invalid address inputs.'}, status=400)
        
    if not state:
        return JsonResponse({'success': False, 'message': 'State is required to check delivery availability.'}, status=400)
        
    # Check if delivery is allowed in this zone and find matching zone for rate
    matching_zone = None
    allowed_zones = DeliveryZone.objects.filter(is_active=True)
    
    if allowed_zones.exists():
        matching_zones = allowed_zones.filter(country__iexact=country, state__iexact=state)
        
        # Resolve most specific zone
        for zone in matching_zones:
            if zone.county and zone.county.lower() != county.lower():
                continue
            if zone.city and zone.city.lower() != city.lower():
                continue
            matching_zone = zone
            break
            
        if not matching_zone:
            return JsonResponse({
                'available': False,
                'message': f'Sorry, we do not deliver to {state} ({country}) at this time.'
            })
            
    # Calculate fee
    config = DeliveryConfig.current()
    
    # Check if subtotal qualifies for free shipping
    is_free = False
    if subtotal >= float(config.free_threshold):
        is_free = True
        delivery_fee = 0.0
    else:
        # Determine zone fee or flat fallback
        if config.fee_type == DeliveryConfig.FeeType.ZONE and matching_zone:
            delivery_fee = float(matching_zone.delivery_fee)
        elif config.fee_type == DeliveryConfig.FeeType.THRESHOLD and matching_zone:
            delivery_fee = float(matching_zone.delivery_fee)
        else:
            delivery_fee = float(config.base_fee)
            
    return JsonResponse({
        'available': True,
        'delivery_fee': round(delivery_fee, 2),
        'distance_km': 0.0,
        'is_free': is_free,
        'message': 'Delivery is available for your address!'
    })


@require_POST
def place_order(request):
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'message': 'Authentication required.'}, status=401)
        
    cart = request.session.get('cart', {})
    if not cart:
        return JsonResponse({'success': False, 'message': 'Your cart is empty.'}, status=400)
        
    try:
        data = json.loads(request.body)
        full_name = data.get('full_name', '').strip()
        phone = data.get('phone', '').strip()
        country = data.get('country', '').strip()
        state = data.get('state', '').strip()
        city = data.get('city', '').strip()
        county = data.get('county', '').strip()
        street_address = data.get('street_address', '').strip()
        postal_code = data.get('postal_code', '').strip()
        
        payment_method = data.get('payment_method', 'Card').strip()
        payment_id = data.get('payment_id', '').strip()
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid checkout data.'}, status=400)
        
    if not (full_name and phone and country and state and city and street_address and postal_code):
        return JsonResponse({'success': False, 'message': 'Please fill all required address fields.'}, status=400)
        
    # Re-verify delivery availability and calculate fee securely
    matching_zone = None
    allowed_zones = DeliveryZone.objects.filter(is_active=True)
    
    if allowed_zones.exists():
        matching_zones = allowed_zones.filter(country__iexact=country, state__iexact=state)
        for zone in matching_zones:
            if zone.county and zone.county.lower() != county.lower():
                continue
            if zone.city and zone.city.lower() != city.lower():
                continue
            matching_zone = zone
            break
            
        if not matching_zone:
            return JsonResponse({'success': False, 'message': 'Selected shipping address is outside our delivery zones.'}, status=400)
            
    # Calculate secure totals
    subtotal = 0.0
    order_items_data = []
    
    for prod_id, qty in cart.items():
        prod = Product.objects.filter(id=int(prod_id)).first()
        if not prod:
            continue
            
        if prod.stock < qty:
            return JsonResponse({
                'success': False,
                'message': f'Sorry, {prod.name} only has {prod.stock} items left in stock.'
            }, status=400)
            
        price = float(prod.discount_price if prod.discount_price else prod.price)
        subtotal += price * qty
        order_items_data.append((prod, qty, price))
        
    # Calculate delivery fee
    config = DeliveryConfig.current()
    
    is_free = False
    if subtotal >= float(config.free_threshold):
        is_free = True
        delivery_fee = 0.0
    else:
        if config.fee_type == DeliveryConfig.FeeType.ZONE and matching_zone:
            delivery_fee = float(matching_zone.delivery_fee)
        elif config.fee_type == DeliveryConfig.FeeType.THRESHOLD and matching_zone:
            delivery_fee = float(matching_zone.delivery_fee)
        else:
            delivery_fee = float(config.base_fee)
            
    total = subtotal + delivery_fee
    
    # Create the Order
    order = Order.objects.create(
        user=request.user,
        full_name=full_name,
        phone=phone,
        country=country,
        state=state,
        city=city,
        county=county,
        street_address=street_address,
        postal_code=postal_code,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        total=total,
        status=Order.Status.PROCESSING if payment_method == 'Card' else Order.Status.PENDING,
        payment_method=payment_method,
        payment_id=payment_id
    )
    
    # Create order items and deduct stock
    for prod, qty, price in order_items_data:
        OrderItem.objects.create(
            order=order,
            product=prod,
            product_name=prod.name,
            price=price,
            quantity=qty
        )
        prod.stock -= qty
        if prod.stock <= 0:
            prod.status = Product.Status.OUT_OF_STOCK
        prod.save()
        
    # Clear the cart session
    request.session['cart'] = {}
    
    return JsonResponse({
        'success': True,
        'message': 'Order placed successfully!',
        'order_id': order.id
    })


def order_success(request, order_id):
    if not request.user.is_authenticated:
        return redirect('/')
        
    order = get_object_or_404(Order.objects.prefetch_related('items'), id=order_id, user=request.user)
    return render(request, 'shop/order_success.html', {'order': order})


def profile_page(request):
    if not request.user.is_authenticated:
        return redirect('/?login_required=1')
        
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    orders = Order.objects.filter(user=request.user).prefetch_related('items', 'items__product', 'items__product__images').order_by('-created_at')
    
    return render(request, 'shop/profile.html', {
        'profile': profile,
        'orders': orders,
        'is_auth': True
    })


@require_POST
def save_profile_address(request):
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'message': 'Authentication required.'}, status=401)
        
    try:
        data = json.loads(request.body)
        phone = data.get('phone', '').strip()
        street_address = data.get('street_address', '').strip()
        city = data.get('city', '').strip()
        county = data.get('county', '').strip()
        state = data.get('state', '').strip()
        country = data.get('country', 'India').strip()
        postal_code = data.get('postal_code', '').strip()
        
        if not street_address or not city or not state or not postal_code:
            return JsonResponse({'success': False, 'message': 'Please fill out all required fields (*).'}, status=400)
            
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        profile.phone = phone
        profile.street_address = street_address
        profile.city = city
        profile.county = county
        profile.state = state
        profile.country = country
        profile.postal_code = postal_code
        profile.save()
        
        return JsonResponse({'success': True, 'message': 'Address saved successfully!'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

