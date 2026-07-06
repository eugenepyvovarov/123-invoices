from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from invoices.models import (
    Customer,
    Invoice,
    Issuer,
    IssuerBankAccount,
    OrderLine,
    PaymentApplication,
    Project,
)
from invoices.views import save_invoice_pdf


MAX_PAGE_SIZE = 100
DRAFT_MUTATION_FIELDS = {
    'issuer',
    'customer',
    'project',
    'bank_account',
    'issued_date',
    'due_date',
    'payment_term',
    'reference_number',
    'notes',
    'comment',
    'tax_value',
    'discount_value',
    'secondary_tax_rate',
    'secondary_tax_name',
    'uses_secondary_tax',
    'lines',
}
FINAL_STATES = {Invoice.STATUS_INVOICED, Invoice.STATUS_OVERDUE, Invoice.STATUS_PAID}


def _issuer_queryset_for_user(user):
    issuers = Issuer.objects.select_related('company').order_by('company__name', 'id')
    if not user.is_superuser:
        issuers = issuers.filter(users=user)
    return issuers


def _issuer_ids_for_user(user) -> list[int]:
    return list(_issuer_queryset_for_user(user).values_list('id', flat=True))


def _base_invoice_queryset(user):
    return (
        Invoice.objects.filter(issuer_id__in=_issuer_ids_for_user(user))
        .select_related('issuer__company', 'customer__company', 'project', 'bank_account', 'payment_term')
        .prefetch_related('orderline_set', 'payment_applications__payment')
    )


def _paginate(request, queryset):
    page = _positive_int(request.query_params.get('page'), default=1, field='page')
    page_size = _positive_int(request.query_params.get('page_size'), default=25, field='page_size')
    page_size = min(page_size, MAX_PAGE_SIZE)
    offset = (page - 1) * page_size
    count = queryset.count()
    return {
        'count': count,
        'page': page,
        'page_size': page_size,
        'results': list(queryset[offset:offset + page_size]),
    }


def _positive_int(value, *, default: int, field: str) -> int:
    if value in (None, ''):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f'{field} must be an integer.')
    if parsed < 1:
        raise ValueError(f'{field} must be at least 1.')
    return parsed


def _decimal(value, *, field: str) -> Decimal:
    if value in (None, ''):
        return Decimal('0')
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f'{field} must be a decimal value.') from exc


def _money(value) -> str:
    return str((value or Decimal('0')).quantize(Decimal('0.01')))


