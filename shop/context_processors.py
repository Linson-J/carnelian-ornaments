from .models import Category


def footer_context(request):
    categories = Category.objects.filter(
        status=Category.Status.ACTIVE,
    ).order_by('name')[:6]
    return {'footer_categories': categories}
