from django.urls import path
from .api_views import ProductAPI

urlpatterns = [
    path('products/', ProductAPI.as_view()),
]