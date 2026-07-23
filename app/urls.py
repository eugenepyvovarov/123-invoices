from django.conf import settings
from django.contrib import admin
from django.http import Http404, HttpResponse
from django.urls import include, path, re_path
from django.views.static import serve


def serve_media(request, path, **kwargs):
    document_root = getattr(settings, 'MEDIA_ROOT', None)
    if not document_root:
        raise Http404()
    response = serve(request, path, document_root=document_root, **kwargs)
    if getattr(response, 'streaming', False):
        non_streaming_response = HttpResponse(
            b''.join(response.streaming_content),
            status=response.status_code,
            content_type=response.get('Content-Type'),
        )
        for header, value in response.items():
            if header.lower() == 'content-type':
                continue
            non_streaming_response[header] = value
        return non_streaming_response
    return response
urlpatterns = [
    path('.well-known/', include('mcp_oauth.well_known_urls')),
    path('oauth/', include('mcp_oauth.urls')),
    path('o/', include('oauth2_provider.urls', namespace='oauth2_provider')),
    path('api/', include('api.urls')),
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('', include('invoices.urls')),
    re_path(r'^media/(?P<path>.*)$', serve_media),
]
