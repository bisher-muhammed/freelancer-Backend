from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from apps.cores.media import protected_media
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
    TokenBlacklistView
)
from drf_spectacular.views import (
    SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

)


urlpatterns = [
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),




    path('api/', include('apps.users.urls')),
    path('api/',include('apps.notifications.urls')),
    path('api/',include('apps.tracking.urls')),
    path('api/',include('apps.freelancer.urls')),
    path('api/', include('apps.adminpanel.urls')),
    path('api/',include('apps.applications.urls')),
    path('api/',include('apps.contract.urls')),
    path('api/',include('apps.billing.urls')),
    path('api/',include('apps.finance.urls')),
    path('admin/', admin.site.urls),
    
]


if settings.DEBUG or settings.SERVE_MEDIA:
    # Uploads go through an access check (screenshots, contract documents and
    # resumes are private). If a proxy serves /media/ directly instead, it
    # bypasses this check — route /media/ to Django in that case.
    urlpatterns += [
        re_path(
            r"^%s(?P<path>.*)$" % settings.MEDIA_URL.lstrip("/"),
            protected_media,
        ),
    ]

