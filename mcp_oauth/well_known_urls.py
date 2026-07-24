from django.urls import path

from . import views

urlpatterns = [
    path('oauth-authorization-server', views.authorization_server_metadata, name='mcp_oauth_as_metadata'),
    path('oauth-protected-resource', views.protected_resource_metadata, name='mcp_oauth_prm'),
]
