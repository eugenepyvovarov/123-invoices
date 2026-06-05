from __future__ import annotations

import io
import os
import zipfile
from datetime import date
from decimal import Decimal
from urllib.parse import urlsplit

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.middleware.csrf import get_token
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.http import FileResponse, Http404, HttpResponse, JsonResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.html import conditional_escape, format_html
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from invoices.models import (
    Expense,
    ImportBatch,
    ImportMapping,
    ImportPreviewRow,
    IncomingEmailSource,
    IncomingInvoiceArtifact,
    IncomingInvoiceCandidate,
    IssuerEmailRoutingRule,
)
from invoices.services.incoming_invoice_conversion import (
    convert_candidate_to_expense,
    mark_candidate_confirmed,
    mark_candidate_duplicate,
    mark_candidate_needs_fetch,
    mark_candidate_not_invoice,
    mark_candidate_rejected,
    mark_candidate_reviewed_unpaid,
    review_metadata_from_cleaned,
)
from invoices.services.expense_import_ai import OpenAICompatibleMappingClient, OpenAICompatibleProviderConfig
from invoices.services.expense_importer import ExpenseImportError, ExpenseImportResult, GenericExpenseImporter
from invoices.utils.company_context import get_active_issuer
from invoices.utils.date_filters import get_global_date_filter
from invoices.views import invalidate_dashboard_cache

from .forms import (
    ExpenseForm,
    IncomingCandidateConversionForm,
    IncomingCandidateReviewForm,
    IncomingEmailSourceForm,
    IssuerEmailRoutingRuleForm,
)

ATTACHMENT_FILTER_VALUES = {'all', 'with', 'without'}
IMPORT_MAPPING_FIELDS = ['paid_date', 'amount', 'description', 'transaction_id', 'currency']


def _format_currency(amount: Decimal | None) -> str:
    value = amount or Decimal('0')
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return f"{value:.2f} €"


def _querystring_without(querydict, *keys) -> str:
    from urllib.parse import urlencode

    remaining = []
    for key, values in querydict.lists():
        if key in keys:
            continue
        for value in values:
            remaining.append((key, value))
    return urlencode(remaining)


def _safe_next_url(next_url: str | None) -> str:
    if not next_url:
        return reverse('expenses:list')

    parsed = urlsplit(next_url)
    if parsed.scheme or parsed.netloc:
        return reverse('expenses:list')

    path = parsed.path or ''
    query = f'?{parsed.query}' if parsed.query else ''
    list_path = reverse('expenses:list')
    if path == list_path:
        return f'{list_path}{query}'
    return list_path


def _current_expense_list_url(request) -> str:
    return _safe_next_url(
        request.POST.get('current_list_url')
        or request.POST.get('next')
        or request.META.get('HTTP_REFERER')
    )


def _querydict_from_list_url(list_url: str) -> QueryDict:
    return QueryDict(urlsplit(list_url).query, mutable=False)


def _filter_expenses(issuer, start, end, availability, search_query=''):
    qs = (
        Expense.objects.filter(issuer=issuer)
        .select_related('customer__company', 'project__customer__company')
    )
    if start:
        qs = qs.filter(paid_date__gte=start)
    if end:
        qs = qs.filter(paid_date__lte=end)
    if availability == 'with':
        qs = qs.exclude(Q(attachment='') | Q(attachment__isnull=True))
    elif availability == 'without':
        qs = qs.filter(Q(attachment='') | Q(attachment__isnull=True))
    if search_query:
        qs = qs.filter(
            Q(description__icontains=search_query)
            | Q(customer__company__name__icontains=search_query)
            | Q(project__title__icontains=search_query)
            | Q(project__project_code__icontains=search_query)
        )
    return qs.order_by('-id')


