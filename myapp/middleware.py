# middleware.py
from django.shortcuts import redirect
from django.conf import settings

class SimplePasswordMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        if not request.session.get('password_verified'):
            if request.path != '/verify-password/' and not request.path.startswith('/static/'):
                return redirect('/verify-password/')
        return self.get_response(request)

