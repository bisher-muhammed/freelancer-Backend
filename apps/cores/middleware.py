from channels.middleware import BaseMiddleware
from django.db import close_old_connections
from channels.db import database_sync_to_async


class JWTAuthMiddleware(BaseMiddleware):

    async def __call__(self, scope, receive, send):

        from django.contrib.auth.models import AnonymousUser
        from django.contrib.auth import get_user_model

        from rest_framework_simplejwt.tokens import AccessToken

        User = get_user_model()

        close_old_connections()

        scope["user"] = AnonymousUser()

        try:

            headers = dict(scope["headers"])

            raw_cookies = headers.get(b"cookie", b"").decode()

            cookie_dict = {}

            for item in raw_cookies.split(";"):

                if "=" in item:

                    key, value = item.strip().split("=", 1)

                    cookie_dict[key] = value

            token = cookie_dict.get("access_token")

            if token:

                access_token = AccessToken(token)

                user = await database_sync_to_async(
                    User.objects.get
                )(id=access_token["user_id"])

                scope["user"] = user

                print("✅ WebSocket authenticated:", user)

            else:

                print("❌ No access cookie found")

        except Exception as e:

            print("❌ WebSocket auth error:", e)

        return await super().__call__(scope, receive, send)