def _build_table_rows(expenses_page, *, csrf_token: str, next_url: str):
    rows = []
    for expense in expenses_page:
        checkbox = format_html(
            '<input type="checkbox" class="field-control--checkbox expense-select" '
            'name="selected" value="{}" form="bulk-download-form" />',
            expense.id,
        )
        identifier = format_html(
            '<a href="#" class="link-primary" data-expense-drawer data-expense-id="{id}">#{id}</a>',
            id=expense.id,
        )
        date_cell = date_format(expense.paid_date, 'j/m/Y') if expense.paid_date else '—'
        if expense.description:
            escaped = conditional_escape(expense.description.strip()).replace('\n', '<br />')
            memo_cell = format_html('<span class="text-wrap">{}</span>', mark_safe(escaped))
        else:
            memo_cell = '—'
        if expense.attachment:
            file_cell = format_html(
                '<a href="{}" class="link-primary" target="_blank" rel="noopener">Yes</a>',
                expense.attachment.url,
            )
        else:
            file_cell = 'No'
        report_cell = format_html(
            '<div class="expense-report-cell">'
            '<form method="post" action="{}" class="expense-report-toggle-form">'
            '<input type="hidden" name="csrfmiddlewaretoken" value="{}" />'
            '<input type="hidden" name="next" value="{}" />'
            '<input type="hidden" name="exclude_from_reports" value="0" />'
            '<label class="expense-report-toggle" title="Do not count">'
            '<input type="checkbox" name="exclude_from_reports" value="1" {} '
            'data-testid="expense-report-toggle-{}" data-expense-report-toggle aria-label="Do not count expense #{} in reports" />'
            '<span class="expense-report-toggle__track" aria-hidden="true"></span>'
            '</label>'
            '<noscript><button type="submit" class="btn btn-sm btn-quiet">Save</button></noscript>'
            '</form>'
            '</div>',
            reverse('expenses:reporting_visibility', args=[expense.pk]),
            csrf_token,
            next_url,
            'checked' if expense.exclude_from_reports else '',
            expense.pk,
            expense.pk,
        )
        amount_cell = _format_currency(expense.amount)
        actions_cell = format_html(
            '<div class="table-actions">'
            '<button type="button" class="btn btn-sm btn-outline-secondary" '
            'data-expense-drawer data-expense-id="{id}">Edit</button>'
            '<button type="button" class="btn btn-sm btn-link text-danger" '
            'data-expense-delete data-expense-id="{id}">Delete</button>'
            '</div>',
            id=expense.id,
        )
        rows.append(
            {
                'cells': [
                    {'content': checkbox, 'align': 'select-cell'},
                    {'content': identifier},
                    {'content': date_cell},
                    {'content': memo_cell},
                    {'content': file_cell},
                    {'content': report_cell},
                    {'content': amount_cell, 'align': 'text-end'},
                    {'content': actions_cell, 'align': 'text-end'},
                ]
            }
        )
    return rows


EXPENSE_ORDER_SESSION_KEY = 'expenses_order'


def _expense_list_context(request, issuer, *, current_list_url: str | None = None):
    original_get = request.GET
    had_global_date_filter = hasattr(request, '_global_date_filter')
    original_global_date_filter = getattr(request, '_global_date_filter', None)
    if current_list_url is not None:
        request.GET = _querydict_from_list_url(current_list_url)
        if had_global_date_filter:
            delattr(request, '_global_date_filter')

    date_filter = get_global_date_filter(request)
    availability = request.GET.get('has_attachment', 'all')
    search_query = (request.GET.get('q') or '').strip()
    if availability not in ATTACHMENT_FILTER_VALUES:
        availability = 'all'

    expenses_qs = _filter_expenses(
        issuer,
        date_filter.get('start'),
        date_filter.get('end'),
        availability,
        search_query,
    )

    order_map = {
        'date_desc': ('-paid_date', '-id'),
        'date_asc': ('paid_date', '-id'),
        'id_desc': ('-id',),
        'id_asc': ('id',),
    }
    default_order = 'date_desc'
    requested_order = request.GET.get('order')
    stored_order = request.session.get(EXPENSE_ORDER_SESSION_KEY)
    if requested_order:
        order_param = requested_order if requested_order in order_map else default_order
        if order_param == default_order:
            request.session.pop(EXPENSE_ORDER_SESSION_KEY, None)
        else:
            request.session[EXPENSE_ORDER_SESSION_KEY] = order_param
    else:
        order_param = stored_order if stored_order in order_map else default_order
        if stored_order and stored_order not in order_map:
            request.session.pop(EXPENSE_ORDER_SESSION_KEY, None)
    if order_param not in order_map:
        order_param = default_order

    expenses_qs = expenses_qs.order_by(*order_map[order_param])

    paginator = Paginator(expenses_qs, 100)
    page_number = request.GET.get('page')
    expenses_page = paginator.get_page(page_number)

    query_without_order = _querystring_without(request.GET, 'order')

    def sortable_column(label, base_key, align=''):
        asc = f'{base_key}_asc'
        desc = f'{base_key}_desc'
        if order_param == asc:
            direction = 'asc'
            next_order = desc
        elif order_param == desc:
            direction = 'desc'
            next_order = asc
        else:
            direction = 'none'
            next_order = desc
        return {
            'label': label,
            'align': align,
            'sortable': True,
            'direction': direction,
            'next_order': next_order,
        }

    order_columns = [
        {'label': '', 'sortable': False, 'align': 'select-cell'},
        sortable_column('#', 'id'),
        sortable_column('Date', 'date'),
        {'label': 'Memo', 'sortable': False},
        {'label': 'File', 'sortable': False},
        {'label': 'Do not count', 'sortable': False},
        {'label': 'Amount', 'sortable': False, 'align': 'text-end'},
        {'label': 'Actions', 'sortable': False, 'align': 'text-end'},
    ]

    safe_current_list_url = _safe_next_url(current_list_url or request.get_full_path())
    rows = _build_table_rows(
        expenses_page,
        csrf_token=get_token(request),
        next_url=safe_current_list_url,
    )

    amount_total = expenses_qs.aggregate(total=Coalesce(Sum('amount'), Decimal('0')))['total']

    context = {
        'order_columns': order_columns,
        'expense_rows': rows,
        'expenses_page': expenses_page,
        'query_without_page': _querystring_without(request.GET, 'page'),
        'query_without_order': query_without_order,
        'availability_filter': availability,
        'search_query': search_query,
        'amount_total': amount_total,
        'global_date_filter': date_filter,
        'current_list_url': safe_current_list_url,
    }

    if current_list_url is not None:
        request.GET = original_get
        if had_global_date_filter:
            request._global_date_filter = original_global_date_filter  # type: ignore[attr-defined]
        elif hasattr(request, '_global_date_filter'):
            delattr(request, '_global_date_filter')

    return context


