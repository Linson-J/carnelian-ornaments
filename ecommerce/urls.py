from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # path('django-admin/', admin.site.urls),  # Commented out in favor of custom /admin-panel/
    path('api/', include('shop.api_urls')),
    path('', include('shop.urls')),
    path('admin-panel/', include('shop.admin_urls')),
    path('accounts/', include('allauth.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
