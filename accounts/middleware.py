from urllib.parse import quote

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch


class LoginRequiredMiddleware:
    """
    Redirect anonymous users to the login page for all non-exempt paths.

    Exemptions: login/logout endpoints, admin URLs, static/media assets, and any paths
    provided via the optional LOGIN_EXEMPT_URLS setting (list of callables or strings).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated or self._is_exempt(request):
            return self.get_response(request)

        login_url = reverse('accounts:login')
        next_param = quote(request.get_full_path())
        return redirect(f"{login_url}?next={next_param}")

    def _is_exempt(self, request) -> bool:
        path = request.path

        # Static/media assets
        static_url = getattr(settings, 'STATIC_URL', None)
        media_url = getattr(settings, 'MEDIA_URL', None)
        if static_url and path.startswith(static_url):
            return True
        if media_url and path.startswith(media_url):
            return True

        # Admin section should keep its own login workflow
        if path.startswith('/admin/'):
            return True

        exempt_paths = self._exempt_paths()
        if path in exempt_paths:
            return True

        for prefix in getattr(settings, 'LOGIN_EXEMPT_URLS', []):
            if path.startswith(prefix):
                return True
        return False

    def _exempt_paths(self):
        paths = []
        try:
            paths.append(reverse('accounts:login'))
        except NoReverseMatch:
            pass
        try:
            paths.append(reverse('accounts:logout'))
        except NoReverseMatch:
            pass
        try:
            paths.append(reverse('accounts:otp_verify'))
        except NoReverseMatch:
            pass
        return paths
