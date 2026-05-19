import csv
import io
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, RequestFactory, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from invoices.forms import InvoiceForm
from invoices.models import Company, Currency, Customer, Expense, Invoice, Issuer, IssuerBankAccount, OrderLine, Payment, PaymentApplication, PaymentTerm, Project
from invoices.services.bank_accounts import resolve_invoice_bank_account
from invoices.services.wise_importer import WiseImportResult, WiseStatementImporter
from invoices.views import (
    DASHBOARD_DEFAULT_MAX_RESULTS,
    DASHBOARD_DEFAULT_INVOICE_STATUS,
    DASHBOARD_INVOICE_STATUS_SESSION_KEY,
    DASHBOARD_MAX_RESULTS_OPTIONS,
    DASHBOARD_MAX_RESULTS_SESSION_KEY,
    INVOICE_STATUS_FILTER_OPTIONS,
    _build_cross_company_dashboard_cache_key,
    _build_cross_company_dashboard_scope,
    _build_cross_company_recent_invoices,
    _build_cross_company_recent_payments,
    _cross_company_dashboard_cache_signature,
    _get_dashboard_filter_state,
    invalidate_dashboard_cache,
)
from tests.support import AuthenticatedCompanyTestCase


class CrossCompanyDashboardScopeTests(AuthenticatedCompanyTestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.issuer_a = Issuer.objects.create(
            company=Company.objects.create(name='Issuer A', customer_information_file_number='VATA')
        )
        self.issuer_b = Issuer.objects.create(
            company=Company.objects.create(name='Issuer B', customer_information_file_number='VATB')
        )
        self.issuer_hidden = Issuer.objects.create(
            company=Company.objects.create(name='Issuer Hidden', customer_information_file_number='VATH')
        )

        self.customer_a = Customer.objects.create(
            issuer=self.issuer_a,
            company=Company.objects.create(name='Client A', customer_information_file_number='CLIENTA'),
        )
        self.customer_b = Customer.objects.create(
            issuer=self.issuer_b,
            company=Company.objects.create(name='Client B', customer_information_file_number='CLIENTB'),
        )
        self.customer_hidden = Customer.objects.create(
            issuer=self.issuer_hidden,
            company=Company.objects.create(name='Client Hidden', customer_information_file_number='CLIENTH'),
        )

        self.project_a = Project.objects.create(customer=self.customer_a, title='Project A', project_code='PRJA')
        self.project_b = Project.objects.create(customer=self.customer_b, title='Project B', project_code='PRJB')
        self.project_hidden = Project.objects.create(
            customer=self.customer_hidden,
            title='Project Hidden',
            project_code='PRJH',
        )

        self.invoice_a = Invoice.objects.create(
            issuer=self.issuer_a,
            customer=self.customer_a,
            project=self.project_a,
            issued_date=date(2024, 1, 10),
            status=Invoice.STATUS_INVOICED,
            total_due=Decimal('100.00'),
        )
        self.invoice_b = Invoice.objects.create(
            issuer=self.issuer_b,
            customer=self.customer_b,
            project=self.project_b,
            issued_date=date(2024, 1, 11),
            status=Invoice.STATUS_INVOICED,
            total_due=Decimal('200.00'),
        )
        self.invoice_hidden = Invoice.objects.create(
            issuer=self.issuer_hidden,
            customer=self.customer_hidden,
            project=self.project_hidden,
            issued_date=date(2024, 1, 12),
            status=Invoice.STATUS_INVOICED,
            total_due=Decimal('300.00'),
        )

        self.payment_a = Payment.objects.create(
            issuer=self.issuer_a,
            customer=self.customer_a,
            project=self.project_a,
            amount=Decimal('100.00'),
            base_currency_amount=Decimal('100.00'),
            received_at=date(2024, 1, 15),
        )
        self.payment_b = Payment.objects.create(
            issuer=self.issuer_b,
            customer=self.customer_b,
            project=self.project_b,
            amount=Decimal('200.00'),
            base_currency_amount=Decimal('200.00'),
            received_at=date(2024, 1, 16),
        )
        self.payment_hidden = Payment.objects.create(
            issuer=self.issuer_hidden,
            customer=self.customer_hidden,
            project=self.project_hidden,
            amount=Decimal('300.00'),
            base_currency_amount=Decimal('300.00'),
            received_at=date(2024, 1, 17),
        )
        PaymentApplication.objects.create(payment=self.payment_a, invoice=self.invoice_a, amount_applied=Decimal('100.00'))
        PaymentApplication.objects.create(payment=self.payment_b, invoice=self.invoice_b, amount_applied=Decimal('200.00'))
        PaymentApplication.objects.create(
            payment=self.payment_hidden,
            invoice=self.invoice_hidden,
            amount_applied=Decimal('300.00'),
        )

        self.expense_a = Expense.objects.create(
            issuer=self.issuer_a,
            customer=self.customer_a,
            project=self.project_a,
            invoice=self.invoice_a,
            paid_date=date(2024, 1, 18),
            amount=Decimal('10.00'),
        )
        self.expense_b = Expense.objects.create(
            issuer=self.issuer_b,
            customer=self.customer_b,
            project=self.project_b,
            invoice=self.invoice_b,
            paid_date=date(2024, 1, 19),
            amount=Decimal('20.00'),
        )
        self.expense_hidden = Expense.objects.create(
            issuer=self.issuer_hidden,
            customer=self.customer_hidden,
            project=self.project_hidden,
            invoice=self.invoice_hidden,
            paid_date=date(2024, 1, 20),
            amount=Decimal('30.00'),
        )

        self.user = self.create_user_with_issuers(
            [self.issuer_a, self.issuer_b],
            username='cross-company-scope-user',
            email='cross-company-scope@example.com',
        )
        self.client.force_login(self.user)

    def test_scope_only_includes_current_users_available_issuers(self):
        request = self.factory.get('/dashboard/cross-company/')
        request.user = self.user
        request.session = self.client.session

        scope = _build_cross_company_dashboard_scope(request)

        self.assertEqual(scope['issuer_ids'], [self.issuer_a.pk, self.issuer_b.pk])
        self.assertQuerySetEqual(
            scope['invoice_queryset'].order_by('pk').values_list('pk', flat=True),
            [self.invoice_a.pk, self.invoice_b.pk],
            transform=lambda value: value,
        )
        self.assertQuerySetEqual(
            scope['payment_queryset'].order_by('pk').values_list('pk', flat=True),
            [self.payment_a.pk, self.payment_b.pk],
            transform=lambda value: value,
        )
        self.assertQuerySetEqual(
            scope['expense_queryset'].order_by('pk').values_list('pk', flat=True),
            [self.expense_a.pk, self.expense_b.pk],
            transform=lambda value: value,
        )

    def test_scope_returns_empty_querysets_when_user_has_no_issuers(self):
        other_user = self.create_user_with_issuers(
            [],
            username='cross-company-empty-user',
            email='cross-company-empty@example.com',
        )
        request = self.factory.get('/dashboard/cross-company/')
        request.user = other_user
        request.session = self.client.session

        scope = _build_cross_company_dashboard_scope(request)

        self.assertEqual(scope['issuer_ids'], [])
        self.assertFalse(scope['invoice_queryset'].exists())
        self.assertFalse(scope['payment_queryset'].exists())
        self.assertFalse(scope['expense_queryset'].exists())

    def test_dashboard_filter_state_accepts_valid_selection(self):
        request = self.factory.get(
            '/dashboard/cross-company/',
            {'invoice_status': Invoice.STATUS_PAID, 'max_results': '50'},
        )
        request.session = self.client.session

        state = _get_dashboard_filter_state(request)

        self.assertEqual(state['invoice_status'], Invoice.STATUS_PAID)
        self.assertEqual(state['invoice_status_options'], INVOICE_STATUS_FILTER_OPTIONS)
        self.assertEqual(state['max_results'], 50)
        self.assertEqual(state['max_results_options'], DASHBOARD_MAX_RESULTS_OPTIONS)
        self.assertEqual(request.session[DASHBOARD_INVOICE_STATUS_SESSION_KEY], Invoice.STATUS_PAID)
        self.assertEqual(request.session[DASHBOARD_MAX_RESULTS_SESSION_KEY], 50)

    def test_dashboard_filter_state_falls_back_for_invalid_values(self):
        request = self.factory.get(
            '/dashboard/cross-company/',
            {'invoice_status': 'not-a-status', 'max_results': '999'},
        )
        request.session = self.client.session

        state = _get_dashboard_filter_state(request)

        self.assertEqual(state['invoice_status'], DASHBOARD_DEFAULT_INVOICE_STATUS)
        self.assertEqual(state['max_results'], DASHBOARD_DEFAULT_MAX_RESULTS)
        self.assertEqual(
            request.session[DASHBOARD_INVOICE_STATUS_SESSION_KEY],
            DASHBOARD_DEFAULT_INVOICE_STATUS,
        )
        self.assertEqual(request.session[DASHBOARD_MAX_RESULTS_SESSION_KEY], DASHBOARD_DEFAULT_MAX_RESULTS)

    def test_cross_company_dashboard_filter_state_persists_on_refresh(self):
        response = self.client.get(
            reverse('cross_company_dashboard'),
            {
                'date_range': 'all',
                'invoice_status': f'{Invoice.STATUS_INVOICED},{Invoice.STATUS_OVERDUE}',
                'max_results': '100',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context['dashboard_invoice_status'],
            f'{Invoice.STATUS_INVOICED},{Invoice.STATUS_OVERDUE}',
        )
        self.assertEqual(response.context['dashboard_max_results'], 100)

        refreshed_response = self.client.get(reverse('cross_company_dashboard'))

        self.assertEqual(refreshed_response.status_code, 200)
        self.assertEqual(
            refreshed_response.context['dashboard_invoice_status'],
            f'{Invoice.STATUS_INVOICED},{Invoice.STATUS_OVERDUE}',
        )
        self.assertEqual(refreshed_response.context['dashboard_max_results'], 100)

    def test_cross_company_dashboard_filters_recent_invoices_by_status_and_date(self):
        today = timezone.localdate()
        old_date = today - timedelta(days=45)
        Invoice.objects.filter(pk=self.invoice_a.pk).update(
            issued_date=today,
            status=Invoice.STATUS_PAID,
            due_date=today + timedelta(days=10),
            amount_due=Decimal('0.00'),
        )
        Invoice.objects.filter(pk=self.invoice_b.pk).update(
            issued_date=today,
            status=Invoice.STATUS_INVOICED,
            due_date=today - timedelta(days=1),
            amount_due=Decimal('200.00'),
        )
        old_overdue_invoice = Invoice.objects.create(
            issuer=self.issuer_a,
            customer=self.customer_a,
            project=self.project_a,
            issued_date=old_date,
            due_date=old_date - timedelta(days=1),
            status=Invoice.STATUS_INVOICED,
            total_due=Decimal('150.00'),
            amount_due=Decimal('150.00'),
        )

        response = self.client.get(
            reverse('cross_company_dashboard'),
            {'date_range': 'this_month', 'invoice_status': Invoice.STATUS_OVERDUE},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [invoice.pk for invoice in response.context['recent_invoices']],
            [self.invoice_b.pk],
        )
        self.assertNotIn(old_overdue_invoice.pk, [invoice.pk for invoice in response.context['recent_invoices']])

    def test_cross_company_dashboard_combined_status_includes_invoiced_and_overdue(self):
        today = timezone.localdate()
        Invoice.objects.filter(pk=self.invoice_a.pk).update(
            issued_date=today,
            status=Invoice.STATUS_INVOICED,
            due_date=today + timedelta(days=10),
            amount_due=Decimal('100.00'),
        )
        Invoice.objects.filter(pk=self.invoice_b.pk).update(
            issued_date=today - timedelta(days=1),
            status=Invoice.STATUS_PAID,
            due_date=today + timedelta(days=10),
            amount_due=Decimal('0.00'),
        )
        overdue_invoice = Invoice.objects.create(
            issuer=self.issuer_b,
            customer=self.customer_b,
            project=self.project_b,
            issued_date=today + timedelta(days=1),
            due_date=today - timedelta(days=1),
            status=Invoice.STATUS_INVOICED,
            total_due=Decimal('250.00'),
            amount_due=Decimal('250.00'),
        )
        draft_invoice = Invoice.objects.create(
            issuer=self.issuer_a,
            customer=self.customer_a,
            project=self.project_a,
            issued_date=today + timedelta(days=2),
            status=Invoice.STATUS_DRAFT,
            total_due=Decimal('50.00'),
        )

        response = self.client.get(
            reverse('cross_company_dashboard'),
            {
                'date_range': 'all',
                'invoice_status': f'{Invoice.STATUS_INVOICED},{Invoice.STATUS_OVERDUE}',
            },
        )

        self.assertEqual(response.status_code, 200)
        recent_invoice_ids = [invoice.pk for invoice in response.context['recent_invoices']]
        self.assertEqual(recent_invoice_ids, [overdue_invoice.pk, self.invoice_a.pk])
        self.assertNotIn(self.invoice_b.pk, recent_invoice_ids)
        self.assertNotIn(draft_invoice.pk, recent_invoice_ids)

    def test_cross_company_dashboard_applies_shared_max_results_to_recent_tables(self):
        today = timezone.localdate()
        for offset in range(30):
            invoice = Invoice.objects.create(
                issuer=self.issuer_a,
                customer=self.customer_a,
                project=self.project_a,
                issued_date=today + timedelta(days=offset),
                status=Invoice.STATUS_INVOICED,
                total_due=Decimal('10.00'),
            )
            payment = Payment.objects.create(
                issuer=self.issuer_a,
                customer=self.customer_a,
                project=self.project_a,
                amount=Decimal('10.00'),
                base_currency_amount=Decimal('10.00'),
                received_at=today + timedelta(days=offset),
            )
            PaymentApplication.objects.create(payment=payment, invoice=invoice, amount_applied=Decimal('10.00'))

        response = self.client.get(
            reverse('cross_company_dashboard'),
            {'date_range': 'all', 'max_results': '25'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['recent_invoices']), 25)
        self.assertEqual(len(response.context['recent_payments']), 25)

        expanded_response = self.client.get(
            reverse('cross_company_dashboard'),
            {'date_range': 'all', 'max_results': '50'},
        )

        self.assertEqual(expanded_response.status_code, 200)
        self.assertEqual(len(expanded_response.context['recent_invoices']), 32)
        self.assertEqual(len(expanded_response.context['recent_payments']), 32)

    def test_cross_company_dashboard_uses_filter_specific_cache_for_recent_tables(self):
        Invoice.objects.filter(pk=self.invoice_a.pk).update(status=Invoice.STATUS_PAID)
        Invoice.objects.filter(pk=self.invoice_b.pk).update(status=Invoice.STATUS_INVOICED)

        all_response = self.client.get(reverse('cross_company_dashboard'), {'date_range': 'all'})
        paid_response = self.client.get(
            reverse('cross_company_dashboard'),
            {'date_range': 'all', 'invoice_status': Invoice.STATUS_PAID},
        )

        self.assertEqual(all_response.status_code, 200)
        self.assertEqual(paid_response.status_code, 200)
        self.assertEqual(
            [invoice.pk for invoice in all_response.context['recent_invoices']],
            [self.invoice_b.pk, self.invoice_a.pk],
        )
        self.assertEqual(
            [invoice.pk for invoice in paid_response.context['recent_invoices']],
            [self.invoice_a.pk],
        )

        scope = _build_cross_company_dashboard_scope(paid_response.wsgi_request)
        signature = _cross_company_dashboard_cache_signature(
            scope['invoice_queryset'],
            scope['payment_queryset'],
            scope['expense_queryset'],
        )
        default_cache_key = _build_cross_company_dashboard_cache_key(
            scope['issuer_ids'],
            'all',
            signature,
        )
        paid_cache_key = _build_cross_company_dashboard_cache_key(
            scope['issuer_ids'],
            'all',
            signature,
            invoice_status=Invoice.STATUS_PAID,
            max_results=DASHBOARD_DEFAULT_MAX_RESULTS,
        )

        self.assertNotEqual(default_cache_key, paid_cache_key)
        self.assertIsNotNone(cache.get(default_cache_key))
        self.assertIsNotNone(cache.get(paid_cache_key))

    def test_cross_company_dashboard_paid_total_uses_base_currency_amount(self):
        response = self.client.get(reverse('cross_company_dashboard'), {'date_range': 'all'})

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'invoices/cross_company_dashboard.html')
        self.assertEqual(response.context['paid_total'], Decimal('300'))

    def test_cross_company_dashboard_paid_total_respects_selected_date_range(self):
        today = timezone.localdate()
        Payment.objects.filter(pk=self.payment_a.pk).update(received_at=today, base_currency_amount=Decimal('125.00'))
        Payment.objects.filter(pk=self.payment_b.pk).update(
            received_at=today - timedelta(days=45),
            base_currency_amount=Decimal('250.00'),
        )
        Payment.objects.filter(pk=self.payment_hidden.pk).update(
            received_at=today,
            base_currency_amount=Decimal('500.00'),
        )

        response = self.client.get(reverse('cross_company_dashboard'), {'date_range': 'this_month'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['paid_total'], Decimal('125'))

    def test_cross_company_dashboard_expense_total_uses_expense_amount(self):
        response = self.client.get(reverse('cross_company_dashboard'), {'date_range': 'all'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['expense_total'], Decimal('30'))

    def test_cross_company_dashboard_uses_separate_cache_namespace(self):
        cache.clear()

        response = self.client.get(reverse('cross_company_dashboard'), {'date_range': 'all'})

        self.assertEqual(response.status_code, 200)

        scope = _build_cross_company_dashboard_scope(response.wsgi_request)
        signature = _cross_company_dashboard_cache_signature(
            scope['invoice_queryset'],
            scope['payment_queryset'],
            scope['expense_queryset'],
        )
        cache_key = _build_cross_company_dashboard_cache_key(
            scope['issuer_ids'],
            response.context['selected_period'],
            signature,
        )

        self.assertIsNotNone(cache.get(cache_key))
        self.assertIsNone(cache.get(f'dashboard:v2:{self.issuer_a.pk}:{response.context["selected_period"]}'))

    def test_dashboard_invalidation_clears_cross_company_cache_for_changed_issuer(self):
        cache.clear()

        response = self.client.get(reverse('cross_company_dashboard'), {'date_range': 'all'})

        self.assertEqual(response.status_code, 200)

        scope = _build_cross_company_dashboard_scope(response.wsgi_request)
        signature = _cross_company_dashboard_cache_signature(
            scope['invoice_queryset'],
            scope['payment_queryset'],
            scope['expense_queryset'],
        )
        cache_key = _build_cross_company_dashboard_cache_key(
            scope['issuer_ids'],
            response.context['selected_period'],
            signature,
        )

        self.assertIsNotNone(cache.get(cache_key))

        invalidate_dashboard_cache(self.issuer_a.pk)

        self.assertIsNone(cache.get(cache_key))

    def test_cross_company_dashboard_renders_kpis_with_two_decimal_formatting(self):
        response = self.client.get(reverse('cross_company_dashboard'), {'date_range': 'all'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<h2>Total income</h2>', html=True)
        self.assertContains(response, '<p>300.00 €</p>', html=True)
        self.assertContains(response, '<h2>Total expenses</h2>', html=True)
        self.assertContains(response, '<p>30.00 €</p>', html=True)

    def test_cross_company_dashboard_renders_expected_page_sections(self):
        response = self.client.get(reverse('cross_company_dashboard'), {'date_range': 'all'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<h1>Dashboard</h1>', html=True)
        self.assertContains(response, 'Combined activity across your available companies.')
        self.assertContains(response, '<label class="form-field__label" for="dashboard-period">Period</label>', html=True)
        self.assertContains(
            response,
            '<option value="all" selected>All time</option>',
            html=True,
        )
        self.assertContains(response, '<h2>Recent invoices</h2>', html=True)
        self.assertContains(response, '<h2>Recent payments</h2>', html=True)

    def test_cross_company_dashboard_renders_shared_24_month_chart_for_accessible_issuers(self):
        today = timezone.localdate()
        current_month_start = today.replace(day=1)

        Invoice.objects.filter(pk=self.invoice_a.pk).update(
            issued_date=today,
            total_due=Decimal('125.00'),
        )
        Invoice.objects.filter(pk=self.invoice_b.pk).update(
            issued_date=today,
            total_due=Decimal('275.00'),
        )
        Invoice.objects.filter(pk=self.invoice_hidden.pk).update(
            issued_date=today,
            total_due=Decimal('900.00'),
        )
        Expense.objects.filter(pk=self.expense_a.pk).update(
            paid_date=today,
            amount=Decimal('15.00'),
            exclude_from_reports=False,
        )
        Expense.objects.filter(pk=self.expense_b.pk).update(
            paid_date=today,
            amount=Decimal('25.00'),
            exclude_from_reports=False,
        )
        Expense.objects.filter(pk=self.expense_hidden.pk).update(
            paid_date=today,
            amount=Decimal('500.00'),
            exclude_from_reports=False,
        )

        response = self.client.get(reverse('cross_company_dashboard'), {'date_range': 'all'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Revenue vs Expense')
        self.assertEqual(len(response.context['dashboard_chart']['months']), 24)

        current_month = next(
            month
            for month in response.context['dashboard_chart']['months']
            if month['month_start'] == current_month_start
        )
        self.assertEqual(current_month['invoiced_total'], Decimal('400.00'))
        self.assertEqual(current_month['expense_total'], Decimal('40.00'))
        self.assertEqual(current_month['combined_total'], Decimal('440.00'))
        self.assertNotContains(response, 'data-value-label=')
        self.assertNotContains(
            response,
            f'data-value-label="{current_month["combined_display"]}"',
        )

    def test_cross_company_dashboard_renders_chart_axes_month_labels_and_toggle_markup(self):
        today = timezone.localdate()
        current_month_start = today.replace(day=1)

        Invoice.objects.filter(pk=self.invoice_a.pk).update(
            issued_date=today,
            total_due=Decimal('125.00'),
        )
        Expense.objects.filter(pk=self.expense_a.pk).update(
            paid_date=today,
            amount=Decimal('175.00'),
            exclude_from_reports=False,
        )

        response = self.client.get(reverse('cross_company_dashboard'), {'date_range': 'all'})

        self.assertEqual(response.status_code, 200)

        dashboard_chart = response.context['dashboard_chart']
        current_month = next(
            month
            for month in dashboard_chart['months']
            if month['month_start'] == current_month_start
        )

        self.assertContains(
            response,
            '<div class="dashboard-chart__legend filter-toggle-group" role="group" aria-label="Toggle revenue and expense series">',
        )
        self.assertContains(
            response,
            'data-dashboard-chart-toggle="revenue"',
        )
        self.assertContains(
            response,
            'data-dashboard-chart-toggle="expense"',
        )
        content = response.content.decode()
        chart_legend = content.split('dashboard-chart__legend', 1)[1].split('</div>', 1)[0]
        self.assertEqual(chart_legend.count('aria-pressed="true"'), 2)
        self.assertEqual(chart_legend.count('aria-disabled="false"'), 2)
        self.assertEqual(chart_legend.count('data-dashboard-chart-toggle-locked="false"'), 2)

        for tick in dashboard_chart['y_axis_ticks']:
            self.assertContains(
                response,
                f'<span class="dashboard-chart__y-axis-label">{tick["label"]}</span>',
                html=True,
            )

        self.assertContains(
            response,
            'class="dashboard-chart__guide-line"',
            count=len(dashboard_chart['y_axis_ticks']),
        )
        self.assertContains(
            response,
            f'<span class="dashboard-chart__month-label">{current_month["month_label"]}</span>',
            html=True,
        )
        self.assertContains(
            response,
            f'<span class="dashboard-chart__x-axis-month">{current_month["month_abbrev"]}</span>',
            html=True,
        )

    def test_cross_company_dashboard_limits_kpis_to_single_users_accessible_issuer(self):
        single_issuer_user = self.create_user_with_issuers(
            [self.issuer_a],
            username='cross-company-single-issuer-user',
            email='cross-company-single-issuer@example.com',
        )
        self.client.force_login(single_issuer_user)

        response = self.client.get(reverse('cross_company_dashboard'), {'date_range': 'all'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['paid_total'], Decimal('100'))
        self.assertEqual(response.context['expense_total'], Decimal('10'))
        self.assertEqual(
            [issuer.pk for issuer in response.context['cross_company_issuers']],
            [self.issuer_a.pk],
        )

    def test_cross_company_dashboard_expense_total_respects_selected_date_range(self):
        today = timezone.localdate()
        Expense.objects.filter(pk=self.expense_a.pk).update(paid_date=today, amount=Decimal('15.00'))
        Expense.objects.filter(pk=self.expense_b.pk).update(
            paid_date=today - timedelta(days=45),
            amount=Decimal('25.00'),
        )
        Expense.objects.filter(pk=self.expense_hidden.pk).update(
            paid_date=today,
            amount=Decimal('50.00'),
        )

        response = self.client.get(reverse('cross_company_dashboard'), {'date_range': 'this_month'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['expense_total'], Decimal('15'))

    def test_cross_company_recent_invoices_are_ordered_by_issued_date_then_number_or_id(self):
        shared_date = date(2024, 2, 20)
        Invoice.objects.filter(pk=self.invoice_a.pk).update(issued_date=shared_date, number=10)
        Invoice.objects.filter(pk=self.invoice_b.pk).update(issued_date=shared_date, number=20)
        Invoice.objects.filter(pk=self.invoice_hidden.pk).update(issued_date=date(2024, 2, 21), number=99)
        older_unnumbered_invoice = Invoice.objects.create(
            issuer=self.issuer_a,
            customer=self.customer_a,
            project=self.project_a,
            issued_date=shared_date,
            status=Invoice.STATUS_INVOICED,
            total_due=Decimal('150.00'),
        )
        newer_unnumbered_invoice = Invoice.objects.create(
            issuer=self.issuer_a,
            customer=self.customer_a,
            project=self.project_a,
            issued_date=shared_date,
            status=Invoice.STATUS_INVOICED,
            total_due=Decimal('175.00'),
        )
        Invoice.objects.filter(pk__in=[older_unnumbered_invoice.pk, newer_unnumbered_invoice.pk]).update(number=None)

        request = self.factory.get('/dashboard/cross-company/')
        request.user = self.user
        request.session = self.client.session
        scope = _build_cross_company_dashboard_scope(request)

        recent_invoices = _build_cross_company_recent_invoices(scope['invoice_queryset'])

        self.assertEqual(
            [invoice.pk for invoice in recent_invoices],
            [self.invoice_b.pk, self.invoice_a.pk, newer_unnumbered_invoice.pk, older_unnumbered_invoice.pk],
        )

    def test_cross_company_recent_invoices_include_company_metadata(self):
        response = self.client.get(reverse('cross_company_dashboard'), {'date_range': 'all'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [invoice.company_name for invoice in response.context['recent_invoices']],
            ['Issuer B', 'Issuer A'],
        )
        self.assertEqual(
            [invoice.company.name for invoice in response.context['recent_invoices']],
            ['Issuer B', 'Issuer A'],
        )

    def test_cross_company_recent_invoice_helper_attaches_company_metadata_in_sorted_results(self):
        request = self.factory.get('/dashboard/cross-company/')
        request.user = self.user
        request.session = self.client.session
        scope = _build_cross_company_dashboard_scope(request)

        recent_invoices = _build_cross_company_recent_invoices(scope['invoice_queryset'])

        self.assertEqual(
            [(invoice.pk, invoice.company_name, invoice.company.name) for invoice in recent_invoices],
            [
                (self.invoice_b.pk, 'Issuer B', 'Issuer B'),
                (self.invoice_a.pk, 'Issuer A', 'Issuer A'),
            ],
        )

    def test_cross_company_recent_payments_are_ordered_by_received_at_then_id(self):
        shared_date = date(2024, 2, 20)
        Payment.objects.filter(pk__in=[self.payment_a.pk, self.payment_b.pk]).update(received_at=shared_date)
        Payment.objects.filter(pk=self.payment_hidden.pk).update(received_at=date(2024, 2, 21))
        earlier_payment = Payment.objects.create(
            issuer=self.issuer_a,
            customer=self.customer_a,
            project=self.project_a,
            amount=Decimal('150.00'),
            base_currency_amount=Decimal('150.00'),
            received_at=shared_date,
        )
        later_payment = Payment.objects.create(
            issuer=self.issuer_a,
            customer=self.customer_a,
            project=self.project_a,
            amount=Decimal('175.00'),
            base_currency_amount=Decimal('175.00'),
            received_at=shared_date,
        )

        request = self.factory.get('/dashboard/cross-company/')
        request.user = self.user
        request.session = self.client.session
        scope = _build_cross_company_dashboard_scope(request)

        recent_payments = _build_cross_company_recent_payments(scope['payment_queryset'])

        self.assertEqual(
            [payment.pk for payment in recent_payments],
            [later_payment.pk, earlier_payment.pk, self.payment_b.pk, self.payment_a.pk],
        )

    def test_cross_company_recent_payments_include_company_metadata(self):
        response = self.client.get(reverse('cross_company_dashboard'), {'date_range': 'all'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [payment.company_name for payment in response.context['recent_payments']],
            ['Issuer B', 'Issuer A'],
        )
        self.assertEqual(
            [payment.company.name for payment in response.context['recent_payments']],
            ['Issuer B', 'Issuer A'],
        )

    def test_cross_company_dashboard_renders_recent_invoices_table_without_project_column(self):
        response = self.client.get(reverse('cross_company_dashboard'), {'date_range': 'all'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-testid="dashboard-recent-invoices"', html=False)

        content = response.content.decode()
        invoices_table = content.split('data-testid="dashboard-recent-invoices"', 1)[1].split('</table>', 1)[0]

        expected_headers = [
            '<th>#</th>',
            '<th>Company</th>',
            '<th>Date</th>',
            '<th>Status</th>',
            '<th>Client</th>',
            '<th class="text-end">Total</th>',
        ]

        header_positions = [invoices_table.index(header) for header in expected_headers]

        self.assertEqual(invoices_table.count('</th>'), len(expected_headers))
        self.assertEqual(header_positions, sorted(header_positions))
        self.assertNotIn('<th>Project</th>', invoices_table)
        self.assertIn('<td>Issuer B</td>', invoices_table)
        self.assertIn('<td>Issuer A</td>', invoices_table)

    def test_cross_company_dashboard_recent_invoices_empty_state_uses_reduced_colspan(self):
        Invoice.objects.all().delete()

        response = self.client.get(reverse('cross_company_dashboard'), {'date_range': 'all'})

        self.assertEqual(response.status_code, 200)

        content = response.content.decode()
        invoices_table = content.split('data-testid="dashboard-recent-invoices"', 1)[1].split('</table>', 1)[0]

        self.assertIn('<td colspan="6" class="text-center text-muted">No invoices yet</td>', invoices_table)

    def test_cross_company_dashboard_renders_invoice_filter_and_shared_limit_controls(self):
        response = self.client.get(
            reverse('cross_company_dashboard'),
            {
                'date_range': 'this_month',
                'invoice_status': Invoice.STATUS_PAID,
                'max_results': '50',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-testid="dashboard-invoice-status-filter"', html=False)
        self.assertContains(response, 'data-testid="dashboard-invoices-max-results"', html=False)
        self.assertContains(response, 'data-testid="dashboard-payments-max-results"', html=False)

        content = response.content.decode()
        self.assertIn('name="invoice_status" value="paid" class="filter-toggle is-active"', content)
        self.assertIn('aria-pressed="true" aria-current="true"', content)
        self.assertEqual(content.count('name="max_results"'), 4)
        self.assertEqual(content.count('<option value="50" selected>50</option>'), 2)
        self.assertIn('<input type="hidden" name="date_range" value="this_month" />', content)
        self.assertIn('<input type="hidden" name="invoice_status" value="paid" />', content)
        self.assertIn('<input type="hidden" name="max_results" value="50" />', content)

    def test_cross_company_dashboard_renders_recent_payments_table_without_project_column(self):
        response = self.client.get(reverse('cross_company_dashboard'), {'date_range': 'all'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-testid="dashboard-recent-payments"', html=False)

        content = response.content.decode()
        payments_table = content.split('data-testid="dashboard-recent-payments"', 1)[1].split('</table>', 1)[0]

        expected_headers = [
            '<th>Date</th>',
            '<th>Company</th>',
            '<th>Invoice</th>',
            '<th>Client</th>',
            '<th class="text-end">Amount</th>',
        ]

        header_positions = [payments_table.index(header) for header in expected_headers]

        self.assertEqual(payments_table.count('</th>'), len(expected_headers))
        self.assertEqual(header_positions, sorted(header_positions))
        self.assertNotIn('<th>Project</th>', payments_table)
        self.assertContains(response, '15/01/2024')
        self.assertContains(response, '16/01/2024')
        self.assertContains(response, '100.00 €')
        self.assertContains(response, '200.00 €')

    def test_cross_company_dashboard_recent_payments_empty_state_uses_reduced_colspan(self):
        Payment.objects.all().delete()

        response = self.client.get(reverse('cross_company_dashboard'), {'date_range': 'all'})

        self.assertEqual(response.status_code, 200)

        content = response.content.decode()
        payments_table = content.split('data-testid="dashboard-recent-payments"', 1)[1].split('</table>', 1)[0]

        self.assertIn('<td colspan="5" class="text-center text-muted">No payments yet</td>', payments_table)

    def test_cross_company_recent_payment_helper_attaches_company_metadata_in_sorted_results(self):
        request = self.factory.get('/dashboard/cross-company/')
        request.user = self.user
        request.session = self.client.session
        scope = _build_cross_company_dashboard_scope(request)

        recent_payments = _build_cross_company_recent_payments(scope['payment_queryset'])

        self.assertEqual(
            [(payment.pk, payment.company_name, payment.company.name) for payment in recent_payments],
            [
                (self.payment_b.pk, 'Issuer B', 'Issuer B'),
                (self.payment_a.pk, 'Issuer A', 'Issuer A'),
            ],
        )


class InvoicePreviewPaymentsTests(AuthenticatedCompanyTestCase):
    def setUp(self):
        issuer_company = Company.objects.create(name='Issuer Co', customer_information_file_number='VATISS')
        self.issuer = Issuer.objects.create(company=issuer_company)

        customer_company = Company.objects.create(name='Customer Co', customer_information_file_number='VATCUST')
        self.customer = Customer.objects.create(issuer=self.issuer, company=customer_company)
        self.project = Project.objects.create(customer=self.customer, title='Project', project_code='PRJ')

        self.invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=date(2024, 1, 15),
            status=Invoice.STATUS_INVOICED,
            total_due=Decimal('100'),
        )

        self.user = self.create_user_with_issuers(
            [self.issuer],
            username='payments-preview-user',
            email='pay@example.com',
        )

    def test_preview_includes_payments_table_when_applied(self):
        payment = Payment.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            amount=Decimal('50'),
            received_at=date(2024, 1, 20),
            status=Payment.STATUS_APPLIED,
        )
        application = PaymentApplication.objects.create(payment=payment, invoice=self.invoice, amount_applied=Decimal('30'))

        self.login_with_active_company(self.user, issuer=self.issuer)

        response = self.client.get(f"{reverse('invoices:edit', args=[self.invoice.id])}?tab=preview")

        self.assertEqual(response.status_code, 200)
        self.assertIn('invoice_payment_applications', response.context)
        self.assertEqual(len(response.context['invoice_payment_applications']), 1)
        self.assertContains(response, 'Payments')
        self.assertContains(response, 'data-payment-edit')
        self.assertContains(
            response,
            reverse('invoices:remove_payment_application', args=[self.invoice.id, application.id]),
        )
        self.assertContains(response, 'Remove from invoice')
        self.assertContains(response, "return confirm('Remove this payment from this invoice? The payment record will be kept.');")
        self.assertContains(response, f'name="project_id" value="{self.project.id}"')


class InvoicePaymentApplicationRemovalTests(AuthenticatedCompanyTestCase):
    def setUp(self):
        self.issuer = Issuer.objects.create(
            company=Company.objects.create(name='Issuer Co', customer_information_file_number='VATISS')
        )
        self.customer = Customer.objects.create(
            issuer=self.issuer,
            company=Company.objects.create(name='Customer Co', customer_information_file_number='VATCUST'),
        )
        self.project = Project.objects.create(customer=self.customer, title='Project', project_code='PRJ')
        self.invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=date(2024, 1, 15),
            due_date=date.today() + timedelta(days=30),
            status=Invoice.STATUS_PAID,
            total_due=Decimal('100.00'),
            amount_paid=Decimal('100.00'),
            amount_due=Decimal('0.00'),
            last_payment_date=date(2024, 1, 20),
        )
        self.payment = Payment.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            amount=Decimal('100.00'),
            received_at=date(2024, 1, 20),
            status=Payment.STATUS_APPLIED,
        )
        self.application = PaymentApplication.objects.create(
            payment=self.payment,
            invoice=self.invoice,
            amount_applied=Decimal('100.00'),
        )
        self.user = self.create_user_with_issuers(
            [self.issuer],
            username='payment-application-removal-user',
            email='payment-removal@example.com',
        )
        self.login_with_active_company(self.user, issuer=self.issuer)

    def removal_url(self, invoice=None, application=None):
        return reverse(
            'invoices:remove_payment_application',
            args=[(invoice or self.invoice).id, (application or self.application).id],
        )

    def test_removes_selected_application_and_preserves_payment(self):
        with patch('invoices.views.save_invoice_pdf', return_value=True) as mocked_pdf, patch(
            'invoices.views.invalidate_dashboard_cache'
        ) as mocked_cache:
            response = self.client.post(
                self.removal_url(),
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'ok': True})
        self.assertFalse(PaymentApplication.objects.filter(pk=self.application.pk).exists())
        self.assertTrue(Payment.objects.filter(pk=self.payment.pk).exists())
        mocked_cache.assert_called_once_with(self.issuer.pk)
        mocked_pdf.assert_called_once_with(response.wsgi_request, self.invoice.id)

        self.payment.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_PENDING)
        self.assertEqual(self.invoice.amount_paid, Decimal('0.00'))
        self.assertEqual(self.invoice.amount_due, Decimal('100.00'))
        self.assertIsNone(self.invoice.last_payment_date)
        self.assertEqual(self.invoice.status, Invoice.STATUS_INVOICED)

    def test_wrong_issuer_application_is_rejected(self):
        other_issuer = Issuer.objects.create(
            company=Company.objects.create(name='Other Issuer', customer_information_file_number='VATOTH')
        )
        other_customer = Customer.objects.create(
            issuer=other_issuer,
            company=Company.objects.create(name='Other Customer', customer_information_file_number='VATOC'),
        )
        other_project = Project.objects.create(customer=other_customer, title='Other Project', project_code='OPRJ')
        other_invoice = Invoice.objects.create(
            issuer=other_issuer,
            customer=other_customer,
            project=other_project,
            total_due=Decimal('50.00'),
        )
        other_payment = Payment.objects.create(
            issuer=other_issuer,
            customer=other_customer,
            project=other_project,
            amount=Decimal('50.00'),
            received_at=date(2024, 1, 21),
            status=Payment.STATUS_APPLIED,
        )
        other_application = PaymentApplication.objects.create(
            payment=other_payment,
            invoice=other_invoice,
            amount_applied=Decimal('50.00'),
        )

        with patch('invoices.views.save_invoice_pdf') as mocked_pdf:
            response = self.client.post(self.removal_url(application=other_application))

        self.assertEqual(response.status_code, 404)
        self.assertTrue(PaymentApplication.objects.filter(pk=other_application.pk).exists())
        mocked_pdf.assert_not_called()

    def test_requires_post_and_does_not_mutate_on_get(self):
        response = self.client.get(self.removal_url())

        self.assertEqual(response.status_code, 405)
        self.assertTrue(PaymentApplication.objects.filter(pk=self.application.pk).exists())
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_APPLIED)

    def test_single_application_marks_payment_pending(self):
        with patch('invoices.views.save_invoice_pdf', return_value=True):
            self.client.post(self.removal_url())

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_PENDING)
        self.assertEqual(self.payment.applications.count(), 0)

    def test_multi_application_keeps_other_applications_and_payment_applied(self):
        second_invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=date(2024, 1, 16),
            status=Invoice.STATUS_PAID,
            total_due=Decimal('40.00'),
            amount_paid=Decimal('40.00'),
            amount_due=Decimal('0.00'),
            last_payment_date=date(2024, 1, 20),
        )
        second_application = PaymentApplication.objects.create(
            payment=self.payment,
            invoice=second_invoice,
            amount_applied=Decimal('40.00'),
        )

        with patch('invoices.views.save_invoice_pdf', return_value=True) as mocked_pdf:
            response = self.client.post(self.removal_url())

        self.assertEqual(response.status_code, 302)
        self.assertFalse(PaymentApplication.objects.filter(pk=self.application.pk).exists())
        self.assertTrue(PaymentApplication.objects.filter(pk=second_application.pk).exists())
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_APPLIED)
        second_invoice.refresh_from_db()
        self.assertEqual(second_invoice.amount_paid, Decimal('40.00'))
        mocked_pdf.assert_called_once_with(response.wsgi_request, self.invoice.id)


class InvoiceListOverdueAmountDisplayTests(AuthenticatedCompanyTestCase):
    def setUp(self):
        issuer_company = Company.objects.create(name='Issuer Co', customer_information_file_number='VATISS')
        self.issuer = Issuer.objects.create(company=issuer_company)

        client_company = Company.objects.create(name='Client', customer_information_file_number='VATC')
        self.customer = Customer.objects.create(issuer=self.issuer, company=client_company)
        self.project = Project.objects.create(customer=self.customer, title='Project', project_code='PRJ')

        self.invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=date(2024, 9, 30),
            due_date=date.today() - timedelta(days=1),
            status=Invoice.STATUS_OVERDUE,
            total_due=Decimal('2675'),
            amount_due=Decimal('500'),
            amount_overdue=Decimal('500'),
        )

        self.user = self.create_user_with_issuers(
            [self.issuer],
            username='overdue-list-user',
            email='overdue@example.com',
        )

    def test_overdue_invoices_show_due_amount_in_parentheses(self):
        self.login_with_active_company(self.user, issuer=self.issuer)

        response = self.client.get(f"{reverse('invoices:list')}?status=overdue&date_range=all")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'account-table__amount-note--danger')
        self.assertContains(response, '(500.00 €)')


class InvoiceListRowActionTests(AuthenticatedCompanyTestCase):
    def setUp(self):
        issuer_company = Company.objects.create(name='Issuer Co', customer_information_file_number='VATISS')
        self.issuer = Issuer.objects.create(company=issuer_company)

        client_company = Company.objects.create(name='Client', customer_information_file_number='VATC')
        self.customer = Customer.objects.create(issuer=self.issuer, company=client_company)
        self.project = Project.objects.create(customer=self.customer, title='Project', project_code='PRJ')

        self.invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=date(2024, 9, 30),
            status=Invoice.STATUS_DRAFT,
            total_due=Decimal('2675'),
        )

        self.user = self.create_user_with_issuers(
            [self.issuer],
            username='invoice-list-row-user',
            email='invoice-list-row@example.com',
        )

    def test_invoice_list_row_number_cell_does_not_render_open_button(self):
        self.login_with_active_company(self.user, issuer=self.issuer)

        response = self.client.get(f"{reverse('invoices:list')}?status=all&date_range=all")

        self.assertEqual(response.status_code, 200)
        number_cell = response.context['invoice_rows'][0]['cells'][1]['content']
        self.assertNotIn('Open', number_cell)
        self.assertNotIn('data-invoice-drawer', number_cell)
        self.assertNotContains(response, '>Open<', html=False)

    def test_invoice_list_row_number_cell_links_to_invoice_edit_route(self):
        self.login_with_active_company(self.user, issuer=self.issuer)

        response = self.client.get(f"{reverse('invoices:list')}?status=all&date_range=all")

        self.assertEqual(response.status_code, 200)
        number_cell = response.context['invoice_rows'][0]['cells'][1]['content']
        invoice_url = reverse('invoices:edit', args=[self.invoice.id])
        invoice_label = self.invoice.sequence_number

        self.assertIn(f'href="{invoice_url}"', number_cell)
        self.assertIn(f'>{invoice_label}<', number_cell)
        self.assertContains(
            response,
            f'<a href="{invoice_url}" class="link-primary">{invoice_label}</a>',
            html=True,
        )


class InvoiceListCombinedStatusFilterTests(AuthenticatedCompanyTestCase):
    def setUp(self):
        issuer_company = Company.objects.create(name='Issuer Co', customer_information_file_number='VATISS')
        self.issuer = Issuer.objects.create(company=issuer_company)

        client_company = Company.objects.create(name='Client', customer_information_file_number='VATC')
        self.customer = Customer.objects.create(issuer=self.issuer, company=client_company)
        self.project = Project.objects.create(customer=self.customer, title='Project', project_code='PRJ')
        self.today = timezone.localdate()

        self.invoice_invoiced = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=self.today - timedelta(days=5),
            due_date=self.today + timedelta(days=5),
            status=Invoice.STATUS_INVOICED,
            total_due=Decimal('100'),
            amount_due=Decimal('100'),
        )
        self.invoice_past_due = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=self.today - timedelta(days=10),
            due_date=self.today - timedelta(days=1),
            status=Invoice.STATUS_INVOICED,
            total_due=Decimal('200'),
            amount_due=Decimal('50'),
        )
        self.invoice_not_overdue = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=self.today - timedelta(days=12),
            due_date=self.today + timedelta(days=2),
            status=Invoice.STATUS_OVERDUE,
            total_due=Decimal('150'),
            amount_due=Decimal('150'),
            amount_overdue=Decimal('150'),
        )
        self.invoice_becomes_overdue = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=self.today - timedelta(days=7),
            due_date=self.today,
            status=Invoice.STATUS_INVOICED,
            total_due=Decimal('125'),
            amount_due=Decimal('125'),
        )
        Invoice.objects.filter(pk=self.invoice_becomes_overdue.pk).update(updated_at=timezone.now() - timedelta(days=1))
        Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=date(2024, 6, 1),
            status=Invoice.STATUS_PAID,
            total_due=Decimal('300'),
            amount_due=Decimal('0'),
        )
        Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=date(2024, 5, 1),
            status=Invoice.STATUS_DRAFT,
            total_due=Decimal('400'),
            amount_due=Decimal('0'),
        )

        self.user = self.create_user_with_issuers(
            [self.issuer],
            username='combined-status-user',
            email='combo@example.com',
        )

    def test_invoiced_and_overdue_filter_returns_both(self):
        self.login_with_active_company(self.user, issuer=self.issuer)

        response = self.client.get(f"{reverse('invoices:list')}?status=invoiced,overdue&date_range=all")

        self.assertEqual(response.status_code, 200)
        invoices_page = response.context['invoices_list']
        self.assertEqual(invoices_page.paginator.count, 3)
        invoice_ids = {inv.id for inv in invoices_page}
        self.assertEqual(
            invoice_ids,
            {
                self.invoice_invoiced.id,
                self.invoice_past_due.id,
                self.invoice_becomes_overdue.id,
            },
        )

        self.assertContains(response, 'Invoiced &amp; Overdue')
        self.assertContains(response, 'data-bulk-selection-summary')
        self.assertContains(response, 'data-total="100.00"')
        self.assertContains(response, 'data-unpaid="100.00"')

    def test_overdue_filter_uses_due_date_and_amount_due(self):
        self.login_with_active_company(self.user, issuer=self.issuer)

        response = self.client.get(f"{reverse('invoices:list')}?status=overdue&date_range=all")

        self.assertEqual(response.status_code, 200)
        invoices_page = response.context['invoices_list']
        self.assertEqual(invoices_page.paginator.count, 1)
        self.assertEqual({inv.id for inv in invoices_page}, {self.invoice_past_due.id})

    def test_overdue_filter_includes_invoice_after_due_date_passes_without_write(self):
        self.login_with_active_company(self.user, issuer=self.issuer)

        with patch('django.utils.timezone.localdate', return_value=self.today + timedelta(days=1)):
            response = self.client.get(f"{reverse('invoices:list')}?status=overdue&date_range=all")

        self.assertEqual(response.status_code, 200)
        invoices_page = response.context['invoices_list']
        self.assertEqual(
            {inv.id for inv in invoices_page},
            {self.invoice_past_due.id, self.invoice_becomes_overdue.id},
        )

    def test_invoice_row_becomes_overdue_after_due_date_passes_without_write(self):
        self.login_with_active_company(self.user, issuer=self.issuer)

        with patch('django.utils.timezone.localdate', return_value=self.today + timedelta(days=1)):
            response = self.client.get(f"{reverse('invoices:list')}?status=all&date_range=all")

        self.assertEqual(response.status_code, 200)

        total_cells_by_invoice_id = {
            invoice.id: row['cells'][5]['content']
            for invoice, row in zip(response.context['invoices_list'], response.context['invoice_rows'])
        }

        self.assertIn(
            'account-table__amount-note--danger',
            total_cells_by_invoice_id[self.invoice_becomes_overdue.id],
        )
        self.assertIn('(125.00 €)', total_cells_by_invoice_id[self.invoice_becomes_overdue.id])

    def test_invoice_rows_render_derived_outstanding_styling(self):
        self.login_with_active_company(self.user, issuer=self.issuer)

        response = self.client.get(f"{reverse('invoices:list')}?status=all&date_range=all")

        self.assertEqual(response.status_code, 200)

        total_cells_by_invoice_id = {
            invoice.id: row['cells'][5]['content']
            for invoice, row in zip(response.context['invoices_list'], response.context['invoice_rows'])
        }

        self.assertIn('account-table__amount-note--danger', total_cells_by_invoice_id[self.invoice_past_due.id])
        self.assertIn('(50.00 €)', total_cells_by_invoice_id[self.invoice_past_due.id])
        self.assertIn('account-table__amount-note--current', total_cells_by_invoice_id[self.invoice_not_overdue.id])
        self.assertIn('(150.00 €)', total_cells_by_invoice_id[self.invoice_not_overdue.id])