def _list_response(request, queryset, serializer):
    try:
        page = _paginate(request, queryset)
    except ValueError as exc:
        return Response({'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    page['results'] = [serializer(item) for item in page['results']]
    return Response(page)


def _company_payload(company):
    if company is None:
        return None
    return {
        'id': company.id,
        'name': company.name,
        'tax_id': company.customer_information_file_number,
        'contact_email': company.contact_email,
    }


def _issuer_payload(issuer: Issuer):
    return {
        'id': issuer.id,
        'company': _company_payload(issuer.company),
        'invoice_format': issuer.invoice_format,
        'next_invoice_number': issuer.next_invoice_number,
    }


def _customer_payload(customer: Customer):
    return {
        'id': customer.id,
        'issuer_id': customer.issuer_id,
        'company': _company_payload(customer.company),
        'is_active': customer.is_active,
        'billing_email': customer.billing_email,
        'billing_contact_name': customer.billing_contact_name,
        'payment_notes': customer.payment_notes,
    }


def _project_payload(project: Project):
    return {
        'id': project.id,
        'issuer_id': project.issuer_id,
        'customer_id': project.customer_id,
        'title': project.title,
        'project_code': project.project_code,
        'status': project.status,
        'billing_reference': project.billing_reference,
    }


def _bank_account_payload(account: IssuerBankAccount):
    return {
        'id': account.id,
        'issuer_id': account.issuer_id,
        'label': account.label,
        'payment_method': account.payment_method,
        'account_details': account.account_details,
        'is_default': account.is_default,
        'is_active': account.is_active,
    }


def _line_payload(line: OrderLine):
    return {
        'id': line.id,
        'line_type': line.line_type,
        'description': line.description,
        'quantity': str(line.quantity),
        'unit_price': _money(line.unit_price),
        'line_total': _money(line.line_total),
        'manual_total': line.manual_total,
        'notes': line.notes,
    }


def _payment_payload(application: PaymentApplication):
    return {
        'payment_id': application.payment_id,
        'amount': str(application.amount_applied),
        'applied_at': application.applied_at.isoformat() if application.applied_at else None,
    }


def _pdf_payload(invoice: Invoice):
    document = invoice.pdf_document
    has_file = bool(document and getattr(document, 'name', ''))
    return {
        'available': has_file,
        'filename': document.name.rsplit('/', 1)[-1] if has_file else None,
        'name': document.name if has_file else None,
        'url': document.url if has_file else None,
        'content_type': 'application/pdf' if has_file else None,
        'size': document.size if has_file else None,
    }


def _invoice_payload(invoice: Invoice, *, include_lines: bool = True):
    payload = {
        'id': invoice.id,
        'issuer_id': invoice.issuer_id,
        'customer_id': invoice.customer_id,
        'project_id': invoice.project_id,
        'bank_account_id': invoice.bank_account_id,
        'reference_number': invoice.reference_number,
        'sequence_number': invoice.sequence_number,
        'status': invoice.status,
        'is_finalized': invoice.status in FINAL_STATES,
        'created_at': invoice.created_at.isoformat() if invoice.created_at else None,
        'updated_at': invoice.updated_at.isoformat() if invoice.updated_at else None,
        'issued_date': invoice.issued_date.isoformat() if invoice.issued_date else None,
        'due_date': invoice.due_date.isoformat() if invoice.due_date else None,
        'sent_date': invoice.sent_date.isoformat() if invoice.sent_date else None,
        'notes': invoice.notes,
        'comment': invoice.comment,
        'totals': {
            'subtotal': _money(invoice.sub_total),
            'tax': _money(invoice.tax_amount),
            'discount': _money(invoice.discount_amount),
            'total': _money(invoice.total_due),
            'balance_due': _money(invoice.amount_due),
            'amount_paid': _money(invoice.amount_paid),
            'amount_overdue': _money(invoice.amount_overdue),
        },
        'pdf': _pdf_payload(invoice),
        'payment_applications': [_payment_payload(application) for application in invoice.payment_applications.all()],
    }
    if include_lines:
        payload['lines'] = [_line_payload(line) for line in invoice.orderline_set.all()]
    return payload


def _visible_issuer_or_400(user, issuer_id):
    issuer = _issuer_queryset_for_user(user).filter(pk=issuer_id).first()
    if issuer is None:
        raise ValueError('issuer does not exist or is not available.')
    return issuer


def _invoice_mutation_payload(data: dict[str, Any], *, partial: bool):
    unknown = set(data) - DRAFT_MUTATION_FIELDS - {'status'}
    if unknown:
        raise ValueError(f'Unsupported invoice fields: {", ".join(sorted(unknown))}.')
    if data.get('status') not in (None, '', Invoice.STATUS_DRAFT):
        raise ValueError('Draft invoice endpoints only accept status=draft.')
    if not partial and 'issuer' not in data:
        raise ValueError('issuer is required.')
    return data


def _set_fk(instance: Invoice, field: str, model, queryset, raw_id):
    if raw_id in (None, ''):
        setattr(instance, field, None)
        return
    try:
        obj = queryset.get(pk=int(raw_id))
    except (model.DoesNotExist, ValueError, TypeError):
        raise ValueError(f'{field} does not exist or is not available.')
    setattr(instance, field, obj)


def _apply_invoice_payload(invoice: Invoice, data: dict[str, Any], *, user, partial: bool):
    data = _invoice_mutation_payload(data, partial=partial)
    issuer = invoice.issuer if invoice.pk else None
    if 'issuer' in data:
        issuer = _visible_issuer_or_400(user, data['issuer'])
        invoice.issuer = issuer
    if issuer is None:
        raise ValueError('issuer is required.')

    customers = Customer.objects.filter(issuer=issuer)
    projects = Project.objects.filter(customer__issuer=issuer)
    bank_accounts = IssuerBankAccount.objects.filter(issuer=issuer)

    if 'customer' in data:
        _set_fk(invoice, 'customer', Customer, customers, data.get('customer'))
    if 'project' in data:
        _set_fk(invoice, 'project', Project, projects, data.get('project'))
        if invoice.project_id:
            invoice.customer = invoice.project.customer
    if 'bank_account' in data:
        _set_fk(invoice, 'bank_account', IssuerBankAccount, bank_accounts, data.get('bank_account'))

    for attr in ('issued_date', 'due_date', 'reference_number', 'notes', 'comment', 'secondary_tax_name'):
        if attr in data:
            setattr(invoice, attr, data[attr] or None if attr in {'issued_date', 'due_date'} else data[attr])
    for attr in ('tax_value', 'discount_value', 'secondary_tax_rate'):
        if attr in data:
            setattr(invoice, attr, _decimal(data[attr], field=attr))
    if 'uses_secondary_tax' in data:
        invoice.uses_secondary_tax = bool(data['uses_secondary_tax'])
    invoice.status = Invoice.STATUS_DRAFT
    invoice.full_clean(exclude=['pdf_document'])


def _replace_lines(invoice: Invoice, raw_lines):
    if raw_lines is None:
        return
    if not isinstance(raw_lines, list):
        raise ValueError('lines must be a list.')
    invoice.orderline_set.all().delete()
    lines = []
    for index, raw in enumerate(raw_lines, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f'line {index} must be an object.')
        unknown = set(raw) - {'line_type', 'description', 'quantity', 'unit_price', 'line_total', 'manual_total', 'notes'}
        if unknown:
            raise ValueError(f'Unsupported line fields on line {index}: {", ".join(sorted(unknown))}.')
        line = OrderLine(
            invoice=invoice,
            line_type=raw.get('line_type') or OrderLine.LINE_TYPE_QUANTITY,
            description=raw.get('description', ''),
            quantity=_decimal(raw.get('quantity', '1'), field=f'lines[{index}].quantity'),
            unit_price=_decimal(raw.get('unit_price', '0'), field=f'lines[{index}].unit_price'),
            manual_total=bool(raw.get('manual_total', False)),
            line_total=_decimal(raw.get('line_total', '0'), field=f'lines[{index}].line_total'),
            notes=raw.get('notes', ''),
        )
        if not line.manual_total:
            line.line_total = line.quantity * line.unit_price
        lines.append(line)
    OrderLine.objects.bulk_create(lines)
    saved_lines = list(invoice.orderline_set.all())
    invoice.calculate_totals(saved_lines)
    invoice.save(update_fields=['sub_total', 'discount_amount', 'tax_base', 'tax_amount', 'total_due', 'base_currency_total', 'updated_at'])


class InvoiceCollectionView(APIView):
    def get(self, request):
        invoices = _base_invoice_queryset(request.user).order_by('-issued_date', '-number', '-id')
        search = request.query_params.get('search')
        if search:
            invoices = invoices.filter(
                Q(reference_number__icontains=search)
                | Q(customer__company__name__icontains=search)
                | Q(project__title__icontains=search)
                | Q(project__project_code__icontains=search)
            )
        for key, field in (('status', 'status'), ('customer', 'customer_id'), ('issuer', 'issuer_id'), ('project', 'project_id')):
            value = request.query_params.get(key)
            if value:
                invoices = invoices.filter(**{field: value})
        return _list_response(request, invoices, lambda invoice: _invoice_payload(invoice, include_lines=False))

    @transaction.atomic
    def post(self, request):
        invoice = Invoice()
        try:
            _apply_invoice_payload(invoice, dict(request.data), user=request.user, partial=False)
            invoice.save()
            _replace_lines(invoice, request.data.get('lines'))
        except ValueError as exc:
            return Response({'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_invoice_payload(invoice), status=status.HTTP_201_CREATED)


class InvoiceDetailView(APIView):
    def get(self, request, invoice_id):
        invoice = get_object_or_404(_base_invoice_queryset(request.user), pk=invoice_id)
        return Response(_invoice_payload(invoice))

    @transaction.atomic
    def patch(self, request, invoice_id):
        invoice = get_object_or_404(_base_invoice_queryset(request.user), pk=invoice_id)
        if invoice.status != Invoice.STATUS_DRAFT:
            return Response({'message': 'Only draft invoices can be updated.'}, status=status.HTTP_409_CONFLICT)
        try:
            _apply_invoice_payload(invoice, dict(request.data), user=request.user, partial=True)
            invoice.save()
            if 'lines' in request.data:
                _replace_lines(invoice, request.data.get('lines'))
        except ValueError as exc:
            return Response({'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_invoice_payload(invoice))


class InvoiceFinalizeView(APIView):
    def post(self, request, invoice_id):
        invoice = get_object_or_404(_base_invoice_queryset(request.user), pk=invoice_id)
        if request.data.get('confirm') is not True:
            return Response({'message': 'confirm=true is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if invoice.status != Invoice.STATUS_DRAFT:
            return Response({'message': 'Only draft invoices can be finalized.'}, status=status.HTTP_409_CONFLICT)
        invoice.status = Invoice.STATUS_INVOICED
        invoice.sent_date = invoice.sent_date or timezone.now().date()
        invoice.save(update_fields=['status', 'sent_date', 'updated_at'])
        return Response(_invoice_payload(invoice))


class InvoiceGeneratePDFView(APIView):
    def post(self, request, invoice_id):
        invoice = get_object_or_404(_base_invoice_queryset(request.user), pk=invoice_id)
        save_invoice_pdf(request, invoice.id)
        invoice.refresh_from_db()
        return Response({'pdf': _pdf_payload(invoice)})


class InvoicePDFView(APIView):
    def get(self, request, invoice_id):
        invoice = get_object_or_404(_base_invoice_queryset(request.user), pk=invoice_id)
        if request.query_params.get('mode') == 'metadata':
            return Response({'invoice_id': invoice.id, 'pdf': _pdf_payload(invoice)})
        if not invoice.pdf_document or not invoice.pdf_document.name:
            return Response({'message': 'Invoice PDF is not available.'}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(invoice.pdf_document.open('rb'), content_type='application/pdf')


class IssuerListView(APIView):
    def get(self, request):
        return _list_response(request, _issuer_queryset_for_user(request.user), _issuer_payload)


class CustomerListView(APIView):
    def get(self, request):
        customers = Customer.objects.filter(issuer_id__in=_issuer_ids_for_user(request.user)).select_related('issuer', 'company').order_by('company__name', 'id')
        search = request.query_params.get('search')
        if search:
            customers = customers.filter(Q(company__name__icontains=search) | Q(billing_email__icontains=search))
        return _list_response(request, customers, _customer_payload)


class ProjectListView(APIView):
    def get(self, request):
        projects = Project.objects.filter(issuer_id__in=_issuer_ids_for_user(request.user)).select_related('customer__company').order_by('title', 'id')
        customer_id = request.query_params.get('customer')
        search = request.query_params.get('search')
        if customer_id:
            projects = projects.filter(customer_id=customer_id)
        if search:
            projects = projects.filter(Q(title__icontains=search) | Q(project_code__icontains=search))
        return _list_response(request, projects, _project_payload)


class BankAccountListView(APIView):
    def get(self, request):
        accounts = IssuerBankAccount.objects.filter(issuer_id__in=_issuer_ids_for_user(request.user)).order_by('issuer_id', 'sort_order', 'label', 'id')
        issuer_id = request.query_params.get('issuer')
        if issuer_id:
            accounts = accounts.filter(issuer_id=issuer_id)
        return _list_response(request, accounts, _bank_account_payload)


class InvoiceLineSuggestionListView(APIView):
    def get(self, request):
        lines = OrderLine.objects.filter(invoice__issuer_id__in=_issuer_ids_for_user(request.user)).select_related('invoice__customer')
        search = request.query_params.get('search')
        customer_id = request.query_params.get('customer')
        issuer_id = request.query_params.get('issuer')
        if search:
            lines = lines.filter(description__icontains=search)
        if customer_id:
            lines = lines.filter(invoice__customer_id=customer_id)
        if issuer_id:
            lines = lines.filter(invoice__issuer_id=issuer_id)
        lines = lines.order_by('-updated_at', '-id')
        return _list_response(request, lines, _line_payload)