def render_expense_list_fragment(request, issuer, *, current_list_url: str | None = None) -> str:
    return render_to_string(
        'expenses/partials/expense_list_results.html',
        _expense_list_context(request, issuer, current_list_url=current_list_url),
        request=request,
    )


def _expense_mutation_success_response(request, issuer, message: str):
    current_list_url = _current_expense_list_url(request)
    messages.success(request, message)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': message,
            'redirect_url': current_list_url,
            'list_url': current_list_url,
            'list_html': render_expense_list_fragment(
                request,
                issuer,
                current_list_url=current_list_url,
            ),
        })
    return redirect(current_list_url)


@require_GET
def expense_index(request):
    issuer = get_active_issuer(request)
    if not issuer:
        messages.error(request, 'Select a company before managing expenses.')
        return redirect('company:settings')

    context = _expense_list_context(request, issuer)
    return render(request, 'expenses/expenses_list.html', context)


def _importer_for_request(request, issuer):
    ai_client = None
    try:
        profile = request.user.profile
    except ObjectDoesNotExist:
        profile = None
    if profile and profile.has_complete_expense_ai_settings():
        ai_client = OpenAICompatibleMappingClient(
            OpenAICompatibleProviderConfig(
                base_url=profile.expense_ai_provider_base_url,
                model=profile.expense_ai_model_name,
                api_key=profile.expense_ai_api_key,
            )
        )
    return GenericExpenseImporter(request.user, issuer, ai_client=ai_client)


def _mapping_json_from_post(post):
    mapping = {}
    for field in IMPORT_MAPPING_FIELDS:
        raw_values = post.getlist(field) if hasattr(post, 'getlist') else [post.get(field)]
        values = [str(value).strip() for value in raw_values if str(value or '').strip()]
        if not values:
            continue
        mapping[field] = values[0] if len(values) == 1 else values
    mapping['amount_mode'] = post.get('amount_mode') or 'absolute'
    date_formats = (post.get('date_formats') or '').strip()
    if date_formats:
        mapping['date_formats'] = [item.strip() for item in date_formats.split(',') if item.strip()]
    return mapping


