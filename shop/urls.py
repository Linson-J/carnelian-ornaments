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
    path('products/<slug:slug>/review/', views.add_product_review, name='add_product_review'),
    path('newsletter/subscribe/', views.newsletter_subscribe, name='newsletter_subscribe'),
    
    # Standard Django login routes commented out & redirected to auth modal:
    # path('login/', auth_views.LoginView.as_view(), name='django_standard_login'),
    path('login/', views.login_redirect_view, name='login'),
    path('accounts/login/', views.login_redirect_view),
    path('accounts/signup/', views.login_redirect_view),

    # AJAX Authentication
    path('auth/login/', views.ajax_login, name='ajax_login'),
    path('auth/signup/', views.ajax_signup, name='ajax_signup'),
    path('auth/logout/', views.ajax_logout, name='ajax_logout'),
    path('auth/otp/request/', views.request_otp, name='request_otp'),
    path('auth/otp/verify/', views.verify_otp, name='verify_otp'),
    path('auth/otp/reset/', views.reset_password, name='reset_password'),
    
    # AJAX Actions
    path('cart/', views.cart_page, name='cart_page'),
    path('cart/add/', views.add_to_cart, name='add_to_cart'),
    path('cart/update/', views.update_cart_quantity, name='update_cart_quantity'),
    path('cart/remove/', views.remove_from_cart, name='remove_from_cart'),
    path('wishlist/', views.wishlist_page, name='wishlist_page'),
    path('wishlist/add/', views.add_to_wishlist, name='add_to_wishlist'),
    path('wishlist/remove/', views.remove_from_wishlist, name='remove_from_wishlist'),
    path('buy-now/', views.buy_now, name='buy_now'),
    path('checkout/', views.checkout_page, name='checkout_page'),
    path('checkout/verify-address/', views.verify_checkout_address, name='verify_checkout_address'),
    path('checkout/place-order/', views.place_order, name='place_order'),
    path('checkout/order-success/<int:order_id>/', views.order_success, name='order_success'),
    
    # User Profile & Saved Address
    path('profile/', views.profile_page, name='profile_page'),
    path('profile/address/save/', views.save_profile_address, name='save_profile_address'),
    
    path('swagger/', schema_view.with_ui('swagger'), name='swagger'),
]
