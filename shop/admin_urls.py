from django.urls import path
from . import admin_views

urlpatterns = [
    # Auth
    path('login/',   admin_views.admin_login,  name='admin_login'),
    path('logout/',  admin_views.admin_logout, name='admin_logout'),

    # Dashboard
    path('',         admin_views.admin_dashboard, name='admin_dashboard'),

    # Products
    path('products/',                  admin_views.admin_products,  name='admin_products'),
    path('products/add/',              admin_views.add_product,     name='add_product'),
    path('products/<int:pk>/edit/',    admin_views.edit_product,    name='edit_product'),
    path('products/<int:pk>/delete/',  admin_views.delete_product,  name='delete_product'),

    # Carousel
    path('carousel/', admin_views.admin_carousel, name='admin_carousel'),
    path('carousel/add/', admin_views.add_carousel_item, name='add_carousel_item'),
    path('carousel/<int:pk>/edit/', admin_views.edit_carousel_item, name='edit_carousel_item'),
    path('carousel/<int:pk>/delete/', admin_views.delete_carousel_item, name='delete_carousel_item'),

    # Security
    path('login-logs/',  admin_views.admin_login_logs, name='admin_login_logs'),
]

# ─── Full URL map ─────────────────────────────────────────────
# /admin-panel/               → dashboard
# /admin-panel/login/         → login page
# /admin-panel/logout/        → logout
# /admin-panel/products/      → product list
# /admin-panel/products/add/  → add product form
# /admin-panel/products/3/edit/   → edit product id=3
# /admin-panel/products/3/delete/ → delete product id=3  (POST only)
# /admin-panel/login-logs/    → security logs
