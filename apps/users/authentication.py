# apps/users/authentication.py

from django.conf import settings
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication

SAFE_METHODS = ("GET", "HEAD", "OPTIONS", "TRACE")


def _origin_allowed(request, origin):
    if origin in getattr(settings, "CORS_ALLOWED_ORIGINS", []):
        return True
    # Same-origin requests (e.g. the browsable API / Swagger on the API host)
    return origin == f"{request.scheme}://{request.get_host()}"


class CookieJWTAuthentication(JWTAuthentication):
    """
    JWT read from the httpOnly ``access_token`` cookie.

    Cookies are sent automatically by browsers, so state-changing requests
    are checked against the Origin header (CSRF defence). Requests without
    an Origin header (non-browser clients such as the desktop tracker) are
    not affected; SameSite=Lax already keeps cross-site form posts from
    carrying the cookie.
    """

    def authenticate(self, request):

        raw_token = request.COOKIES.get("access_token")

        if raw_token is None:
            return None

        if request.method not in SAFE_METHODS:
            origin = request.META.get("HTTP_ORIGIN")
            if origin and not _origin_allowed(request, origin):
                raise PermissionDenied("Cross-site request blocked.")

        validated_token = self.get_validated_token(raw_token)

        return self.get_user(validated_token), validated_token
