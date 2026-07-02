from django_filters import rest_framework as filters
from django.http import FileResponse
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from api.scoping import accessible_issuer_ids_for_user, accessible_issuers_for_user
from api.serializers import (
    AccountSerializer,
    BankAccountSerializer,
    CustomerSerializer,
    InvoiceSerializer,
    IssuerSerializer,
    ProjectSerializer,
)
from invoices.models import Customer, Invoice, IssuerBankAccount, Project
from invoices.services.cached_totals import recalc_invoice_amounts
from invoices.views import invalidate_dashboard_cache, save_invoice_pdf


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


class InvoiceFilter(filters.FilterSet):
    issuer = filters.NumberFilter(field_name='issuer_id')
    customer = filters.NumberFilter(field_name='customer_id')
    project = filters.NumberFilter(field_name='project_id')
    status = filters.CharFilter(field_name='status')
    external_id = filters.CharFilter(field_name='external_id')
    issued_after = filters.DateFilter(field_name='issued_date', lookup_expr='gte')
    issued_before = filters.DateFilter(field_name='issued_date', lookup_expr='lte')
    due_after = filters.DateFilter(field_name='due_date', lookup_expr='gte')
    due_before = filters.DateFilter(field_name='due_date', lookup_expr='lte')

    class Meta:
        model = Invoice
        fields = [
            'issuer', 'customer', 'project', 'status', 'external_id',
            'issued_after', 'issued_before', 'due_after', 'due_before',
        ]


class InvoiceViewSet(viewsets.ModelViewSet):
    serializer_class = InvoiceSerializer
    filterset_class = InvoiceFilter
    search_fields = [
        'external_id', 'reference_number', 'customer__company__name', 'project__title',
        'comment', 'notes',
    ]
    ordering_fields = [
        'id', 'external_id', 'reference_number', 'status', 'issued_date', 'due_date',
        'total_due', 'amount_due', 'created_at', 'updated_at',
    ]
    ordering = ['-issued_date', '-id']

    FINALIZED_STATUSES = {Invoice.STATUS_INVOICED, Invoice.STATUS_OVERDUE, Invoice.STATUS_PAID}

    def get_queryset(self):
        return Invoice.objects.select_related(
            'issuer', 'customer', 'customer__company', 'project', 'bank_account', 'currency'
        ).prefetch_related('orderline_set').filter(
            issuer_id__in=accessible_issuer_ids_for_user(self.request.user)
        )

    def perform_create(self, serializer):
        invoice = serializer.save()
        invalidate_dashboard_cache(invoice.issuer_id)

    def perform_update(self, serializer):
        invoice = serializer.save()
        invalidate_dashboard_cache(invoice.issuer_id)

    def perform_destroy(self, instance):
        if instance.status in self.FINALIZED_STATUSES:
            raise ValidationError('Finalized invoices cannot be deleted through the API.')
        issuer_id = instance.issuer_id
        instance.delete()
        invalidate_dashboard_cache(issuer_id)

    @action(detail=True, methods=['post'], url_path='finalize')
    def finalize(self, request, pk=None):
        invoice = self.get_object()
        if invoice.status in self.FINALIZED_STATUSES:
            raise ValidationError('Invoice is already finalized.')
        if not invoice.issued_date:
            invoice.issued_date = timezone.localdate()
        invoice.calculate_totals(invoice.orderline_set.all())
        invoice.status = Invoice.STATUS_INVOICED
        invoice.save()
        recalc_invoice_amounts(invoice.pk)
        invalidate_dashboard_cache(invoice.issuer_id)
        serializer = self.get_serializer(invoice)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='generate-pdf')
    def generate_pdf(self, request, pk=None):
        invoice = self.get_object()
        invoice.calculate_totals(invoice.orderline_set.all())
        invoice.save()
        recalc_invoice_amounts(invoice.pk)
        try:
            save_invoice_pdf(request, invoice.pk)
        except RuntimeError as exc:
            raise ValidationError({'pdf': str(exc)}) from exc
        invoice.refresh_from_db()
        invalidate_dashboard_cache(invoice.issuer_id)
        serializer = self.get_serializer(invoice)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='download-pdf')
    def download_pdf(self, request, pk=None):
        invoice = self.get_object()
        if not getattr(invoice, 'pdf_document', None) or not invoice.pdf_document.name:
            raise NotFound('PDF is not available for this invoice.')
        try:
            return FileResponse(
                invoice.pdf_document.open('rb'),
                as_attachment=True,
                filename=invoice.pdf_document.name.rsplit('/', 1)[-1],
                content_type='application/pdf',
            )
        except FileNotFoundError as exc:
            raise NotFound('PDF is not available for this invoice.') from exc