def _import_context(request, issuer, *, batch=None, result=None, error='', stage='upload'):
    mappings = ImportMapping.objects.visible_to(request.user).order_by('scope', 'name')
    preview_rows = batch.preview_rows.all() if batch else []
    mapping_json = {}
    selected_mapping = None
    if batch:
        selected_mapping = batch.mapping
        mapping_json = batch.metadata.get('mapping_json') or (batch.mapping.mapping_json if batch.mapping else {})
    return {
        'stage': stage,
        'batch': batch,
        'result': result,
        'error': error,
        'available_mappings': mappings,
        'selected_mapping': selected_mapping,
        'mapping_json': mapping_json,
        'mapping_fields': IMPORT_MAPPING_FIELDS,
        'preview_rows': preview_rows,
    }


@require_http_methods(['GET', 'POST'])
def expense_csv_import(request):
    issuer = get_active_issuer(request)
    if not issuer:
        messages.error(request, 'Select a company before importing expenses.')
        return redirect('company:settings')

    if request.method == 'GET':
        return render(request, 'expenses/expense_import.html', _import_context(request, issuer))

    uploads = request.FILES.getlist('statements')
    if not uploads:
        context = _import_context(request, issuer, error='Upload at least one expense statement file (CSV, XLS, XLSX, or ZIP).')
        return render(request, 'expenses/expense_import.html', context, status=400)

    importer = _importer_for_request(request, issuer)
    try:
        parsed_files = importer.parse_uploads(uploads)
        headers = parsed_files[0].headers
        selected_mapping = None
        mapping_id = request.POST.get('mapping')
        if mapping_id:
            selected_mapping = ImportMapping.objects.visible_to(request.user).get(pk=mapping_id)
        mapping, mapping_source = importer.resolve_mapping(headers, parsed_files[0].rows[:5], mapping=selected_mapping)
        importer.validate_mapping(mapping.mapping_json, headers)
        rows = []
        for parsed in parsed_files:
            importer.validate_mapping(mapping.mapping_json, parsed.headers)
            rows.extend((parsed.source_name, row) for row in parsed.rows)
        if not rows:
            raise ExpenseImportError('No transactions found in the uploaded files.')
        batch = importer.create_preview_batch(parsed_files, mapping, rows)
        batch.metadata.update({
            'mapping_source': mapping_source,
            'mapping_json': mapping.mapping_json,
            'raw_rows': [{'source_name': source_name, 'row': row} for source_name, row in rows],
        })
        batch.save(update_fields=['metadata', 'updated_at'])
    except (ExpenseImportError, ImportMapping.DoesNotExist) as exc:
        context = _import_context(request, issuer, error=str(exc))
        return render(request, 'expenses/expense_import.html', context, status=400)

    return render(request, 'expenses/expense_import.html', _import_context(request, issuer, batch=batch, stage='mapping'))


@require_POST
def expense_csv_import_review(request, batch_id):
    issuer = get_active_issuer(request)
    if not issuer:
        messages.error(request, 'Select a company before importing expenses.')
        return redirect('company:settings')
    batch = get_object_or_404(ImportBatch, pk=batch_id, user=request.user, issuer=issuer, status=ImportBatch.STATUS_MAPPED)
    importer = _importer_for_request(request, issuer)
    mapping_json = _mapping_json_from_post(request.POST)
    try:
        importer.validate_mapping(mapping_json, batch.raw_headers)
    except ExpenseImportError as exc:
        batch.metadata['mapping_json'] = mapping_json
        context = _import_context(request, issuer, batch=batch, error=str(exc), stage='mapping')
        return render(request, 'expenses/expense_import.html', context, status=400)

    mapping = batch.mapping
    save_name = (request.POST.get('save_mapping_name') or '').strip()
    if save_name:
        mapping, _ = ImportMapping.objects.update_or_create(
            scope=ImportMapping.SCOPE_USER,
            owner=request.user,
            name=save_name,
            defaults={
                'normalized_header_signature': batch.normalized_header_signature,
                'mapping_json': mapping_json,
                'default_row_selection_rules': {},
                'read_only': False,
            },
        )
    batch.mapping = mapping if mapping and mapping.pk else None
    batch.metadata.update({'mapping_json': mapping_json})
    batch.save(update_fields=['mapping', 'metadata', 'updated_at'])
    batch.preview_rows.all().delete()
    for index, raw_row in enumerate(batch.metadata.get('raw_rows', []), start=1):
        row_data = raw_row.get('row', {})
        mapped_data, errors = importer.normalize_row(row_data, mapping_json, source_name=raw_row.get('source_name', ''))
        rules = mapping.default_row_selection_rules if mapping else {}
        default_selected, skip_reason = importer._default_selected(row_data, rules)
        if skip_reason:
            mapped_data['skip_reason'] = skip_reason
        ImportPreviewRow.objects.create(
            batch=batch,
            row_index=index,
            raw_data=row_data,
            mapped_data=mapped_data,
            default_selected=default_selected,
            selected=default_selected,
            validation_errors=errors,
            fingerprint=importer._row_fingerprint(row_data, raw_row.get('source_name', '')),
        )
    return render(request, 'expenses/expense_import.html', _import_context(request, issuer, batch=batch, stage='preview'))


