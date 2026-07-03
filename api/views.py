from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django_filters import rest_framework as filters
from django.http import FileResponse
from django.utils import timezone
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
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
    ExpenseSerializer,
    InvoiceSerializer,
    IssuerSerializer,
    PaymentApplicationSerializer,
    PaymentSerializer,
    ProjectSerializer,
)
from invoices.models import Customer, Expense, Invoice, IssuerBankAccount, Payment, PaymentApplication, Project
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


class PaymentFilter(filters.FilterSet):
    issuer = filters.NumberFilter(field_name='issuer_id')
    customer = filters.NumberFilter(field_name='customer_id')
    project = filters.NumberFilter(field_name='project_id')
    status = filters.CharFilter(field_name='status')
    external_id = filters.CharFilter(field_name='external_id')
    received_after = filters.DateFilter(field_name='received_at', lookup_expr='gte')
    received_before = filters.DateFilter(field_name='received_at', lookup_expr='lte')

    class Meta:
        model = Payment
        fields = ['issuer', 'customer', 'project', 'status', 'external_id', 'received_after', 'received_before']


class PaymentViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentSerializer
    filterset_class = PaymentFilter
    search_fields = ['external_id', 'memo', 'customer__company__name', 'project__title']
    ordering_fields = ['id', 'external_id', 'amount', 'received_at', 'created_at', 'updated_at']
    ordering = ['-received_at', '-id']

    def get_queryset(self):
        return Payment.objects.select_related(
            'issuer', 'customer', 'customer__company', 'project', 'currency'
        ).prefetch_related('applications', 'applications__invoice').filter(
            issuer_id__in=accessible_issuer_ids_for_user(self.request.user)
        )

    def _refresh_applications(self, payment):
        invoice_ids = list(payment.applications.values_list('invoice_id', flat=True))
        for invoice_id in invoice_ids:
            recalc_invoice_amounts(invoice_id)
        invalidate_dashboard_cache(payment.issuer_id)

    def perform_update(self, serializer):
        payment = serializer.save()
        self._refresh_applications(payment)

    def perform_destroy(self, instance):
        issuer_id = instance.issuer_id
        invoice_ids = list(instance.applications.values_list('invoice_id', flat=True))
        instance.delete()
        for invoice_id in invoice_ids:
            recalc_invoice_amounts(invoice_id)
        invalidate_dashboard_cache(issuer_id)


class PaymentApplicationFilter(filters.FilterSet):
    issuer = filters.NumberFilter(field_name='payment__issuer_id')
    payment = filters.NumberFilter(field_name='payment_id')
    invoice = filters.NumberFilter(field_name='invoice_id')
    external_id = filters.CharFilter(field_name='external_id')

    class Meta:
        model = PaymentApplication
        fields = ['issuer', 'payment', 'invoice', 'external_id']


class PaymentApplicationViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentApplicationSerializer
    filterset_class = PaymentApplicationFilter
    search_fields = ['external_id', 'payment__memo', 'invoice__reference_number']
    ordering_fields = ['id', 'applied_at', 'amount_applied']
    ordering = ['-applied_at', '-id']

    def get_queryset(self):
        return PaymentApplication.objects.select_related(
            'payment', 'payment__issuer', 'payment__customer', 'invoice', 'invoice__issuer'
        ).filter(payment__issuer_id__in=accessible_issuer_ids_for_user(self.request.user))

    def perform_create(self, serializer):
        application = serializer.save()
        recalc_invoice_amounts(application.invoice_id)
        invalidate_dashboard_cache(application.invoice.issuer_id)

    def perform_update(self, serializer):
        old_invoice_id = serializer.instance.invoice_id
        application = serializer.save()
        for invoice_id in {old_invoice_id, application.invoice_id}:
            recalc_invoice_amounts(invoice_id)
        invalidate_dashboard_cache(application.invoice.issuer_id)

    def perform_destroy(self, instance):
        invoice_id = instance.invoice_id
        issuer_id = instance.invoice.issuer_id
        instance.delete()
        recalc_invoice_amounts(invoice_id)
        invalidate_dashboard_cache(issuer_id)


class ExpenseFilter(filters.FilterSet):
    issuer = filters.NumberFilter(field_name='issuer_id')
    customer = filters.NumberFilter(field_name='customer_id')
    project = filters.NumberFilter(field_name='project_id')
    invoice = filters.NumberFilter(field_name='invoice_id')
    external_id = filters.CharFilter(field_name='external_id')
    paid_after = filters.DateFilter(field_name='paid_date', lookup_expr='gte')
    paid_before = filters.DateFilter(field_name='paid_date', lookup_expr='lte')
    has_attachment = filters.BooleanFilter(method='filter_has_attachment')

    class Meta:
        model = Expense
        fields = ['issuer', 'customer', 'project', 'invoice', 'external_id', 'paid_after', 'paid_before', 'has_attachment']

    def filter_has_attachment(self, queryset, name, value):
        if value:
            return queryset.exclude(attachment='').exclude(attachment__isnull=True)
        return queryset.filter(attachment='') | queryset.filter(attachment__isnull=True)


class ExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = ExpenseSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filterset_class = ExpenseFilter
    search_fields = ['external_id', 'description', 'customer__company__name', 'project__title']
    ordering_fields = ['id', 'external_id', 'paid_date', 'amount', 'created_at', 'updated_at']
    ordering = ['-paid_date', '-id']

    def get_queryset(self):
        return Expense.objects.select_related(
            'issuer', 'customer', 'customer__company', 'project', 'invoice'
        ).filter(issuer_id__in=accessible_issuer_ids_for_user(self.request.user))

    def perform_create(self, serializer):
        expense = serializer.save()
        invalidate_dashboard_cache(expense.issuer_id)

    def perform_update(self, serializer):
        expense = serializer.save()
        invalidate_dashboard_cache(expense.issuer_id)

    def perform_destroy(self, instance):
        issuer_id = instance.issuer_id
        instance.delete()
        invalidate_dashboard_cache(issuer_id)

    @action(detail=True, methods=['get'], url_path='download-attachment')
    def download_attachment(self, request, pk=None):
        expense = self.get_object()
        if not expense.attachment:
            raise NotFound('Attachment is not available for this expense.')
        try:
            return FileResponse(
                expense.attachment.open('rb'),
                as_attachment=True,
                filename=expense.attachment.name.rsplit('/', 1)[-1],
            )
        except FileNotFoundError as exc:
            raise NotFound('Attachment is not available for this expense.') from exc


def _decimal(value):
    return Decimal(value or 0).quantize(Decimal('0.01'))


def _month_iso(value):
    if value is None:
        return None
    if hasattr(value, 'date'):
        value = value.date()
    return value.isoformat()


class DashboardReportView(APIView):
    """Return account-level or issuer-filtered dashboard report JSON."""

    def get(self, request):
        issuer_ids = list(accessible_issuer_ids_for_user(request.user))
        selected_issuers = request.query_params.getlist('issuer') or request.query_params.getlist('issuer[]')
        if selected_issuers:
            try:
                requested_ids = {int(value) for value in selected_issuers}
            except (TypeError, ValueError) as exc:
                raise ValidationError({'issuer': 'Issuer filters must be numeric IDs.'}) from exc
            issuer_ids = [issuer_id for issuer_id in issuer_ids if issuer_id in requested_ids]

        invoice_qs = Invoice.objects.filter(issuer_id__in=issuer_ids)
        payment_qs = Payment.objects.filter(issuer_id__in=issuer_ids)
        expense_qs = Expense.objects.filter(issuer_id__in=issuer_ids, exclude_from_reports=False)

        totals = {
            'invoice_total': _decimal(invoice_qs.aggregate(total=Sum('total_due'))['total']),
            'amount_paid': _decimal(invoice_qs.aggregate(total=Sum('amount_paid'))['total']),
            'amount_due': _decimal(invoice_qs.aggregate(total=Sum('amount_due'))['total']),
            'amount_overdue': _decimal(invoice_qs.aggregate(total=Sum('amount_overdue'))['total']),
            'payment_total': _decimal(payment_qs.aggregate(total=Sum('base_currency_amount'))['total']),
            'expense_total': _decimal(expense_qs.aggregate(total=Sum('amount'))['total']),
        }
        monthly_revenue = invoice_qs.annotate(month=TruncMonth('issued_date')).values('month').annotate(
            total=Sum('total_due'), count=Count('id')
        ).order_by('month')
        monthly_expenses = expense_qs.annotate(month=TruncMonth('paid_date')).values('month').annotate(
            total=Sum('amount'), count=Count('id')
        ).order_by('month')
        status_rows = invoice_qs.values('status').annotate(
            count=Count('id'), amount_due=Sum('amount_due'), amount_overdue=Sum('amount_overdue')
        ).order_by('status')
        recent_invoices = invoice_qs.select_related('issuer__company', 'customer__company').order_by('-issued_date', '-id')[:10]
        recent_payments = payment_qs.select_related('issuer__company', 'customer__company').order_by('-received_at', '-id')[:10]
        recent_expenses = expense_qs.select_related('issuer__company').order_by('-paid_date', '-id')[:10]

        return Response({
            'issuer_ids': issuer_ids,
            'totals': {key: str(value) for key, value in totals.items()},
            'monthly_revenue': [
                {'month': _month_iso(row['month']), 'total': str(_decimal(row['total'])), 'count': row['count']}
                for row in monthly_revenue
            ],
            'monthly_expenses': [
                {'month': _month_iso(row['month']), 'total': str(_decimal(row['total'])), 'count': row['count']}
                for row in monthly_expenses
            ],
            'receivables': [
                {
                    'status': row['status'], 'count': row['count'],
                    'amount_due': str(_decimal(row['amount_due'])),
                    'amount_overdue': str(_decimal(row['amount_overdue'])),
                }
                for row in status_rows
            ],
            'recent_activity': {
                'invoices': [
                    {'id': invoice.pk, 'issuer_id': invoice.issuer_id, 'customer_name': str(invoice.customer), 'status': invoice.status, 'issued_date': invoice.issued_date, 'total_due': str(_decimal(invoice.total_due))}
                    for invoice in recent_invoices
                ],
                'payments': [
                    {'id': payment.pk, 'issuer_id': payment.issuer_id, 'customer_name': str(payment.customer), 'received_at': payment.received_at, 'amount': str(_decimal(payment.amount))}
                    for payment in recent_payments
                ],
                'expenses': [
                    {'id': expense.pk, 'issuer_id': expense.issuer_id, 'paid_date': expense.paid_date, 'amount': str(_decimal(expense.amount)), 'description': expense.description}
                    for expense in recent_expenses
                ],
            },
        })
