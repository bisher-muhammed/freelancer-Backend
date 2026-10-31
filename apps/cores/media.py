"""
Access-controlled serving of uploaded files under MEDIA_URL.

Screenshots, contract documents and resumes contain private data, so they
are no longer world-readable. File URLs are unchanged (/media/<path>), and
browsers send the auth cookie with same-site image/link requests.
"""
from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.http import Http404
from django.views.static import serve

from apps.users.authentication import CookieJWTAuthentication

PUBLIC_PREFIXES = ("client_profiles/", "freelancer_profiles/")
AUTHENTICATED_PREFIXES = ("freelancer_resumes/",)


def _request_user(request):
    try:
        result = CookieJWTAuthentication().authenticate(request)
    except Exception:
        return None
    if not result:
        return None
    user = result[0]
    return user if user.is_active else None


def _is_contract_party(user, contract):
    return user == contract.offer.client or user == contract.offer.freelancer.user


def _can_access(user, path):
    if user.is_staff:
        return True

    if path.startswith(AUTHENTICATED_PREFIXES):
        return True

    if path.startswith("screenshots/"):
        from apps.tracking.models import Screenshot

        shot = (
            Screenshot.objects
            .select_related("block__session__user", "block__session__contract__offer__client",
                            "block__session__contract__offer__freelancer__user")
            .filter(image=path)
            .first()
        )
        if not shot:
            return False
        session = shot.block.session
        return user == session.user or user == session.contract.offer.client

    if path.startswith("contract_documents/"):
        from apps.contract.models import ContractDocument

        doc = (
            ContractDocument.objects
            .select_related("contract__offer__client", "contract__offer__freelancer__user")
            .filter(file=path)
            .first()
        )
        return bool(doc) and _is_contract_party(user, doc.contract)

    return False


def protected_media(request, path):
    if not path.startswith(PUBLIC_PREFIXES):
        user = _request_user(request)
        # 404 rather than 403 so private file names are not confirmed
        if user is None or not _can_access(user, path):
            raise Http404("File not found")

    try:
        response = serve(request, path, document_root=settings.MEDIA_ROOT)
    except SuspiciousFileOperation:
        # e.g. "../" traversal attempts
        raise Http404("File not found")
    if not path.startswith(PUBLIC_PREFIXES):
        response["Cache-Control"] = "private, max-age=300"
    return response
