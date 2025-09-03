from django.conf import settings
from django.shortcuts import render
from django.utils import translation

from rest_framework.authentication import TokenAuthentication
from management.models.state import State


def responde_404(request):
    response = render(request, "404.html", {})
    response.status_code = 404
    return response


EXTRA_USER_AUTHORIZATION_ROUTES = (
    {
        "/db": {
            "check": lambda u: u.state.has_extra_user_permission(State.ExtraUserPermissionChoices.DATABASE_SCHEMA),
            "else": lambda r: responde_404(request=r),
        },
        "/api/schema": {
            "check": lambda u: u.state.has_extra_user_permission(State.ExtraUserPermissionChoices.API_SCHEMAS),
            "else": lambda r: responde_404(request=r),
        },
    }
    if not settings.DEBUG
    else {}
)

# In development it ok if everybody can see the admin paths
IF_NOT_ADMIN_404_ROUTES = (
    []
    if settings.DEBUG
    else [
        "/admin",
        "/admin_chat",
    ]
)


def _is_blocked_route(path):
    for route in IF_NOT_ADMIN_404_ROUTES:
        if path.startswith(route):
            return True
    return False


def _requires_extra_user_permission(path):
    # Only applicable for users, admins dont need these extra permissions
    for route in list(EXTRA_USER_AUTHORIZATION_ROUTES.keys()):
        try:
            if path.startswith(route):
                return True, EXTRA_USER_AUTHORIZATION_ROUTES[route]
        except:
            pass  # If the check fails we assume the user doesn't have reqired permissions
    return False, None


def _404_if_not_staff(request, get_response, allow_management_user=False):
    if not request.user.is_authenticated or not request.user.is_staff:
        if (
            allow_management_user
            and request.user.is_authenticated
            and (request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER))
        ):
            return get_response(request)
        return responde_404(request)
    else:
        return get_response(request)


class AdminPathBlockingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith("/admin/login"):
            # See what I did here, you can only render the admin login if you add `?opensesame`
            if not settings.DEBUG and settings.ADMIN_OPEN_KEYPHRASE not in request.GET:
                return _404_if_not_staff(request, self.get_response)
        else:
            if _is_blocked_route(path):
                if "matching" in path:
                    return _404_if_not_staff(request, self.get_response, allow_management_user=True)
                return _404_if_not_staff(request, self.get_response)

            # Now check for extra user permissions,
            # Sometimes we might want to allow specific users to view the api/schema for example
            extra_auth, auth_tools = _requires_extra_user_permission(path)
            if (extra_auth and auth_tools) and not (request.user.is_authenticated and request.user.is_staff):
                has_permission = False
                try:
                    has_permission = not auth_tools["check"](request.user)
                    if has_permission:
                        return auth_tools["else"](request)
                except:
                    return auth_tools["else"](request)

        return self.get_response(request)


USE_TAG_HEADER = "HTTP_X_USETAGSONLY"


class OverwriteSessionLangIfAcceptLangHeaderSet:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """
        We add our own http header that can be used to for usage of **only** translations tags for the frontends!
        """
        if USE_TAG_HEADER in request.META and request.META[USE_TAG_HEADER].lower() in ("true", "1", "t"):
            with translation.override("tag"):
                return self.get_response(request)
        else:
            return self.get_response(request)


class CsrfBypassMiddleware:
    """
    Middleware that allows bypassing CSRF checks for requests with a valid
    X-CSRF-Bypass-Token header that matches tokens from environment variable.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        # Get bypass tokens from environment variable
        self.bypass_tokens = self._get_bypass_tokens()
    
    def _get_bypass_tokens(self):
        """Get CSRF bypass tokens from settings."""
        from django.conf import settings
        return getattr(settings, 'CSRF_BYPASS_TOKENS', [])
    
    def __call__(self, request):
        print("--------------------------------TBS:")
        print(request.META)
        bypass_token = request.META.get('HTTP_X_CSRF_BYPASS_TOKEN')
        requested_with_header = request.META.get('HTTP_X_REQUESTED_WITH')
        print("--------------------------------TBS:")
        print(bypass_token)
        print(requested_with_header)
        
        if bypass_token and bypass_token in self.bypass_tokens:
            request._csrf_bypass = True
            setattr(request, "_dont_enforce_csrf_checks", True)
            # Set flag to modify session cookie SameSite attribute
            request._modify_session_cookie_samesite = True
        
        return self.get_response(request)


class SessionCookieSameSiteMiddleware:
    """
    Middleware that modifies session cookies to set SameSite=None
    when CSRF bypass is requested, allowing cross-origin requests.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        
        # Check if we need to modify session cookie SameSite attribute
        if hasattr(request, '_modify_session_cookie_samesite') and request._modify_session_cookie_samesite:
            # Get the session cookie name from Django settings
            from django.conf import settings
            session_cookie_name = getattr(settings, 'SESSION_COOKIE_NAME', 'sessionid')
            
            # Check if session cookie exists in response
            if session_cookie_name in response.cookies:
                cookie = response.cookies[session_cookie_name]
                # Set SameSite=None to allow cross-origin requests
                cookie['samesite'] = 'None'
                # Note: SameSite=None requires Secure=True for HTTPS
                if not settings.DEBUG:
                    cookie['secure'] = True
        
        return response