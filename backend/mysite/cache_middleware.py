"""Cache-Control middleware for Django dev server.

Static assets (CSS/JS/images) get long cache. HTML pages get no-cache.
"""
import re

STATIC_CTYPES = re.compile(
    r'text/(css|javascript)|image/|font/|application/(javascript|font)'
)


class CacheControlMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Check by URL path first
        path = request.path.lower()
        if path.startswith('/static/') or path.startswith('/media/'):
            response['Cache-Control'] = 'public, max-age=3600'
        elif STATIC_CTYPES.search(response.get('Content-Type', '')):
            response['Cache-Control'] = 'public, max-age=3600'
        else:
            response['Cache-Control'] = 'no-cache'

        return response
