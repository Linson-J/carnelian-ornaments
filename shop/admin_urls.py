from django.urls import path
from . import admin_views

urlpatterns = [
    path('',          admin_views.admin_dashboard, name='admin_dashboard'),  # /admin-panel/
    path('login/',    admin_views.admin_login,      name='admin_login'),      # /admin-panel/login/
    path('logout/',   admin_views.admin_logout,     name='admin_logout'),     # /admin-panel/logout/
    path('products/', admin_views.admin_products,   name='admin_products'),   # /admin-panel/products/
    path('add-product/', admin_views.add_product,   name='add_product'),      # /admin-panel/add-product/
]
