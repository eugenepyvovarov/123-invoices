from django_filters import rest_framework as filters
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from api.scoping import accessible_issuer_ids_for_user, accessible_issuers_for_user
from api.serializers import (
    AccountSerializer,
    BankAccountSerializer,
    CustomerSerializer,
    IssuerSerializer,
    ProjectSerializer,
)
from invoices.models import Customer, IssuerBankAccount, Project


class IssuerScopedMixin:
    issuer_lookup = 'issuer_id'

    def accessible_issuer_ids(self):
        return accessible_issuer_ids_for_user(self.request.user)

    def filter_by_issuer_param(self, queryset):
        issuer_id = self.request.query_params.get('issuer')
        if issuer_id:
            queryset = queryset.filter(**{self.issuer_lookup: issuer_id})
        return queryset


class MeView(APIView):
    """Return metadata for the authenticated API account."""

    def get(self, request):
        return Response({
            'account': AccountSerializer(request.user).data,
            'issuers': IssuerSerializer(
                accessible_issuers_for_user(request.user).prefetch_related('bank_accounts'),
                many=True,
                context={'request': request},
            ).data,
        })


class IssuerViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = IssuerSerializer
    search_fields = ['company__name', 'company__contact_email']
    ordering_fields = ['id', 'company__name']
    ordering = ['company__name', 'id']

    def get_queryset(self):
        return accessible_issuers_for_user(self.request.user).prefetch_related('bank_accounts')


class BankAccountViewSet(IssuerScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = BankAccountSerializer
    filterset_fields = ['issuer', 'is_active', 'is_default', 'payment_method']
    search_fields = ['label', 'payment_method', 'account_details', 'issuer__company__name']
    ordering_fields = ['id', 'issuer', 'sort_order', 'label', 'created_at', 'updated_at']
    ordering = ['issuer', 'sort_order', 'label', 'id']

    def get_queryset(self):
        return IssuerBankAccount.objects.select_related('issuer', 'issuer__company').filter(
            issuer_id__in=self.accessible_issuer_ids()
        )


class CustomerFilter(filters.FilterSet):
    issuer = filters.NumberFilter(field_name='issuer_id')
    external_id = filters.CharFilter(field_name='external_id')
    is_active = filters.BooleanFilter(field_name='is_active')

    class Meta:
        model = Customer
        fields = ['issuer', 'external_id', 'is_active']


class CustomerViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerSerializer
    filterset_class = CustomerFilter
    search_fields = [
        'external_id', 'company__name', 'company__contact_name', 'company__contact_email',
        'billing_email', 'billing_contact_name',
    ]
    ordering_fields = ['id', 'external_id', 'company__name', 'is_active']
    ordering = ['company__name', 'id']

    def get_queryset(self):
        return Customer.objects.select_related(
            'issuer', 'company', 'currency', 'payment_term'
        ).filter(issuer_id__in=accessible_issuer_ids_for_user(self.request.user))


class ProjectFilter(filters.FilterSet):
    issuer = filters.NumberFilter(field_name='issuer_id')
    customer = filters.NumberFilter(field_name='customer_id')
    status = filters.CharFilter(field_name='status')
    external_id = filters.CharFilter(field_name='external_id')

    class Meta:
        model = Project
        fields = ['issuer', 'customer', 'status', 'external_id']


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    filterset_class = ProjectFilter
    search_fields = [
        'external_id', 'title', 'project_code', 'billing_reference',
        'customer__company__name',
    ]
    ordering_fields = ['id', 'external_id', 'title', 'project_code', 'status', 'created_at', 'updated_at']
    ordering = ['title', 'id']

    def get_queryset(self):
        return Project.objects.select_related(
            'issuer', 'customer', 'customer__company', 'payment_term'
        ).filter(issuer_id__in=accessible_issuer_ids_for_user(self.request.user))
