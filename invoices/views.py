from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation
import io
import logging
import re
import zipfile
from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.core.files.base import ContentFile
from django.core.cache import cache
from django.template.loader import render_to_string
from django.core.paginator import Paginator
from django.db.models import (
    Sum,
    Case,
    When,
    DecimalField,
    IntegerField,
    Q,
    Count,
    Max,
    OuterRef,
    Subquery,
    Value,
)
from django.db.models.functions import Coalesce, TruncMonth
from django.db import transaction
from django.utils.html import format_html
from django.utils.formats import date_format
from django.utils import timezone

from invoices.forms import (
    AddressForm,
    BackupConfigurationForm,
    CompanyForm,
    CustomerStatusForm,
    CustomerBillingForm,
    InvoiceForm,
    IssuerBankAccountFormSet,
    IssuerCompanyForm,
    IssuerSettingsForm,
    IssuerSifSettingsForm,
    OrderLineFormSet,
    ProjectForm,
)
from invoices.management.commands.run_backup_scheduler import get_backup_scheduling_timezone
from invoices.models import (
    Company,
    Customer,
    Expense,
    Invoice,
    Issuer,
    OrderLine,
    Project,
    Payment,
    PaymentApplication,
    PaymentTerm,
    BackupConfiguration,
    BackupRun,
    IssuerSifSettings,
)
from invoices.services.backups import execute_backup, generate_backup_download_url
from invoices.services.bank_accounts import bank_account_for_project, resolve_invoice_bank_account
from invoices.services.invoice_state import is_invoice_overdue, overdue_q
from invoices.services.payment_notes import resolve_invoice_payment_notes
from invoices.services.sif import get_sif_readiness, get_sif_settings
from invoices.services.cached_totals import recalc_invoice_amounts
from invoices.services.backups import BackupDestinationCheckError, test_backup_destination
from invoices.services.wise_importer import WiseImportError, WiseStatementImporter
from invoices.utils.company_context import (
    get_active_issuer,
    set_active_company,
    get_available_issuers,
)
from invoices.utils.date_filters import ROLLING_YEAR_DATE_RANGE_KEY, get_global_date_filter
from invoices.utils.sanitize import sanitize_decimal_columns

logger = logging.getLogger(__name__)
ZERO_DECIMAL = Decimal('0')
COMBINED_INVOICED_OVERDUE_FILTER = f"{Invoice.STATUS_INVOICED},{Invoice.STATUS_OVERDUE}"
DASHBOARD_INVOICE_STATUS_SESSION_KEY = 'dashboard_invoice_status'
DASHBOARD_MAX_RESULTS_SESSION_KEY = 'dashboard_max_results'
DASHBOARD_DEFAULT_INVOICE_STATUS = 'all'
DASHBOARD_MAX_RESULTS_OPTIONS = (25, 50, 100)
DASHBOARD_DEFAULT_MAX_RESULTS = 25
INVOICE_STATUS_FILTER_OPTIONS = [
    ('all', 'All'),
    (Invoice.STATUS_DRAFT, 'Draft'),
    (Invoice.STATUS_INVOICED, 'Invoiced'),
    (COMBINED_INVOICED_OVERDUE_FILTER, 'Invoiced & Overdue'),
    (Invoice.STATUS_OVERDUE, 'Overdue'),
    (Invoice.STATUS_PAID, 'Paid'),
]
BACKUP_RUN_STATUS_INDICATORS = {
    BackupRun.STATUS_SUCCEEDED: {
        'icon': 'circle-check',
        'variant': 'success',
        'label': 'Succeeded',
    },
    BackupRun.STATUS_FAILED: {
        'icon': 'circle-x',
        'variant': 'danger',
        'label': 'Failed',
    },
    BackupRun.STATUS_IN_PROGRESS: {
        'icon': 'progress',
        'variant': 'muted',
        'label': 'In progress',
    },
}


def _next_backup_run_at(configuration, *, now=None):
    if not configuration.is_enabled:
        return None

    current_time = timezone.localtime(now or timezone.now(), get_backup_scheduling_timezone())
    next_run = current_time.replace(
        hour=configuration.daily_run_time.hour,
        minute=configuration.daily_run_time.minute,
        second=0,
        microsecond=0,
    )
    if next_run <= current_time:
        next_run += timedelta(days=1)
    return next_run


def _build_transient_backup_configuration(configuration, cleaned_data):
    field_names = [field.name for field in BackupConfiguration._meta.fields]
    transient_values = {
        field_name: getattr(configuration, field_name)
        for field_name in field_names
        if field_name not in {'id', 'pk'}
    }
    transient_values.update(cleaned_data)

    return BackupConfiguration(pk=configuration.pk, **transient_values)


def _format_recent_backup_datetime(value, *, include_year):
    localized_value = timezone.localtime(value)
    format_string = 'M j'
    if include_year:
        format_string = f'{format_string}, Y'
    return f"{date_format(localized_value, format_string)}, {date_format(localized_value, 'H:i')}"


def _prepare_recent_backup_runs(recent_runs):
    prepared_runs = []
    previous_started_year = None
    previous_finished_year = None

    for run in recent_runs:
        run.status_indicator = BACKUP_RUN_STATUS_INDICATORS.get(
            run.status,
            BACKUP_RUN_STATUS_INDICATORS[BackupRun.STATUS_IN_PROGRESS],
        ).copy()
        started_at_local = timezone.localtime(run.started_at)
        started_year = started_at_local.year
        run.started_at_shows_year = previous_started_year != started_year
        run.started_at_display = _format_recent_backup_datetime(
            run.started_at,
            include_year=run.started_at_shows_year,
        )
        previous_started_year = started_year

        if run.finished_at:
            finished_at_local = timezone.localtime(run.finished_at)
            finished_year = finished_at_local.year
            run.finished_at_shows_year = previous_finished_year != finished_year
            run.finished_at_display = _format_recent_backup_datetime(
                run.finished_at,
                include_year=run.finished_at_shows_year,
            )
            previous_finished_year = finished_year
        else:
            run.finished_at_shows_year = False
            run.finished_at_display = ''

        run.download_url = reverse('backup_run_download', args=[run.id]) if run.storage_object_key else ''
        prepared_runs.append(run)

    return prepared_runs


def _backup_settings_context(
    request,
    *,
    backup_form,
    backup_configuration,
    recent_runs,
    backup_tab,
    test_feedback_message='',
    test_feedback_level='info',
    save_feedback_message='',
    save_feedback_level='info',
):
    return {
        'backup_form': backup_form,
        'backup_configuration': backup_configuration,
        'next_backup_run_at': _next_backup_run_at(backup_configuration),
        'backup_scheduling_timezone': str(get_backup_scheduling_timezone()),
        'recent_backup_runs': recent_runs,
        'backup_tab': backup_tab,
        'test_feedback_message': test_feedback_message,
        'test_feedback_level': test_feedback_level,
        'save_feedback_message': save_feedback_message,
        'save_feedback_level': save_feedback_level,
    }


def _backup_settings_ajax_response(request, context, *, status=200, badge_configuration=None):
    badge_context = {**context, 'backup_configuration': badge_configuration or context['backup_configuration']}
    return JsonResponse(
        {
            'success': status < 400,
            'active_tab': 'backup-settings-panel',
            'fragments': {
                'settings_panel': render_to_string(
                    'invoices/partials/backup_settings_settings_panel.html',
                    context,
                    request=request,
                ),
                'status_badge': render_to_string(
                    'invoices/partials/backup_settings_status_badge.html',
                    badge_context,
                    request=request,
                ),
            },
        },
        status=status,
    )


def _safe_company_switch_redirect(next_url: str | None) -> str:
    if not next_url:
        return reverse('dashboard')

    parsed = urlsplit(next_url)
    path = parsed.path or ''
    query = f'?{parsed.query}' if parsed.query else ''

    if path in {'', '/'} or path == reverse('dashboard') or path == '/dashboard/':
        return f"{reverse('dashboard')}{query}"

    for list_path in (
        reverse('invoices:list'),
        reverse('customers:list'),
        reverse('projects:list'),
        reverse('expenses:list'),
        reverse('company:settings'),
        reverse('backup_settings'),
    ):
        if path == list_path:
            return f'{list_path}{query}'

    detail_fallbacks = (
        (r'^/invoices/\d+/.+$', reverse('invoices:list')),
        (r'^/invoices/\d+/?$', reverse('invoices:list')),
        (r'^/customers/\d+/.+$', reverse('customers:list')),
        (r'^/customers/\d+/?$', reverse('customers:list')),
        (r'^/projects/\d+/.+$', reverse('projects:list')),
        (r'^/projects/\d+/?$', reverse('projects:list')),
        (r'^/expenses/\d+/.+$', reverse('expenses:list')),
        (r'^/expenses/\d+/?$', reverse('expenses:list')),
    )
    for pattern, fallback in detail_fallbacks:
        if re.match(pattern, path):
            return fallback

    return reverse('dashboard')


def _safe_cross_company_row_redirect(next_url: str | None) -> str:
    if not next_url:
        return reverse('cross_company_dashboard')

    parsed = urlsplit(next_url)
    if parsed.scheme or parsed.netloc:
        return reverse('cross_company_dashboard')

    path = parsed.path or ''
    query = f'?{parsed.query}' if parsed.query else ''

    if path in {'', '/'}:
        return reverse('cross_company_dashboard')

    allowed_exact_paths = {
        reverse('dashboard'),
        '/dashboard/',
        reverse('cross_company_dashboard'),
        reverse('invoices:list'),
        reverse('customers:list'),
        reverse('projects:list'),
        reverse('expenses:list'),
    }
    if path in allowed_exact_paths:
        return f'{path}{query}'

    allowed_detail_patterns = (
        r'^/invoices/\d+/?$',
        r'^/customers/\d+/?$',
        r'^/projects/\d+/?$',
    )
    if any(re.match(pattern, path) for pattern in allowed_detail_patterns):
        return f'{path}{query}'

    return reverse('cross_company_dashboard')


def invalidate_dashboard_cache(issuer_id):
    periods = [ROLLING_YEAR_DATE_RANGE_KEY, 'this_month', 'last_month', 'ytd', 'last_year', 'all']
    for period in periods:
        cache.delete(f'dashboard:{issuer_id}:{period}')
        cache.delete(f'dashboard:v2:{issuer_id}:{period}')

    cross_company_registry_key = _cross_company_dashboard_registry_key(issuer_id)
    cross_company_cache_keys = cache.get(cross_company_registry_key, set())
    if cross_company_cache_keys:
        cache.delete_many(list(cross_company_cache_keys))
    cache.delete(cross_company_registry_key)


PER_COMPANY_DASHBOARD_CACHE_PREFIX = 'dashboard:v2'
CROSS_COMPANY_DASHBOARD_CACHE_PREFIX = 'dashboard:cross-company:v1'


def _dashboard_cache_signature(base_qs, expense_qs):
    invoice_stats = base_qs.aggregate(invoice_count=Count('pk'), latest_updated_at=Max('updated_at'))
    expense_stats = expense_qs.aggregate(expense_count=Count('pk'), latest_updated_at=Max('updated_at'))
    latest_updated_at = invoice_stats['latest_updated_at']
    expense_latest_updated_at = expense_stats['latest_updated_at']
    return {
        'invoice_count': invoice_stats['invoice_count'] or 0,
        'latest_updated_at': latest_updated_at.isoformat() if latest_updated_at else None,
        'expense_count': expense_stats['expense_count'] or 0,
        'expense_latest_updated_at': (
            expense_latest_updated_at.isoformat() if expense_latest_updated_at else None
        ),
    }


def _cross_company_dashboard_cache_signature(invoice_queryset, payment_queryset, expense_queryset):
    invoice_stats = invoice_queryset.aggregate(invoice_count=Count('pk'), latest_updated_at=Max('updated_at'))
    payment_stats = payment_queryset.aggregate(payment_count=Count('pk'), latest_updated_at=Max('updated_at'))
    expense_stats = expense_queryset.aggregate(expense_count=Count('pk'), latest_updated_at=Max('updated_at'))
    return {
        'invoice_count': invoice_stats['invoice_count'] or 0,
        'invoice_latest_updated_at': (
            invoice_stats['latest_updated_at'].isoformat() if invoice_stats['latest_updated_at'] else None
        ),
        'payment_count': payment_stats['payment_count'] or 0,
        'payment_latest_updated_at': (
            payment_stats['latest_updated_at'].isoformat() if payment_stats['latest_updated_at'] else None
        ),
        'expense_count': expense_stats['expense_count'] or 0,
        'expense_latest_updated_at': (
            expense_stats['latest_updated_at'].isoformat() if expense_stats['latest_updated_at'] else None
        ),
    }


def _build_cross_company_dashboard_cache_key(
    issuer_ids,
    period_key,
    cache_signature,
    *,
    invoice_status=DASHBOARD_DEFAULT_INVOICE_STATUS,
    max_results=DASHBOARD_DEFAULT_MAX_RESULTS,
):
    issuer_token = '-'.join(str(issuer_id) for issuer_id in sorted(issuer_ids)) or 'none'
    return (
        f"{CROSS_COMPANY_DASHBOARD_CACHE_PREFIX}:{issuer_token}:{period_key}:"
        f"{invoice_status}:{max_results}:"
        f"{cache_signature['invoice_count']}:{cache_signature['invoice_latest_updated_at'] or 'none'}:"
        f"{cache_signature['payment_count']}:{cache_signature['payment_latest_updated_at'] or 'none'}:"
        f"{cache_signature['expense_count']}:{cache_signature['expense_latest_updated_at'] or 'none'}"
    )


def _get_dashboard_filter_state(request):
    status_options = INVOICE_STATUS_FILTER_OPTIONS
    valid_statuses = {value for value, _label in status_options}
    selected_status = request.GET.get('invoice_status')

    if selected_status is not None:
        if selected_status in valid_statuses:
            active_status = selected_status
        else:
            active_status = DASHBOARD_DEFAULT_INVOICE_STATUS
        request.session[DASHBOARD_INVOICE_STATUS_SESSION_KEY] = active_status
    else:
        active_status = request.session.get(
            DASHBOARD_INVOICE_STATUS_SESSION_KEY,
            DASHBOARD_DEFAULT_INVOICE_STATUS,
        )
        if active_status not in valid_statuses:
            active_status = DASHBOARD_DEFAULT_INVOICE_STATUS

    selected_max_results = request.GET.get('max_results')
    max_results_values = {str(value): value for value in DASHBOARD_MAX_RESULTS_OPTIONS}

    if selected_max_results is not None:
        active_max_results = max_results_values.get(selected_max_results, DASHBOARD_DEFAULT_MAX_RESULTS)
        request.session[DASHBOARD_MAX_RESULTS_SESSION_KEY] = active_max_results
    else:
        active_max_results = request.session.get(
            DASHBOARD_MAX_RESULTS_SESSION_KEY,
            DASHBOARD_DEFAULT_MAX_RESULTS,
        )
        if str(active_max_results) not in max_results_values:
            active_max_results = DASHBOARD_DEFAULT_MAX_RESULTS
        else:
            active_max_results = int(active_max_results)

    return {
        'invoice_status': active_status,
        'invoice_status_options': status_options,
        'max_results': active_max_results,
        'max_results_options': DASHBOARD_MAX_RESULTS_OPTIONS,
    }


def _apply_dashboard_invoice_status_filter(invoice_queryset, invoice_status):
    if invoice_status == DASHBOARD_DEFAULT_INVOICE_STATUS:
        return invoice_queryset
    return _apply_invoice_list_status_filter(invoice_queryset, invoice_status)


def _cross_company_dashboard_registry_key(issuer_id):
    return f'{CROSS_COMPANY_DASHBOARD_CACHE_PREFIX}:registry:{issuer_id}'


def _register_cross_company_dashboard_cache_key(issuer_ids, cache_key):
    for issuer_id in issuer_ids:
        registry_key = _cross_company_dashboard_registry_key(issuer_id)
        registered_cache_keys = cache.get(registry_key, set())
        if cache_key in registered_cache_keys:
            continue
        cache.set(registry_key, {*registered_cache_keys, cache_key}, 300)

STATUS_BADGE_CLASSES = {
    Invoice.STATUS_DRAFT: 'status-badge status-badge--draft',
    Invoice.STATUS_INVOICED: 'status-badge status-badge--invoiced',
    Invoice.STATUS_OVERDUE: 'status-badge status-badge--overdue',
    Invoice.STATUS_PAID: 'status-badge status-badge--paid',
}
STATUS_LABELS = dict(Invoice.STATUS_CHOICES)


def _invoice_list_status(invoice):
    if invoice.status in (Invoice.STATUS_DRAFT, Invoice.STATUS_PAID):
        return invoice.status
    if is_invoice_overdue(due_date=invoice.due_date, amount_due=invoice.amount_due):
        return Invoice.STATUS_OVERDUE
    return Invoice.STATUS_INVOICED