class CrossSurfaceOverdueConsistencyTests(AuthenticatedCompanyTestCase):
    def setUp(self):
        self.today = timezone.localdate()
        previous_month_day = self.today.replace(day=1) - timedelta(days=1)
        issuer_company = Company.objects.create(name='Issuer Co', customer_information_file_number='VATISS')
        self.issuer = Issuer.objects.create(company=issuer_company)

        client_company = Company.objects.create(name='Client', customer_information_file_number='VATC')
        self.customer = Customer.objects.create(issuer=self.issuer, company=client_company)
        self.project = Project.objects.create(customer=self.customer, title='Project', project_code='PRJ')

        self.current_invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=self.today - timedelta(days=3),
            due_date=self.today + timedelta(days=5),
            status=Invoice.STATUS_OVERDUE,
            total_due=Decimal('100'),
            amount_due=Decimal('100'),
            amount_overdue=Decimal('100'),
        )
        self.overdue_invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=previous_month_day,
            due_date=self.today - timedelta(days=1),
            status=Invoice.STATUS_INVOICED,
            total_due=Decimal('50'),
            amount_due=Decimal('50'),
            amount_overdue=Decimal('0'),
        )

        self.user = self.create_user_with_issuers(
            [self.issuer],
            username='cross-surface-user',
            email='cross@example.com',
        )

    def _activate_company(self):
        self.login_with_active_company(self.user, issuer=self.issuer)

    @staticmethod
    def _total_cells(response):
        return {
            invoice.id: row['cells'][5]['content']
            for invoice, row in zip(response.context['invoices_list'], response.context['invoice_rows'])
        }

    @staticmethod
    def _account_rows_by_invoice_id(response):
        rows = {}
        for row in response.context['account_rows']:
            if row.get('type') != 'invoice' or not row.get('url'):
                continue
            invoice_id = int(row['url'].rstrip('/').split('/')[-1])
            rows[invoice_id] = row
        return rows

    def test_invoice_list_customer_detail_and_project_detail_stay_aligned(self):
        self._activate_company()

        invoices_response = self.client.get(f"{reverse('invoices:list')}?status=all&date_range=all")
        customer_response = self.client.get(reverse('customers:detail', args=[self.customer.id]))
        project_response = self.client.get(reverse('projects:detail', args=[self.project.id]))

        self.assertEqual(invoices_response.status_code, 200)
        self.assertEqual(customer_response.status_code, 200)
        self.assertEqual(project_response.status_code, 200)

        total_cells = self._total_cells(invoices_response)
        self.assertIn('account-table__amount-note--current', total_cells[self.current_invoice.id])
        self.assertIn('account-table__amount-note--danger', total_cells[self.overdue_invoice.id])

        customer_rows = self._account_rows_by_invoice_id(customer_response)
        self.assertFalse(customer_rows[self.current_invoice.id]['outstanding_is_overdue'])
        self.assertTrue(customer_rows[self.overdue_invoice.id]['outstanding_is_overdue'])
        self.assertEqual(customer_response.context['invoice_totals']['pending_total'], Decimal('150'))
        self.assertEqual(customer_response.context['invoice_totals']['overdue_total'], Decimal('50'))

        customer_projects = {project.pk: project for project in customer_response.context['projects']}
        self.assertEqual(customer_projects[self.project.pk].pending_total, Decimal('150'))
        self.assertEqual(customer_projects[self.project.pk].overdue_total, Decimal('50'))

        project_rows = self._account_rows_by_invoice_id(project_response)
        self.assertFalse(project_rows[self.current_invoice.id]['outstanding_is_overdue'])
        self.assertTrue(project_rows[self.overdue_invoice.id]['outstanding_is_overdue'])
        self.assertEqual(project_response.context['pending_balance'], Decimal('150'))
        self.assertEqual(project_response.context['overdue_total'], Decimal('50'))

    def test_dashboard_does_not_render_total_spending_kpi(self):
        self._activate_company()
        Expense.objects.create(
            issuer=self.issuer,
            paid_date=self.today,
            amount=Decimal('75.50'),
            description='Software subscription',
        )

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Total spending')
        self.assertContains(response, 'class="kpi-card"', count=4)
        self.assertNotIn('total_spending', response.context)

        cached = cache.get(f"dashboard:v2:{self.issuer.pk}:{response.context['selected_period']}")
        self.assertIsNotNone(cached)
        self.assertNotIn('total_spending', cached)

    def test_dashboard_routes_keep_per_company_template_behavior(self):
        self._activate_company()

        root_response = self.client.get(reverse('dashboard'), {'date_range': 'all'})
        alias_response = self.client.get('/dashboard/', {'date_range': 'all'})

        self.assertEqual(root_response.status_code, 200)
        self.assertEqual(alias_response.status_code, 200)
        self.assertTemplateUsed(root_response, 'invoices/dashboard.html')
        self.assertTemplateUsed(alias_response, 'invoices/dashboard.html')
        self.assertNotIn('is_cross_company_dashboard', root_response.context)
        self.assertNotIn('is_cross_company_dashboard', alias_response.context)
        self.assertContains(root_response, '<h2>Top Pending Invoices</h2>', html=True)
        self.assertContains(alias_response, '<h2>Top Pending Invoices</h2>', html=True)
        self.assertContains(root_response, '<h2>Overdue Invoices</h2>', html=True)
        self.assertContains(alias_response, '<h2>Overdue Invoices</h2>', html=True)
        self.assertContains(root_response, '<h2>Invoiced All time</h2>', html=True)
        self.assertContains(alias_response, '<h2>Invoiced All time</h2>', html=True)
        self.assertEqual(root_response.context['paid_total'], alias_response.context['paid_total'])
        self.assertEqual(root_response.context['pending_total'], alias_response.context['pending_total'])
        self.assertEqual(root_response.context['overdue_total'], alias_response.context['overdue_total'])

    def test_dashboard_aggregates_monthly_expenses_for_active_issuer(self):
        self._activate_company()
        other_company = Company.objects.create(name='Other Issuer Co', customer_information_file_number='VATOTHER')
        other_issuer = Issuer.objects.create(company=other_company)

        Expense.objects.create(
            issuer=self.issuer,
            paid_date=self.today,
            amount=Decimal('75.50'),
            description='Active issuer expense',
        )
        Expense.objects.create(
            issuer=other_issuer,
            paid_date=self.today,
            amount=Decimal('30.00'),
            description='Other issuer expense',
        )

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['dashboard_chart']['months']), 24)
        self.assertEqual(response.context['dashboard_chart']['months'][-1]['invoiced_total'], Decimal('100'))
        self.assertEqual(response.context['dashboard_chart']['months'][-1]['expense_total'], Decimal('75.50'))
        self.assertEqual(response.context['dashboard_chart']['months'][-1]['combined_total'], Decimal('175.50'))

        cached = cache.get(f"dashboard:v2:{self.issuer.pk}:{response.context['selected_period']}")
        self.assertIsNotNone(cached)
        self.assertEqual(cached['context']['dashboard_chart']['months'][-1]['invoiced_total'], Decimal('100'))
        self.assertEqual(cached['context']['dashboard_chart']['months'][-1]['expense_total'], Decimal('75.50'))
        self.assertEqual(cached['context']['dashboard_chart']['months'][-1]['combined_total'], Decimal('175.50'))
        self.assertEqual(cached['dashboard_chart']['months'][-1]['invoiced_total'], Decimal('100'))
        self.assertEqual(cached['dashboard_chart']['months'][-1]['expense_total'], Decimal('75.50'))
        self.assertEqual(cached['dashboard_chart']['months'][-1]['combined_total'], Decimal('175.50'))

    def test_dashboard_chart_uses_invoiced_and_reportable_expenses_for_same_month(self):
        self._activate_company()

        current_month_start = self.today.replace(day=1)

        Expense.objects.create(
            issuer=self.issuer,
            paid_date=self.today,
            amount=Decimal('75.50'),
            description='Included expense',
        )
        Expense.objects.create(
            issuer=self.issuer,
            paid_date=self.today,
            amount=Decimal('125.00'),
            description='Excluded expense',
            exclude_from_reports=True,
        )

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        current_month = next(
            month
            for month in response.context['dashboard_chart']['months']
            if month['month_start'] == current_month_start
        )
        self.assertEqual(current_month['invoiced_total'], Decimal('100'))
        self.assertEqual(current_month['expense_total'], Decimal('75.50'))
        self.assertEqual(current_month['combined_total'], Decimal('175.50'))

        cached = cache.get(f"dashboard:v2:{self.issuer.pk}:{response.context['selected_period']}")
        self.assertIsNotNone(cached)
        cached_current_month = next(
            month
            for month in cached['dashboard_chart']['months']
            if month['month_start'] == current_month_start
        )
        self.assertEqual(cached_current_month['invoiced_total'], Decimal('100'))
        self.assertEqual(cached_current_month['expense_total'], Decimal('75.50'))
        self.assertEqual(cached_current_month['combined_total'], Decimal('175.50'))

    def test_dashboard_chart_renders_uncapped_expense_size_on_shared_scale(self):
        self._activate_company()

        current_month_start = self.today.replace(day=1)

        Expense.objects.create(
            issuer=self.issuer,
            paid_date=self.today,
            amount=Decimal('175.00'),
            description='Large included expense',
        )

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        current_month = next(
            month
            for month in response.context['dashboard_chart']['months']
            if month['month_start'] == current_month_start
        )
        self.assertEqual(current_month['invoiced_total'], Decimal('100'))
        self.assertEqual(current_month['expense_total'], Decimal('175.00'))
        self.assertEqual(current_month['combined_total'], Decimal('275.00'))

        cached = cache.get(f"dashboard:v2:{self.issuer.pk}:{response.context['selected_period']}")
        self.assertIsNotNone(cached)
        cached_current_month = next(
            month
            for month in cached['dashboard_chart']['months']
            if month['month_start'] == current_month_start
        )
        self.assertEqual(cached_current_month['invoiced_total'], Decimal('100'))
        self.assertEqual(cached_current_month['expense_total'], Decimal('175.00'))
        self.assertEqual(cached_current_month['combined_total'], Decimal('275.00'))
        self.assertContains(
            response,
            'style="--revenue-size: calc(500 / 1000); --expense-size: calc(875 / 1000);"',
        )
        self.assertContains(
            response,
            (
                f'aria-label="{current_month["month_label"]} invoiced '
                f'{current_month["invoiced_display"]}, expenses {current_month["expense_display"]}"'
            ),
        )

    def test_dashboard_chart_max_total_uses_shared_uncapped_series_maximum(self):
        self._activate_company()

        Expense.objects.create(
            issuer=self.issuer,
            paid_date=self.today,
            amount=Decimal('175.00'),
            description='Large included expense',
        )

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['dashboard_chart']['max_total'], Decimal('175.00'))

        cached = cache.get(f"dashboard:v2:{self.issuer.pk}:{response.context['selected_period']}")
        self.assertIsNotNone(cached)
        self.assertEqual(cached['dashboard_chart']['max_total'], Decimal('175.00'))

    def test_dashboard_chart_exposes_shared_axis_tick_metadata_for_labels_and_guides(self):
        self._activate_company()

        Expense.objects.create(
            issuer=self.issuer,
            paid_date=self.today,
            amount=Decimal('175.00'),
            description='Large included expense',
        )

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        dashboard_chart = response.context['dashboard_chart']
        self.assertEqual(dashboard_chart['axis_max'], Decimal('200'))
        self.assertEqual(
            dashboard_chart['y_axis_ticks'],
            [
                {'value': Decimal('200'), 'label': '€200', 'ratio': 1.0},
                {'value': Decimal('150'), 'label': '€150', 'ratio': 0.75},
                {'value': Decimal('100'), 'label': '€100', 'ratio': 0.5},
                {'value': Decimal('50'), 'label': '€50', 'ratio': 0.25},
                {'value': Decimal('0'), 'label': '€0', 'ratio': 0.0},
            ],
        )

        cached = cache.get(f"dashboard:v2:{self.issuer.pk}:{response.context['selected_period']}")
        self.assertIsNotNone(cached)
        self.assertEqual(cached['dashboard_chart']['axis_max'], Decimal('200'))
        self.assertEqual(cached['dashboard_chart']['y_axis_ticks'], dashboard_chart['y_axis_ticks'])

    def test_dashboard_chart_compacts_large_axis_tick_labels(self):
        self._activate_company()

        Expense.objects.create(
            issuer=self.issuer,
            paid_date=self.today,
            amount=Decimal('61000.00'),
            description='Large included expense',
        )

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context['dashboard_chart']['y_axis_ticks'],
            [
                {'value': Decimal('80000'), 'label': '€80K', 'ratio': 1.0},
                {'value': Decimal('60000'), 'label': '€60K', 'ratio': 0.75},
                {'value': Decimal('40000'), 'label': '€40K', 'ratio': 0.5},
                {'value': Decimal('20000'), 'label': '€20K', 'ratio': 0.25},
                {'value': Decimal('0'), 'label': '€0', 'ratio': 0.0},
            ],
        )

    def test_dashboard_chart_exposes_monthly_totals_and_accessible_text(self):
        self._activate_company()

        current_month_start = self.today.replace(day=1)
        prior_month_end = current_month_start - timedelta(days=1)
        last_month_start = prior_month_end.replace(day=1)
        two_months_ago_start = (last_month_start - timedelta(days=1)).replace(day=1)
        three_months_ago_start = (two_months_ago_start - timedelta(days=1)).replace(day=1)

        Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=two_months_ago_start + timedelta(days=2),
            due_date=two_months_ago_start + timedelta(days=16),
            status=Invoice.STATUS_INVOICED,
            total_due=Decimal('50.00'),
            amount_due=Decimal('50.00'),
            amount_overdue=Decimal('0.00'),
        )
        Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=three_months_ago_start + timedelta(days=4),
            due_date=three_months_ago_start + timedelta(days=18),
            status=Invoice.STATUS_INVOICED,
            total_due=Decimal('80.00'),
            amount_due=Decimal('80.00'),
            amount_overdue=Decimal('0.00'),
        )
        Expense.objects.create(
            issuer=self.issuer,
            paid_date=two_months_ago_start + timedelta(days=3),
            amount=Decimal('10.00'),
            description='Two months ago expense',
        )
        Expense.objects.create(
            issuer=self.issuer,
            paid_date=three_months_ago_start + timedelta(days=6),
            amount=Decimal('20.00'),
            description='Three months ago expense',
        )

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)

        months_by_start = {
            month['month_start']: month
            for month in response.context['dashboard_chart']['months']
        }
        two_months_ago = months_by_start[two_months_ago_start]
        three_months_ago = months_by_start[three_months_ago_start]

        self.assertEqual(two_months_ago['invoiced_total'], Decimal('50.00'))
        self.assertEqual(two_months_ago['expense_total'], Decimal('10.00'))
        self.assertEqual(two_months_ago['combined_total'], Decimal('60.00'))
        self.assertEqual(two_months_ago['revenue_display'], '50.00 €')
        self.assertEqual(two_months_ago['expense_display'], '10.00 €')
        self.assertEqual(two_months_ago['combined_display'], '60.00 €')

        self.assertEqual(three_months_ago['invoiced_total'], Decimal('80.00'))
        self.assertEqual(three_months_ago['expense_total'], Decimal('20.00'))
        self.assertEqual(three_months_ago['combined_total'], Decimal('100.00'))
        self.assertEqual(three_months_ago['revenue_display'], '80.00 €')
        self.assertEqual(three_months_ago['expense_display'], '20.00 €')
        self.assertEqual(three_months_ago['combined_display'], '100.00 €')

        for month in (three_months_ago, two_months_ago):
            self.assertContains(
                response,
                (
                    f'<span class="dashboard-chart__month-label">{month["month_label"]}</span>'
                    f'<span class="visually-hidden">: Invoiced {month["invoiced_display"]}, '
                    f'Expenses {month["expense_display"]}</span>'
                ),
                html=True,
            )
            self.assertContains(
                response,
                (
                    f'aria-label="{month["month_label"]} invoiced '
                    f'{month["invoiced_display"]}, expenses {month["expense_display"]}"'
                ),
            )
            self.assertIn('month_abbrev', month)
            self.assertIn('month_year_marker', month)

    def test_dashboard_cache_refreshes_after_expense_change(self):
        self._activate_company()

        expense = Expense.objects.create(
            issuer=self.issuer,
            paid_date=self.today,
            amount=Decimal('25.00'),
            description='Cached expense',
        )

        initial_response = self.client.get(reverse('dashboard'))

        self.assertEqual(initial_response.status_code, 200)
        self.assertEqual(initial_response.context['dashboard_chart']['months'][-1]['expense_total'], Decimal('25.00'))
        self.assertEqual(initial_response.context['dashboard_chart']['months'][-1]['combined_total'], Decimal('125.00'))

        initial_cached = cache.get(f"dashboard:v2:{self.issuer.pk}:{initial_response.context['selected_period']}")
        self.assertIsNotNone(initial_cached)
        self.assertEqual(initial_cached['dashboard_chart']['months'][-1]['expense_total'], Decimal('25.00'))

        expense.amount = Decimal('75.50')
        expense.save()

        refreshed_response = self.client.get(reverse('dashboard'))

        self.assertEqual(refreshed_response.status_code, 200)
        self.assertEqual(refreshed_response.context['dashboard_chart']['months'][-1]['expense_total'], Decimal('75.50'))
        self.assertEqual(refreshed_response.context['dashboard_chart']['months'][-1]['combined_total'], Decimal('175.50'))

        cached = cache.get(f"dashboard:v2:{self.issuer.pk}:{refreshed_response.context['selected_period']}")
        self.assertIsNotNone(cached)
        self.assertEqual(cached['dashboard_chart']['months'][-1]['expense_total'], Decimal('75.50'))

    def test_dashboard_chart_copy_and_legend_label_series_colors(self):
        self._activate_company()

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Revenue vs Expense')
        self.assertNotContains(
            response,
            'Monthly totals for non-draft invoices and reportable expenses, with blue bars for invoiced totals and orange expense overlays within each monthly bar.',
        )
        self.assertContains(response, 'aria-label="Toggle revenue and expense series"')
        self.assertContains(response, 'data-dashboard-chart-toggle="revenue"')
        self.assertContains(response, 'data-dashboard-chart-toggle="expense"')
        self.assertContains(
            response,
            'Revenue and expense totals for the previous twenty-four months',
        )

    def test_dashboard_chart_exposes_monthly_invoiced_and_expense_accessible_labels(self):
        self._activate_company()

        target_month_start = ((self.today.replace(day=1) - timedelta(days=40)).replace(day=1))
        Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=target_month_start + timedelta(days=4),
            due_date=target_month_start + timedelta(days=18),
            status=Invoice.STATUS_INVOICED,
            total_due=Decimal('321.00'),
            amount_due=Decimal('321.00'),
            amount_overdue=Decimal('0.00'),
        )
        Expense.objects.create(
            issuer=self.issuer,
            paid_date=target_month_start + timedelta(days=6),
            amount=Decimal('75.50'),
            description='Accessible expense',
        )

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)

        target_month = next(
            month
            for month in response.context['dashboard_chart']['months']
            if month['month_start'] == target_month_start
        )
        self.assertContains(
            response,
            (
                f'<span class="dashboard-chart__month-label">{target_month["month_label"]}</span>'
                f'<span class="visually-hidden">: Invoiced {target_month["invoiced_display"]}, '
                f'Expenses {target_month["expense_display"]}</span>'
            ),
            html=True,
        )
        self.assertContains(
            response,
            (
                f'<span class="data visually-hidden">{target_month["month_label"]}: '
                f'Invoiced {target_month["invoiced_display"]}, Expenses {target_month["expense_display"]}</span>'
            ),
            html=True,
        )

    def test_dashboard_chart_renders_updated_copy_legend_and_separate_caption_markup(self):
        self._activate_company()

        target_month_start = ((self.today.replace(day=1) - timedelta(days=40)).replace(day=1))
        Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=target_month_start + timedelta(days=4),
            due_date=target_month_start + timedelta(days=18),
            status=Invoice.STATUS_INVOICED,
            total_due=Decimal('321.00'),
            amount_due=Decimal('321.00'),
            amount_overdue=Decimal('0.00'),
        )
        Expense.objects.create(
            issuer=self.issuer,
            paid_date=target_month_start + timedelta(days=6),
            amount=Decimal('75.50'),
            description='Rendered expense',
        )

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)

        html = response.content.decode()
        target_month = next(
            month
            for month in response.context['dashboard_chart']['months']
            if month['month_start'] == target_month_start
        )
        months = response.context['dashboard_chart']['months']

        self.assertContains(response, 'Revenue vs Expense')
        self.assertContains(
            response,
            '<div class="dashboard-chart__legend filter-toggle-group" role="group" aria-label="Toggle revenue and expense series">',
        )
        self.assertContains(
            response,
            (
                '<button type="button" '
                'class="filter-toggle is-active dashboard-chart__legend-toggle '
                'dashboard-chart__legend-toggle--revenue" '
                'data-dashboard-chart-toggle="revenue" aria-pressed="true" '
                'aria-disabled="false" data-dashboard-chart-toggle-locked="false">'
                'Revenue</button>'
            ),
            html=True,
        )
        self.assertContains(
            response,
            (
                '<button type="button" '
                'class="filter-toggle is-active dashboard-chart__legend-toggle '
                'dashboard-chart__legend-toggle--expense" '
                'data-dashboard-chart-toggle="expense" aria-pressed="true" '
                'aria-disabled="false" data-dashboard-chart-toggle-locked="false">'
                'Expenses</button>'
            ),
            html=True,
        )
        self.assertContains(
            response,
            '<div class="dashboard-chart__y-axis" aria-hidden="true">',
        )
        self.assertContains(
            response,
            '<ul class="dashboard-chart__x-axis" aria-hidden="true">',
        )
        self.assertContains(
            response,
            '<span class="dashboard-chart__y-axis-label">€200</span>',
            html=True,
        )
        self.assertContains(
            response,
            '<span class="dashboard-chart__y-axis-label">€0</span>',
            html=True,
        )
        self.assertContains(
            response,
            '<table class="dashboard-chart__table">',
        )
        self.assertContains(response, '<th scope="col">Monthly totals</th>', html=True)
        self.assertContains(
            response,
            (
                f'aria-label="{target_month["month_label"]} invoiced '
                f'{target_month["invoiced_display"]}, expenses {target_month["expense_display"]}"'
            ),
        )
        self.assertNotContains(response, 'data-value-label=')
        self.assertNotContains(
            response,
            f'data-value-label="{target_month["combined_display"]}"',
        )
        self.assertContains(
            response,
            '<span class="dashboard-chart__bar-revenue" aria-hidden="true"></span>',
            count=len(months),
            html=True,
        )
        self.assertContains(
            response,
            '<span class="dashboard-chart__bar-expense" aria-hidden="true"></span>',
            count=len(months),
            html=True,
        )
        self.assertContains(
            response,
            'class="dashboard-chart__guide-line"',
            count=len(response.context['dashboard_chart']['y_axis_ticks']),
        )
        self.assertContains(
            response,
            f'<span class="dashboard-chart__x-axis-month">{target_month["month_abbrev"]}</span>',
            html=True,
        )
        self.assertContains(
            response,
            '<span class="dashboard-chart__x-axis-year">',
        )
        self.assertNotContains(response, 'charts-css column')
        self.assertContains(
            response,
            (
                '<span class="dashboard-chart__bar-caption '
                'dashboard-chart__bar-caption--revenue" aria-hidden="true">'
                f'{target_month["revenue_display"]}</span>'
            ),
            html=True,
        )
        self.assertContains(
            response,
            (
                '<span class="dashboard-chart__bar-caption '
                'dashboard-chart__bar-caption--expense" aria-hidden="true">'
                f'{target_month["expense_display"]}</span>'
            ),
            html=True,
        )
        self.assertContains(response, 'class="dashboard-chart__bar"', count=len(months))
        self.assertNotContains(response, 'multiple stacked')
        self.assertNotIn('dashboard-chart__series-label', html)

    def test_dashboard_overdue_widgets_follow_derived_overdue_rule(self):
        self._activate_company()

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['overdue_total'], Decimal('50'))
        self.assertEqual(
            list(response.context['top_overdue'].values_list('pk', flat=True)),
            [self.overdue_invoice.pk],
        )
        self.assertContains(response, '<strong class="text-danger">50.00 €</strong>', html=True)

    def test_remaining_status_labels_use_derived_overdue_state(self):
        self._activate_company()

        dashboard_response = self.client.get(reverse('dashboard'))
        edit_response = self.client.get(reverse('invoices:edit', args=[self.overdue_invoice.id]))
        customer_response = self.client.get(reverse('customers:detail', args=[self.customer.id]))
        project_response = self.client.get(reverse('projects:detail', args=[self.project.id]))

        self.assertEqual(
            {invoice.pk: invoice.display_status_label for invoice in dashboard_response.context['recent_invoices']},
            {
                self.current_invoice.pk: 'Invoiced',
                self.overdue_invoice.pk: 'Overdue',
            },
        )
        self.assertEqual(edit_response.context['invoice'].display_status_label, 'Overdue')
        self.assertEqual(edit_response.context['invoice'].display_status_badge_class, 'status-badge status-badge--overdue')
        self.assertEqual(
            {invoice.pk: invoice.display_status_label for invoice in customer_response.context['invoice_list']},
            {
                self.current_invoice.pk: 'Invoiced',
                self.overdue_invoice.pk: 'Overdue',
            },
        )
        self.assertEqual(
            {invoice.pk: invoice.display_status_label for invoice in project_response.context['invoices']},
            {
                self.current_invoice.pk: 'Invoiced',
                self.overdue_invoice.pk: 'Overdue',
            },
        )

    def test_payment_drawer_outstanding_invoices_use_derived_overdue_flag(self):
        self._activate_company()

        edit_response = self.client.get(reverse('invoices:edit', args=[self.overdue_invoice.id]))
        detail_response = self.client.get(reverse('projects:detail', args=[self.project.id]))
        outstanding_response = self.client.get(
            reverse('projects:outstanding_invoices', args=[self.project.id]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(
            {invoice.pk: invoice.is_overdue for invoice in edit_response.context['project_outstanding_invoices']},
            {
                self.current_invoice.pk: False,
                self.overdue_invoice.pk: True,
            },
        )
        self.assertEqual(
            {invoice.pk: invoice.is_overdue for invoice in detail_response.context['project_outstanding_invoices']},
            {
                self.current_invoice.pk: False,
                self.overdue_invoice.pk: True,
            },
        )
        self.assertEqual(
            {item['id']: item['is_overdue'] for item in outstanding_response.json()['items']},
            {
                self.current_invoice.pk: False,
                self.overdue_invoice.pk: True,
            },
        )


class InvoiceRecentItemsTests(AuthenticatedCompanyTestCase):
    def setUp(self):
        issuer_company = Company.objects.create(name='Issuer Co', customer_information_file_number='VATISS')
        self.issuer = Issuer.objects.create(company=issuer_company)

        client_company = Company.objects.create(name='Client', customer_information_file_number='VATC')
        self.customer = Customer.objects.create(issuer=self.issuer, company=client_company)
        self.project = Project.objects.create(customer=self.customer, title='Project', project_code='PRJ')

        self.previous_invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=date(2024, 4, 10),
            status=Invoice.STATUS_DRAFT,
        )
        OrderLine.objects.create(invoice=self.previous_invoice, description='Translation', quantity=1, unit_price=100)

        self.invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=date(2024, 5, 10),
            status=Invoice.STATUS_DRAFT,
        )
        OrderLine.objects.create(invoice=self.invoice, description='Current draft work', quantity=2, unit_price=200)

        self.user = self.create_user_with_issuers(
            [self.issuer],
            username='recent-items-user',
            email='recent@example.com',
        )
        self.login_with_active_company(self.user, issuer=self.issuer)

    def test_recent_items_in_context(self):
        response = self.client.get(reverse('invoices:edit', args=[self.invoice.id]))
        recent_items = response.context['recent_items_data']
        self.assertEqual(len(recent_items), 1)
        self.assertEqual(recent_items[0]['description'], 'Translation')

    def test_create_form_renders_recent_items_toggle_control(self):
        response = self.client.get(f"{reverse('invoices:add')}?project={self.project.id}")

        self.assertContains(response, 'data-recent-items-component', html=False)
        self.assertContains(response, f'data-selected-project="{self.project.id}"', html=False)
        self.assertContains(response, 'data-recent-items-toggle', html=False)
        self.assertContains(response, 'type="button"', html=False)
        self.assertContains(response, 'aria-controls="invoice-recent-items-panel"', html=False)
        self.assertContains(response, 'aria-expanded="true"', html=False)
        self.assertContains(response, 'id="invoice-recent-items-panel"', html=False)
        self.assertContains(response, 'data-recent-items-wrapper', html=False)
        self.assertContains(response, 'id="invoice-recent-items-data"', html=False)
        self.assertContains(response, 'Translation')
        self.assertContains(response, 'invoices/js/recent_items.js')

    def test_draft_edit_renders_recent_items_toggle_and_excludes_current_invoice(self):
        response = self.client.get(f"{reverse('invoices:edit', args=[self.invoice.id])}?tab=edit")

        self.assertContains(response, 'data-recent-items-component', html=False)
        self.assertContains(response, f'data-selected-project="{self.project.id}"', html=False)
        self.assertContains(response, f'data-exclude-invoice="{self.invoice.id}"', html=False)
        self.assertContains(response, 'data-recent-items-toggle', html=False)
        self.assertContains(response, 'type="button"', html=False)
        self.assertContains(response, 'aria-controls="invoice-profile-recent-items-panel"', html=False)
        self.assertContains(response, 'id="invoice-profile-recent-items-panel"', html=False)
        self.assertContains(response, 'id="invoice-profile-recent-items-data"', html=False)
        self.assertContains(response, 'Translation')
        recent_descriptions = [item['description'] for item in response.context['recent_items_data']]
        self.assertNotIn('Current draft work', recent_descriptions)
        self.assertContains(response, 'invoices/js/recent_items.js')

    def test_project_recent_items_endpoint_honors_valid_invoice_exclusion(self):
        response = self.client.get(reverse('projects:recent_items', args=[self.project.id]))
        descriptions = [item['description'] for item in response.json()['items']]
        self.assertIn('Translation', descriptions)
        self.assertIn('Current draft work', descriptions)

        excluded_response = self.client.get(
            f"{reverse('projects:recent_items', args=[self.project.id])}?exclude_invoice={self.invoice.id}"
        )
        excluded_descriptions = [item['description'] for item in excluded_response.json()['items']]
        self.assertIn('Translation', excluded_descriptions)
        self.assertNotIn('Current draft work', excluded_descriptions)

    def test_project_recent_items_endpoint_ignores_cross_issuer_exclusion(self):
        other_company = Company.objects.create(name='Other Issuer', customer_information_file_number='VATOTHER')
        other_issuer = Issuer.objects.create(company=other_company)
        other_customer_company = Company.objects.create(name='Other Client', customer_information_file_number='VATOC')
        other_customer = Customer.objects.create(issuer=other_issuer, company=other_customer_company)
        other_project = Project.objects.create(customer=other_customer, title='Other Project', project_code='OPRJ')
        other_invoice = Invoice.objects.create(
            issuer=other_issuer,
            customer=other_customer,
            project=other_project,
            issued_date=date(2024, 5, 12),
            status=Invoice.STATUS_DRAFT,
        )

        response = self.client.get(
            f"{reverse('projects:recent_items', args=[self.project.id])}?exclude_invoice={other_invoice.id}"
        )

        descriptions = [item['description'] for item in response.json()['items']]
        self.assertIn('Current draft work', descriptions)

    def test_non_draft_edit_does_not_render_recent_items_component(self):
        self.invoice.status = Invoice.STATUS_INVOICED
        self.invoice.save(update_fields=['status'])

        response = self.client.get(f"{reverse('invoices:edit', args=[self.invoice.id])}?tab=edit")

        self.assertNotContains(response, 'invoice-profile-recent-items-panel')
        self.assertNotContains(response, 'data-exclude-invoice', html=False)

    def test_recent_items_deduplicate_duplicates(self):
        duplicate_invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=date(2024, 6, 10),
            status=Invoice.STATUS_DRAFT,
        )
        OrderLine.objects.create(
            invoice=duplicate_invoice,
            description='Translation',
            quantity=Decimal('1'),
            unit_price=Decimal('100'),
        )
        OrderLine.objects.create(
            invoice=duplicate_invoice,
            description='Translation',
            quantity=Decimal('1'),
            unit_price=Decimal('100'),
        )

        response = self.client.get(reverse('projects:recent_items', args=[self.project.id]))

        data = response.json()
        descriptions = [item['description'] for item in data['items']]
        self.assertEqual(descriptions.count('Translation'), 1)


