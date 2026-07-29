from django.urls import path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view

from . import views

schema_view = get_schema_view(
    openapi.Info(
        title="Ecommerce API",
        default_version='v1',
    ),
)
urlpatterns = [
    path('', views.home, name='home'),
    path('shop/', views.shop_all, name='shop_all'),
    path('categories/', views.categories_all, name='categories_all'),
    path('products/<slug:slug>/', views.product_detail, name='product_detail'),
    path('newsletter/subscribe/', views.newsletter_subscribe, name='newsletter_subscribe'),
    path('swagger/', schema_view.with_ui('swagger'), name='swagger'),
]
