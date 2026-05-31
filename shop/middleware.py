# ─── FILE 5: shop/middleware.py  (CREATE NEW) ─────────────────

import hmac
from django.http import HttpResponseForbidden
from django.conf import settings

class AdminAPITokenMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/secret-admin/'):
            incoming = request.META.get(settings.ADMIN_API_HEADER, '')
            expected = settings.ADMIN_API_SECRET
            if not hmac.compare_digest(incoming, expected):
                return HttpResponseForbidden('<h1>403 Forbidden</h1>')
        return self.get_response(request)