@require_POST
def expense_csv_import_confirm(request, batch_id):
    issuer = get_active_issuer(request)
    if not issuer:
        messages.error(request, 'Select a company before importing expenses.')
        return redirect('company:settings')
    batch = get_object_or_404(ImportBatch, pk=batch_id, user=request.user, issuer=issuer, status=ImportBatch.STATUS_MAPPED)
    selected = {int(value) for value in request.POST.getlist('selected_rows') if value.isdigit()}
    result = ExpenseImportResult(batch=batch, mapping=batch.mapping)
    result.rows_processed = batch.preview_rows.count()
    _importer_for_request(request, issuer).import_selected_preview_rows(batch, result, selected_row_indexes=selected)
    invalidate_dashboard_cache(issuer.pk)
    return render(request, 'expenses/expense_import.html', _import_context(request, issuer, batch=batch, result=result, stage='result'))


@require_POST
def expense_reporting_visibility(request, pk):
    issuer = get_active_issuer(request)
    if not issuer:
        messages.error(request, 'Select a company before managing expenses.')
        return redirect('company:settings')

    expense = get_object_or_404(Expense, pk=pk, issuer=issuer)
    exclude_from_reports = request.POST.get('exclude_from_reports') in {'1', 'true', 'on'}
    if expense.exclude_from_reports != exclude_from_reports:
        expense.exclude_from_reports = exclude_from_reports
        expense.save(update_fields=['exclude_from_reports'])
        invalidate_dashboard_cache(issuer.pk)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'exclude_from_reports': expense.exclude_from_reports,
        })
    return redirect(_safe_next_url(request.POST.get('next')))


@require_http_methods(['GET', 'POST'])
def expense_drawer(request, pk=None):
    issuer = get_active_issuer(request)
    if not issuer:
        messages.error(request, 'Select a company before managing expenses.')
        return redirect('company:settings')

    expense = None
    if pk:
        expense = get_object_or_404(Expense, pk=pk, issuer=issuer)
    else:
        expense = Expense(issuer=issuer, paid_date=date.today())

    if request.method == 'POST':
        form = ExpenseForm(request.POST, request.FILES, instance=expense, issuer=issuer)
        if form.is_valid():
            form.save(issuer=issuer)
            invalidate_dashboard_cache(issuer.pk)
            return _expense_mutation_success_response(request, issuer, 'Expense saved successfully.')

        html = render_to_string(
            'expenses/partials/expense_drawer.html',
            _drawer_context(form, request.path),
            request=request,
        )
        return JsonResponse({'success': False, 'html': html}, status=400)

    form = ExpenseForm(instance=expense, issuer=issuer)
    html = render_to_string(
        'expenses/partials/expense_drawer.html',
        _drawer_context(form, request.path),
        request=request,
    )
    return HttpResponse(html)


def _drawer_context(form: ExpenseForm, action_url: str):
    project_options = []
    for project in form.fields['project'].queryset.select_related('customer__company'):
        label = project.project_code or project.title
        if project.project_code and project.title:
            label = f"{project.project_code} — {project.title}"
        project_options.append({
            'id': project.pk,
            'label': label,
            'customer': project.customer_id,
        })

    return {
        'form': form,
        'project_options': project_options,
        'action_url': action_url,
    }


@require_POST
def expense_delete(request, pk):
    issuer = get_active_issuer(request)
    if not issuer:
        return JsonResponse({'error': 'Select a company first.'}, status=400)

    expense = get_object_or_404(Expense, pk=pk, issuer=issuer)

    if expense.attachment:
        expense.attachment.delete(save=False)
    expense.delete()
    invalidate_dashboard_cache(issuer.pk)
    return _expense_mutation_success_response(request, issuer, 'Expense deleted.')


