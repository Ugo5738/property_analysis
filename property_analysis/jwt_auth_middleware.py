from channels.db import database_sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from jwt import decode as jwt_decode
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import UntypedToken


@database_sync_to_async
def get_user(user_id):
    User = get_user_model()
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return AnonymousUser()

class JWTAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        headers = dict(scope['headers'])
        if b'authorization' in headers:
            try:
                token_name, token_key = headers[b'authorization'].decode().split()
                if token_name == 'Bearer':
                    # Decode the token
                    UntypedToken(token_key)
                    decoded_data = jwt_decode(token_key, settings.SECRET_KEY, algorithms=["HS256"])
                    user_id = decoded_data['user_id']
                    scope['user'] = await get_user(user_id)
            except (InvalidToken, TokenError, KeyError):
                scope['user'] = AnonymousUser()
        else:
            scope['user'] = AnonymousUser()

        return await self.app(scope, receive, send)
