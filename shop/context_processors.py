from .models import Category, PopupBanner


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

    return {
        'footer_categories': categories,
        'all_categories': all_categories,
        'cart_count': cart_count,
        'active_popup_banner': active_popup_banner,
        'homepage_popup_banners': homepage_popup_banners,
    }