@require_POST
def expense_bulk_download(request):
    issuer = get_active_issuer(request)
    if not issuer:
        messages.error(request, 'Select a company before downloading expenses.')
        return redirect('company:settings')

    selected_ids = request.POST.getlist('selected')
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or reverse('expenses:list')

    if not selected_ids:
        messages.warning(request, 'Select at least one expense to download.')
        return redirect(next_url)

    expenses = Expense.objects.filter(pk__in=selected_ids, issuer=issuer)
    buffer = io.BytesIO()
    added = 0
    seen_names: set[str] = set()

    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for expense in expenses:
            attachment = expense.attachment
            if not attachment:
                continue
            try:
                attachment.open('rb')
                data = attachment.read()
            except Exception:
                continue
            finally:
                try:
                    attachment.close()
                except Exception:
                    pass

            if not data:
                continue

            paid_str = expense.paid_date.strftime('%Y-%m-%d') if expense.paid_date else 'undated'
            stored_name = os.path.basename(attachment.name)
            arcname = f"{paid_str}_{stored_name}"
            counter = 1
            unique_name = arcname
            while unique_name in seen_names:
                unique_name = f"{paid_str}_{counter}_{stored_name}"
                counter += 1
            seen_names.add(unique_name)

            try:
                archive.writestr(unique_name, data)
                added += 1
            except Exception:
                continue

    if added == 0:
        messages.warning(request, 'Selected expenses do not have attachments to download.')
        return redirect(next_url)

    buffer.seek(0)
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    filename = f'expenses_{timestamp}.zip'
    response = HttpResponse(buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _available_issuers(request):
    issuers = request.user.issuers.select_related('company').order_by('company__name')
    if request.user.is_superuser:
        from invoices.models import Issuer

        issuers = Issuer.objects.select_related('company').order_by('company__name')
    return issuers


def _incoming_candidate_queryset(request):
    issuers = _available_issuers(request)
    if request.user.is_superuser:
        return (
            IncomingInvoiceCandidate.objects.select_related(
                'source', 'suggested_issuer__company', 'confirmed_issuer__company', 'selected_artifact', 'converted_expense'
            )
            .prefetch_related('artifacts')
            .distinct()
        )
    issuer_ids = list(issuers.values_list('id', flat=True))
    return (
        IncomingInvoiceCandidate.objects.select_related(
            'source', 'suggested_issuer__company', 'confirmed_issuer__company', 'selected_artifact', 'converted_expense'
        )
        .prefetch_related('artifacts')
        .filter(
            Q(source__issuer_id__in=issuer_ids)
            | Q(source__issuer__isnull=True, source__user=request.user, suggested_issuer__isnull=True, confirmed_issuer__isnull=True)
            | Q(suggested_issuer_id__in=issuer_ids)
            | Q(confirmed_issuer_id__in=issuer_ids)
        )
        .distinct()
    )


def _get_incoming_candidate(request, pk):
    return get_object_or_404(_incoming_candidate_queryset(request), pk=pk)


def _apply_incoming_filters(request, qs):
    status = request.GET.get('status') or ''
    company = request.GET.get('company') or ''
    source = request.GET.get('source') or ''
    confidence = request.GET.get('confidence') or ''
    missing_review = request.GET.get('missing_review') or ''
    date_from = request.GET.get('date_from') or ''
    date_to = request.GET.get('date_to') or ''
    if status:
        qs = qs.filter(status=status)
    if company:
        qs = qs.filter(Q(confirmed_issuer_id=company) | Q(suggested_issuer_id=company) | Q(source__issuer_id=company))
    if source:
        qs = qs.filter(source_id=source)
    if confidence == 'high':
        qs = qs.filter(detection_metadata__company_confidence__gte=0.8)
    elif confidence == 'low':
        qs = qs.filter(Q(detection_metadata__company_confidence__lt=0.8) | Q(detection_metadata__company_confidence__isnull=True))
    if missing_review:
        qs = qs.filter(Q(confirmed_issuer__isnull=True) | Q(selected_artifact__isnull=True))
    if date_from:
        qs = qs.filter(received_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(received_at__date__lte=date_to)
    return qs, {
        'status': status,
        'company': company,
        'source': source,
        'confidence': confidence,
        'missing_review': missing_review,
        'date_from': date_from,
        'date_to': date_to,
    }


def incoming_inbox(request):
    qs, filters = _apply_incoming_filters(request, _incoming_candidate_queryset(request))
    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get('page'))
    issuers = _available_issuers(request)
    if request.user.is_superuser:
        sources = IncomingEmailSource.objects.all().order_by('display_name')
    else:
        sources = IncomingEmailSource.objects.filter(
            Q(issuer__in=issuers) | Q(issuer__isnull=True, user=request.user)
        ).order_by('display_name')
    return render(request, 'expenses/incoming_inbox.html', {
        'candidates': page,
        'filters': filters,
        'status_choices': IncomingInvoiceCandidate.STATUS_CHOICES,
        'issuers': issuers,
        'sources': sources,
    })


@require_http_methods(['GET', 'POST'])
def incoming_source_settings(request):
    issuers = _available_issuers(request)
    if request.user.is_superuser:
        sources = IncomingEmailSource.objects.all().select_related('issuer__company')
    else:
        sources = IncomingEmailSource.objects.filter(
            Q(issuer__in=issuers) | Q(issuer__isnull=True, user=request.user)
        ).select_related('issuer__company')
    if request.method == 'POST':
        form = IncomingEmailSourceForm(request.POST, user=request.user, issuers=issuers)
        if form.is_valid():
            form.save()
            messages.success(request, 'Incoming email source saved.')
            return redirect('expenses:incoming_sources')
    else:
        form = IncomingEmailSourceForm(user=request.user, issuers=issuers)
    return render(request, 'expenses/incoming_sources.html', {'form': form, 'sources': sources})


@require_http_methods(['GET', 'POST'])
def incoming_routing_settings(request):
    active_issuer = get_active_issuer(request)
    if not active_issuer:
        messages.error(request, 'Select a company before managing routing rules.')
        return redirect('company:settings')
    rule, _ = IssuerEmailRoutingRule.objects.get_or_create(issuer=active_issuer)
    if request.method == 'POST':
        form = IssuerEmailRoutingRuleForm(request.POST, instance=rule, issuer=active_issuer)
        if form.is_valid():
            form.save()
            messages.success(request, 'Incoming routing settings saved.')
            return redirect('expenses:incoming_routing')
    else:
        form = IssuerEmailRoutingRuleForm(instance=rule, issuer=active_issuer)
    return render(request, 'expenses/incoming_routing.html', {'form': form, 'issuer': active_issuer})


def incoming_candidate_detail(request, pk):
    candidate = _get_incoming_candidate(request, pk)
    issuers = _available_issuers(request)
    form = IncomingCandidateReviewForm(candidate=candidate, issuers=issuers)
    return render(
        request,
        'expenses/incoming_candidate_detail.html',
        _incoming_candidate_detail_context(candidate, form, issuers),
    )


def _incoming_candidate_detail_context(candidate, form, issuers):
    detection = candidate.detection_metadata or {}
    issuer_names = {issuer.pk: str(issuer) for issuer in issuers}
    company_scores = []
    for score in detection.get('company_scores') or []:
        issuer_id = score.get('issuer_id')
        company_scores.append({
            'issuer': issuer_names.get(issuer_id, f"Company #{issuer_id}"),
            'confidence': score.get('confidence') or '—',
            'reasons': score.get('reasons') or [],
        })
    duplicate = candidate.duplicate_metadata or {}
    return {
        'candidate': candidate,
        'review_form': form,
        'routing_feedback': {
            'invoice_confidence': detection.get('invoice_confidence') or '—',
            'company_confidence': detection.get('company_confidence') or '—',
            'company_reasons': detection.get('company_reasons') or detection.get('reasons') or [],
            'company_warning': detection.get('company_warning'),
            'company_scores': company_scores,
        },
        'duplicate_feedback': {
            'is_duplicate': duplicate.get('is_duplicate'),
            'reasons': duplicate.get('reasons') or [],
            'candidate_ids': duplicate.get('candidate_ids') or [],
            'expense_ids': duplicate.get('expense_ids') or [],
        },
    }


@require_POST
def incoming_candidate_action(request, pk):
    candidate = _get_incoming_candidate(request, pk)
    form = IncomingCandidateReviewForm(request.POST, candidate=candidate, issuers=_available_issuers(request))
    if not form.is_valid():
        issuers = _available_issuers(request)
        return render(
            request,
            'expenses/incoming_candidate_detail.html',
            _incoming_candidate_detail_context(candidate, form, issuers),
            status=400,
        )
    action = form.cleaned_data['action']
    if action == IncomingCandidateReviewForm.ACTION_REJECT:
        mark_candidate_rejected(candidate)
        messages.success(request, 'Candidate rejected and kept in history.')
    elif action == IncomingCandidateReviewForm.ACTION_NOT_INVOICE:
        mark_candidate_not_invoice(candidate)
        messages.success(request, 'Candidate marked as not an invoice.')
    elif action == IncomingCandidateReviewForm.ACTION_NEEDS_FETCH:
        mark_candidate_needs_fetch(candidate)
        messages.success(request, 'Candidate marked as needing manual fetch.')
    elif action == IncomingCandidateReviewForm.ACTION_DUPLICATE:
        mark_candidate_duplicate(candidate)
        messages.success(request, 'Candidate marked as duplicate.')
    elif action == IncomingCandidateReviewForm.ACTION_LINK_EXISTING:
        mark_candidate_duplicate(candidate, existing_expense=form.cleaned_data['existing_expense'])
        messages.success(request, 'Candidate linked to an existing expense as a duplicate.')
    elif action == IncomingCandidateReviewForm.ACTION_REVIEWED_UNPAID:
        mark_candidate_reviewed_unpaid(
            candidate,
            issuer=form.cleaned_data['confirmed_issuer'],
            artifact=form.cleaned_data['selected_artifact'],
            metadata=review_metadata_from_cleaned(form.cleaned_data),
        )
        messages.success(request, 'Candidate marked reviewed/unpaid; no expense was created.')
    else:
        mark_candidate_confirmed(
            candidate,
            issuer=form.cleaned_data['confirmed_issuer'],
            artifact=form.cleaned_data['selected_artifact'],
            metadata=review_metadata_from_cleaned(form.cleaned_data),
        )
        messages.success(request, 'Company and artifact selection saved.')
    return redirect('expenses:incoming_detail', pk=candidate.pk)


@require_http_methods(['GET', 'POST'])
def incoming_candidate_convert(request, pk):
    candidate = _get_incoming_candidate(request, pk)
    if request.method == 'POST':
        form = IncomingCandidateConversionForm(request.POST, candidate=candidate, issuers=_available_issuers(request))
        if form.is_valid():
            if form.cleaned_data['paid_state'] == 'unpaid':
                mark_candidate_reviewed_unpaid(
                    candidate,
                    issuer=form.cleaned_data['confirmed_issuer'],
                    artifact=form.cleaned_data['selected_artifact'],
                    metadata=review_metadata_from_cleaned(form.cleaned_data),
                )
                messages.success(request, 'Candidate marked reviewed/unpaid; no expense was created.')
                return redirect('expenses:incoming_detail', pk=candidate.pk)
            expense = convert_candidate_to_expense(
                candidate,
                issuer=form.cleaned_data['confirmed_issuer'],
                artifact=form.cleaned_data['selected_artifact'],
                vendor=form.cleaned_data['vendor'],
                description=form.cleaned_data['description'],
                amount=form.cleaned_data['amount'],
                currency=form.cleaned_data['currency'],
                paid_date=form.cleaned_data['paid_date'],
                duplicate_override=form.cleaned_data['duplicate_override'],
            )
            messages.success(request, 'Incoming invoice converted to an expense.')
            return redirect(f"{reverse('expenses:list')}?q={expense.pk}")
    else:
        form = IncomingCandidateConversionForm(candidate=candidate, issuers=_available_issuers(request))
    return render(request, 'expenses/incoming_conversion.html', {'candidate': candidate, 'form': form})


def incoming_artifact_download(request, pk, artifact_id):
    candidate = _get_incoming_candidate(request, pk)
    artifact = get_object_or_404(candidate.artifacts, pk=artifact_id)
    if not artifact.file:
        raise Http404()
    artifact.file.open('rb')
    response = FileResponse(artifact.file, content_type=artifact.content_type or 'application/octet-stream')
    response['Content-Disposition'] = f'attachment; filename="{artifact.display_name}"'
    return response


def incoming_artifact_preview(request, pk, artifact_id):
    candidate = _get_incoming_candidate(request, pk)
    artifact = get_object_or_404(candidate.artifacts, pk=artifact_id)
    if not artifact.file:
        raise Http404()
    artifact.file.open('rb')
    return FileResponse(artifact.file, content_type=artifact.content_type or 'application/octet-stream')