def _set_invoice_display_state(invoice):
    invoice_status = _invoice_list_status(invoice)
    invoice.display_status = invoice_status
    invoice.display_status_label = STATUS_LABELS.get(invoice_status, invoice.get_status_display())
    invoice.display_status_badge_class = STATUS_BADGE_CLASSES.get(invoice_status, 'status-badge')
    invoice.is_overdue = invoice_status == Invoice.STATUS_OVERDUE
    return invoice


def _set_invoice_display_states(invoices):
    for invoice in invoices:
        _set_invoice_display_state(invoice)
    return invoices

CUSTOMER_ORDER_COLUMN_CONFIG = [
    {
        'label': 'Title',
        'asc': 'name',
        'desc': 'name_desc',
        'default': 'asc',
        'align': '',
    },
    {
        'label': 'Projects',
        'asc': 'projects_asc',
        'desc': 'projects_desc',
        'default': 'desc',
        'align': 'text-end',
    },
    {
        'label': 'Paid',
        'asc': 'paid_asc',
        'desc': 'paid_desc',
        'default': 'desc',
        'align': 'text-end',
    },
    {
        'label': 'Pending',
        'asc': 'pending_asc',
        'desc': 'pending_desc',
        'default': 'desc',
        'align': 'text-end',
    },
    {
        'label': 'Last activity',
        'asc': 'last_activity_asc',
        'desc': 'last_activity_desc',
        'default': 'desc',
        'align': '',
    },
]

CUSTOMER_ORDER_SESSION_KEY = 'customers_order'


def _apply_date_range(qs, start=None, end=None):
    if start:
        qs = qs.filter(issued_date__gte=start)
    if end:
        qs = qs.filter(issued_date__lte=end)
    return qs


def _coerce_decimal(amount) -> Decimal:
    value = amount
    if value in (None, ''):
        return ZERO_DECIMAL
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return ZERO_DECIMAL


def _format_currency(amount):
    """
    Return a standardized currency string with two decimal places and euro suffix.
    Falls back to 0.00 € on invalid input.
    """
    value = _coerce_decimal(amount)
    return f"{value:.2f} €"


def _format_currency_axis_label(amount):
    """Return compact euro-prefixed labels for dashboard chart axis ticks."""
    value = _coerce_decimal(amount)
    sign = "-" if value < ZERO_DECIMAL else ""
    absolute = abs(value)

    def _format_scaled(number: Decimal) -> str:
        if number == number.quantize(Decimal("1")):
            return str(number.quantize(Decimal("1")))
        return f"{number.quantize(Decimal('0.1')).normalize()}"

    if absolute >= Decimal("1000000"):
        return f"{sign}€{_format_scaled(absolute / Decimal('1000000'))}M"
    if absolute >= Decimal("1000"):
        return f"{sign}€{_format_scaled(absolute / Decimal('1000'))}K"
    return f"{sign}€{absolute.quantize(Decimal('1'))}"


def _invoice_display_number(invoice):
    label = invoice.sequence_number if hasattr(invoice, 'sequence_number') else ''
    if not label:
        return str(invoice.id)
    prefix = 'Database id: '
    if label.startswith(prefix):
        return label[len(prefix):]
    return label


def _get_last_query_value(request, key, default=None):
    values = request.GET.getlist(key)
    if not values:
        return default
    return values[-1]

def _invoice_period_bounds(period_key):
    today = date.today()
    if period_key == 'this_month':
        start = today.replace(day=1)
        return start, today
    if period_key == 'last_month':
        first_of_this = today.replace(day=1)
        last_month_end = first_of_this - timedelta(days=1)
        return last_month_end.replace(day=1), last_month_end
    if period_key == 'last_90_days':
        return today - timedelta(days=90), today
    if period_key == 'ytd':
        return today.replace(month=1, day=1), today
    return None, None


def _base_querystring(querydict):
    params = querydict.copy()
    params.pop('page', None)
    base = params.urlencode()
    return base


def _querystring_without(querydict, *keys):
    params = querydict.copy()
    for key in keys:
        params.pop(key, None)
    return params.urlencode()


def _apply_invoice_list_status_filter(invoices_qs, status_filter):
    valid_invoice_statuses = {choice[0] for choice in Invoice.STATUS_CHOICES}

    if ',' in status_filter:
        selected_statuses = [
            item for item in status_filter.split(',') if item in valid_invoice_statuses
        ]
        if not selected_statuses:
            return invoices_qs

        if Invoice.STATUS_OVERDUE in selected_statuses:
            selected_statuses = [
                item for item in selected_statuses if item != Invoice.STATUS_OVERDUE
            ]
            invoice_filter = overdue_q()
            if selected_statuses:
                invoice_filter |= Q(status__in=selected_statuses)
            return invoices_qs.filter(invoice_filter)

        return invoices_qs.filter(status__in=selected_statuses)

    if status_filter == Invoice.STATUS_OVERDUE:
        return invoices_qs.filter(overdue_q())

    return invoices_qs.filter(status=status_filter)


def _recent_items_payload(project, exclude_invoice=None, limit=5):
    if not project:
        return []
    qs = OrderLine.objects.filter(invoice__project=project)
    if exclude_invoice is not None:
        qs = qs.exclude(invoice=exclude_invoice)
    qs = qs.order_by('-invoice__created_at', '-pk')

    items = []
    seen = set()
    fetch_limit = limit * 10 if limit else 50
    for description, quantity, unit_price in qs.values_list('description', 'quantity', 'unit_price')[:fetch_limit]:
        normalized_description = (description or '').strip()
        quantity_str = str(quantity or '')
        unit_price_str = str(unit_price or '')
        key = (normalized_description, quantity_str, unit_price_str)
        if key in seen:
            continue
        seen.add(key)
        items.append({
            'description': normalized_description,
            'quantity': quantity_str,
            'unit_price': unit_price_str,
        })
        if limit and len(items) >= limit:
            break
    return items


def _payment_terms_meta():
    return [
        {
            'id': term.id,
            'name': term.name,
            'days': term.days,
        }
        for term in PaymentTerm.objects.order_by('days', 'name')
    ]


def _project_payment_defaults(issuer):
    projects = Project.objects.filter(customer__issuer=issuer).select_related('payment_term', 'customer__payment_term')
    payload = []
    for project in projects:
        bank_account = bank_account_for_project(project, issuer=issuer)
        payload.append({
            'id': project.id,
            'payment_term': project.payment_term_id,
            'customer_payment_term': project.customer.payment_term_id if project.customer else None,
            'bank_account': bank_account.pk if bank_account else None,
        })
    return payload


def _customer_payment_defaults(issuer):
    customers = Customer.objects.filter(issuer=issuer).select_related('payment_term')
    return [
        {
            'id': customer.id,
            'payment_term': customer.payment_term_id,
        }
        for customer in customers
    ]


def _invoice_currency_meta(invoice):
    currency = getattr(invoice, 'currency', None)
    if not currency and getattr(invoice, 'customer', None):
        currency = invoice.customer.currency

    symbol = ''
    code = ''
    if currency:
        symbol = getattr(currency, 'symbol', '') or ''
        code = getattr(currency, 'code', '') or ''

    primary = symbol or code or '€'
    display = primary
    if code and symbol and symbol != code:
        display = f"{symbol} ({code})"

    return {
        'currency': currency,
        'symbol': primary,
        'code': code,
        'display': display,
    }


def _invoice_currency_symbol(invoice):
    return _invoice_currency_meta(invoice)['symbol']


def _invoice_notes(invoice):
    if not invoice:
        return ''
    if getattr(invoice, 'notes', None):
        return invoice.notes
    project = getattr(invoice, 'project', None)
    return getattr(project, 'comment', '') if project else ''


def _suggest_invoice_reference(issuer, issued_date=None):
    if not issuer:
        return ''
    numbering_date = issued_date or date.today()
    next_number = issuer.next_invoice_number or 1
    return issuer.render_invoice_reference(numbering_date, next_number)


def _resolve_selected_project(form, invoice, issuer):
    project = invoice.project
    if form is None:
        return project
    try:
        cleaned_project = form.cleaned_data.get('project')
        if cleaned_project:
            return cleaned_project
    except AttributeError:
        # form was not validated yet or invalid; fall back to raw data
        pass

    project_id = form.data.get('project') if hasattr(form, 'data') else None
    if project_id:
        try:
            return Project.objects.get(pk=project_id, customer__issuer=issuer)
        except Project.DoesNotExist:
            return project
    return project


def view_invoices(request):
    sanitize_decimal_columns()
    issuer = get_active_issuer(request)
    date_filter = get_global_date_filter(request)
    range_start = date_filter['start']
    range_end = date_filter['end']
    invoices_page = Paginator([], 25).get_page(1)
    status_filter = request.GET.get('status', 'all')
    period_filter = request.GET.get('period', 'all')
    project_filter = request.GET.get('project')
    customer_filter = request.GET.get('customer')
    search_query = request.GET.get('q', '').strip()
    page_number = request.GET.get('page', 1)

    status_options = INVOICE_STATUS_FILTER_OPTIONS
    period_options = [
        ('all', 'All time'),
        ('this_month', 'This month'),
        ('last_month', 'Last month'),
        ('last_90_days', 'Last 90 days'),
        ('ytd', 'Year to date'),
    ]

    show_status_column = False
    order_columns = [
        {'label': '', 'sortable': False, 'align': 'select-cell'},
        {'label': '#', 'sortable': False},
        {'label': 'Date', 'sortable': False},
        {'label': 'Client', 'sortable': False},
        {'label': 'Project', 'sortable': False},
        {'label': 'Total', 'sortable': False, 'align': 'text-end'},
    ]
    invoice_rows = []

    if issuer:
        invoices_qs = Invoice.objects.filter(issuer=issuer).select_related('project', 'customer__company').order_by('-issued_date', '-number')

        if range_start:
            invoices_qs = invoices_qs.filter(issued_date__gte=range_start)
        if range_end:
            invoices_qs = invoices_qs.filter(issued_date__lte=range_end)

        valid_status = {choice[0] for choice in status_options}
        if status_filter in valid_status and status_filter != 'all':
            invoices_qs = _apply_invoice_list_status_filter(invoices_qs, status_filter)
        else:
            status_filter = 'all'

        valid_periods = {choice[0] for choice in period_options}
        if period_filter in valid_periods and period_filter != 'all':
            start, end = _invoice_period_bounds(period_filter)
            if start and end:
                invoices_qs = invoices_qs.filter(issued_date__gte=start, issued_date__lte=end)
        else:
            period_filter = 'all'

        if project_filter:
            invoices_qs = invoices_qs.filter(project_id=project_filter)
        if customer_filter:
            invoices_qs = invoices_qs.filter(customer_id=customer_filter)

        if search_query:
            invoices_qs = invoices_qs.filter(
                Q(sequence__icontains=search_query)
                | Q(number__icontains=search_query)
                | Q(customer__company__name__icontains=search_query)
                | Q(project__project_code__icontains=search_query)
            )

        paginator = Paginator(invoices_qs, 25)
        invoices_page = paginator.get_page(page_number)

        for invoice in invoices_page:
            _set_invoice_display_state(invoice)
            invoice_total = _coerce_decimal(invoice.total_due)
            outstanding_amount = _coerce_decimal(invoice.amount_due)
            if outstanding_amount <= ZERO_DECIMAL:
                outstanding_amount = None
            invoice_status = invoice.display_status
            outstanding_is_overdue = invoice_status == Invoice.STATUS_OVERDUE
            checkbox_cell = format_html(
                '<input type="checkbox" class="field-control--checkbox invoice-select" name="selected" value="{}" data-total="{}" data-unpaid="{}" form="bulk-actions-form" />',
                invoice.id,
                f"{invoice_total:.2f}",
                f"{(outstanding_amount or ZERO_DECIMAL):.2f}",
            )
            number_cell = format_html(
                '<a href="{}" class="link-primary">{}</a>',
                reverse('invoices:edit', args=[invoice.id]),
                _invoice_display_number(invoice),
            )
            issued_date_display = date_format(invoice.issued_date, 'j M Y') if invoice.issued_date else '—'
            if invoice.customer:
                client_cell = format_html(
                    '<a href="{}" class="link-primary">{}</a>',
                    reverse('customers:detail', args=[invoice.customer.id]),
                    invoice.customer,
                )
            else:
                client_cell = '—'
            if invoice.project:
                project_cell = format_html(
                    '<a href="{}" class="link-primary">{}</a>',
                    reverse('projects:detail', args=[invoice.project.id]),
                    invoice.project.title,
                )
            else:
                project_cell = '—'

            total_cell = format_html('{}', _format_currency(invoice_total))
            if outstanding_amount:
                amount_note_class = 'account-table__amount-note'
                if outstanding_is_overdue:
                    amount_note_class += ' account-table__amount-note--danger'
                else:
                    amount_note_class += ' account-table__amount-note--current'
                total_cell = format_html(
                    '{}<div class="{}">({})</div>',
                    _format_currency(invoice_total),
                    amount_note_class,
                    _format_currency(outstanding_amount),
                )

            row_cells = [
                {'content': checkbox_cell, 'align': 'select-cell'},
                {'content': number_cell},
                {'content': issued_date_display},
                {'content': client_cell},
                {'content': project_cell},
                {'content': total_cell, 'align': 'text-end'},
            ]

            invoice_rows.append({'cells': row_cells})
    else:
        messages.info(request, 'Add a company before creating invoices.')
    payment_terms_meta = _payment_terms_meta() if issuer else []
    project_payment_defaults = _project_payment_defaults(issuer) if issuer else []
    customer_payment_defaults = _customer_payment_defaults(issuer) if issuer else []

    context = {
        'invoices_list': invoices_page,
        'status_filter': status_filter,
        'period_filter': period_filter,
        'project_filter': project_filter or '',
        'customer_filter': customer_filter or '',
        'search_query': search_query,
        'status_options': status_options,
        'base_querystring': _base_querystring(request.GET),
        'query_without_status': _querystring_without(request.GET, 'status', 'page'),
        'query_without_page': _querystring_without(request.GET, 'page'),
        'order_columns': order_columns,
        'invoice_rows': invoice_rows,
        'query_without_order': _querystring_without(request.GET, 'order'),
        'payment_terms_meta': payment_terms_meta,
        'project_payment_defaults': project_payment_defaults,
        'customer_payment_defaults': customer_payment_defaults,
    }
    return render(request, 'invoices/view_invoices.html', context)


@require_POST
def invoice_status_update(request, id):
    issuer = get_active_issuer(request)
    if not issuer:
        messages.error(request, 'Select a company before updating invoices.')
        return redirect('company:settings')

    invoice = get_object_or_404(Invoice, pk=id, issuer=issuer)
    new_status = request.POST.get('status')
    valid_statuses = {choice[0] for choice in Invoice.STATUS_CHOICES}

    if new_status in valid_statuses:
        if invoice.status != new_status:
            invoice.status = new_status
            invoice.save(update_fields=['status'])
            try:
                save_invoice_pdf(request, invoice.id)
            except RuntimeError:
                pass
            invalidate_dashboard_cache(issuer.pk)
            messages.success(request, f'Invoice {invoice.sequence_number} updated to {invoice.get_status_display()}')
    else:
        messages.error(request, 'Invalid status selected.')

    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or reverse('invoices:list')
    return redirect(next_url)


