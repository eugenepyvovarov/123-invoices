from django.urls import path

from . import views

urlpatterns = [
    path('metadata/', views.authorization_server_metadata, name='mcp_oauth_metadata'),
    path('introspect/', views.introspect, name='mcp_oauth_introspect'),
]
