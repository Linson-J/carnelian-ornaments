from .models import Category


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
    
    return {
        'footer_categories': categories,
        'all_categories': all_categories,
        'cart_count': cart_count,
    }