class InvoiceDrawerTests(AuthenticatedCompanyTestCase):
    def setUp(self):
        issuer_company = Company.objects.create(name='Issuer Co', customer_information_file_number='VATISS')
        self.issuer = Issuer.objects.create(company=issuer_company)

        client_company = Company.objects.create(name='Client', customer_information_file_number='VATC')
        self.customer = Customer.objects.create(issuer=self.issuer, company=client_company)
        self.term_30 = PaymentTerm.objects.create(name='Net 30', days=30)
        self.customer.payment_term = self.term_30
        self.customer.save(update_fields=['payment_term'])
        self.project = Project.objects.create(
            customer=self.customer,
            title='Project',
            project_code='PRJ',
            payment_term=self.term_30,
        )
        self.previous_invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=date(2024, 12, 15),
            status=Invoice.STATUS_DRAFT,
        )
        OrderLine.objects.create(
            invoice=self.previous_invoice,
            description='Prior drawer work',
            quantity=Decimal('3'),
            unit_price=Decimal('75'),
        )

        self.invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=date(2025, 1, 15),
            status=Invoice.STATUS_DRAFT,
        )
        self.invoice.refresh_from_db()
        self.invoice.payment_term = self.term_30
        self.invoice.due_date = self.invoice.issued_date + timedelta(days=self.term_30.days)
        self.invoice.save(update_fields=['payment_term', 'due_date'])
        self.order_line = OrderLine.objects.create(
            invoice=self.invoice,
            description='Initial work',
            quantity=Decimal('1'),
            unit_price=Decimal('100'),
        )

        self.user = self.create_user_with_issuers(
            [self.issuer],
            username='invoice-drawer-user',
            email='drawer@example.com',
        )
        self.login_with_active_company(self.user, issuer=self.issuer)

    def _drawer_payload(self):
        total_forms = 2
        return {
            'reference_number': self.invoice.reference_number,
            'issued_date': self.invoice.issued_date.isoformat(),
            'due_date': self.invoice.due_date.isoformat() if self.invoice.due_date else '',
            'status': Invoice.STATUS_DRAFT,
            'project': str(self.project.id),
            'payment_term': str(self.term_30.id),
            'orderline_set-TOTAL_FORMS': str(total_forms),
            'orderline_set-INITIAL_FORMS': '1',
            'orderline_set-MIN_NUM_FORMS': '0',
            'orderline_set-MAX_NUM_FORMS': '1000',
            'orderline_set-0-id': str(self.order_line.id),
            'orderline_set-0-line_type': OrderLine.LINE_TYPE_QUANTITY,
            'orderline_set-0-description': 'Initial work',
            'orderline_set-0-quantity': '1',
            'orderline_set-0-unit_price': '100',
            'orderline_set-0-DELETE': '',
            'orderline_set-1-id': '',
            'orderline_set-1-line_type': OrderLine.LINE_TYPE_QUANTITY,
            'orderline_set-1-description': '',
            'orderline_set-1-quantity': '',
            'orderline_set-1-unit_price': '',
            'orderline_set-1-DELETE': '',
        }

    def test_delete_invoice_via_view(self):
        response = self.client.post(reverse('invoices:delete', args=[self.invoice.id]))

        self.assertRedirects(response, reverse('invoices:list'))
        self.assertFalse(Invoice.objects.filter(pk=self.invoice.id).exists())

    def test_drawer_renders_shared_recent_items_component_with_invoice_exclusion(self):
        response = self.client.get(reverse('invoices:drawer', args=[self.invoice.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-recent-items-component', html=False)
        self.assertContains(response, f'data-selected-project="{self.project.id}"', html=False)
        self.assertContains(response, f'data-exclude-invoice="{self.invoice.id}"', html=False)
        self.assertContains(response, 'aria-controls="invoice-drawer-recent-items-panel"', html=False)
        self.assertContains(response, 'id="invoice-drawer-recent-items-panel"', html=False)
        self.assertContains(response, 'id="invoice-drawer-recent-items-data"', html=False)
        self.assertContains(response, 'Prior drawer work')
        recent_descriptions = [item['description'] for item in response.context['recent_items_data']]
        self.assertNotIn('Initial work', recent_descriptions)

    def test_delete_line_item_from_drawer(self):
        payload = self._drawer_payload()
        payload['orderline_set-0-DELETE'] = 'on'

        response = self.client.post(reverse('invoices:drawer', args=[self.invoice.id]), data=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(OrderLine.objects.filter(invoice=self.invoice).count(), 0)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.total_due, Decimal('0'))

    def test_re_add_line_item_after_deleting_existing(self):
        payload = self._drawer_payload()
        payload['orderline_set-0-DELETE'] = 'on'
        payload['orderline_set-1-description'] = 'Retainer'
        payload['orderline_set-1-quantity'] = '2'
        payload['orderline_set-1-unit_price'] = '50'

        response = self.client.post(reverse('invoices:drawer', args=[self.invoice.id]), data=payload)

        self.assertEqual(response.status_code, 200)
        lines = OrderLine.objects.filter(invoice=self.invoice)
        self.assertEqual(lines.count(), 1)
        line = lines.first()
        self.assertEqual(line.description, 'Retainer')
        self.assertEqual(line.quantity, Decimal('2'))
        self.assertEqual(line.unit_price, Decimal('50'))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.total_due, Decimal('100'))

    def test_quick_save_endpoint(self):
        payload = self._drawer_payload()

        response = self.client.post(reverse('invoices:quick_save', args=[self.invoice.id]), data=payload)

        self.assertEqual(response.status_code, 200)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.payment_term, self.term_30)
        self.assertEqual(self.invoice.due_date, self.invoice.issued_date + timedelta(days=self.term_30.days))


class InvoiceCreationViewTests(AuthenticatedCompanyTestCase):
    def setUp(self):
        issuer_company = Company.objects.create(name='Issuer Primary', customer_information_file_number='VATISS')
        self.issuer = Issuer.objects.create(company=issuer_company)

        client_company = Company.objects.create(name='Client Alpha', customer_information_file_number='VATC1')
        self.customer = Customer.objects.create(issuer=self.issuer, company=client_company)
        self.term_30 = PaymentTerm.objects.create(name='Net 30', days=30)
        self.term_45 = PaymentTerm.objects.create(name='Net 45', days=45)
        self.customer.payment_term = self.term_30
        self.customer.save(update_fields=['payment_term'])
        self.project = Project.objects.create(
            customer=self.customer,
            title='Alpha Project',
            project_code='ALP1',
            payment_term=self.term_45,
        )

        self.user = self.create_user_with_issuers(
            [self.issuer],
            username='invoice-create-user',
            email='invoice-create@example.com',
        )
        self.login_with_active_company(self.user, issuer=self.issuer)

    def test_get_add_invoice_does_not_precreate(self):
        existing_count = Invoice.objects.count()

        response = self.client.get(reverse('invoices:add'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Invoice.objects.count(), existing_count)
        self.assertIn('invoice_form', response.context)
        self.assertIn('order_formset', response.context)
        expected_hint = self.issuer.render_invoice_reference(date.today(), self.issuer.next_invoice_number)
        self.assertEqual(response.context['reference_number_hint'], expected_hint)
        form = response.context['invoice_form']
        self.assertEqual(form['reference_number'].value(), expected_hint)

    def test_post_add_invoice_creates_invoice_and_lines(self):
        reference_hint = self.issuer.render_invoice_reference(date.today(), self.issuer.next_invoice_number)
        payload = {
            'reference_number': reference_hint,
            'issued_date': date.today().isoformat(),
            'status': Invoice.STATUS_DRAFT,
            'project': str(self.project.id),
            'payment_term': '',
            'due_date': '',
            'orderline_set-TOTAL_FORMS': '2',
            'orderline_set-INITIAL_FORMS': '0',
            'orderline_set-MIN_NUM_FORMS': '0',
            'orderline_set-MAX_NUM_FORMS': '1000',
            'orderline_set-0-id': '',
            'orderline_set-0-line_type': OrderLine.LINE_TYPE_QUANTITY,
            'orderline_set-0-description': 'Consulting hours',
            'orderline_set-0-quantity': '2',
            'orderline_set-0-unit_price': '150',
            'orderline_set-0-DELETE': '',
            'orderline_set-1-id': '',
            'orderline_set-1-line_type': OrderLine.LINE_TYPE_QUANTITY,
            'orderline_set-1-description': '',
            'orderline_set-1-quantity': '',
            'orderline_set-1-unit_price': '',
            'orderline_set-1-DELETE': '',
            'reference_number_hint': reference_hint,
        }

        with patch('invoices.views.save_invoice_pdf', return_value=True) as mocked_pdf:
            response = self.client.post(reverse('invoices:add'), data=payload)

        self.assertEqual(Invoice.objects.count(), 1)
        invoice = Invoice.objects.get()
        self.assertRedirects(response, f"{reverse('invoices:edit', args=[invoice.id])}?tab=edit")
        self.assertEqual(invoice.project, self.project)
        self.assertEqual(invoice.customer, self.customer)
        self.assertEqual(invoice.total_due, Decimal('300'))
        self.assertEqual(invoice.payment_term, self.term_45)
        self.assertEqual(invoice.due_date, date.today() + timedelta(days=self.term_45.days))
        expected_reference = invoice.issuer.render_invoice_reference(invoice.issued_date, invoice.number)
        self.assertEqual(invoice.reference_number, expected_reference)
        lines = OrderLine.objects.filter(invoice=invoice)
        self.assertEqual(lines.count(), 1)
        line = lines.first()
        self.assertEqual(line.description, 'Consulting hours')
        self.assertEqual(line.quantity, Decimal('2'))
        self.assertEqual(line.unit_price, Decimal('150'))
        mocked_pdf.assert_called_once()

    def test_post_add_invoice_persists_customer_currency_snapshot(self):
        sek = Currency.objects.create(
            code='SEK',
            name='Swedish Krona',
            symbol='kr',
            exchange_rate_to_base=Decimal('0.09123456'),
        )
        self.customer.currency = sek
        self.customer.save(update_fields=['currency'])

        reference_hint = self.issuer.render_invoice_reference(date.today(), self.issuer.next_invoice_number)
        payload = {
            'reference_number': reference_hint,
            'issued_date': date.today().isoformat(),
            'status': Invoice.STATUS_DRAFT,
            'project': str(self.project.id),
            'payment_term': '',
            'due_date': '',
            'orderline_set-TOTAL_FORMS': '1',
            'orderline_set-INITIAL_FORMS': '0',
            'orderline_set-MIN_NUM_FORMS': '0',
            'orderline_set-MAX_NUM_FORMS': '1000',
            'orderline_set-0-id': '',
            'orderline_set-0-line_type': OrderLine.LINE_TYPE_QUANTITY,
            'orderline_set-0-description': 'Consulting hours',
            'orderline_set-0-quantity': '2',
            'orderline_set-0-unit_price': '150',
            'orderline_set-0-DELETE': '',
            'reference_number_hint': reference_hint,
        }

        with patch('invoices.views.save_invoice_pdf', return_value=True):
            self.client.post(reverse('invoices:add'), data=payload)

        invoice = Invoice.objects.get()
        self.assertEqual(invoice.currency, sek)
        self.assertEqual(invoice.exchange_rate, sek.exchange_rate_to_base)

    def test_post_add_invoice_leaves_currency_empty_without_customer_currency(self):
        reference_hint = self.issuer.render_invoice_reference(date.today(), self.issuer.next_invoice_number)
        payload = {
            'reference_number': reference_hint,
            'issued_date': date.today().isoformat(),
            'status': Invoice.STATUS_DRAFT,
            'project': str(self.project.id),
            'payment_term': '',
            'due_date': '',
            'orderline_set-TOTAL_FORMS': '1',
            'orderline_set-INITIAL_FORMS': '0',
            'orderline_set-MIN_NUM_FORMS': '0',
            'orderline_set-MAX_NUM_FORMS': '1000',
            'orderline_set-0-id': '',
            'orderline_set-0-line_type': OrderLine.LINE_TYPE_QUANTITY,
            'orderline_set-0-description': 'Consulting hours',
            'orderline_set-0-quantity': '2',
            'orderline_set-0-unit_price': '150',
            'orderline_set-0-DELETE': '',
            'reference_number_hint': reference_hint,
        }

        with patch('invoices.views.save_invoice_pdf', return_value=True):
            self.client.post(reverse('invoices:add'), data=payload)

        invoice = Invoice.objects.get()
        self.assertIsNone(invoice.currency)

    def test_get_add_invoice_prefills_project_from_query(self):
        url = f"{reverse('invoices:add')}?project={self.project.id}"

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        form = response.context['invoice_form']
        self.assertEqual(str(form['project'].value()), str(self.project.id))
        self.assertEqual(response.context['selected_project_id'], self.project.id)
        self.assertEqual(str(form['payment_term'].value()), str(self.term_45.id))
        self.assertEqual(str(form['due_date'].value()), (date.today() + timedelta(days=self.term_45.days)).isoformat())


class InvoiceNumberingTests(TestCase):
    def setUp(self):
        issuer_company = Company.objects.create(name='Issuer Format Co', customer_information_file_number='VATFMT')
        self.issuer = Issuer.objects.create(
            company=issuer_company,
            invoice_format='INV-{{YYYY}}/{{MM}}-{{ID}}',
            next_invoice_number=7,
        )
        client_company = Company.objects.create(name='Client Format', customer_information_file_number='VATCF')
        self.customer = Customer.objects.create(issuer=self.issuer, company=client_company)
        self.project = Project.objects.create(customer=self.customer, title='Format Project', project_code='FMT1')

    def test_custom_format_applied_and_counter_incremented(self):
        invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=date(2025, 2, 3),
            status=Invoice.STATUS_DRAFT,
        )
        self.assertEqual(invoice.number, 7)
        self.assertEqual(invoice.reference_number, 'INV-2025/02-0007')
        self.issuer.refresh_from_db()
        self.assertEqual(self.issuer.next_invoice_number, 8)

    def test_default_format_used_when_blank(self):
        self.issuer.invoice_format = ''
        self.issuer.next_invoice_number = 15
        self.issuer.save(update_fields=['invoice_format', 'next_invoice_number'])

        invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=date(2024, 9, 10),
            status=Invoice.STATUS_DRAFT,
        )

        self.assertEqual(invoice.number, 15)
        self.assertEqual(invoice.reference_number, '2024.0015')
        self.issuer.refresh_from_db()
        self.assertEqual(self.issuer.next_invoice_number, 16)


