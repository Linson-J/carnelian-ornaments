from functools import wraps

from django.shortcuts import redirect


def admin_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.session.get('admin_authenticated'):
            return redirect('admin_login')
        return view_func(request, *args, **kwargs)

    return wrapper


def login_required_ajax(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.http import JsonResponse
            return JsonResponse({'login_required': True}, status=401)
        return view_func(request, *args, **kwargs)

    return wrapper

