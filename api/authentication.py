from django.utils.crypto import constant_time_compare
from rest_framework import authentication, exceptions

from accounts.models import ApiToken


class ApiTokenAuthentication(authentication.BaseAuthentication):
    """Authenticate API clients with account-bound Bearer tokens."""

    keyword = 'Bearer'

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode('utf-8')
        if not header:
            return None

        parts = header.split()
        if len(parts) != 2 or parts[0].lower() != self.keyword.lower():
            raise exceptions.AuthenticationFailed('Invalid API token.')

        token = parts[1]
        prefix = ApiToken.parse_token(token)
        if not prefix:
            raise exceptions.AuthenticationFailed('Invalid API token.')

        token_hash = ApiToken.make_secret_hash(token)
        candidates = ApiToken.objects.select_related('owner').filter(prefix=prefix)
        api_token = None
        for candidate in candidates:
            if constant_time_compare(candidate.secret_hash, token_hash):
                api_token = candidate
                break

        if api_token is None:
            raise exceptions.AuthenticationFailed('Invalid API token.')
        if api_token.is_revoked:
            raise exceptions.AuthenticationFailed('API token has been revoked.')
        if api_token.is_expired:
            raise exceptions.AuthenticationFailed('API token has expired.')
        if not api_token.owner.is_active:
            raise exceptions.AuthenticationFailed('API token owner is inactive.')

        api_token.mark_used()
        return api_token.owner, api_token

    def authenticate_header(self, request):
        return self.keyword