class InvoiceEditViewCurrencyPersistenceTests(AuthenticatedCompanyTestCase):
    def setUp(self):
        issuer_company = Company.objects.create(name='Issuer Edit', customer_information_file_number='VATISS')
        self.issuer = Issuer.objects.create(company=issuer_company)

        client_company = Company.objects.create(name='Client Edit', customer_information_file_number='VATC1')
        self.customer = Customer.objects.create(issuer=self.issuer, company=client_company)
        self.term_30 = PaymentTerm.objects.create(name='Net 30', days=30)
        self.project = Project.objects.create(
            customer=self.customer,
            title='Edit Project',
            project_code='EDT1',
            payment_term=self.term_30,
        )
        self.invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=date(2025, 1, 1),
            status=Invoice.STATUS_DRAFT,
            payment_term=self.term_30,
            due_date=date(2025, 1, 31),
        )
        self.line = OrderLine.objects.create(
            invoice=self.invoice,
            description='Existing work',
            quantity=Decimal('1'),
            unit_price=Decimal('100'),
        )

        self.user = self.create_user_with_issuers(
            [self.issuer],
            username='invoice-edit-currency-user',
            email='invoice-edit-currency@example.com',
        )
        self.login_with_active_company(self.user, issuer=self.issuer)

    def _payload(self):
        return {
            'reference_number': self.invoice.reference_number,
            'issued_date': self.invoice.issued_date.isoformat(),
            'due_date': self.invoice.due_date.isoformat(),
            'status': Invoice.STATUS_DRAFT,
            'project': str(self.project.id),
            'payment_term': str(self.term_30.id),
            'notes': '',
            'orderline_set-TOTAL_FORMS': '1',
            'orderline_set-INITIAL_FORMS': '1',
            'orderline_set-MIN_NUM_FORMS': '0',
            'orderline_set-MAX_NUM_FORMS': '1000',
            'orderline_set-0-id': str(self.line.id),
            'orderline_set-0-line_type': OrderLine.LINE_TYPE_QUANTITY,
            'orderline_set-0-description': self.line.description,
            'orderline_set-0-quantity': str(self.line.quantity),
            'orderline_set-0-unit_price': str(self.line.unit_price),
            'orderline_set-0-DELETE': '',
        }

    def test_post_edit_persists_missing_customer_currency_snapshot(self):
        sek = Currency.objects.create(
            code='SEK',
            name='Swedish Krona',
            symbol='kr',
            exchange_rate_to_base=Decimal('0.09123456'),
        )
        self.customer.currency = sek
        self.customer.save(update_fields=['currency'])
        Invoice.objects.filter(pk=self.invoice.pk).update(currency=None, exchange_rate=Decimal('1'))
        self.invoice.refresh_from_db()

        with patch('invoices.views.save_invoice_pdf', return_value=True):
            response = self.client.post(reverse('invoices:edit', args=[self.invoice.id]), data=self._payload())

        self.assertEqual(response.status_code, 302)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.currency, sek)
        self.assertEqual(self.invoice.exchange_rate, sek.exchange_rate_to_base)

    def test_post_edit_leaves_currency_empty_without_customer_currency(self):
        Invoice.objects.filter(pk=self.invoice.pk).update(currency=None, exchange_rate=Decimal('1'))
        self.invoice.refresh_from_db()

        with patch('invoices.views.save_invoice_pdf', return_value=True):
            response = self.client.post(reverse('invoices:edit', args=[self.invoice.id]), data=self._payload())

        self.assertEqual(response.status_code, 302)
        self.invoice.refresh_from_db()
        self.assertIsNone(self.invoice.currency)


class InvoiceFormTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name='Client', customer_information_file_number='VAT')
        issuer_company = Company.objects.create(name='Issuer', customer_information_file_number='VATISS')
        issuer = Issuer.objects.create(company=issuer_company)
        self.term_30 = PaymentTerm.objects.create(name='Net 30', days=30)
        self.customer = Customer.objects.create(issuer=issuer, company=company, payment_term=self.term_30)
        self.project = Project.objects.create(customer=self.customer, title='Proj', project_code='PR1', payment_term=self.term_30)
        self.issuer = issuer
        self.default_account = IssuerBankAccount.objects.create(
            issuer=issuer,
            label='Default EUR',
            payment_method='Bank transfer',
            account_details='DEFAULT-IBAN',
            is_default=True,
            is_active=True,
        )
        self.secondary_account = IssuerBankAccount.objects.create(
            issuer=issuer,
            label='Secondary EUR',
            payment_method='Wire',
            account_details='SECONDARY-IBAN',
            is_default=False,
            is_active=True,
            sort_order=2,
        )

    def _build_form(self, *, instance=None):
        return InvoiceForm(
            data={
                'project': self.project.id,
                'reference_number': '2025.0001',
                'issued_date': '2025-01-01',
                'due_date': '',
                'payment_term': '',
                'bank_account': self.default_account.id,
                'status': Invoice.STATUS_DRAFT,
            },
            issuer=self.issuer,
            instance=instance or Invoice(issuer=self.issuer),
        )

    def test_form_rejects_project_not_linked_to_issuer(self):
        other_company = Company.objects.create(name='Other Issuer', customer_information_file_number='VAT3')
        other_issuer = Issuer.objects.create(company=other_company)
        other_customer_company = Company.objects.create(name='Other client', customer_information_file_number='VAT2')
        other_customer = Customer.objects.create(issuer=other_issuer, company=other_customer_company)
        other_project = Project.objects.create(customer=other_customer, title='Other Proj', project_code='PR2')

        form = InvoiceForm(
            data={
                'project': other_project.id,
                'reference_number': '2025.0001',
                'issued_date': '2025-01-01',
                'due_date': '',
                'payment_term': '',
                'bank_account': '',
                'status': Invoice.STATUS_DRAFT,
            },
            issuer=self.issuer,
            instance=Invoice(issuer=self.issuer),
        )

        self.assertFalse(form.is_valid())
        self.assertIn('project', form.errors)

    def test_form_valid_with_matching_project(self):
        form = self._build_form()

        self.assertTrue(form.is_valid())
        invoice = form.save(commit=False)
        self.assertEqual(invoice.project, self.project)
        self.assertEqual(invoice.customer, self.customer)
        self.assertEqual(invoice.payment_term, self.term_30)
        self.assertEqual(invoice.bank_account, self.default_account)
        self.assertEqual(invoice.due_date, date(2025, 1, 31))

    def test_new_invoice_defaults_to_customer_last_used_active_account(self):
        Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            bank_account=self.secondary_account,
            issued_date=date(2025, 1, 1),
            status=Invoice.STATUS_DRAFT,
        )

        form = InvoiceForm(instance=Invoice(issuer=self.issuer), issuer=self.issuer, customer=self.customer)

        self.assertEqual(form.fields['bank_account'].initial, self.secondary_account.id)
        self.assertEqual(resolve_invoice_bank_account(self.issuer, customer=self.customer), self.secondary_account)

    def test_new_invoice_defaults_to_issuer_default_without_customer_history(self):
        form = InvoiceForm(instance=Invoice(issuer=self.issuer), issuer=self.issuer, customer=self.customer)

        self.assertEqual(form.fields['bank_account'].initial, self.default_account.id)

    def test_edit_invoice_initial_uses_current_bank_account(self):
        invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            bank_account=self.secondary_account,
            issued_date=date(2025, 1, 1),
            status=Invoice.STATUS_DRAFT,
        )

        form = InvoiceForm(instance=invoice, issuer=self.issuer, customer=self.customer)

        self.assertEqual(form.fields['bank_account'].initial, self.secondary_account.id)

    def test_edit_invoice_save_preserves_current_bank_account(self):
        invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            bank_account=self.secondary_account,
            issued_date=date(2025, 1, 1),
            status=Invoice.STATUS_DRAFT,
        )
        form = self._build_form(instance=invoice)
        form.data = form.data.copy()
        form.data['bank_account'] = self.secondary_account.id

        self.assertTrue(form.is_valid())
        saved_invoice = form.save()
        saved_invoice.refresh_from_db()

        self.assertEqual(saved_invoice.bank_account, self.secondary_account)

    def test_form_rejects_bank_account_from_other_issuer(self):
        other_issuer = Issuer.objects.create(
            company=Company.objects.create(name='Other Issuer', customer_information_file_number='VATOTHER')
        )
        other_account = IssuerBankAccount.objects.create(
            issuer=other_issuer,
            label='Other Account',
            account_details='OTHER-IBAN',
            is_default=True,
            is_active=True,
        )
        form = InvoiceForm(
            data={
                'project': self.project.id,
                'reference_number': '2025.0001',
                'issued_date': '2025-01-01',
                'due_date': '',
                'payment_term': '',
                'bank_account': other_account.id,
                'status': Invoice.STATUS_DRAFT,
            },
            issuer=self.issuer,
            instance=Invoice(issuer=self.issuer),
        )

        self.assertFalse(form.is_valid())
        self.assertIn('bank_account', form.errors)

    def test_manual_bank_account_override_is_saved(self):
        form = self._build_form()
        form.data = form.data.copy()
        form.data['bank_account'] = self.secondary_account.id

        self.assertTrue(form.is_valid())
        invoice = form.save()
        invoice.refresh_from_db()

        self.assertEqual(invoice.bank_account, self.secondary_account)

    def test_transactionless_project_available_in_project_queryset(self):
        other_issuer_company = Company.objects.create(
            name='Other Issuer',
            customer_information_file_number='VAT3',
        )
        other_issuer = Issuer.objects.create(company=other_issuer_company)
        other_customer_company = Company.objects.create(
            name='Other client',
            customer_information_file_number='VAT2',
        )
        other_customer = Customer.objects.create(issuer=other_issuer, company=other_customer_company)
        other_project = Project.objects.create(customer=other_customer, title='Other Proj', project_code='PR2')

        form = InvoiceForm(issuer=self.issuer)

        project_queryset = form.fields['project'].queryset
        self.assertIn(self.project, project_queryset)
        self.assertNotIn(other_project, project_queryset)

    def test_form_save_applies_customer_currency_snapshot_before_commit(self):
        sek = Currency.objects.create(
            code='SEK',
            name='Swedish Krona',
            symbol='kr',
            exchange_rate_to_base=Decimal('0.09123456'),
        )
        self.customer.currency = sek
        self.customer.save(update_fields=['currency'])

        form = self._build_form()

        self.assertTrue(form.is_valid())
        invoice = form.save(commit=False)

        self.assertEqual(invoice.currency, sek)
        self.assertEqual(invoice.exchange_rate, sek.exchange_rate_to_base)

    def test_form_save_persists_customer_currency_snapshot_on_create(self):
        sek = Currency.objects.create(
            code='SEK',
            name='Swedish Krona',
            symbol='kr',
            exchange_rate_to_base=Decimal('0.09123456'),
        )
        self.customer.currency = sek
        self.customer.save(update_fields=['currency'])

        form = self._build_form()

        self.assertTrue(form.is_valid())
        saved_invoice = form.save()
        saved_invoice.refresh_from_db()

        self.assertEqual(saved_invoice.currency, sek)
        self.assertEqual(saved_invoice.exchange_rate, sek.exchange_rate_to_base)

    def test_form_save_persists_missing_currency_on_edit(self):
        sek = Currency.objects.create(
            code='SEK',
            name='Swedish Krona',
            symbol='kr',
            exchange_rate_to_base=Decimal('0.09123456'),
        )
        self.customer.currency = sek
        self.customer.save(update_fields=['currency'])
        invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=date(2025, 1, 1),
            status=Invoice.STATUS_DRAFT,
        )
        Invoice.objects.filter(pk=invoice.pk).update(currency=None)
        invoice.refresh_from_db()

        form = self._build_form(instance=invoice)

        self.assertTrue(form.is_valid())
        saved_invoice = form.save()
        saved_invoice.refresh_from_db()

        self.assertEqual(saved_invoice.currency, sek)
        self.assertEqual(saved_invoice.exchange_rate, sek.exchange_rate_to_base)

    def test_form_save_leaves_currency_empty_without_customer_currency(self):
        form = self._build_form()

        self.assertTrue(form.is_valid())
        invoice = form.save(commit=False)

        self.assertIsNone(invoice.currency)

    def test_form_save_persists_empty_currency_when_customer_has_none(self):
        form = self._build_form()

        self.assertTrue(form.is_valid())
        saved_invoice = form.save()
        saved_invoice.refresh_from_db()

        self.assertIsNone(saved_invoice.currency)

    def test_inactive_projects_not_listed(self):
        self.project.status = Project.STATUS_INACTIVE
        self.project.save()

        form = InvoiceForm(issuer=self.issuer)
        self.assertNotIn(self.project, form.fields['project'].queryset)

    def test_projects_from_inactive_customers_not_listed(self):
        self.customer.is_active = False
        self.customer.save(update_fields=['is_active'])

        form = InvoiceForm(issuer=self.issuer)
        self.assertNotIn(self.project, form.fields['project'].queryset)