@require_POST
def invoice_bulk_action(request):
    issuer = get_active_issuer(request)
    if not issuer:
        messages.error(request, 'Select a company before managing invoices.')
        return redirect('company:settings')

    action = request.POST.get('action')
    selected_ids = request.POST.getlist('selected')
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or reverse('invoices:list')

    if not selected_ids:
        messages.warning(request, 'Select at least one invoice to perform bulk actions.')
        return redirect(next_url)

    invoices = Invoice.objects.filter(pk__in=selected_ids, issuer=issuer)
    if not invoices.exists():
        messages.warning(request, 'No matching invoices found.')
        return redirect(next_url)

    if action == 'mark_paid':
        updated = invoices.exclude(status=Invoice.STATUS_PAID).update(status=Invoice.STATUS_PAID)
        if updated:
            invalidate_dashboard_cache(issuer.pk)
            messages.success(request, f'Marked {updated} invoice(s) as paid.')
        else:
            messages.info(request, 'Selected invoices were already paid.')

    elif action == 'generate_pdfs':
        generated = 0
        for inv in invoices:
            try:
                save_invoice_pdf(request, inv.id)
                generated += 1
            except RuntimeError:
                messages.warning(request, f'PDF generation unavailable for {inv.sequence_number}.')
        if generated:
            messages.success(request, f'Generated {generated} PDF(s).')

    elif action == 'download_pdfs':
        buffer = io.BytesIO()
        added = 0
        existing_names = set()
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            for inv in invoices:
                # Ensure a PDF exists; try to generate if missing
                need_generate = not getattr(inv, 'pdf_document', None) or not getattr(inv.pdf_document, 'name', '')
                if need_generate:
                    try:
                        save_invoice_pdf(request, inv.id)
                        inv.refresh_from_db(fields=['pdf_document'])
                    except RuntimeError:
                        continue
                    except Exception:
                        continue
                if not getattr(inv, 'pdf_document', None) or not getattr(inv.pdf_document, 'name', ''):
                    continue
                try:
                    inv.pdf_document.open('rb')
                    data = inv.pdf_document.read()
                except Exception:
                    continue
                finally:
                    try:
                        inv.pdf_document.close()
                    except Exception:
                        pass

                safe_identifier = (
                    inv.sequence_number.replace('/', '-').replace(' ', '-').replace('.', '-').replace(':', '-')
                )
                customer_slug = (
                    inv.customer.company.name.replace(' ', '-') if inv.customer and inv.customer.company else 'customer'
                )
                issued_str = inv.issued_date.isoformat() if inv.issued_date else 'undated'
                base_name = f"{safe_identifier}_{customer_slug}_{issued_str}.pdf"
                arcname = base_name
                # Ensure unique name inside zip
                i = 1
                while arcname in existing_names:
                    arcname = f"{safe_identifier}_{customer_slug}_{issued_str}_{i}.pdf"
                    i += 1
                existing_names.add(arcname)
                try:
                    zf.writestr(arcname, data)
                    added += 1
                except Exception:
                    # Skip problematic file
                    continue

        if added == 0:
            messages.warning(request, 'No PDFs could be generated for the selected invoices.')
            return redirect(next_url)
        buffer.seek(0)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'invoices_{timestamp}.zip'
        resp = HttpResponse(buffer.getvalue(), content_type='application/zip')
        resp['Content-Disposition'] = f'attachment; filename="{filename}"'
        return resp

    elif action == 'delete':
        count = invoices.count()
        for inv in invoices:
            inv.delete()
        invalidate_dashboard_cache(issuer.pk)
        messages.success(request, f'Deleted {count} invoice(s).')

    else:
        messages.error(request, 'Select a valid bulk action.')

    return redirect(next_url)


