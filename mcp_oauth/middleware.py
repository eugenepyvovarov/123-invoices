from django.conf import settings
from django.http import JsonResponse

from .validators import configured_resource, normalized_resource


class ResourceIndicatorMiddleware:
    """Require exact MCP resource indicators for OAuth protocol requests."""

    paths = ('/o/authorize/', '/o/token/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path in self.paths and getattr(settings, 'MCP_OAUTH_REQUIRE_RESOURCE', True):
            resource = normalized_resource(request.GET.get('resource') or request.POST.get('resource'))
            if resource != configured_resource():
                return JsonResponse(
                    {'error': 'invalid_target', 'error_description': 'The OAuth resource indicator must exactly match the MCP resource.'},
                    status=400,
                )
        return self.get_response(request)