class InvoiceBankAccountViewTests(AuthenticatedCompanyTestCase):
    def setUp(self):
        self.issuer = Issuer.objects.create(
            company=Company.objects.create(
                name='Issuer',
                customer_information_file_number='VATISS',
                payment_terms='Pay promptly.',
            )
        )
        self.user = self.create_user_with_issuers([self.issuer])
        self.login_with_active_company(self.user, issuer=self.issuer)
        self.customer = Customer.objects.create(
            issuer=self.issuer,
            company=Company.objects.create(name='Client', customer_information_file_number='VATC'),
        )
        self.project = Project.objects.create(customer=self.customer, title='Project', project_code='PR1')
        self.default_account = IssuerBankAccount.objects.create(
            issuer=self.issuer,
            label='Default EUR',
            payment_method='Bank transfer',
            account_details='DEFAULT-IBAN',
            is_default=True,
            is_active=True,
        )
        self.secondary_account = IssuerBankAccount.objects.create(
            issuer=self.issuer,
            label='Secondary EUR',
            payment_method='Wire',
            account_details='SECONDARY-IBAN',
            is_default=False,
            is_active=True,
        )

    def test_bulk_last_month_copies_previous_invoice_account(self):
        previous = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            bank_account=self.secondary_account,
            issued_date=date.today() - timedelta(days=40),
            status=Invoice.STATUS_DRAFT,
        )
        OrderLine.objects.create(
            invoice=previous,
            description='Monthly work',
            quantity=Decimal('2'),
            unit_price=Decimal('50'),
        )

        response = self.client.post(reverse('invoices:bulk_last_month'), {
            'action': 'create',
            'selected': [str(self.project.id)],
            f'project-{self.project.id}-description': ['Monthly work'],
            f'project-{self.project.id}-quantity': ['2'],
            f'project-{self.project.id}-unit_price': ['50'],
        })

        self.assertEqual(response.status_code, 302)
        created = Invoice.objects.exclude(pk=previous.pk).get(project=self.project)
        self.assertEqual(created.bank_account, self.secondary_account)

    def test_pdf_preview_renders_invoice_selected_account(self):
        invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            bank_account=self.secondary_account,
            issued_date=date(2025, 1, 1),
            status=Invoice.STATUS_DRAFT,
        )
        OrderLine.objects.create(
            invoice=invoice,
            description='Work',
            quantity=Decimal('1'),
            unit_price=Decimal('100'),
        )

        response = self.client.get(reverse('invoices:pdf', args=[invoice.id]))

        self.assertContains(response, 'SECONDARY-IBAN')
        self.assertNotContains(response, 'DEFAULT-IBAN')