def _period_bounds(period_key):
    from datetime import date, timedelta
    today = date.today()
    if period_key == 'last_month':
        first_of_this = today.replace(day=1)
        last_month_end = first_of_this - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        return last_month_start, last_month_end
    if period_key == 'qtd':
        # quarter to date
        month = ((today.month - 1) // 3) * 3 + 1
        start = date(today.year, month, 1)
        return start, today
    if period_key == 'ytd':
        start = date(today.year, 1, 1)
        return start, today
    # default this_month
    start = today.replace(day=1)
    return start, today


def _build_recent_month_starts(month_count=24):
    today = date.today()
    current_total = today.year * 12 + (today.month - 1)
    month_starts = []
    for delta in range(month_count - 1, -1, -1):
        total_months = current_total - delta
        year = total_months // 12
        month = total_months % 12 + 1
        month_starts.append(date(year, month, 1))
    return month_starts


def _build_dashboard_chart_axis_metadata(max_total, interval_count=4):
    max_value = _coerce_decimal(max_total)
    if max_value <= ZERO_DECIMAL:
        return {
            'axis_max': ZERO_DECIMAL,
            'ticks': [
                {
                    'value': ZERO_DECIMAL,
                    'label': _format_currency_axis_label(ZERO_DECIMAL),
                    'ratio': 0.0,
                }
            ],
        }

    raw_step = max_value / Decimal(interval_count)
    magnitude = Decimal('1').scaleb(raw_step.adjusted())
    normalized_step = raw_step / magnitude
    if normalized_step <= Decimal('1'):
        nice_normalized_step = Decimal('1')
    elif normalized_step <= Decimal('2'):
        nice_normalized_step = Decimal('2')
    elif normalized_step <= Decimal('5'):
        nice_normalized_step = Decimal('5')
    else:
        nice_normalized_step = Decimal('10')

    step = nice_normalized_step * magnitude
    axis_max = step * Decimal(interval_count)
    ticks = []
    for tick_index in range(interval_count, -1, -1):
        tick_value = step * Decimal(tick_index)
        ticks.append(
            {
                'value': tick_value,
                'label': _format_currency_axis_label(tick_value),
                'ratio': float(tick_value / axis_max) if axis_max else 0.0,
            }
        )

    return {
        'axis_max': axis_max,
        'ticks': ticks,
    }


def _build_dashboard_chart(invoice_queryset, expense_queryset):
    active_statuses = [Invoice.STATUS_INVOICED, Invoice.STATUS_OVERDUE]
    non_draft_statuses = active_statuses + [Invoice.STATUS_PAID]
    month_starts = _build_recent_month_starts()
    chart_start = month_starts[0]

    trend_rows = (
        invoice_queryset.filter(
            status__in=non_draft_statuses,
            issued_date__isnull=False,
            issued_date__gte=chart_start,
        )
        .annotate(month_start=TruncMonth('issued_date'))
        .values('month_start')
        .annotate(total=Coalesce(Sum('total_due'), Decimal('0')))
    )
    expense_trend_rows = (
        expense_queryset.filter(
            exclude_from_reports=False,
            paid_date__isnull=False,
            paid_date__gte=chart_start,
        )
        .annotate(month_start=TruncMonth('paid_date'))
        .values('month_start')
        .annotate(total=Coalesce(Sum('amount'), Decimal('0')))
    )

    totals_by_month = {
        (month_date.year, month_date.month): Decimal('0') for month_date in month_starts
    }
    expense_totals_by_month = {
        (month_date.year, month_date.month): Decimal('0') for month_date in month_starts
    }
    for row in trend_rows:
        month_val = row.get('month_start')
        if not month_val:
            continue
        totals_by_month[(month_val.year, month_val.month)] = row.get('total') or Decimal('0')
    for row in expense_trend_rows:
        month_val = row.get('month_start')
        if not month_val:
            continue
        expense_totals_by_month[(month_val.year, month_val.month)] = row.get('total') or Decimal('0')

    max_total = Decimal('0')
    chart_months = []
    trend_series = []
    expense_trend_totals = []

    for index, month_date in enumerate(month_starts):
        key = (month_date.year, month_date.month)
        total_value = totals_by_month.get(key, Decimal('0'))
        expense_total_value = expense_totals_by_month.get(key, Decimal('0'))
        if not isinstance(total_value, Decimal):
            total_value = Decimal(total_value)
        if not isinstance(expense_total_value, Decimal):
            expense_total_value = Decimal(expense_total_value)
        combined_total_value = total_value + expense_total_value
        month_max_total = max(total_value, expense_total_value)
        if month_max_total > max_total:
            max_total = month_max_total

        if total_value >= Decimal('1000'):
            compact = float(total_value / Decimal('1000'))
            if compact >= 10:
                amount_display = f"{compact:.0f}K €"
            else:
                amount_display = f"{compact:.1f}K €"
        else:
            amount_display = f"{format(total_value, '.2f')} €"

        if max_total > ZERO_DECIMAL:
            ratio = float(total_value / max_total)
        else:
            ratio = 0.0

        chart_months.append(
            {
                'month_start': month_date,
                'month_label': date_format(month_date, 'M Y'),
                'month_abbrev': date_format(month_date, 'M'),
                'month_year_marker': f"'{date_format(month_date, 'y')}" if index == 0 or month_date.month == 1 else '',
                'invoiced_total': total_value,
                'expense_total': expense_total_value,
                'combined_total': combined_total_value,
                'revenue_display': _format_currency(total_value),
                'invoiced_display': _format_currency(total_value),
                'expense_display': _format_currency(expense_total_value),
                'combined_display': _format_currency(combined_total_value),
                'amount_display': amount_display,
            }
        )

        if ratio < 0.1:
            color = '#9ec5ff'
        elif ratio < 0.2:
            color = '#7aafff'
        elif ratio < 0.35:
            color = '#5799ff'
        elif ratio < 0.5:
            color = '#3a84fa'
        elif ratio < 0.7:
            color = '#2f73f0'
        elif ratio < 0.9:
            color = '#2967e6'
        else:
            color = '#2563eb'
        trend_series.append(
            {
                'amount_display': amount_display,
                'size': f"{ratio:.4f}",
                'ratio': ratio,
                'color': color,
            }
        )
        expense_trend_totals.append(expense_total_value)

    axis_metadata = _build_dashboard_chart_axis_metadata(max_total)
    dashboard_chart = {
        'months': chart_months,
        'max_total': max_total,
        'axis_max': axis_metadata['axis_max'],
        'y_axis_ticks': axis_metadata['ticks'],
    }
    return dashboard_chart, trend_series, expense_trend_totals


def _build_dashboard_context(request, issuer, date_filter):
    range_start = date_filter['start']
    range_end = date_filter['end']
    period_key = date_filter['key']
    period_label = date_filter['label']
    legacy_cache_key = f'{PER_COMPANY_DASHBOARD_CACHE_PREFIX}:{issuer.pk}:{period_key}'
    base_qs = Invoice.objects.filter(issuer=issuer)
    expense_base_qs = Expense.objects.filter(issuer=issuer)

    invoice_cache_version = base_qs.aggregate(
        count=Count('pk'),
        latest_updated_at=Max('updated_at'),
    )
    expense_cache_version = expense_base_qs.aggregate(
        count=Count('pk'),
        latest_updated_at=Max('updated_at'),
    )
    latest_updated_at = invoice_cache_version['latest_updated_at']
    latest_updated_token = latest_updated_at.isoformat() if latest_updated_at else 'none'
    latest_expense_updated_at = expense_cache_version['latest_updated_at']
    latest_expense_updated_token = (
        latest_expense_updated_at.isoformat() if latest_expense_updated_at else 'none'
    )
    cache_key = (
        f"{PER_COMPANY_DASHBOARD_CACHE_PREFIX}:{issuer.pk}:{period_key}:"
        f"{invoice_cache_version['count']}:{latest_updated_token}:"
        f"{expense_cache_version['count']}:{latest_expense_updated_token}"
    )
    cached = cache.get(cache_key)
    cache_signature = _dashboard_cache_signature(base_qs, expense_base_qs)
    cached = cache.get(cache_key)

    if cached and cached.get('signature') != cache_signature:
        cached = None

    if not cached:
        active_statuses = [Invoice.STATUS_INVOICED, Invoice.STATUS_OVERDUE]
        non_draft_statuses = active_statuses + [Invoice.STATUS_PAID]

        pending_total = _apply_date_range(
            base_qs.filter(status__in=active_statuses),
            range_start,
            range_end,
        ).aggregate(total=Coalesce(Sum('amount_due'), Decimal('0')))['total']

        overdue_total = _apply_date_range(
            base_qs.filter(overdue_q()),
            range_start,
            range_end,
        ).aggregate(total=Coalesce(Sum('amount_due'), Decimal('0')))['total']

        invoiced_total = _apply_date_range(
            base_qs.filter(status__in=non_draft_statuses),
            range_start,
            range_end,
        ).aggregate(total=Coalesce(Sum('total_due'), Decimal('0')))['total']

        paid_total = _apply_date_range(
            base_qs.filter(status=Invoice.STATUS_PAID),
            range_start,
            range_end,
        ).aggregate(total=Coalesce(Sum('total_due'), Decimal('0')))['total']

        top_pending_ids = list(
            _apply_date_range(
                base_qs.filter(status__in=active_statuses),
                range_start,
                range_end,
            )
            .order_by('-amount_due')
            .values_list('id', flat=True)[:5]
        )

        top_overdue_ids = list(
            _apply_date_range(
                base_qs.filter(overdue_q()),
                range_start,
                range_end,
            )
            .order_by('-issued_date')
            .values_list('id', flat=True)[:5]
        )

        recent_invoice_ids = list(
            _apply_date_range(base_qs, range_start, range_end)
            .order_by('-issued_date', '-number')
            .values_list('id', flat=True)[:10]
        )

        dashboard_chart, trend_series, expense_trend_totals = _build_dashboard_chart(
            base_qs,
            Expense.objects.filter(issuer=issuer),
        )

        cached_context = {
            'dashboard_chart': dashboard_chart,
            'invoiced_trend': trend_series,
            'expense_trend_totals': expense_trend_totals,
        }

        cached = {
            'signature': cache_signature,
            'pending_total': pending_total,
            'overdue_total': overdue_total,
            'invoiced_total': invoiced_total,
            'paid_total': paid_total,
            'top_pending_ids': top_pending_ids,
            'top_overdue_ids': top_overdue_ids,
            'recent_invoice_ids': recent_invoice_ids,
            'period_label': period_label,
            'context': cached_context,
            'dashboard_chart': dashboard_chart,
            'invoiced_trend': trend_series,
            'expense_trend_totals': expense_trend_totals,
        }
        cache.set(cache_key, cached, 300)
        cache.set(legacy_cache_key, cached, 300)

    pending_total = cached['pending_total']
    overdue_total = cached['overdue_total']
    invoiced_total = cached['invoiced_total']
    paid_total = cached['paid_total']
    cached_context = cached.get('context', {})
    dashboard_chart = cached_context.get(
        'dashboard_chart',
        cached.get('dashboard_chart', {'months': []}),
    )
    invoiced_trend = cached_context.get('invoiced_trend', cached.get('invoiced_trend', []))
    expense_trend_totals = cached_context.get(
        'expense_trend_totals',
        cached.get('expense_trend_totals', []),
    )

    def ordered_invoices(ids):
        if not ids:
            return Invoice.objects.none()
        ordering = Case(
            *[When(pk=pk, then=pos) for pos, pk in enumerate(ids)],
            output_field=IntegerField(),
        )
        return (
            Invoice.objects.filter(pk__in=ids)
            .select_related('project', 'customer__company')
            .order_by(ordering)
        )

    top_pending = ordered_invoices(cached['top_pending_ids'])
    top_overdue = ordered_invoices(cached['top_overdue_ids'])
    recent_invoices = _set_invoice_display_states(list(ordered_invoices(cached['recent_invoice_ids'])))

    return {
        'pending_total': pending_total,
        'overdue_total': overdue_total,
        'invoiced_total': invoiced_total,
        'paid_total': paid_total,
        'selected_period': period_key,
        'period_name': cached['period_label'],
        'top_pending': top_pending,
        'top_overdue': top_overdue,
        'recent_invoices': recent_invoices,
        'dashboard_chart': dashboard_chart,
        'invoiced_trend': invoiced_trend,
        'expense_trend_totals': expense_trend_totals,
    }


def _build_cross_company_dashboard_scope(request):
    issuers = list(get_available_issuers(request).select_related('company'))
    issuer_ids = [issuer.pk for issuer in issuers]

    if not issuer_ids:
        return {
            'issuers': issuers,
            'issuer_ids': issuer_ids,
            'invoice_queryset': Invoice.objects.none(),
            'payment_queryset': Payment.objects.none(),
            'expense_queryset': Expense.objects.none(),
        }

    return {
        'issuers': issuers,
        'issuer_ids': issuer_ids,
        'invoice_queryset': Invoice.objects.filter(issuer_id__in=issuer_ids).select_related(
            'issuer__company',
            'project',
            'customer__company',
        ),
        'payment_queryset': Payment.objects.filter(issuer_id__in=issuer_ids).select_related(
            'issuer__company',
            'customer__company',
            'project',
        ),
        'expense_queryset': Expense.objects.filter(issuer_id__in=issuer_ids).select_related(
            'issuer__company',
            'customer__company',
            'project',
            'invoice',
        ),
    }


def _build_cross_company_recent_invoices(invoice_queryset, *, start=None, end=None, limit=DASHBOARD_DEFAULT_MAX_RESULTS):
    recent_invoices = _apply_date_range(invoice_queryset, start, end)
    recent_invoices = recent_invoices.annotate(
        dashboard_has_number=Case(
            When(number__isnull=False, then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        )
    ).order_by('-issued_date', '-dashboard_has_number', '-number', '-pk')[:limit]

    invoices = _set_invoice_display_states(list(recent_invoices))
    for invoice in invoices:
        invoice.company = invoice.issuer.company if invoice.issuer_id and invoice.issuer else None
        invoice.company_name = invoice.company.name if invoice.company else ''
    return invoices


def _build_cross_company_recent_payments(payment_queryset, *, start=None, end=None, limit=DASHBOARD_DEFAULT_MAX_RESULTS):
    recent_payments = payment_queryset
    if start:
        recent_payments = recent_payments.filter(received_at__gte=start)
    if end:
        recent_payments = recent_payments.filter(received_at__lte=end)
    recent_payments = recent_payments.prefetch_related('applications__invoice').order_by('-received_at', '-pk')[:limit]

    payments = list(recent_payments)
    for payment in payments:
        payment.company = payment.issuer.company if payment.issuer_id and payment.issuer else None
        payment.company_name = payment.company.name if payment.company else ''
        first_application = next(iter(payment.applications.all()), None)
        payment.dashboard_invoice = first_application.invoice if first_application else None
    return payments


def dashboard(request):
    sanitize_decimal_columns()
    issuer = get_active_issuer(request)
    if not issuer:
        messages.error(request, 'Add a company before proceeding.')
        return redirect('company:settings')

    date_filter = get_global_date_filter(request)
    context = _build_dashboard_context(request, issuer, date_filter)
    return render(request, 'invoices/dashboard.html', context)


def cross_company_dashboard(request):
    sanitize_decimal_columns()
    scope = _build_cross_company_dashboard_scope(request)
    issuers = scope['issuers']
    if not issuers:
        messages.error(request, 'Add a company before proceeding.')
        return redirect('company:settings')

    date_filter = get_global_date_filter(request)
    dashboard_filter_state = _get_dashboard_filter_state(request)
    invoice_queryset = scope['invoice_queryset']
    payment_queryset = scope['payment_queryset']
    expense_queryset = scope['expense_queryset']
    if date_filter['start']:
        invoice_queryset = invoice_queryset.filter(issued_date__gte=date_filter['start'])
        payment_queryset = payment_queryset.filter(received_at__gte=date_filter['start'])
        expense_queryset = expense_queryset.filter(paid_date__gte=date_filter['start'])
    if date_filter['end']:
        invoice_queryset = invoice_queryset.filter(issued_date__lte=date_filter['end'])
        payment_queryset = payment_queryset.filter(received_at__lte=date_filter['end'])
        expense_queryset = expense_queryset.filter(paid_date__lte=date_filter['end'])

    recent_invoice_queryset = _apply_dashboard_invoice_status_filter(
        invoice_queryset,
        dashboard_filter_state['invoice_status'],
    )
    max_results = dashboard_filter_state['max_results']

    cache_signature = _cross_company_dashboard_cache_signature(
        invoice_queryset,
        payment_queryset,
        expense_queryset,
    )
    cache_key = _build_cross_company_dashboard_cache_key(
        scope['issuer_ids'],
        date_filter['key'],
        cache_signature,
        invoice_status=dashboard_filter_state['invoice_status'],
        max_results=max_results,
    )
    cached = cache.get(cache_key)

    if cached and cached.get('signature') != cache_signature:
        cached = None

    if not cached:
        paid_total = payment_queryset.aggregate(
            total=Coalesce(
                Sum('base_currency_amount'),
                Value(ZERO_DECIMAL),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )['total']
        expense_total = expense_queryset.aggregate(
            total=Coalesce(
                Sum('amount'),
                Value(ZERO_DECIMAL),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )['total']
        recent_invoice_ids = list(
            recent_invoice_queryset.annotate(
                dashboard_has_number=Case(
                    When(number__isnull=False, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            ).order_by('-issued_date', '-dashboard_has_number', '-number', '-pk').values_list('id', flat=True)[:max_results]
        )
        recent_payment_ids = list(
            payment_queryset.order_by('-received_at', '-pk').values_list('id', flat=True)[:max_results]
        )
        dashboard_chart, invoiced_trend, expense_trend_totals = _build_dashboard_chart(
            scope['invoice_queryset'],
            scope['expense_queryset'],
        )
        cached = {
            'signature': cache_signature,
            'paid_total': paid_total,
            'expense_total': expense_total,
            'recent_invoice_ids': recent_invoice_ids,
            'recent_payment_ids': recent_payment_ids,
            'dashboard_chart': dashboard_chart,
            'invoiced_trend': invoiced_trend,
            'expense_trend_totals': expense_trend_totals,
        }
        cache.set(cache_key, cached, 300)
        _register_cross_company_dashboard_cache_key(scope['issuer_ids'], cache_key)

    def ordered_cross_company_invoices(ids):
        if not ids:
            return Invoice.objects.none()
        ordering = Case(
            *[When(pk=pk, then=pos) for pos, pk in enumerate(ids)],
            output_field=IntegerField(),
        )
        return scope['invoice_queryset'].filter(pk__in=ids).order_by(ordering)

    def ordered_cross_company_payments(ids):
        if not ids:
            return Payment.objects.none()
        ordering = Case(
            *[When(pk=pk, then=pos) for pos, pk in enumerate(ids)],
            output_field=IntegerField(),
        )
        return scope['payment_queryset'].filter(pk__in=ids).order_by(ordering)

    paid_total = cached['paid_total']
    expense_total = cached['expense_total']
    dashboard_chart = cached.get('dashboard_chart', {'months': []})
    recent_invoices = _build_cross_company_recent_invoices(
        ordered_cross_company_invoices(cached['recent_invoice_ids']),
        limit=max_results,
    )
    recent_payments = _build_cross_company_recent_payments(
        ordered_cross_company_payments(cached['recent_payment_ids']),
        limit=max_results,
    )

    context = {
        'pending_total': ZERO_DECIMAL,
        'overdue_total': ZERO_DECIMAL,
        'invoiced_total': ZERO_DECIMAL,
        'paid_total': paid_total,
        'expense_total': expense_total,
        'selected_period': date_filter['key'],
        'period_name': date_filter['label'],
        'top_pending': Invoice.objects.none(),
        'top_overdue': Invoice.objects.none(),
        'recent_invoices': recent_invoices,
        'recent_payments': recent_payments,
        'dashboard_chart': dashboard_chart,
        'invoiced_trend': cached.get('invoiced_trend', []),
        'expense_trend_totals': cached.get('expense_trend_totals', []),
        'is_cross_company_dashboard': True,
        'cross_company_issuers': issuers,
        'dashboard_invoice_status': dashboard_filter_state['invoice_status'],
        'dashboard_invoice_status_options': dashboard_filter_state['invoice_status_options'],
        'dashboard_max_results': max_results,
        'dashboard_max_results_options': dashboard_filter_state['max_results_options'],
    }
    return render(request, 'invoices/cross_company_dashboard.html', context)


def bulk_last_month(request):
    """Preview and generate last month's invoices in bulk.
    For each active project with at least one prior invoice, copy the most recent invoice's lines
    and create a draft with issued_date = last day of last month.
    """
    sanitize_decimal_columns()
    issuer = get_active_issuer(request)
    if not issuer:
        messages.error(request, 'Add a company before proceeding.')
        return redirect('company:settings')

    from datetime import date, timedelta
    today = date.today()
    first_of_this = today.replace(day=1)
    last_month_end = first_of_this - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    # Candidates: active projects with any prior invoice (could filter by last month only, but copying last invoice helps speed)
    projects = Project.objects.filter(
        customer__issuer=issuer, status=Project.STATUS_ACTIVE
    ).prefetch_related('invoices').order_by('title')

    candidates = []
    for project in projects:
        last_invoice = project.invoices.order_by('-issued_date', '-number').first()
        if last_invoice:
            candidates.append({'project': project, 'invoice': last_invoice})

    candidates = []
    for project in projects:
        last_invoice = project.invoices.order_by('-issued_date', '-number').prefetch_related('orderline_set').first()
        if last_invoice:
            lines = [
                {
                    'description': line.description or '',
                    'quantity': line.quantity or Decimal('0'),
                    'unit_price': line.unit_price or Decimal('0'),
                }
                for line in OrderLine.objects.filter(invoice=last_invoice)
            ]
            if lines:
                candidates.append({
                    'project': project,
                    'last_invoice': last_invoice,
                    'lines': lines,
                })

    candidates_map = {str(item['project'].pk): item for item in candidates}

    if request.method == 'POST':
        action = request.POST.get('action', 'create')
        selected_ids = request.POST.getlist('selected')
        created = 0
        generated = 0
        skipped_projects = []

        for pid in selected_ids:
            candidate = candidates_map.get(pid)
            if not candidate:
                continue

            descriptions = request.POST.getlist(f'project-{pid}-description')
            quantities = request.POST.getlist(f'project-{pid}-quantity')
            prices = request.POST.getlist(f'project-{pid}-unit_price')

            payload = []
            for desc, qty, price in zip(descriptions, quantities, prices):
                desc = (desc or '').strip()
                qty = (qty or '').strip()
                price = (price or '').strip()
                if not desc:
                    continue
                try:
                    quantity = Decimal(qty) if qty else Decimal('0')
                except (InvalidOperation, ValueError):
                    quantity = Decimal('0')
                try:
                    unit_price = Decimal(price) if price else Decimal('0')
                except (InvalidOperation, ValueError):
                    unit_price = Decimal('0')

                if quantity == 0 and unit_price == 0:
                    continue
                payload.append((desc, quantity, unit_price))

            if not payload:
                skipped_projects.append(candidate['project'].project_code)
                continue

            last_invoice = candidate['last_invoice']
            project = candidate['project']
            new_inv = Invoice.objects.create(
                issuer=issuer,
                customer=last_invoice.customer,
                project=project,
                bank_account=last_invoice.bank_account if (
                    last_invoice.bank_account_id
                    and last_invoice.bank_account.is_active
                    and last_invoice.bank_account.issuer_id == issuer.id
                ) else resolve_invoice_bank_account(issuer, customer=last_invoice.customer, project=project),
                issued_date=last_month_end,
                status=Invoice.STATUS_DRAFT,
            )

            for desc, quantity, unit_price in payload:
                OrderLine.objects.create(
                    invoice=new_inv,
                    description=desc,
                    quantity=quantity,
                    unit_price=unit_price,
                )

            new_inv.calculate_totals(OrderLine.objects.filter(invoice=new_inv))
            new_inv.save()
            created += 1

            if action == 'create_and_generate':
                try:
                    save_invoice_pdf(request, new_inv.id)
                    generated += 1
                except RuntimeError:
                    messages.warning(
                        request,
                        f'Invoice {new_inv.sequence_number} created but PDF generation is unavailable.',
                    )

        if created:
            if action == 'create_and_generate':
                messages.success(
                    request,
                    f'Created {created} draft invoice(s) and generated {generated} PDF(s).',
                )
            else:
                messages.success(request, f'Created {created} draft invoice(s) for last month.')
        else:
            messages.warning(
                request,
                'No invoices created. Make sure at least one project is selected and line items contain data.',
            )

        if skipped_projects:
            messages.info(
                request,
                'Skipped projects with no line items: ' + ', '.join(skipped_projects)
            )

        invalidate_dashboard_cache(issuer.pk)

        return redirect('dashboard')

    context = {
        'candidates': [
            {
                'project': item['project'],
                'invoice': item['last_invoice'],
                'lines': item['lines'],
            }
            for item in candidates
        ],
        'last_month_start': last_month_start,
        'last_month_end': last_month_end,
    }
    return render(request, 'invoices/bulk_last_month.html', context)


def add_invoice(request):
    issuer = get_active_issuer(request)
    if not issuer:
        messages.error(request, 'Add a company before creating invoices.')
        return redirect('company:settings')

    if not Project.objects.filter(
        customer__issuer=issuer,
        customer__is_active=True,
        status=Project.STATUS_ACTIVE,
    ).exists():
        messages.error(request, 'Create a project before creating invoices.')
        return redirect('projects:add')

    reference_number_hint = ''
    selected_project = None
    prefilled_customer = None

    customer_raw = request.GET.get('customer')
    if request.method == 'POST':
        customer_raw = request.POST.get('customer') or customer_raw
    if customer_raw:
        try:
            prefilled_customer = Customer.objects.get(
                pk=int(customer_raw),
                issuer=issuer,
                is_active=True,
            )
        except (Customer.DoesNotExist, ValueError, TypeError):
            prefilled_customer = None

    if request.method == 'POST':
        reference_number_hint = request.POST.get('reference_number_hint', '')
        invoice_seed = Invoice(issuer=issuer)
        invoice_form = InvoiceForm(
            request.POST,
            instance=invoice_seed,
            issuer=issuer,
            customer=prefilled_customer,
        )
        order_formset = OrderLineFormSet(request.POST, instance=invoice_seed)
        selected_project = _resolve_selected_project(invoice_form, invoice_seed, issuer)

        if not reference_number_hint:
            issued_raw = invoice_form.data.get('issued_date') if hasattr(invoice_form, 'data') else None
            issued_for_hint = None
            if issued_raw:
                try:
                    issued_for_hint = date.fromisoformat(issued_raw)
                except (TypeError, ValueError):
                    issued_for_hint = None
            reference_number_hint = _suggest_invoice_reference(issuer, issued_for_hint)

        if invoice_form.is_valid() and order_formset.is_valid():
            with transaction.atomic():
                new_invoice = invoice_form.save(commit=False)
                new_invoice.issuer = issuer

                reference_value = invoice_form.cleaned_data.get('reference_number') or ''
                suggestion_current = _suggest_invoice_reference(issuer, invoice_form.cleaned_data.get('issued_date'))
                if (
                    not reference_value
                    or reference_value == reference_number_hint
                    or reference_value == suggestion_current
                ):
                    new_invoice.reference_number = ''

                new_invoice.save()

                order_formset.instance = new_invoice
                order_formset.save()

                invoice_orders = OrderLine.objects.filter(invoice=new_invoice)
                new_invoice.calculate_totals(invoice_orders)
                new_invoice.save()

            try:
                save_invoice_pdf(request, new_invoice.id)
            except RuntimeError:
                messages.warning(
                    request,
                    f'Invoice {new_invoice.sequence_number} created but PDF generation is unavailable.',
                )
            invalidate_dashboard_cache(issuer.pk)
            messages.success(request, 'Invoice created successfully.')
            return redirect(f"{reverse('invoices:edit', args=[new_invoice.id])}?tab=edit")
    else:
        issued_default = date.today()
        invoice_seed = Invoice(issuer=issuer, issued_date=issued_default)
        reference_number_hint = _suggest_invoice_reference(issuer, issued_default)
        invoice_seed.reference_number = reference_number_hint

        project_id = request.GET.get('project')
        if project_id:
            selected_project = Project.objects.filter(
                pk=project_id,
                customer__issuer=issuer,
                customer__is_active=True,
                status=Project.STATUS_ACTIVE,
            ).first()
            if selected_project:
                invoice_seed.project = selected_project
                invoice_seed.customer = selected_project.customer
                if not invoice_seed.notes and selected_project.comment:
                    invoice_seed.notes = selected_project.comment
                default_term = selected_project.payment_term or (
                    selected_project.customer.payment_term if selected_project.customer else None
                )
                if default_term:
                    invoice_seed.payment_term = default_term
                prefilled_customer = selected_project.customer
        if prefilled_customer and not invoice_seed.customer_id:
            invoice_seed.customer = prefilled_customer
        if invoice_seed.payment_term and invoice_seed.issued_date and not invoice_seed.due_date:
            invoice_seed.due_date = invoice_seed.issued_date + timedelta(days=invoice_seed.payment_term.days)
        if not invoice_seed.bank_account_id:
            invoice_seed.bank_account = resolve_invoice_bank_account(
                issuer,
                customer=invoice_seed.customer or prefilled_customer,
                project=invoice_seed.project,
            )

        invoice_form = InvoiceForm(
            instance=invoice_seed,
            issuer=issuer,
            customer=prefilled_customer,
        )
        order_formset = OrderLineFormSet(instance=invoice_seed)

        if not selected_project:
            selected_project = invoice_seed.project
        if not selected_project:
            init_project_pk = invoice_form.initial.get('project')
            if init_project_pk:
                selected_project = invoice_form.fields['project'].queryset.filter(pk=init_project_pk).first()

    recent_items_data = _recent_items_payload(selected_project)
    payment_terms_meta = _payment_terms_meta()
    project_payment_defaults = _project_payment_defaults(issuer)
    customer_payment_defaults = _customer_payment_defaults(issuer)
    discount_rate = str(getattr(invoice_seed, 'discount_value', Decimal('0')) or Decimal('0'))
    tax_rate = str(getattr(invoice_seed, 'tax_value', Decimal('0')) or Decimal('0'))
    currency_meta = _invoice_currency_meta(invoice_seed)
    currency_symbol = currency_meta['symbol']
    context = {
        'invoice_form': invoice_form,
        'order_formset': order_formset,
        'selected_project_id': selected_project.id if selected_project else '',
        'recent_items_data': recent_items_data,
        'reference_number_hint': reference_number_hint,
        'payment_terms_meta': payment_terms_meta,
        'project_payment_defaults': project_payment_defaults,
        'customer_payment_defaults': customer_payment_defaults,
        'discount_rate': discount_rate,
        'tax_rate': tax_rate,
        'currency_symbol': currency_symbol,
        'currency_code': currency_meta['code'],
        'currency_display': currency_meta['display'],
        'prefilled_customer_id': prefilled_customer.id if prefilled_customer else '',
    }
    return render(request, 'invoices/form_invoice.html', context)


def make_invoice(request, id):
    """Invoice page with tabs: Preview (default) and Edit.

    - Preview shows HTML version used for PDF generation (via existing /pdf/ route)
    - Edit shows the current invoice form
    """
    sanitize_decimal_columns()
    issuer = get_active_issuer(request)
    invoice = get_object_or_404(Invoice, pk=id, issuer=issuer)
    selected_project = invoice.project

    active_tab = request.GET.get('tab') or 'preview'

    if request.method == 'POST':
        active_tab = 'edit'
        invoice_form = InvoiceForm(request.POST, instance=invoice, issuer=issuer)
        order_formset = OrderLineFormSet(request.POST, instance=invoice)

        project_id = invoice_form.data.get('project') if invoice_form.is_bound else None
        if project_id:
            selected_project = Project.objects.filter(pk=project_id, customer__issuer=issuer).first()

        if invoice_form.is_valid() and order_formset.is_valid():
            invoice = invoice_form.save(commit=False)
            invoice.issuer = issuer
            invoice.save()

            order_formset.instance = invoice
            order_formset.save()

            invoice_orders = OrderLine.objects.filter(invoice=invoice)
            invoice.calculate_totals(invoice_orders)
            invoice.save()
            save_invoice_pdf(request, id)

            return redirect(f"{reverse('invoices:edit', args=[invoice.id])}?tab=edit")
        # fall through to re-render with errors on the edit tab
    else:  # GET request
        invoice_form = InvoiceForm(instance=invoice, issuer=issuer)
        order_formset = OrderLineFormSet(instance=invoice)

    # Recent items payload (used by JS if needed in future)
    recent_items_data = _recent_items_payload(selected_project, exclude_invoice=invoice)
    selected_project_id = selected_project.id if selected_project else None
    currency_meta = _invoice_currency_meta(invoice)
    invoice_payment_applications = []
    if invoice.status in (Invoice.STATUS_INVOICED, Invoice.STATUS_OVERDUE, Invoice.STATUS_PAID):
        invoice_payment_applications = list(
            PaymentApplication.objects.filter(invoice=invoice)
            .select_related('payment')
            .order_by('-payment__received_at', '-payment__id')
        )

    project_outstanding_invoices = []
    if invoice.project:
        project_outstanding_invoices = _set_invoice_display_states(
            list(
                Invoice.objects.filter(
                    issuer=invoice.issuer,
                    project=invoice.project,
                    status__in=[Invoice.STATUS_INVOICED, Invoice.STATUS_OVERDUE],
                    amount_due__gt=ZERO_DECIMAL,
                )
                .select_related('project', 'customer__company')
                .order_by('-issued_date', '-number')
            )
        )

    context = {
        'invoice': invoice,
        'invoice_form': invoice_form,
        'order_formset': order_formset,
        'selected_project_id': selected_project_id,
        'recent_items_data': recent_items_data,
        'recent_items_exclude_invoice_id': invoice.id,
        'show_recent_items': invoice.status == Invoice.STATUS_DRAFT,
        'status_badge_class': _set_invoice_display_state(invoice).display_status_badge_class,
        'active_tab': active_tab,
        'preview_url': reverse('invoices:pdf', args=[invoice.id]),
        'invoice_remaining': _invoice_remaining_amount(invoice),
        'show_add_payment': _invoice_remaining_amount(invoice) > ZERO_DECIMAL,
        'payment_context': 'invoice',
        'payment_terms_meta': _payment_terms_meta(),
        'project_payment_defaults': _project_payment_defaults(issuer),
        'customer_payment_defaults': _customer_payment_defaults(issuer),
        'discount_rate': str(invoice.discount_value or Decimal('0')),
        'tax_rate': str(invoice.tax_value or Decimal('0')),
        'currency_symbol': currency_meta['symbol'],
        'currency_code': currency_meta['code'],
        'currency_display': currency_meta['display'],
        'invoice_notes': _invoice_notes(invoice),
        'invoice_payment_applications': invoice_payment_applications,
        # Payment drawer helpers
        'customer_projects': (
            list(
                Project.objects.filter(
                    customer=invoice.customer,
                    status=Project.STATUS_ACTIVE,
                ).order_by('title')
            ) if invoice.customer else []
        ),
        'project_outstanding_invoices': project_outstanding_invoices,
    }

    return render(request, 'invoices/invoice_profile.html', context)


def invoice_drawer(request, id):
    sanitize_decimal_columns()
    issuer = get_active_issuer(request)
    invoice = get_object_or_404(Invoice, pk=id, issuer=issuer)
    order_lines = OrderLine.objects.filter(invoice=invoice)
    currency_meta = _invoice_currency_meta(invoice)

    if request.method == 'POST':
        form = InvoiceForm(request.POST, instance=invoice, issuer=issuer)
        formset = OrderLineFormSet(request.POST, instance=invoice)
        if form.is_valid() and formset.is_valid():
            inv = form.save(commit=False)
            inv.issuer = issuer
            inv.save()
            formset.instance = inv
            for form_obj in formset.forms:
                cleaned = getattr(form_obj, 'cleaned_data', None)
                if not cleaned:
                    continue
                if cleaned.get('DELETE'):
                    existing = cleaned.get('id')
                    if existing:
                        existing.delete()
                    continue
                if not cleaned.get('id'):
                    quantity = cleaned.get('quantity') or Decimal('0')
                    unit_price = cleaned.get('unit_price') or Decimal('0')
                    description = (cleaned.get('description') or '').strip()
                    if not description and quantity == 0 and unit_price == 0:
                        continue
                obj = form_obj.save(commit=False)
                obj.invoice = inv
                obj.save()
            if hasattr(formset, 'save_m2m'):
                formset.save_m2m()
            inv.calculate_totals(OrderLine.objects.filter(invoice=inv))
            inv.save()
            try:
                save_invoice_pdf(request, inv.id)
            except RuntimeError:
                pass
            invalidate_dashboard_cache(issuer.pk)
        else:
            selected_project = _resolve_selected_project(form, invoice, issuer)
            response = render(request, 'invoices/partials/invoice_form_inner.html', {
                'invoice': invoice,
                'invoice_form': form,
                'order_formset': formset,
                'selected_project_id': selected_project.id if selected_project else '',
                'recent_items_data': _recent_items_payload(selected_project, exclude_invoice=invoice),
                'recent_items_exclude_invoice_id': invoice.id,
                'status_badge_class': _set_invoice_display_state(invoice).display_status_badge_class,
                'payment_terms_meta': _payment_terms_meta(),
                'project_payment_defaults': _project_payment_defaults(issuer),
                'customer_payment_defaults': _customer_payment_defaults(issuer),
                'discount_rate': str(invoice.discount_value or Decimal('0')),
                'tax_rate': str(invoice.tax_value or Decimal('0')),
                'currency_symbol': currency_meta['symbol'],
                'currency_code': currency_meta['code'],
                'currency_display': currency_meta['display'],
                'invoice_notes': _invoice_notes(invoice),
            })
            return response

    form = InvoiceForm(instance=invoice, issuer=issuer)
    formset = OrderLineFormSet(instance=invoice)
    selected_project = _resolve_selected_project(form, invoice, issuer)
    currency_meta = _invoice_currency_meta(invoice)
    return render(request, 'invoices/partials/invoice_form_inner.html', {
        'invoice': invoice,
        'invoice_form': form,
        'order_formset': formset,
        'selected_project_id': selected_project.id if selected_project else '',
        'recent_items_data': _recent_items_payload(selected_project, exclude_invoice=invoice),
        'recent_items_exclude_invoice_id': invoice.id,
        'status_badge_class': _set_invoice_display_state(invoice).display_status_badge_class,
        'payment_terms_meta': _payment_terms_meta(),
        'project_payment_defaults': _project_payment_defaults(issuer),
        'customer_payment_defaults': _customer_payment_defaults(issuer),
        'discount_rate': str(invoice.discount_value or Decimal('0')),
        'tax_rate': str(invoice.tax_value or Decimal('0')),
        'currency_symbol': currency_meta['symbol'],
        'currency_code': currency_meta['code'],
        'currency_display': currency_meta['display'],
        'invoice_notes': _invoice_notes(invoice),
    })


from django.views.decorators.csrf import csrf_exempt
@csrf_exempt
def invoice_autosave(request, id):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'POST required'}, status=405)

    sanitize_decimal_columns()
    issuer = get_active_issuer(request)
    invoice = get_object_or_404(Invoice, pk=id, issuer=issuer)
    data = request.POST.dict()

    # Header fields
    fields = ['reference_number', 'issued_date', 'due_date', 'payment_term', 'status', 'project', 'bank_account', 'notes']
    changed = False
    project_changed = False
    payment_term_changed = False
    issued_date_changed = False
    due_date_changed = False
    for f in fields:
        if f in data and data[f] != '':
            if f == 'project':
                try:
                    proj = Project.objects.get(pk=data[f], customer__issuer=issuer)
                except Project.DoesNotExist:
                    continue
                if invoice.project_id != proj.id:
                    invoice.project = proj
                    invoice.customer = invoice.project.customer
                    changed = True
                    project_changed = True
            elif f == 'issued_date':
                from datetime import datetime as dt
                try:
                    new_date = dt.strptime(data[f], '%Y-%m-%d').date()
                    if invoice.issued_date != new_date:
                        invoice.issued_date = new_date
                        changed = True
                        issued_date_changed = True
                except ValueError:
                    pass
            elif f == 'due_date':
                from datetime import datetime as dt
                try:
                    new_due = dt.strptime(data[f], '%Y-%m-%d').date()
                except ValueError:
                    new_due = None
                if invoice.due_date != new_due:
                    invoice.due_date = new_due
                    changed = True
                    due_date_changed = True
            elif f == 'payment_term':
                try:
                    term = PaymentTerm.objects.get(pk=data[f])
                except PaymentTerm.DoesNotExist:
                    continue
                if invoice.payment_term_id != term.id:
                    invoice.payment_term = term
                    changed = True
                    payment_term_changed = True
            elif f == 'bank_account':
                try:
                    account = issuer.bank_accounts.get(pk=data[f], is_active=True)
                except Exception:
                    continue
                if invoice.bank_account_id != account.id:
                    invoice.bank_account = account
                    changed = True
            elif f == 'reference_number':
                val = data[f].strip()
                if invoice.reference_number != val:
                    invoice.reference_number = val
                    changed = True
            else:
                val = data[f]
                if getattr(invoice, f) != val:
                    setattr(invoice, f, val)
                    changed = True
        elif f == 'payment_term' and f in data and data[f] == '':
            if invoice.payment_term_id is not None:
                invoice.payment_term = None
                changed = True
                payment_term_changed = True
        elif f == 'bank_account' and f in data and data[f] == '':
            if invoice.bank_account_id is not None:
                invoice.bank_account = None
                changed = True
        elif f == 'due_date' and f in data and data[f] == '':
            if invoice.due_date is not None:
                invoice.due_date = None
                changed = True
                due_date_changed = True
        elif f == 'notes' and f in data and data[f] == '':
            if invoice.notes:
                invoice.notes = ''
                changed = True

    if (project_changed or not invoice.payment_term_id) and invoice.project:
        if not payment_term_changed:
            default_term = invoice.project.payment_term or (
                invoice.project.customer.payment_term if invoice.project.customer else None
            )
            if default_term and invoice.payment_term_id != default_term.id:
                invoice.payment_term = default_term
                changed = True
                payment_term_changed = True

    if invoice.issued_date and invoice.payment_term and (issued_date_changed or payment_term_changed) and not due_date_changed:
        suggested_due = invoice.issued_date + timedelta(days=invoice.payment_term.days)
        if invoice.due_date != suggested_due:
            invoice.due_date = suggested_due
            changed = True

    if project_changed and invoice.project and not invoice.bank_account_id:
        suggested_account = resolve_invoice_bank_account(issuer, customer=invoice.customer, project=invoice.project, exclude_invoice=invoice)
        if suggested_account and invoice.bank_account_id != suggested_account.id:
            invoice.bank_account = suggested_account
            changed = True

    if changed:
        invoice.save()
        invalidate_dashboard_cache(issuer.pk)
        try:
            save_invoice_pdf(request, invoice.id)
        except RuntimeError:
            pass

    return JsonResponse({
        'ok': True,
        'total_due': str(invoice.total_due),
        'sub_total': str(invoice.sub_total),
        'status': invoice.get_status_display(),
    })


@require_POST
def invoice_quick_save(request, id):
    sanitize_decimal_columns()
    issuer = get_active_issuer(request)
    invoice = get_object_or_404(Invoice, pk=id, issuer=issuer)

    form = InvoiceForm(request.POST, instance=invoice, issuer=issuer)
    formset = OrderLineFormSet(request.POST, instance=invoice)
    currency_meta = _invoice_currency_meta(invoice)

    if form.is_valid() and formset.is_valid():
        with transaction.atomic():
            inv = form.save(commit=False)
            inv.issuer = issuer
            inv.save()

            formset.instance = inv
            formset.save()

            orders = OrderLine.objects.filter(invoice=inv)
            inv.calculate_totals(orders)
            inv.save()

        invalidate_dashboard_cache(issuer.pk)
        return JsonResponse({'ok': True})

    errors = {
        'invoice': form.errors,
        'order_lines': formset.errors,
        'non_form_errors': formset.non_form_errors(),
    }
    return JsonResponse({
        'ok': False,
        'errors': errors,
        'currency_symbol': currency_meta['symbol'],
        'currency_code': currency_meta['code'],
        'currency_display': currency_meta['display'],
        'invoice_notes': _invoice_notes(invoice),
    }, status=400)


@require_POST
def delete_invoice(request, id):
    issuer = get_active_issuer(request)
    try:
        invoice = get_object_or_404(Invoice, pk=id, issuer=issuer)
        invoice.delete()
    except Exception:
        messages.error(request, 'Something went wrong')
    else:
        invalidate_dashboard_cache(issuer.pk)
    return redirect('invoices:list')


def save_invoice_pdf(request, inv_id):
    try:
        from django_weasyprint.views import WeasyTemplateResponse
    except OSError as exc:
        raise RuntimeError("WeasyPrint dependencies are not available on this system.") from exc
    from django.contrib.staticfiles import finders

    invoice = Invoice.objects.get(pk=inv_id)
    raw_lines = list(OrderLine.objects.filter(invoice=invoice))
    order_lines = []
    for line in raw_lines:
        quantity = line.quantity or Decimal('0')
        unit_price = line.unit_price or Decimal('0')
        amount = line.line_total or Decimal('0')
        if not amount:
            amount = unit_price
        order_lines.append({
            'description': line.description,
            'quantity': quantity,
            'unit_price': unit_price,
            'amount': amount,
        })
    min_rows = 5
    empty_rows_count = max(min_rows - len(order_lines), 0)

    currency_meta = _invoice_currency_meta(invoice)

    context = {
        'invoice': invoice,
        'order_lines': order_lines,
        'empty_rows': range(empty_rows_count),
        'project_name': invoice.project.title if invoice.project else '',
        'currency_symbol': currency_meta['symbol'],
        'currency_code': currency_meta['code'],
        'currency_display': currency_meta['display'],
        'invoice_notes': _invoice_notes(invoice),
        'payment_notes': resolve_invoice_payment_notes(invoice),
        'bank_account': invoice.bank_account,
        # Inline CSS for reliable PDF styling even when static URLs are not reachable (e.g., inside containers)
        'pdf_inline_css': '',
    }

    css_path = finders.find('invoices/css/render_invoice_pdf_styles.css')
    if css_path:
        with open(css_path, encoding='utf-8') as css_file:
            context['pdf_inline_css'] = css_file.read()

    pdf_render = WeasyTemplateResponse(
        request=request, template='invoices/invoice_pdf.html', context=context).rendered_content
    safe_identifier = (
        invoice.sequence_number.replace('/', '-').replace(' ', '-').replace('.', '-').replace(':', '-')
    )
    customer_slug = invoice.customer.company.name.replace(" ", "-") if invoice.customer and invoice.customer.company else "customer"
    pdf_file_name = f"{safe_identifier}_{customer_slug}_{invoice.issued_date}.pdf"

    # Overwrite existing pdf with the new one
    invoice.pdf_document.delete()
    invoice.pdf_document.save(pdf_file_name, ContentFile(pdf_render))

    return True


def check_pdf(request, id):
    issuer = get_active_issuer(request)
    invoice = get_object_or_404(Invoice, pk=id, issuer=issuer)
    raw_lines = list(OrderLine.objects.filter(invoice=invoice))
    order_lines = []
    for line in raw_lines:
        quantity = line.quantity or Decimal('0')
        unit_price = line.unit_price or Decimal('0')
        amount = line.line_total or Decimal('0')
        if not amount:
            amount = unit_price
        order_lines.append({
            'description': line.description,
            'quantity': quantity,
            'unit_price': unit_price,
            'amount': amount,
        })
    min_rows = 5
    empty_rows_count = max(min_rows - len(order_lines), 0)

    currency_meta = _invoice_currency_meta(invoice)

    context = {
        'invoice': invoice,
        'order_lines': order_lines,
        'empty_rows': range(empty_rows_count),
        'project_name': invoice.project.title if invoice.project else '',
        'currency_symbol': currency_meta['symbol'],
        'currency_code': currency_meta['code'],
        'currency_display': currency_meta['display'],
        'invoice_notes': _invoice_notes(invoice),
        'payment_notes': resolve_invoice_payment_notes(invoice),
        'bank_account': invoice.bank_account,
    }

    return render(request, 'invoices/invoice_pdf.html', context)

def invoice_generate_pdf(request, id):
    """Generate a fresh PDF for the invoice and redirect to the file URL.

    Opens in a new tab when link uses target="_blank".
    """
    issuer = get_active_issuer(request)
    invoice = get_object_or_404(Invoice, pk=id, issuer=issuer)
    try:
        save_invoice_pdf(request, invoice.id)
        invoice.refresh_from_db(fields=['pdf_document'])
        if getattr(invoice, 'pdf_document', None) and invoice.pdf_document.url:
            return redirect(invoice.pdf_document.url)
        messages.error(request, 'PDF was generated but no file URL is available.')
    except RuntimeError as exc:
        messages.error(request, f'PDF generation failed: {exc}')
    except Exception:
        messages.error(request, 'Something went wrong while generating the PDF.')
    # Fallback to staying on the invoice page
    return redirect(f"{reverse('invoices:edit', args=[invoice.id])}?tab=preview")


def _invoice_remaining_amount(invoice: Invoice) -> Decimal:
    applied = PaymentApplication.objects.filter(invoice=invoice).aggregate(
        total=Coalesce(Sum('amount_applied'), Decimal('0')),
    )['total']
    remaining = (invoice.total_due or ZERO_DECIMAL) - (applied or ZERO_DECIMAL)
    return max(remaining, ZERO_DECIMAL)


def _parse_decimal_input(raw: str) -> Decimal:
    """Parse decimal strings tolerant of common formats (comma decimal, spaces, euro sign)."""
    if raw is None:
        raise InvalidOperation('missing')
    s = str(raw).strip()
    s = s.replace('€', '').replace('\xa0', '').replace(' ', '')
    # Convert comma decimal if no dot present
    if ',' in s and '.' not in s:
        s = s.replace(',', '.')
    # If both separators present, drop commas as thousands
    if ',' in s and '.' in s:
        s = s.replace(',', '')
    return Decimal(s)


def invoice_add_payment(request, id):
    issuer = get_active_issuer(request)
    invoice = get_object_or_404(Invoice, pk=id, issuer=issuer)

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'POST required'}, status=405)

    # Inputs
    amount_raw = (request.POST.get('amount') or '').strip()
    received_at_raw = (request.POST.get('received_at') or '').strip()
    memo = (request.POST.get('memo') or '').strip()
    apply_to_ids = [val.replace(',', '').replace(' ', '') for val in request.POST.getlist('apply_to') if val]
    if not apply_to_ids:
        return JsonResponse({'ok': False, 'error': 'Select at least one invoice'}, status=400)

    # Parse amount
    try:
        amount = _parse_decimal_input(amount_raw)
    except (InvalidOperation, ValueError):
        return JsonResponse({'ok': False, 'error': 'Invalid amount'}, status=400)
    if amount <= ZERO_DECIMAL:
        return JsonResponse({'ok': False, 'error': 'Amount must be positive'}, status=400)

    # Parse date
    from datetime import datetime as dt
    received_at = invoice.issued_date
    if received_at_raw:
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
            try:
                received_at = dt.strptime(received_at_raw, fmt).date()
                break
            except ValueError:
                continue

    # Determine target invoices (limit to same issuer + project as current invoice)
    target_qs = (
        Invoice.objects.filter(
            pk__in=apply_to_ids,
            issuer=issuer,
            project=invoice.project,
            status__in=[Invoice.STATUS_INVOICED, Invoice.STATUS_OVERDUE],
            amount_due__gt=ZERO_DECIMAL,
        )
        .order_by('issued_date', 'number', 'id')
    )
    targets = list(target_qs)
    if not targets:
        return JsonResponse({'ok': False, 'error': 'No outstanding invoices selected'}, status=400)

    currency = invoice.currency or (invoice.customer.currency if invoice.customer else None)
    exchange_rate = currency.exchange_rate_to_base if currency else Decimal('1')

    with transaction.atomic():
        payment = Payment.objects.create(
            issuer=issuer,
            customer=invoice.customer,
            project=invoice.project,
            currency=currency,
            amount=amount,
            exchange_rate=exchange_rate,
            base_currency_amount=None,  # let model default handle
            received_at=received_at or date.today(),
            status=Payment.STATUS_APPLIED,
            memo=memo,
        )
        remaining_to_apply = amount
        for inv in targets:
            if remaining_to_apply <= ZERO_DECIMAL:
                break
            inv_remaining = inv.amount_due or ZERO_DECIMAL
            if inv_remaining <= ZERO_DECIMAL:
                continue
            portion = inv_remaining if inv_remaining <= remaining_to_apply else remaining_to_apply
            PaymentApplication.objects.create(
                payment=payment,
                invoice=inv,
                amount_applied=portion,
            )
            remaining_to_apply -= portion

    try:
        # Refresh PDFs for all impacted invoices
        for inv in targets:
            save_invoice_pdf(request, inv.id)
    except RuntimeError:
        pass

    return JsonResponse({'ok': True})


@require_POST
def invoice_remove_payment_application(request, id, application_id):
    issuer = get_active_issuer(request)
    invoice = get_object_or_404(Invoice, pk=id, issuer=issuer)
    application = get_object_or_404(
        PaymentApplication.objects.select_related('payment'),
        pk=application_id,
        invoice=invoice,
        payment__issuer=issuer,
    )
    payment = application.payment

    with transaction.atomic():
        application.delete()
        has_remaining_applications = PaymentApplication.objects.filter(payment=payment).exists()
        next_status = Payment.STATUS_APPLIED if has_remaining_applications else Payment.STATUS_PENDING
        if payment.status != next_status:
            payment.status = next_status
            payment.save(update_fields=['status', 'updated_at'])
        recalc_invoice_amounts(invoice.id)

    invalidate_dashboard_cache(issuer.pk)
    try:
        save_invoice_pdf(request, invoice.id)
    except RuntimeError:
        pass

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('Hx-Request'):
        return JsonResponse({'ok': True})
    return redirect(f"{reverse('invoices:edit', args=[invoice.id])}?tab=preview")

def add_customer(request):
    issuer = get_active_issuer(request)
    if not issuer:
        messages.error(request, 'Add a company before creating customers.')
        return redirect('company:settings')

    new_customer = Customer.objects.create(issuer=issuer)
    return redirect(f"{reverse('customers:detail', args=[new_customer.id])}?tab=edit")


def make_customer(request, id):
    request.GET = request.GET.copy()
    request.GET['tab'] = 'edit'
    return customer_profile(request, id)


def customer_profile(request, id):
    sanitize_decimal_columns()
    issuer = get_active_issuer(request)
    if not issuer:
        messages.error(request, 'Add a company before viewing customers.')
        return redirect('company:settings')

    customer = get_object_or_404(
        Customer.objects.select_related('company'), pk=id, issuer=issuer
    )

    company_instance = customer.company
    address_instance = company_instance.address if company_instance and getattr(company_instance, 'address', None) else None

    active_tab = request.GET.get('tab') or request.POST.get('tab') or 'activity'

    if request.method == 'POST':
        company_form = CompanyForm(request.POST, instance=company_instance)
        address_form = AddressForm(request.POST, instance=address_instance)
        status_form = CustomerStatusForm(request.POST, initial={'is_active': customer.is_active})
        billing_form = CustomerBillingForm(request.POST, instance=customer)

        if all([company_form.is_valid(), address_form.is_valid(), status_form.is_valid(), billing_form.is_valid()]):
            is_active = status_form.cleaned_data['is_active']
            customer = billing_form.save(commit=False)

            address = address_form.save(commit=False)
            if not address.alias:
                address.alias = 'Default'
            address.save()

            company = company_form.save(commit=False)
            company.address = address
            company.save()

            customer.company = company
            customer.issuer = issuer
            if customer.is_active != is_active:
                customer.is_active = is_active
            updates = ['company', 'issuer', 'currency', 'payment_term', 'payment_notes', 'is_active']

            contact_email = getattr(company, 'contact_email', '').strip() if company else ''
            contact_name = getattr(company, 'contact_name', '').strip() if company else (company.name if company else '')

            if contact_email and customer.billing_email != contact_email:
                customer.billing_email = contact_email
                updates.append('billing_email')
            if contact_name and customer.billing_contact_name != contact_name:
                customer.billing_contact_name = contact_name
                updates.append('billing_contact_name')

            customer.save(update_fields=list(dict.fromkeys(updates)))

            messages.success(request, 'Customer saved successfully')
            return redirect(f"{reverse('customers:detail', args=[customer.id])}?tab=edit")
        else:
            active_tab = 'edit'
    else:
        company_form = CompanyForm(instance=company_instance)
        address_form = AddressForm(instance=address_instance)
        status_form = CustomerStatusForm(initial={'is_active': customer.is_active})
        billing_form = CustomerBillingForm(instance=customer)

    date_filter = get_global_date_filter(request)
    range_start = date_filter['start']
    range_end = date_filter['end']

    customer_invoices = Invoice.objects.filter(customer=customer)
    if range_start:
        customer_invoices = customer_invoices.filter(issued_date__gte=range_start)
    if range_end:
        customer_invoices = customer_invoices.filter(issued_date__lte=range_end)
    invoice_metrics_qs = customer_invoices.exclude(status=Invoice.STATUS_DRAFT)
    customer_invoices = _set_invoice_display_states(
        list(
            customer_invoices.select_related('project')
            .order_by('-issued_date', '-id')
        )
    )

    customer_payments = customer.payments.all()
    if range_start:
        customer_payments = customer_payments.filter(received_at__gte=range_start)
    if range_end:
        customer_payments = customer_payments.filter(received_at__lte=range_end)
    customer_payments = customer_payments.prefetch_related('applications__invoice').order_by('-received_at', '-id')

    invoice_totals = invoice_metrics_qs.aggregate(
        invoiced_total=Coalesce(Sum('total_due'), Decimal('0')),
        paid_total=Coalesce(Sum('amount_paid'), Decimal('0')),
        pending_total=Coalesce(Sum('amount_due'), Decimal('0')),
        overdue_total=Coalesce(
            Sum(
                'amount_due',
                filter=overdue_q(),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            Decimal('0'),
        ),
    )

    account_balance = invoice_totals['pending_total']

    account_rows = []
    for invoice in customer_invoices:
        invoice_total = invoice.total_due or ZERO_DECIMAL
        outstanding_balance = invoice.amount_due or ZERO_DECIMAL
        if outstanding_balance <= ZERO_DECIMAL:
            outstanding_balance = None
        outstanding_is_overdue = bool(
            outstanding_balance and is_invoice_overdue(due_date=invoice.due_date, amount_due=outstanding_balance)
        )
        account_rows.append(
            {
                'type': 'invoice',
                'type_order': 0,
                'title': f"Invoice {invoice.sequence_number}",
                'url': reverse('invoices:edit', args=[invoice.id]),
                'date': invoice.issued_date,
                'status_code': invoice.status,
                'amount': invoice.total_due or ZERO_DECIMAL,
                'outstanding_amount': outstanding_balance,
                'outstanding_is_overdue': outstanding_is_overdue,
                'details': [],
                'sort_key': datetime.combine(invoice.issued_date or date.min, datetime.min.time()),
            }
        )

    for payment in customer_payments:
        applications = list(payment.applications.all())
        detail_links = [
            {
                'label': application.invoice.sequence_number,
                'url': reverse('invoices:edit', args=[application.invoice.id]),
            }
            for application in applications
            if application.invoice
        ]
        detail_labels = [f"#{detail['label']}" for detail in detail_links]
        payment_title = 'Payment'
        if detail_labels:
            payment_title = f"Payment for {', '.join(detail_labels)}"

        account_rows.append(
            {
                'type': 'payment',
                'type_order': 1,
                'title': payment_title,
                'url': None,
                'date': payment.received_at,
                'amount': payment.amount,
                'status_code': payment.status,
                'details': detail_links,
                'sort_key': datetime.combine(payment.received_at, datetime.min.time()),
            }
        )

    account_rows.sort(key=lambda row: (row['sort_key'], row['type_order']), reverse=True)

    invoice_date_filter = Q()
    if range_start:
        invoice_date_filter &= Q(invoices__issued_date__gte=range_start)
    if range_end:
        invoice_date_filter &= Q(invoices__issued_date__lte=range_end)

    project_invoice_filter = invoice_date_filter & ~Q(invoices__status=Invoice.STATUS_DRAFT)

    projects = customer.projects.select_related('customer__company').annotate(
        invoiced_total=Coalesce(
            Sum(
                'invoices__total_due',
                filter=project_invoice_filter,
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            Decimal('0'),
        ),
        paid_total=Coalesce(
            Sum(
                'invoices__amount_paid',
                filter=project_invoice_filter,
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            Decimal('0'),
        ),
        pending_total=Coalesce(
            Sum(
                'invoices__amount_due',
                filter=project_invoice_filter,
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            Decimal('0'),
        ),
        overdue_total=Coalesce(
            Sum(
                'invoices__amount_due',
                filter=project_invoice_filter & overdue_q(prefix='invoices__'),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            Decimal('0'),
        ),
        last_invoice_date=Max('invoices__issued_date', filter=project_invoice_filter),
    ).order_by('title')

    # Build payment drawer context for customer-level payments
    customer_projects = list(
        customer.projects.filter(status=Project.STATUS_ACTIVE).order_by('title')
    )
    selected_payment_project = customer_projects[0] if customer_projects else None
    project_outstanding = []
    if selected_payment_project:
        project_outstanding = _set_invoice_display_states(
            list(
                Invoice.objects.filter(
                    issuer=issuer,
                    customer=customer,
                    project=selected_payment_project,
                    status__in=[Invoice.STATUS_INVOICED, Invoice.STATUS_OVERDUE],
                    amount_due__gt=ZERO_DECIMAL,
                ).order_by('-issued_date', '-number')
            )
        )

    context = {
        'customer': customer,
        'company_form': company_form,
        'address_form': address_form,
        'status_form': status_form,
        'billing_form': billing_form,
        'active_tab': active_tab,
        'projects': projects,
        'account_rows': account_rows,
        'invoice_totals': invoice_totals,
        'account_balance': account_balance,
        'date_filter': date_filter,
        # Lists for new tabs
        'invoice_list': customer_invoices,
        'payment_list': customer_payments,
        # Payment drawer
        'payment_context': 'customer',
        'customer_projects': customer_projects,
        'selected_project_id': selected_payment_project.id if selected_payment_project else '',
        'project_outstanding_invoices': project_outstanding,
    }

    template_name = 'invoices/customer_profile.html'
    if active_tab == 'edit' and request.headers.get('Hx-Request'):
        template_name = 'invoices/partials/customer_edit_form.html'
    return render(request, template_name, context)


@require_POST
def customer_add_payment(request, id):
    issuer = get_active_issuer(request)
    customer = get_object_or_404(Customer, pk=id, issuer=issuer)

    amount_raw = (request.POST.get('amount') or '').strip()
    received_at_raw = (request.POST.get('received_at') or '').strip()
    memo = (request.POST.get('memo') or '').strip()
    apply_to_ids = [val.replace(',', '').replace(' ', '') for val in request.POST.getlist('apply_to')]
    if not apply_to_ids:
        return JsonResponse({'ok': False, 'error': 'Select at least one invoice'}, status=400)
    project_id = (request.POST.get('project_id') or '').replace(',', '').replace(' ', '')
    payment_id_raw = (request.POST.get('payment_id') or '').replace(',', '').replace(' ', '')

    try:
        amount = _parse_decimal_input(amount_raw)
    except (InvalidOperation, ValueError):
        return JsonResponse({'ok': False, 'error': 'Invalid amount'}, status=400)
    if amount <= ZERO_DECIMAL:
        return JsonResponse({'ok': False, 'error': 'Amount must be positive'}, status=400)

    from datetime import datetime as dt
    received_at = date.today()
    if received_at_raw:
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
            try:
                received_at = dt.strptime(received_at_raw, fmt).date()
                break
            except ValueError:
                continue

    base_qs = Invoice.objects.filter(issuer=issuer, customer=customer)
    if project_id:
        base_qs = base_qs.filter(project_id=project_id)
    if payment_id_raw:
        # When editing an existing payment, allow selecting invoices even if no longer outstanding
        target_qs = base_qs.filter(pk__in=apply_to_ids)
    else:
        target_qs = base_qs.filter(
            status__in=[Invoice.STATUS_INVOICED, Invoice.STATUS_OVERDUE],
            amount_due__gt=ZERO_DECIMAL,
            pk__in=apply_to_ids,
        )

    targets = list(target_qs.order_by('issued_date', 'number', 'id'))
    if not targets:
        return JsonResponse({'ok': False, 'error': 'No outstanding invoices selected'}, status=400)

    project = None
    if project_id:
        project = Project.objects.filter(pk=project_id, customer=customer).first()

    currency = getattr(customer, 'currency', None)
    exchange_rate = currency.exchange_rate_to_base if currency else Decimal('1')

    with transaction.atomic():
        if payment_id_raw:
            payment = get_object_or_404(Payment, pk=payment_id_raw, issuer=issuer, customer=customer)
            # Replace applications
            payment.applications.all().delete()
            payment.amount = amount
            payment.received_at = received_at or date.today()
            payment.project = project
            payment.memo = memo
            if currency:
                payment.currency = currency
                payment.exchange_rate = exchange_rate or payment.exchange_rate
            payment.status = Payment.STATUS_APPLIED
            payment.save()
        else:
            payment = Payment.objects.create(
                issuer=issuer,
                customer=customer,
                project=project,
                currency=currency,
                amount=amount,
                exchange_rate=exchange_rate,
                base_currency_amount=None,
                received_at=received_at or date.today(),
                status=Payment.STATUS_APPLIED,
                memo=memo,
            )
        remaining_to_apply = amount
        for inv in targets:
            if remaining_to_apply <= ZERO_DECIMAL:
                break
            inv_remaining = inv.amount_due or ZERO_DECIMAL
            if inv_remaining <= ZERO_DECIMAL:
                continue
            portion = inv_remaining if inv_remaining <= remaining_to_apply else remaining_to_apply
            PaymentApplication.objects.create(
                payment=payment,
                invoice=inv,
                amount_applied=portion,
            )
            remaining_to_apply -= portion

    try:
        for inv in targets:
            save_invoice_pdf(request, inv.id)
    except RuntimeError:
        pass

    return JsonResponse({'ok': True})


def payment_prefill(request, id):
    issuer = get_active_issuer(request)
    payment = get_object_or_404(Payment.objects.select_related('customer', 'project'), pk=id, issuer=issuer)
    apps = list(payment.applications.select_related('invoice__project').all())
    primary_project_id = payment.project_id
    if not primary_project_id:
        first_invoice = next((app.invoice for app in apps if app.invoice and app.invoice.project_id), None)
        if first_invoice:
            primary_project_id = first_invoice.project_id

    data = {
        'id': payment.id,
        'customer_id': payment.customer_id,
        'project_id': primary_project_id,
        'amount': f"{(payment.amount or ZERO_DECIMAL):.2f}",
        'received_at': payment.received_at.isoformat() if payment.received_at else '',
        'memo': payment.memo or '',
        'invoice_ids': [str(app.invoice_id) for app in apps if app.invoice_id],
        'invoices': [{
            'id': app.invoice.id,
            'sequence_number': _invoice_display_number(app.invoice),
            'issued_date': app.invoice.issued_date.isoformat() if app.invoice.issued_date else '',
            'total_due': f"{(app.invoice.total_due or ZERO_DECIMAL):.2f}",
            'amount_due': f"{(app.invoice.amount_due or ZERO_DECIMAL):.2f}",
            'is_overdue': is_invoice_overdue(due_date=app.invoice.due_date, amount_due=app.invoice.amount_due),
        } for app in apps if app.invoice_id],
    }
    return JsonResponse({'ok': True, 'payment': data})


@require_POST
def payment_delete(request, id):
    issuer = get_active_issuer(request)
    payment = get_object_or_404(Payment, pk=id, issuer=issuer)
    # Collect affected invoice ids for optional PDF refresh
    affected = list(payment.applications.values_list('invoice_id', flat=True))
    payment.delete()
    try:
        for inv_id in affected:
            save_invoice_pdf(request, inv_id)
    except RuntimeError:
        pass
    return JsonResponse({'ok': True})


@require_POST
def payments_import_wise(request):
    issuer = get_active_issuer(request)
    if not issuer:
        return JsonResponse({'ok': False, 'error': 'Select a company before importing payments.'}, status=400)

    uploads = request.FILES.getlist('statements')
    if not uploads:
        return JsonResponse({'ok': False, 'error': 'Upload at least one ZIP or CSV statement.'}, status=400)

    importer = WiseStatementImporter(issuer=issuer)
    try:
        result = importer.import_files(uploads)
    except WiseImportError as exc:
        logger.warning('Wise import failed for issuer %s: %s', issuer.pk, exc)
        return JsonResponse({'ok': False, 'error': str(exc)}, status=400)

    payload = {'ok': True}
    payload.update(result.as_dict())
    return JsonResponse(payload)


def project_outstanding_invoices(request, id):
    issuer = get_active_issuer(request)
    project = get_object_or_404(Project, pk=id, customer__issuer=issuer)
    invoices = (
        Invoice.objects.filter(
            issuer=issuer,
            project=project,
            status__in=[Invoice.STATUS_INVOICED, Invoice.STATUS_OVERDUE],
            amount_due__gt=ZERO_DECIMAL,
        )
        .select_related('project')
        .order_by('-issued_date', '-number')
    )
    items = []
    for inv in invoices:
        items.append({
            'id': inv.id,
            'sequence_number': _invoice_display_number(inv),
            'issued_date': inv.issued_date.isoformat() if inv.issued_date else '',
            'total_due': f"{(inv.total_due or ZERO_DECIMAL):.2f}",
            'amount_due': f"{(inv.amount_due or ZERO_DECIMAL):.2f}",
            'is_overdue': is_invoice_overdue(due_date=inv.due_date, amount_due=inv.amount_due),
        })
    return JsonResponse({'ok': True, 'items': items})


def view_customers(request):
    issuer = get_active_issuer(request)
    date_filter = get_global_date_filter(request)
    range_start = date_filter['start']
    range_end = date_filter['end']
    status_filter = _get_last_query_value(request, 'status', 'active') or 'active'

    customers = Customer.objects.none()
    status_options = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('all', 'All'),
    ]

    order_map = {
        'name': 'company__name',
        'name_desc': '-company__name',
        'projects_desc': '-projects_count',
        'projects_asc': 'projects_count',
        'paid_desc': '-paid_total',
        'paid_asc': 'paid_total',
        'pending_desc': '-pending_total',
        'pending_asc': 'pending_total',
        'last_activity_desc': '-last_activity',
        'last_activity_asc': 'last_activity',
    }

    default_order = 'name'
    requested_order = request.GET.get('order')
    stored_order = request.session.get(CUSTOMER_ORDER_SESSION_KEY)

    if requested_order:
        order_param = requested_order if requested_order in order_map else default_order
        if order_param == default_order:
            request.session.pop(CUSTOMER_ORDER_SESSION_KEY, None)
        else:
            request.session[CUSTOMER_ORDER_SESSION_KEY] = order_param
    else:
        order_param = stored_order if stored_order in order_map else default_order
        if stored_order and stored_order not in order_map:
            request.session.pop(CUSTOMER_ORDER_SESSION_KEY, None)

    if issuer:
        customers = Customer.objects.filter(issuer=issuer).select_related('company')
        if status_filter == 'active':
            customers = customers.filter(is_active=True)
        elif status_filter == 'inactive':
            customers = customers.filter(is_active=False)
        else:
            status_filter = 'all'

        project_count_subquery = Project.objects.filter(customer=OuterRef('pk')).values('customer').annotate(
            cnt=Count('pk')
        ).values('cnt')[:1]

        invoice_stats = Invoice.objects.filter(customer=OuterRef('pk')).exclude(status=Invoice.STATUS_DRAFT)
        if range_start:
            invoice_stats = invoice_stats.filter(issued_date__gte=range_start)
        if range_end:
            invoice_stats = invoice_stats.filter(issued_date__lte=range_end)

        invoice_stats = (
            invoice_stats
            .values('customer')
            .annotate(
                paid_total=Coalesce(
                    Sum(
                        'total_due',
                        filter=Q(status=Invoice.STATUS_PAID),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    ),
                    Decimal('0'),
                ),
                pending_total=Coalesce(
                    Sum(
                        'amount_due',
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    ),
                    Decimal('0'),
                ),
                overdue_total=Coalesce(
                    Sum(
                        'amount_due',
                        filter=overdue_q(),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    ),
                    Decimal('0'),
                ),
                last_activity=Max('issued_date'),
            )
            .order_by()
        )

        customers = customers.annotate(
            projects_count=Coalesce(Subquery(project_count_subquery), Value(0, output_field=IntegerField())),
            paid_total=Coalesce(Subquery(invoice_stats.values('paid_total')[:1]), Decimal('0')),
            pending_total=Coalesce(Subquery(invoice_stats.values('pending_total')[:1]), Decimal('0')),
            overdue_total=Coalesce(Subquery(invoice_stats.values('overdue_total')[:1]), Decimal('0')),
            last_activity=Subquery(invoice_stats.values('last_activity')[:1]),
        )

        order_by = order_map.get(order_param, 'company__name')
        customers = customers.order_by(order_by, 'company__name')

    query_without_order = _querystring_without(request.GET, 'order')
    order_columns = []
    for column in CUSTOMER_ORDER_COLUMN_CONFIG:
        is_active = order_param in {column['asc'], column['desc']}
        if is_active:
            direction = 'asc' if order_param == column['asc'] else 'desc'
            next_order = column['desc'] if direction == 'asc' else column['asc']
        else:
            direction = 'none'
            default_key = column.get('default', 'asc')
            next_order = column[default_key]
        href = f"?order={next_order}"
        if query_without_order:
            href = f"{href}&{query_without_order}"
        order_columns.append(
            {
                'label': column['label'],
                'align': column.get('align', ''),
                'is_active': is_active,
                'direction': direction,
                'next_order': next_order,
                'href': href,
            }
        )

    customer_rows = []
    for customer in customers:
        if customer.company:
            title_cell = format_html(
                '<a href="{}" class="link-primary table-title">{}</a>',
                reverse('customers:detail', args=[customer.id]),
                customer.company.name,
            )
        else:
            title_cell = '—'

        pending_classes = ' pending-amount--overdue' if customer.overdue_total else ''
        pending_display = _format_currency(customer.pending_total)
        pending_cell = format_html(
            '<span class="pending-amount{}">{}</span>',
            pending_classes,
            pending_display,
        )

        last_activity = (
            date_format(customer.last_activity, 'j M Y')
            if customer.last_activity
            else '—'
        )

        customer_rows.append(
            {
                'cells': [
                    {'content': title_cell},
                    {'content': format_html('{}', customer.projects_count), 'align': 'text-end'},
                    {'content': format_html('{}', _format_currency(customer.paid_total)), 'align': 'text-end'},
                    {'content': pending_cell, 'align': 'text-end'},
                    {'content': last_activity},
                ]
            }
        )

    context = {
        'customer_list': customers,
        'status_filter': status_filter,
        'status_options': status_options,
        'order_filter': order_param,
        'order_columns': order_columns,
        'query_without_order': query_without_order,
        'customer_rows': customer_rows,
    }
    return render(request, 'invoices/view_customers.html', context)


def view_projects(request):
    sanitize_decimal_columns()
    issuer = get_active_issuer(request)
    date_filter = get_global_date_filter(request)
    range_start = date_filter['start']
    range_end = date_filter['end']
    if not issuer:
        messages.error(request, 'Add a company before managing projects.')
        return redirect('company:settings')
    project_list = Project.objects.none()
    if issuer:
        project_status = request.GET.get('project_status', Project.STATUS_ACTIVE)
        order_query = request.GET.get('order')
        if order_query:
            request.session['projects_order'] = order_query
            order_param = order_query
        else:
            order_param = request.session.get('projects_order', 'title')

        project_list = Project.objects.filter(customer__issuer=issuer).select_related('customer__company')
        if project_status != 'all':
            project_list = project_list.filter(status=project_status)
        date_q = Q()
        if range_start:
            date_q &= Q(invoices__issued_date__gte=range_start)
        if range_end:
            date_q &= Q(invoices__issued_date__lte=range_end)

        invoice_filter = date_q & ~Q(invoices__status=Invoice.STATUS_DRAFT)

        project_list = project_list.annotate(
            pending_balance=Coalesce(
                Sum(
                    'invoices__amount_due',
                    filter=invoice_filter,
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
                Decimal('0')
            ),
            paid_total=Coalesce(
                Sum(
                    'invoices__amount_paid',
                    filter=invoice_filter,
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
                Decimal('0')
            ),
        overdue_total=Coalesce(
            Sum(
                'invoices__amount_due',
                filter=invoice_filter & overdue_q(prefix='invoices__'),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            Decimal('0')
        ),
        )
        order_map = {
            'title': 'title',
            'title_desc': '-title',
            'client': 'customer__company__name',
            'client_desc': '-customer__company__name',
            'paid': 'paid_total',
            'paid_desc': '-paid_total',
            'pending_desc': '-pending_balance',
            'pending_asc': 'pending_balance',
        }
        if order_param not in order_map:
            order_param = 'title'
        request.session['projects_order'] = order_param

        project_list = project_list.order_by(order_map[order_param], 'title')

    query_without_order = _querystring_without(request.GET, 'order')

    order_columns_config = [
        {
            'label': 'Title',
            'asc': 'title',
            'desc': 'title_desc',
            'default': 'asc',
            'align': '',
        },
        {
            'label': 'Client',
            'asc': 'client',
            'desc': 'client_desc',
            'default': 'asc',
            'align': '',
        },
        {
            'label': 'Paid',
            'asc': 'paid',
            'desc': 'paid_desc',
            'default': 'desc',
            'align': 'text-end',
        },
        {
            'label': 'Pending',
            'asc': 'pending_asc',
            'desc': 'pending_desc',
            'default': 'desc',
            'align': 'text-end',
        },
    ]

    order_columns_context = []
    for column in order_columns_config:
        is_active = order_param in {column['asc'], column['desc']}
        if is_active:
            direction = 'asc' if order_param == column['asc'] else 'desc'
            next_order = column['desc'] if direction == 'asc' else column['asc']
        else:
            direction = 'none'
            default_key = column.get('default', 'asc')
            next_order = column[default_key]
        href = f"?order={next_order}"
        if query_without_order:
            href = f"{href}&{query_without_order}"
        order_columns_context.append(
            {
                'label': column['label'],
                'align': column.get('align', ''),
                'is_active': is_active,
                'direction': direction,
                'next_order': next_order,
                'href': href,
            }
        )

    project_rows = []
    for project in project_list:
        customer = project.customer
        if customer and customer.company:
            client_cell = format_html(
                '<a href="{}" class="link">{}</a>',
                reverse('customers:detail', args=[customer.id]),
                customer.company.name,
            )
        else:
            client_cell = '—'
        project_rows.append(
            {
                'cells': [
                    {
                        'content': format_html(
                            '<a href="{}" class="link-primary table-title">{}</a>',
                            reverse('projects:detail', args=[project.id]),
                            project.title,
                        )
                    },
                    {'content': client_cell},
                    {'content': format_html('{}', _format_currency(project.paid_total)), 'align': 'text-end'},
                    {
                        'content': format_html(
                            '<span class="pending-amount{}">{}</span>',
                            ' pending-amount--overdue' if project.overdue_total else '',
                            _format_currency(project.pending_balance),
                        ),
                        'align': 'text-end',
                    },
                ]
            }
        )

    context = {
        'project_list': project_list,
        'project_status_filter': project_status if issuer else Project.STATUS_ACTIVE,
        'order_filter': order_param,
        'order_columns': order_columns_context,
        'query_without_order': query_without_order,
        'project_rows': project_rows,
    }
    return render(request, 'invoices/view_projects.html', context)


def delete_customer(request, id):
    try:
        issuer = get_active_issuer(request)
        customer = get_object_or_404(Customer, pk=id, issuer=issuer)
        if customer.company:
            company = customer.company
            if company.address:
                company.address.delete()
            company.delete()
        customer.delete()
        messages.success(request, 'Customer deleted successfully')
    except Customer.DoesNotExist:
        messages.error(request, 'Customer not found')
    except Exception as e:
        messages.error(request, f'Something went wrong: {str(e)}')

    return redirect('customers:list')


def save_all_invoices_pdf(request):
    sanitize_decimal_columns()
    issuer = get_active_issuer(request)
    if not issuer:
        messages.error(request, 'Select a company before saving invoices.')
        return redirect('invoices:list')

    invoices = Invoice.objects.filter(issuer=issuer)
    for invoice in invoices:
        save_invoice_pdf(request, invoice.id)

    return redirect('invoices:list')


@require_POST
def switch_company(request):
    next_url = _safe_company_switch_redirect(request.POST.get('next'))
    company_id = request.POST.get('company_id')

    try:
        if not set_active_company(request, int(company_id)):
            messages.error(request, 'Company not found.')
    except (TypeError, ValueError):
        messages.error(request, 'Invalid company selection.')

    return redirect(next_url)


def cross_company_switch_redirect(request):
    next_url = _safe_cross_company_row_redirect(request.GET.get('next'))
    company_id = request.GET.get('company_id')

    try:
        if not set_active_company(request, int(company_id)):
            messages.error(request, 'Company not found.')
            return redirect('cross_company_dashboard')
    except (TypeError, ValueError):
        messages.error(request, 'Invalid company selection.')
        return redirect('cross_company_dashboard')

    return redirect(next_url)


def add_project(request):
    issuer = get_active_issuer(request)
    if not issuer:
        messages.error(request, 'Add a company before creating projects.')
        return redirect('company:settings')

    if not Customer.objects.filter(issuer=issuer).exists():
        messages.error(request, 'Create a customer before adding a project.')
        return redirect('customers:add')

    payment_defaults = _customer_payment_defaults(issuer)

    initial = {}
    customer_param = request.GET.get('customer')
    if customer_param:
        try:
            customer_initial = Customer.objects.get(pk=int(customer_param), issuer=issuer)
            initial['customer'] = customer_initial
        except (Customer.DoesNotExist, ValueError, TypeError):
            pass

    if request.method == 'POST':
        form = ProjectForm(request.POST, issuer=issuer)
        if form.is_valid():
            project = form.save()
            messages.success(request, 'Project created successfully')
            return redirect('projects:list')
    else:
        form = ProjectForm(issuer=issuer, initial=initial)

    return render(request, 'invoices/form_project.html', {
        'form': form,
        'project': None,
        'customer_payment_defaults': payment_defaults,
    })


def edit_project(request, id):
    issuer = get_active_issuer(request)
    if not issuer:
        messages.error(request, 'Add a company before editing projects.')
        return redirect('company:settings')
    project = get_object_or_404(Project, pk=id, customer__issuer=issuer)

    payment_defaults = _customer_payment_defaults(issuer)

    if request.method == 'POST':
        form = ProjectForm(request.POST, instance=project, issuer=issuer)
        if form.is_valid():
            form.save()
            messages.success(request, 'Project updated successfully')
            return redirect('projects:list')
    else:
        form = ProjectForm(instance=project, issuer=issuer)

    return render(request, 'invoices/form_project.html', {
        'form': form,
        'project': project,
        'customer_payment_defaults': payment_defaults,
    })


def project_detail(request, id):
    sanitize_decimal_columns()
    issuer = get_active_issuer(request)
    if not issuer:
        messages.error(request, 'Add a company before viewing projects.')
        return redirect('company:settings')
    active_tab = request.GET.get('tab') or request.POST.get('tab') or 'activity'
    date_filter = get_global_date_filter(request)
    range_start = date_filter['start']
    range_end = date_filter['end']

    project = get_object_or_404(
        Project.objects.select_related('customer__company'), pk=id, customer__issuer=issuer)

    if request.method == 'POST':
        project_form = ProjectForm(request.POST, instance=project, issuer=issuer)
        if project_form.is_valid():
            project_form.save()
            messages.success(request, 'Project updated successfully')
            return redirect(f"{reverse('projects:detail', args=[project.id])}?tab=edit")
        active_tab = 'edit'
    else:
        project_form = ProjectForm(instance=project, issuer=issuer)

    project_invoices = project.invoices.select_related('customer__company').prefetch_related('payment_applications__payment')
    if range_start:
        project_invoices = project_invoices.filter(issued_date__gte=range_start)
    if range_end:
        project_invoices = project_invoices.filter(issued_date__lte=range_end)

    metrics_qs = project_invoices.exclude(status=Invoice.STATUS_DRAFT)
    metrics = metrics_qs.aggregate(
        invoiced_total=Coalesce(Sum('total_due'), Decimal('0')),
        paid_total=Coalesce(Sum('amount_paid'), Decimal('0')),
        pending_total=Coalesce(Sum('amount_due'), Decimal('0')),
        overdue_total=Coalesce(
            Sum(
                'amount_due',
                filter=overdue_q(),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            Decimal('0'),
        ),
        last_invoice_date=Max('issued_date'),
    )

    invoices = _set_invoice_display_states(list(project_invoices.order_by('-issued_date', '-number')))

    project_payments_qs = (
        Payment.objects.filter(issuer=issuer)
        .filter(Q(project=project) | Q(applications__invoice__project=project))
        .distinct()
    )
    if range_start:
        project_payments_qs = project_payments_qs.filter(received_at__gte=range_start)
    if range_end:
        project_payments_qs = project_payments_qs.filter(received_at__lte=range_end)
    project_payments = list(
        project_payments_qs.prefetch_related('applications__invoice').order_by('-received_at', '-id')
    )

    account_rows = []
    for invoice in invoices:
        invoice_total = invoice.total_due or ZERO_DECIMAL
        outstanding = invoice.amount_due or ZERO_DECIMAL
        outstanding_display = outstanding if outstanding > ZERO_DECIMAL else None
        outstanding_is_overdue = bool(
            outstanding_display and is_invoice_overdue(due_date=invoice.due_date, amount_due=outstanding_display)
        )
        issued_dt = invoice.issued_date or date.min
        account_rows.append(
            {
                'type': 'invoice',
                'type_order': 0,
                'title': f"Invoice {_invoice_display_number(invoice)}",
                'url': reverse('invoices:edit', args=[invoice.id]),
                'date': invoice.issued_date,
                'amount': invoice_total,
                'outstanding_amount': outstanding_display,
                'outstanding_is_overdue': outstanding_is_overdue,
                'details': [],
                'sort_key': datetime.combine(issued_dt, datetime.min.time()),
            }
        )

    for payment in project_payments:
        applications = list(payment.applications.all())
        detail_links = [
            {
                'label': _invoice_display_number(app.invoice),
                'url': reverse('invoices:edit', args=[app.invoice.id]),
            }
            for app in applications if app.invoice
        ]
        account_rows.append(
            {
                'type': 'payment',
                'type_order': 1,
                'title': 'Payment',
                'url': None,
                'date': payment.received_at,
                'amount': payment.amount,
                'details': detail_links,
                'outstanding_amount': None,
                'sort_key': datetime.combine(payment.received_at, datetime.min.time()),
            }
        )

    account_rows.sort(key=lambda row: (row['sort_key'], row['type_order']), reverse=True)

    customer_projects = []
    selected_payment_project = None
    project_outstanding = []
    if project.customer:
        customer_projects = list(
            project.customer.projects.filter(status=Project.STATUS_ACTIVE).order_by('title')
        )
        if not any(prj.id == project.id for prj in customer_projects):
            customer_projects.insert(0, project)
        selected_payment_project = project
        project_outstanding = _set_invoice_display_states(
            list(
                Invoice.objects.filter(
                    issuer=issuer,
                    customer=project.customer,
                    project=project,
                    status__in=[Invoice.STATUS_INVOICED, Invoice.STATUS_OVERDUE],
                    amount_due__gt=ZERO_DECIMAL,
                )
                .select_related('project')
                .order_by('-issued_date', '-number')
            )
        )

    context = {
        'project': project,
        'invoices': invoices,
        'invoiced_total': metrics['invoiced_total'],
        'paid_total': metrics['paid_total'],
        'pending_balance': metrics['pending_total'],
        'overdue_total': metrics['overdue_total'],
        'last_invoice_date': metrics['last_invoice_date'],
        'account_rows': account_rows,
        'payment_list': project_payments,
        'payment_context': 'project',
        'customer_projects': customer_projects,
        'selected_project_id': selected_payment_project.id if selected_payment_project else '',
        'project_outstanding_invoices': project_outstanding,
        'active_tab': active_tab,
        'project_form': project_form,
        'date_filter': date_filter,
    }

    return render(request, 'invoices/project_detail.html', context)


def project_recent_items(request, id):
    issuer = get_active_issuer(request)
    project = get_object_or_404(
        Project.objects.filter(customer__issuer=issuer), pk=id
    )
    exclude_invoice = None
    exclude_invoice_id = request.GET.get('exclude_invoice')
    if exclude_invoice_id:
        exclude_invoice = Invoice.objects.filter(
            pk=exclude_invoice_id,
            issuer=issuer,
            project=project,
        ).first()
    items = _recent_items_payload(project, exclude_invoice=exclude_invoice)

    return JsonResponse({'items': items})


@login_required
def backup_settings(request):
    if not request.user.is_superuser:
        raise PermissionDenied

    configuration = BackupConfiguration.load()
    recent_runs = _prepare_recent_backup_runs(list(BackupRun.objects.all()[:10]))
    backup_tab = 'recent-backups'
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        backup_form = BackupConfigurationForm(request.POST, instance=configuration)
        action = request.POST.get('action')
        backup_tab = 'settings'

        if action == 'test_s3_connection':
            if backup_form.is_valid_for_connection_test():
                tested_configuration = _build_transient_backup_configuration(
                    configuration,
                    backup_form.cleaned_data,
                )
                try:
                    test_backup_destination(tested_configuration)
                except BackupDestinationCheckError as error:
                    context = _backup_settings_context(
                        request,
                        backup_form=backup_form,
                        backup_configuration=tested_configuration,
                        recent_runs=recent_runs,
                        backup_tab=backup_tab,
                        test_feedback_message=str(error),
                        test_feedback_level='danger',
                    )
                    if is_ajax:
                        return _backup_settings_ajax_response(
                            request,
                            context,
                            badge_configuration=BackupConfiguration.load(),
                        )
                    messages.error(request, str(error))
                    configuration = tested_configuration
                else:
                    context = _backup_settings_context(
                        request,
                        backup_form=backup_form,
                        backup_configuration=tested_configuration,
                        recent_runs=recent_runs,
                        backup_tab=backup_tab,
                        test_feedback_message='S3 connection test succeeded.',
                        test_feedback_level='success',
                    )
                    if is_ajax:
                        return _backup_settings_ajax_response(
                            request,
                            context,
                            badge_configuration=BackupConfiguration.load(),
                        )
                    messages.success(request, 'S3 connection test succeeded.')
                    configuration = tested_configuration
            else:
                context = _backup_settings_context(
                    request,
                    backup_form=backup_form,
                    backup_configuration=configuration,
                    recent_runs=recent_runs,
                    backup_tab=backup_tab,
                )
                if is_ajax:
                    return _backup_settings_ajax_response(
                        request,
                        context,
                        status=400,
                    )
        elif backup_form.is_valid():
            configuration = backup_form.save()
            backup_form = BackupConfigurationForm(instance=configuration)
            context = _backup_settings_context(
                request,
                backup_form=backup_form,
                backup_configuration=configuration,
                recent_runs=recent_runs,
                backup_tab=backup_tab,
                save_feedback_message='Backup settings saved successfully.',
                save_feedback_level='success',
            )
            if is_ajax:
                return _backup_settings_ajax_response(request, context)
            messages.success(request, 'Backup settings saved successfully.')
            return redirect('backup_settings')
        elif is_ajax:
            context = _backup_settings_context(
                request,
                backup_form=backup_form,
                backup_configuration=configuration,
                recent_runs=recent_runs,
                backup_tab=backup_tab,
            )
            return _backup_settings_ajax_response(request, context, status=400)
    else:
        backup_form = BackupConfigurationForm(instance=configuration)

    context = _backup_settings_context(
        request,
        backup_form=backup_form,
        backup_configuration=configuration,
        recent_runs=recent_runs,
        backup_tab=backup_tab,
    )

    return render(request, 'invoices/backup_settings.html', context)


@login_required
def backup_run_detail(request, id):
    if not request.user.is_superuser:
        raise PermissionDenied

    backup_run = get_object_or_404(BackupRun, pk=id)

    return render(
        request,
        'invoices/backup_run_detail.html',
        {'backup_run': backup_run},
    )


@login_required
def backup_run_download(request, id):
    if not request.user.is_superuser:
        raise PermissionDenied

    backup_run = get_object_or_404(BackupRun, pk=id)
    if not backup_run.storage_object_key:
        raise PermissionDenied

    return redirect(generate_backup_download_url(backup_run))


@require_POST
def run_backup_now(request):
    if not request.user.is_superuser:
        raise PermissionDenied

    configuration = BackupConfiguration.load()

    try:
        execute_backup(configuration, trigger_source=BackupRun.TRIGGER_SOURCE_MANUAL)
    except BlockingIOError:
        messages.warning(request, 'A backup run is already in progress.')
    except Exception:
        messages.error(request, 'Backup run failed. Check recent runs for details.')
    else:
        messages.success(request, 'Backup run completed successfully.')

    return redirect('backup_settings')


def edit_company(request):
    issuer_queryset = get_available_issuers(request).select_related('company__address')
    active_issuer = get_active_issuer(request)

    create_new = False
    target_issuer = None

    if request.method == 'POST':
        create_new = request.POST.get('create_new') == '1'
        company_id = request.POST.get('company_id')
        if company_id:
            target_issuer = issuer_queryset.filter(company_id=company_id).first()
            if target_issuer is None:
                raise PermissionDenied
    else:
        create_new = request.GET.get('new') == '1'
        company_id = request.GET.get('company')
        if company_id:
            target_issuer = issuer_queryset.filter(company_id=company_id).first()
            if target_issuer is None:
                raise PermissionDenied

    if not target_issuer and not create_new:
        target_issuer = active_issuer

    company_instance = target_issuer.company if target_issuer and target_issuer.company else None
    address_instance = company_instance.address if company_instance and company_instance.address else None
    sif_settings_instance = get_sif_settings(target_issuer) if target_issuer else IssuerSifSettings()

    if request.method == 'POST':
        company_form = IssuerCompanyForm(request.POST, instance=None if create_new else company_instance)
        address_form = AddressForm(request.POST, instance=address_instance if not create_new else None)
        issuer_form = IssuerSettingsForm(request.POST, instance=target_issuer)
        sif_form = IssuerSifSettingsForm(
            request.POST,
            instance=sif_settings_instance,
            issuer_company_tax_id=request.POST.get('issuer_company-customer_information_file_number'),
        )
        bank_account_formset = IssuerBankAccountFormSet(
            request.POST,
            instance=target_issuer or Issuer(),
            prefix='bank_accounts',
        )

        if (
            company_form.is_valid()
            and address_form.is_valid()
            and issuer_form.is_valid()
            and sif_form.is_valid()
            and bank_account_formset.is_valid()
        ):
            with transaction.atomic():
                address = address_form.save()
                company = company_form.save(commit=False)
                company.address = address
                company.save()

                issuer = issuer_form.save(commit=False)
                issuer.company = company
                issuer.save()
                issuer_form.save_m2m()

                sif_settings = sif_form.save(commit=False)
                sif_settings.issuer = issuer
                sif_settings.save()

                bank_account_formset.instance = issuer
                bank_account_formset.save()

                default_account = issuer.bank_accounts.filter(is_active=True, is_default=True).first()
                if default_account:
                    company.bank_account_number = default_account.account_details
                    company.payment_method = default_account.payment_method
                    company.save(update_fields=['bank_account_number', 'payment_method'])

            set_active_company(request, company.id)

            messages.success(request, 'Company information saved successfully')
            return redirect('company:settings')
    else:
        company_form = IssuerCompanyForm(instance=company_instance)
        address_form = AddressForm(instance=address_instance)
        issuer_form = IssuerSettingsForm(instance=target_issuer)
        sif_form = IssuerSifSettingsForm(instance=sif_settings_instance)
        bank_account_formset = IssuerBankAccountFormSet(instance=target_issuer, prefix='bank_accounts')

    sif_readiness = get_sif_readiness(target_issuer) if target_issuer else None

    context = {
        'company_form': company_form,
        'address_form': address_form,
        'issuer_form': issuer_form,
        'sif_form': sif_form,
        'sif_readiness': sif_readiness,
        'bank_account_formset': bank_account_formset,
        'issuer_list': issuer_queryset,
        'target_issuer': target_issuer,
        'create_new': create_new,
    }

    return render(request, 'invoices/company_settings.html', context)
