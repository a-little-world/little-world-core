from django.middleware.csrf import CsrfViewMiddleware
from django.utils.deprecation import MiddlewareMixin


class CustomCsrfViewMiddleware(CsrfViewMiddleware):
    """
    Custom CSRF middleware that allows bypassing CSRF checks for requests
    with a valid X-CSRF-Bypass-Token header.
    """
    
    def process_view(self, request, callback, callback_args, callback_kwargs):
        # Check if CSRF bypass is requested
        if hasattr(request, '_csrf_bypass') and request._csrf_bypass:
            # Skip CSRF validation for this request
            return None
        
        # Proceed with normal CSRF validation
        return super().process_view(request, callback, callback_args, callback_kwargs) 