class InvoiceCurrencySnapshotTests(TestCase):
    def setUp(self):
        issuer_company = Company.objects.create(name='Issuer', customer_information_file_number='VATISS')
        customer_company = Company.objects.create(name='Client', customer_information_file_number='VATC')
        self.issuer = Issuer.objects.create(company=issuer_company)
        self.customer_currency = Currency.objects.create(
            code='SEK',
            name='Swedish Krona',
            symbol='kr',
            exchange_rate_to_base=Decimal('0.09123456'),
        )
        self.explicit_currency = Currency.objects.create(
            code='USD',
            name='US Dollar',
            symbol='$',
            exchange_rate_to_base=Decimal('0.95000000'),
        )
        self.customer = Customer.objects.create(
            issuer=self.issuer,
            company=customer_company,
            currency=self.customer_currency,
        )
        self.project = Project.objects.create(customer=self.customer, title='Proj', project_code='PR1')

    def test_save_uses_customer_currency_when_invoice_currency_missing(self):
        invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=date(2025, 1, 1),
            status=Invoice.STATUS_DRAFT,
            total_due=Decimal('4500.00'),
        )

        self.assertEqual(invoice.currency, self.customer_currency)
        self.assertEqual(invoice.exchange_rate, self.customer_currency.exchange_rate_to_base)
        self.assertEqual(invoice.base_currency_total, Decimal('410.56'))

    def test_snapshot_helper_fills_missing_fields_from_project_customer(self):
        invoice = Invoice(
            issuer=self.issuer,
            project=self.project,
            issued_date=date(2025, 1, 1),
            status=Invoice.STATUS_DRAFT,
            total_due=Decimal('4500.00'),
        )

        invoice.apply_missing_currency_snapshot()

        self.assertEqual(invoice.currency, self.customer_currency)
        self.assertEqual(invoice.exchange_rate, self.customer_currency.exchange_rate_to_base)
        self.assertEqual(invoice.base_currency_total, Decimal('410.56'))

    def test_save_preserves_explicit_invoice_currency(self):
        invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            currency=self.explicit_currency,
            issued_date=date(2025, 1, 1),
            status=Invoice.STATUS_DRAFT,
        )

        self.assertEqual(invoice.currency, self.explicit_currency)

    def test_snapshot_helper_preserves_explicit_invoice_currency(self):
        invoice = Invoice(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            currency=self.explicit_currency,
            exchange_rate=Decimal('1'),
            issued_date=date(2025, 1, 1),
            status=Invoice.STATUS_DRAFT,
            total_due=Decimal('4500.00'),
        )

        invoice.apply_missing_currency_snapshot()

        self.assertEqual(invoice.currency, self.explicit_currency)
        self.assertEqual(invoice.exchange_rate, Decimal('1'))
        self.assertEqual(invoice.base_currency_total, Decimal('0'))

    def test_save_preserves_existing_base_currency_total(self):
        invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=date(2025, 1, 1),
            status=Invoice.STATUS_DRAFT,
            total_due=Decimal('4500.00'),
            base_currency_total=Decimal('999.99'),
        )

        self.assertEqual(invoice.currency, self.customer_currency)
        self.assertEqual(invoice.base_currency_total, Decimal('999.99'))


