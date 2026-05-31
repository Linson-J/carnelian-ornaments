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
    # path('api/', include('shop.api_urls')),
    path('swagger/', schema_view.with_ui('swagger'), name='swagger'),
]