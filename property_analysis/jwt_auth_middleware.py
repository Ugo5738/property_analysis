from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from jwt import decode as jwt_decode
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken, UntypedToken

from accounts.models import User  # Direct import of your User model
from property_analysis.config.logging_config import configure_logger

logger = configure_logger(__name__)


class JWTAuthMiddleware(BaseMiddleware):
    def __init__(self, inner):
        super().__init__(inner)
        self.inner = inner

    @database_sync_to_async
    def get_user(self, user_id):
        try:
            user = User.objects.get(id=user_id)
            print(f"Found user with phone: {user.phone}")

            # Set is_authenticated explicitly
            setattr(user, "_is_authenticated", True)
            logger.info(f"Successfully retrieved user {user_id}")
            return user

        except User.DoesNotExist:
            logger.warning(f"User with id {user_id} does not exist")
            anonymous_user = AnonymousUser()
            setattr(anonymous_user, "_is_authenticated", False)
            return anonymous_user
        except Exception as e:
            logger.error(f"Unexpected error retrieving user {user_id}: {str(e)}")
            anonymous_user = AnonymousUser()
            setattr(anonymous_user, "_is_authenticated", False)
            return anonymous_user

    async def __call__(self, scope, receive, send):
        try:
            query_string = scope.get("query_string", b"").decode()
            query_params = parse_qs(query_string)
            token = query_params.get("token", [None])[0]

            if token:
                try:
                    access_token = AccessToken(token)
                    user_id = access_token["user_id"]

                    user = await self.get_user(user_id)

                    if user and user.is_authenticated:
                        scope["user"] = user
                        print(
                            f"Set authenticated user in scope with phone: {user.phone}"
                        )
                    else:
                        print("Setting AnonymousUser due to no valid user")
                        scope["user"] = AnonymousUser()

                except (InvalidToken, TokenError) as e:
                    logger.warning(f"Invalid token: {str(e)}")
                    scope["user"] = AnonymousUser()
                except Exception as e:
                    logger.error(f"Unexpected error in middleware: {str(e)}")
                    scope["user"] = AnonymousUser()
            else:
                scope["user"] = AnonymousUser()

        except Exception as e:
            logger.error(f"Error in middleware: {str(e)}")
            scope["user"] = AnonymousUser()

        return await self.inner(scope, receive, send)
