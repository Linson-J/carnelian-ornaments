from .models import Category


def footer_context(request):
    categories = Category.objects.filter(
        status=Category.Status.ACTIVE,
    ).order_by('name')[:6]
    all_categories = Category.objects.filter(
        status=Category.Status.ACTIVE,
    ).prefetch_related('products').order_by('name')
    return {
        'footer_categories': categories,
        'all_categories': all_categories,
    }
