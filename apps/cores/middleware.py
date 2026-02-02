from urllib.parse import parse_qs
from channels.middleware import BaseMiddleware
from django.db import close_old_connections

class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        # Lazy imports to avoid AppRegistryNotReady
        from django.contrib.auth.models import AnonymousUser
        from django.contrib.auth import get_user_model
        from rest_framework_simplejwt.tokens import AccessToken

        User = get_user_model()
        close_old_connections()

        query_string = parse_qs(scope.get("query_string", b"").decode())
        token = query_string.get("token")
        scope["user"] = AnonymousUser()

        if token:
            try:
                access_token = AccessToken(token[0])
                user = await User.objects.aget(id=access_token["user_id"])
                scope["user"] = user
                print("✅ JWT user resolved:", user)
            except Exception as e:
                print("❌ JWT error:", e)

        return await super().__call__(scope, receive, send)