class InvoiceCurrencyBackfillMigrationTests(TransactionTestCase):
    migrate_from = [('invoices', '0055_invoice_notes')]
    migrate_to = [('invoices', '0056_backfill_invoice_currency')]

    def _migrate_with_setup(self, setup_data):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        state = setup_data(old_apps)

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        return new_apps, state

    @staticmethod
    def _create_invoice_context(old_apps, *, customer_currency_code='SEK', include_customer_currency=True):
        CompanyModel = old_apps.get_model('invoices', 'Company')
        CurrencyModel = old_apps.get_model('invoices', 'Currency')
        CustomerModel = old_apps.get_model('invoices', 'Customer')
        InvoiceModel = old_apps.get_model('invoices', 'Invoice')
        IssuerModel = old_apps.get_model('invoices', 'Issuer')
        ProjectModel = old_apps.get_model('invoices', 'Project')

        issuer_company = CompanyModel.objects.create(name='Issuer', customer_information_file_number='VATISS')
        customer_company = CompanyModel.objects.create(name='Client', customer_information_file_number='VATC')
        issuer = IssuerModel.objects.create(company=issuer_company)
        customer_currency = CurrencyModel.objects.create(
            code=customer_currency_code,
            name='Swedish Krona',
            symbol='kr',
            exchange_rate_to_base=Decimal('0.09123456'),
        )
        explicit_currency = CurrencyModel.objects.create(
            code='USD',
            name='US Dollar',
            symbol='$',
            exchange_rate_to_base=Decimal('0.95000000'),
        )
        customer = CustomerModel.objects.create(
            issuer=issuer,
            company=customer_company,
            currency=customer_currency if include_customer_currency else None,
        )
        project = ProjectModel.objects.create(customer=customer, title='Proj', project_code=f'PR-{customer_currency_code}')

        return {
            'InvoiceModel': InvoiceModel,
            'customer': customer,
            'customer_currency': customer_currency,
            'explicit_currency': explicit_currency,
            'issuer': issuer,
            'project': project,
        }

    def test_backfill_repairs_repairable_rows(self):
        def setup_data(old_apps):
            context = self._create_invoice_context(old_apps)
            invoice = context['InvoiceModel'].objects.create(
                issuer=context['issuer'],
                project=context['project'],
                issued_date=date(2025, 1, 1),
                status='draft',
                total_due=Decimal('4500.00'),
                exchange_rate=Decimal('1'),
                base_currency_total=Decimal('0'),
            )
            context['invoice_id'] = invoice.pk
            return context

        new_apps, state = self._migrate_with_setup(setup_data)
        InvoiceModel = new_apps.get_model('invoices', 'Invoice')
        invoice = InvoiceModel.objects.get(pk=state['invoice_id'])

        self.assertEqual(invoice.currency_id, state['customer_currency'].pk)
        self.assertEqual(invoice.exchange_rate, Decimal('0.09123456'))
        self.assertEqual(invoice.base_currency_total, Decimal('410.56'))

    def test_backfill_leaves_already_correct_rows_unchanged(self):
        def setup_data(old_apps):
            context = self._create_invoice_context(old_apps)
            invoice = context['InvoiceModel'].objects.create(
                issuer=context['issuer'],
                customer=context['customer'],
                project=context['project'],
                currency=context['explicit_currency'],
                issued_date=date(2025, 1, 1),
                status='draft',
                total_due=Decimal('4500.00'),
                exchange_rate=Decimal('1.23000000'),
                base_currency_total=Decimal('999.99'),
            )
            context['invoice_id'] = invoice.pk
            return context

        new_apps, state = self._migrate_with_setup(setup_data)
        InvoiceModel = new_apps.get_model('invoices', 'Invoice')
        invoice = InvoiceModel.objects.get(pk=state['invoice_id'])

        self.assertEqual(invoice.currency_id, state['explicit_currency'].pk)
        self.assertEqual(invoice.exchange_rate, Decimal('1.23000000'))
        self.assertEqual(invoice.base_currency_total, Decimal('999.99'))

    def test_backfill_leaves_unrecoverable_rows_unchanged(self):
        def setup_data(old_apps):
            context = self._create_invoice_context(old_apps, customer_currency_code='NOK', include_customer_currency=False)
            invoice = context['InvoiceModel'].objects.create(
                issuer=context['issuer'],
                customer=context['customer'],
                project=context['project'],
                issued_date=date(2025, 1, 1),
                status='draft',
                total_due=Decimal('4500.00'),
                exchange_rate=Decimal('1'),
                base_currency_total=Decimal('0'),
            )
            context['invoice_id'] = invoice.pk
            return context

        new_apps, state = self._migrate_with_setup(setup_data)
        InvoiceModel = new_apps.get_model('invoices', 'Invoice')
        invoice = InvoiceModel.objects.get(pk=state['invoice_id'])

        self.assertIsNone(invoice.currency_id)
        self.assertEqual(invoice.exchange_rate, Decimal('1.00000000'))
        self.assertEqual(invoice.base_currency_total, Decimal('0.00'))


class WiseImporterServiceTests(TestCase):
    FIELDNAMES = [
        'TransferWise ID', 'Date', 'Date Time', 'Amount', 'Currency', 'Description', 'Payment Reference',
        'Running Balance', 'Exchange From', 'Exchange To', 'Exchange Rate', 'Payer Name', 'Payee Name',
        'Payee Account Number', 'Merchant', 'Card Last Four Digits', 'Card Holder Full Name', 'Attachment',
        'Note', 'Total fees', 'Exchange To Amount', 'Transaction Type', 'Transaction Details Type',
    ]

    def setUp(self):
        self.company = Company.objects.create(name='Acme')
        self.issuer = Issuer.objects.create(company=self.company)
        Currency.objects.create(code='EUR', name='Euro', symbol='€')

    def _upload(self, name: str, rows: list[dict]) -> SimpleUploadedFile:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=self.FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        content = buffer.getvalue().encode('utf-8')
        return SimpleUploadedFile(name, content, content_type='text/csv')

    def test_creates_expenses_from_debit_rows(self):
        rows = [
            {
                'TransferWise ID': 'CARD-001',
                'Date': '07-11-2025',
                'Date Time': '07-11-2025 09:06:18.060',
                'Amount': '-500.00',
                'Currency': 'EUR',
                'Description': 'Invoice 1',
                'Transaction Type': 'DEBIT',
                'Transaction Details Type': 'CARD',
            },
            {
                'TransferWise ID': 'CARD-002',
                'Date': '07-11-2025',
                'Date Time': '07-11-2025 09:06:18.060',
                'Amount': '-10.00',
                'Currency': 'EUR',
                'Description': 'Conversion',
                'Transaction Type': 'DEBIT',
                'Transaction Details Type': 'CONVERSION',
            },
        ]
        upload = self._upload('statement.csv', rows)
        importer = WiseStatementImporter(self.issuer)

        result = importer.import_files([upload])

        self.assertEqual(result.created, 1)
        self.assertEqual(result.skipped_conversions, 1)
        expense = Expense.objects.get()
        self.assertEqual(expense.external_id, 'CARD-001')
        self.assertEqual(expense.amount, Decimal('500'))
        self.assertEqual(expense.description, 'Invoice 1')

    def test_skips_existing_transactions(self):
        Expense.objects.create(
            issuer=self.issuer,
            paid_date='2024-01-01',
            amount=Decimal('10'),
            description='Manual',
            external_id='CARD-001',
        )

        rows = [
            {
                'TransferWise ID': 'CARD-001',
                'Date': '07-11-2025',
                'Date Time': '07-11-2025 09:06:18.060',
                'Amount': '-500.00',
                'Currency': 'EUR',
                'Description': 'Invoice',
                'Transaction Type': 'DEBIT',
                'Transaction Details Type': 'CARD',
            },
            {
                'TransferWise ID': 'CARD-002',
                'Date': '07-11-2025',
                'Date Time': '07-11-2025 09:06:18.060',
                'Amount': '100.00',
                'Currency': 'EUR',
                'Description': 'Deposit',
                'Transaction Type': 'CREDIT',
                'Transaction Details Type': 'DEPOSIT',
            },
        ]
        upload = self._upload('statement.csv', rows)
        importer = WiseStatementImporter(self.issuer)

        result = importer.import_files([upload])

        self.assertEqual(result.created, 0)
        self.assertEqual(result.skipped_existing, 1)
        self.assertEqual(result.skipped_not_debit, 1)


class WiseImportViewTests(AuthenticatedCompanyTestCase):
    def setUp(self):
        self.client = Client()
        self.company = Company.objects.create(name='Globex')
        self.issuer = Issuer.objects.create(company=self.company)

        self.user = self.create_user_with_issuers(
            [self.issuer],
            username='wise-import-user',
            email='wise@example.com',
        )
        self.login_with_active_company(self.user, issuer=self.issuer)

    def _file(self):
        content = (
            '"TransferWise ID",Date,"Date Time",Amount,Currency,"Description","Payment Reference","Running Balance","Exchange From","Exchange To","Exchange Rate","Payer Name","Payee Name","Payee Account Number",Merchant,"Card Last Four Digits","Card Holder Full Name",Attachment,Note,"Total fees","Exchange To Amount","Transaction Type","Transaction Details Type"\n'
            'CARD-001,07-11-2025,"07-11-2025 09:06:18.060",-500.00,EUR,"Invoice",,,,,,,,,,,,,0.00,,DEBIT,CARD\n'
        ).encode('utf-8')
        return SimpleUploadedFile('statement.csv', content, content_type='text/csv')

    @patch('invoices.views.WiseStatementImporter')
    def test_import_view_processes_uploaded_files(self, importer_cls):
        importer_instance = importer_cls.return_value
        importer_instance.import_files.return_value = WiseImportResult(created=2)

        response = self.client.post(
            reverse('invoices:payments_import_wise'),
            data={'statements': self._file()},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        importer_cls.assert_called_once_with(issuer=self.issuer)
        importer_instance.import_files.assert_called_once()

    def test_import_view_requires_file(self):
        response = self.client.post(
            reverse('invoices:payments_import_wise'),
            data={},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('upload', response.json()['error'].lower())
