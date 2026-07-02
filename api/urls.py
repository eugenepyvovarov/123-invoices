from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny
from rest_framework.routers import DefaultRouter

from api.views import BankAccountViewSet, CustomerViewSet, IssuerViewSet, MeView, ProjectViewSet


app_name = 'api'

router = DefaultRouter()
router.register('issuers', IssuerViewSet, basename='issuer')
router.register('bank-accounts', BankAccountViewSet, basename='bankaccount')
router.register('customers', CustomerViewSet, basename='customer')
router.register('projects', ProjectViewSet, basename='project')

urlpatterns = [
    path('', include(router.urls)),
    path('me/', MeView.as_view(), name='me'),
    path('schema/', SpectacularAPIView.as_view(permission_classes=[AllowAny]), name='schema'),
    path(
        'docs/',
        SpectacularSwaggerView.as_view(url_name='api:schema', permission_classes=[AllowAny]),
        name='docs',
    ),
]
