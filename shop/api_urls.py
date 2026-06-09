# ─── shop/api_urls.py ─────────────────────────────────────────
from django.urls import path
from .api_views import (
    CategoryListCreateView,
    CategoryDetailView,
    ProductListCreateView,
    ProductDetailView,
    ProductImageView,
    CarouselListCreateView,
    CarouselDetailView,
)

urlpatterns = [
    # Categories
    path('categories/',      CategoryListCreateView.as_view()),
    path('categories/<int:pk>/', CategoryDetailView.as_view()),

    # Products
    path('products/',            ProductListCreateView.as_view()),
    path('products/<int:pk>/',   ProductDetailView.as_view()),

    # Product image gallery
    path('products/<int:pk>/images/',                  ProductImageView.as_view()),
    path('products/<int:pk>/images/<int:image_id>/',   ProductImageView.as_view()),

    # Carousel
    path('carousel/',            CarouselListCreateView.as_view()),
    path('carousel/<int:pk>/',   CarouselDetailView.as_view()),
]