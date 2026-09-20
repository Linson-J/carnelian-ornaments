import re

from .models import Category, Order, PopupBanner, StoreAddressSettings


def _external_url(value):
    value = (value or '').strip()
    if not value:
        return ''
    if value.startswith(('http://', 'https://')):
        return value
    return f'https://{value}'


def _whatsapp_url(value):
    digits = re.sub(r'\D+', '', value or '')
    if not digits:
        return ''
    return f'https://wa.me/{digits}'


def footer_context(request):
    categories = Category.objects.filter(
        status=Category.Status.ACTIVE,
    ).order_by('name')[:6]
    all_categories = Category.objects.filter(
        status=Category.Status.ACTIVE,
    ).prefetch_related('products').order_by('name')
    
    # Safely retrieve cart count from session
    cart = request.session.get('cart', {})
    cart_count = sum(cart.values()) if isinstance(cart, dict) else 0
    
    # Get active entry popup banner
    active_popup_banner = PopupBanner.objects.filter(is_active=True).first()
    
    # Get active popup banners configured to show on homepage
    homepage_popup_banners = PopupBanner.objects.filter(is_active=True, show_on_homepage=True).order_by('-created_at')

    store_contact = StoreAddressSettings.current()
    footer_social_links = [
        {'name': 'Instagram', 'url': _external_url(store_contact.instagram_url), 'icon': 'ri-instagram-line'},
        {'name': 'Facebook', 'url': _external_url(store_contact.facebook_url), 'icon': 'ri-facebook-circle-line'},
        {'name': 'Pinterest', 'url': _external_url(store_contact.pinterest_url), 'icon': 'ri-pinterest-line'},
        {'name': 'YouTube', 'url': _external_url(store_contact.youtube_url), 'icon': 'ri-youtube-line'},
        {'name': 'X', 'url': _external_url(store_contact.x_url), 'icon': 'ri-twitter-x-line'},
    ]
    footer_social_links = [link for link in footer_social_links if link['url']]

    return {
        'footer_categories': categories,
        'all_categories': all_categories,
        'cart_count': cart_count,
        'active_popup_banner': active_popup_banner,
        'homepage_popup_banners': homepage_popup_banners,
        'store_contact': store_contact,
        'store_whatsapp_url': _whatsapp_url(store_contact.whatsapp_number),
        'footer_social_links': footer_social_links,
    }


def admin_order_context(request):
    if not request.path.startswith('/admin-panel/') or not request.session.get('admin_authenticated'):
        return {}

    waiting_statuses = [
        Order.Status.PENDING,
        Order.Status.PROCESSING,
        Order.Status.SHIPPED,
        Order.Status.RETURN_REQUESTED,
    ]
    visible_orders = Order.objects.exclude(
        payment_method='PhonePe',
        payment_status__in=[
            Order.PaymentStatus.PENDING,
            Order.PaymentStatus.FAILED,
            Order.PaymentStatus.CANCELLED,
            Order.PaymentStatus.TIMEOUT,
        ],
    )
    latest_order = visible_orders.order_by('-id').first()

    return {
        'admin_waiting_order_count': visible_orders.filter(status__in=waiting_statuses).count(),
        'admin_latest_order_id': latest_order.id if latest_order else 0,
    }

