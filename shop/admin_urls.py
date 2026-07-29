from django.urls import path

from . import admin_views

urlpatterns = [
    path('login/', admin_views.admin_login, name='admin_login'),
    path('logout/', admin_views.admin_logout, name='admin_logout'),
    path('', admin_views.admin_dashboard, name='admin_dashboard'),
    path('products/', admin_views.admin_products, name='admin_products'),
    path('products/add/', admin_views.add_product, name='add_product'),
    path('products/<int:pk>/edit/', admin_views.edit_product, name='edit_product'),
    path('products/<int:pk>/delete/', admin_views.delete_product, name='delete_product'),
    path('categories/', admin_views.admin_categories, name='admin_categories'),
    path('carousel/', admin_views.admin_carousel, name='admin_carousel'),
    path('carousel/add/', admin_views.add_carousel_item, name='add_carousel_item'),
    path('carousel/<int:pk>/edit/', admin_views.edit_carousel_item, name='edit_carousel_item'),
    path('carousel/<int:pk>/delete/', admin_views.delete_carousel_item, name='delete_carousel_item'),
    path('home-sections/', admin_views.admin_home_sections, name='admin_home_sections'),
    path('offers/', admin_views.admin_offers, name='admin_offers'),
    path('login-logs/', admin_views.admin_login_logs, name='admin_login_logs'),
    path('settings/', admin_views.admin_settings, name='admin_settings'),
]
