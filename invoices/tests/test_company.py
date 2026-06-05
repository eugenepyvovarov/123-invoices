from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory, TestCase
from django.urls import reverse

from invoices.company_deduplication import _normalize_company_contact_email, _normalize_company_tax_id
from invoices.models import Address, Company, Customer, Invoice, Issuer, IssuerBankAccount, OrderLine, PaymentTerm, Project
from invoices.utils.company_context import get_active_issuer
from tests.support import AuthenticatedCompanyTestCase, IssuerUserTestMixin


class EditCompanyViewTests(AuthenticatedCompanyTestCase):
    def setUp(self):
        self.term_30 = PaymentTerm.objects.create(name='Net 30', days=30)
        self.term_15 = PaymentTerm.objects.create(name='Net 15', days=15)
        address = Address.objects.create(full_address='Old address')
        company = Company.objects.create(
            name='Old Co',
            customer_information_file_number='VAT123',
            bank_account_number='ES00 0000 0000 0000',
            payment_method='Bank transfer',
            payment_terms='Due upon receipt',
            payment_term=self.term_30,
            address=address,
        )
        self.issuer = Issuer.objects.create(company=company)
        self.primary_account = IssuerBankAccount.objects.create(
            issuer=self.issuer,
            label='Primary EUR',
            payment_method='Bank transfer',
            account_details='ES00 0000 0000 0000',
            is_active=True,
            is_default=True,
            sort_order=1,
        )

        self.user = self.create_user_with_issuers(
            [self.issuer],
            username='edit-company-user',
            email='company@example.com',
        )
        self.login_with_active_company(self.user, issuer=self.issuer)

    def _build_settings_payload(self, **overrides):
        payload = {
            'company_id': str(self.issuer.company_id),
            'create_new': '0',
            'issuer_company-name': 'New Co',
            'issuer_company-customer_information_file_number': 'VAT999',
            'issuer_company-contact_name': 'Accounts Payable',
            'issuer_company-contact_email': 'billing@example.com',
            'issuer_company-payment_terms': 'Net 30 days',
            'issuer_company-payment_term': str(self.term_15.id),
            'address-full_address': '123 Main St\nBarcelona',
            'issuer_settings-invoice_format': '{{YYYY}}-{{MM}}-{{ID}}',
            'issuer_settings-next_invoice_number': '12',
            'bank_accounts-TOTAL_FORMS': '2',
            'bank_accounts-INITIAL_FORMS': '1',
            'bank_accounts-MIN_NUM_FORMS': '0',
            'bank_accounts-MAX_NUM_FORMS': '1000',
            'bank_accounts-0-id': str(self.primary_account.id),
            'bank_accounts-0-issuer': str(self.issuer.id),
            'bank_accounts-0-label': 'Primary EUR',
            'bank_accounts-0-payment_method': 'Bank transfer',
            'bank_accounts-0-account_details': 'ES12 3456 7890 1234',
            'bank_accounts-0-is_active': 'on',
            'bank_accounts-0-sort_order': '1',
            'bank_accounts-0-is_default': 'on',
        }
        payload.update(overrides)
        return payload

    def test_updates_existing_company(self):
        payload = self._build_settings_payload()

        response = self.client.post(reverse('company:settings'), data=payload)

        self.assertRedirects(response, reverse('company:settings'))

        company = Company.objects.get(pk=self.issuer.company_id)
        self.assertEqual(company.name, 'New Co')
        self.assertEqual(company.customer_information_file_number, 'VAT999')
        self.assertEqual(company.bank_account_number, 'ES12 3456 7890 1234')
        self.assertEqual(company.payment_terms, 'Net 30 days')
        self.assertEqual(company.payment_term, self.term_15)
        self.assertEqual(company.contact_name, 'Accounts Payable')
        self.assertEqual(company.contact_email, 'billing@example.com')
        self.assertEqual(company.address.full_address, '123 Main St\nBarcelona')

        issuer = Issuer.objects.get(pk=self.issuer.pk)
        self.assertEqual(issuer.invoice_format, '{{YYYY}}-{{MM}}-{{ID}}')
        self.assertEqual(issuer.next_invoice_number, 12)

    def test_updates_existing_company_allows_duplicate_tax_id_during_manual_edit(self):
        duplicate = Company.objects.create(name='Existing Duplicate', customer_information_file_number=' vat999 ')

        response = self.client.post(reverse('company:settings'), data=self._build_settings_payload())

        self.assertRedirects(response, reverse('company:settings'))
        company = Company.objects.get(pk=self.issuer.company_id)
        self.assertEqual(company.customer_information_file_number, 'VAT999')
        self.assertEqual(
            {
                _normalize_company_tax_id(company.customer_information_file_number)
                for company in Company.objects.filter(pk__in=[company.pk, duplicate.pk])
            },
            {'VAT999'},
        )

    def test_updates_existing_company_allows_duplicate_name_and_contact_email_during_manual_edit(self):
        duplicate = Company.objects.create(name='new co', contact_email=' Billing@Example.com ')

        response = self.client.post(reverse('company:settings'), data=self._build_settings_payload())

        self.assertRedirects(response, reverse('company:settings'))
        company = Company.objects.get(pk=self.issuer.company_id)
        self.assertEqual(company.name, 'New Co')
        self.assertEqual(company.contact_email, 'billing@example.com')
        self.assertEqual(
            [
                (_normalize_company_contact_email(current.contact_email), current.name.casefold())
                for current in Company.objects.filter(pk__in=[company.pk, duplicate.pk]).order_by('pk')
            ],
            [('billing@example.com', 'new co'), ('billing@example.com', 'new co')],
        )

    def test_creates_company_when_missing(self):
        payload = {
            'create_new': '1',
            'issuer_company-name': 'My Company',
            'issuer_company-customer_information_file_number': 'VAT001',
            'issuer_company-payment_terms': 'Payment due in 15 days',
            'issuer_company-payment_term': str(self.term_30.id),
            'address-full_address': '1 Infinite Loop\nCupertino',
            'issuer_settings-invoice_format': 'INV-{{YY}}{{MM}}-{{ID}}',
            'issuer_settings-next_invoice_number': '5',
            'bank_accounts-TOTAL_FORMS': '1',
            'bank_accounts-INITIAL_FORMS': '0',
            'bank_accounts-MIN_NUM_FORMS': '0',
            'bank_accounts-MAX_NUM_FORMS': '1000',
            'bank_accounts-0-label': 'Primary EUR',
            'bank_accounts-0-payment_method': 'Bank transfer',
            'bank_accounts-0-account_details': 'BE68 5390 0754 7034',
            'bank_accounts-0-is_active': 'on',
            'bank_accounts-0-sort_order': '1',
            'bank_accounts-0-is_default': 'on',
        }

        response = self.client.post(reverse('company:settings'), data=payload)

        self.assertRedirects(response, reverse('company:settings'))

        issuer = Issuer.objects.order_by('-id').first()
        self.assertIsNotNone(issuer)
        self.assertIsNotNone(issuer.company)
        self.assertEqual(issuer.company.name, 'My Company')
        self.assertEqual(issuer.company.customer_information_file_number, 'VAT001')
        self.assertEqual(issuer.company.address.full_address, '1 Infinite Loop\nCupertino')
        self.assertEqual(issuer.company.payment_term, self.term_30)
        account = issuer.bank_accounts.get()
        self.assertEqual(account.account_details, 'BE68 5390 0754 7034')
        self.assertTrue(account.is_default)
        self.assertEqual(issuer.invoice_format, 'INV-{{YY}}{{MM}}-{{ID}}')
        self.assertEqual(issuer.next_invoice_number, 5)

    def test_adds_secondary_bank_account(self):
        payload = self._build_settings_payload(
            **{
                'bank_accounts-1-label': 'Secondary USD',
                'bank_accounts-1-payment_method': 'Wire transfer',
                'bank_accounts-1-account_details': 'US00 1111 2222',
                'bank_accounts-1-is_active': 'on',
                'bank_accounts-1-sort_order': '2',
            }
        )

        response = self.client.post(reverse('company:settings'), data=payload)

        self.assertRedirects(response, reverse('company:settings'))
        accounts = self.issuer.bank_accounts.order_by('sort_order')
        self.assertEqual(accounts.count(), 2)
        self.assertEqual(accounts[1].label, 'Secondary USD')
        self.assertFalse(accounts[1].is_default)

    def test_switches_default_bank_account(self):
        secondary = IssuerBankAccount.objects.create(
            issuer=self.issuer,
            label='Secondary USD',
            payment_method='Wire transfer',
            account_details='US00 1111 2222',
            is_active=True,
            sort_order=2,
        )
        payload = self._build_settings_payload(
            **{
                'bank_accounts-TOTAL_FORMS': '3',
                'bank_accounts-INITIAL_FORMS': '2',
                'bank_accounts-0-is_default': '',
                'bank_accounts-1-id': str(secondary.id),
                'bank_accounts-1-issuer': str(self.issuer.id),
                'bank_accounts-1-label': 'Secondary USD',
                'bank_accounts-1-payment_method': 'Wire transfer',
                'bank_accounts-1-account_details': 'US00 1111 2222',
                'bank_accounts-1-is_active': 'on',
                'bank_accounts-1-sort_order': '2',
                'bank_accounts-1-is_default': 'on',
            }
        )

        response = self.client.post(reverse('company:settings'), data=payload)

        self.assertRedirects(response, reverse('company:settings'))
        self.primary_account.refresh_from_db()
        secondary.refresh_from_db()
        self.assertFalse(self.primary_account.is_default)
        self.assertTrue(secondary.is_default)

    def test_deactivating_default_requires_another_active_default(self):
        payload = self._build_settings_payload(
            **{
                'bank_accounts-0-is_active': '',
            }
        )

        response = self.client.post(reverse('company:settings'), data=payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'The default bank account must be active.')
        self.primary_account.refresh_from_db()
        self.assertTrue(self.primary_account.is_active)
        self.assertTrue(self.primary_account.is_default)

    def test_deactivates_non_default_bank_account(self):
        secondary = IssuerBankAccount.objects.create(
            issuer=self.issuer,
            label='Secondary USD',
            payment_method='Wire transfer',
            account_details='US00 1111 2222',
            is_active=True,
            sort_order=2,
        )
        payload = self._build_settings_payload(
            **{
                'bank_accounts-TOTAL_FORMS': '3',
                'bank_accounts-INITIAL_FORMS': '2',
                'bank_accounts-1-id': str(secondary.id),
                'bank_accounts-1-issuer': str(self.issuer.id),
                'bank_accounts-1-label': 'Secondary USD',
                'bank_accounts-1-payment_method': 'Wire transfer',
                'bank_accounts-1-account_details': 'US00 1111 2222',
                'bank_accounts-1-sort_order': '2',
            }
        )

        response = self.client.post(reverse('company:settings'), data=payload)

        self.assertRedirects(response, reverse('company:settings'))
        secondary.refresh_from_db()
        self.assertFalse(secondary.is_active)
        self.assertFalse(secondary.is_default)


class CompanySelectionTests(AuthenticatedCompanyTestCase):
    def setUp(self):
        company_a = Company.objects.create(
            name='Company A',
            customer_information_file_number='VATA',
        )
        self.issuer_a = Issuer.objects.create(company=company_a)

        client_company_a = Company.objects.create(
            name='Client A',
            customer_information_file_number='CUSTA',
        )
        customer_a = Customer.objects.create(issuer=self.issuer_a, company=client_company_a)
        project_a = Project.objects.create(
            customer=customer_a,
            title='Project A',
            project_code='PRA',
        )
        self.invoice_a = Invoice.objects.create(
            issuer=self.issuer_a,
            customer=customer_a,
            project=project_a,
            issued_date=date(2024, 1, 15),
            status=Invoice.STATUS_DRAFT,
        )

        company_b = Company.objects.create(
            name='Company B',
            customer_information_file_number='VATB',
        )
        self.issuer_b = Issuer.objects.create(company=company_b)

        client_company_b = Company.objects.create(
            name='Client B',
            customer_information_file_number='CUSTB',
        )
        customer_b = Customer.objects.create(issuer=self.issuer_b, company=client_company_b)
        project_b = Project.objects.create(
            customer=customer_b,
            title='Project B',
            project_code='PRB',
        )
        self.invoice_b = Invoice.objects.create(
            issuer=self.issuer_b,
            customer=customer_b,
            project=project_b,
            issued_date=date(2024, 2, 10),
            status=Invoice.STATUS_DRAFT,
        )
        OrderLine.objects.create(invoice=self.invoice_b, description='Consulting', quantity=1, unit_price=Decimal('100'))
        self.customer_a = customer_a
        self.customer_b = customer_b
        self.project_a = project_a
        self.project_b = project_b

        self.user = self.create_user_with_issuers(
            [self.issuer_a, self.issuer_b],
            username='company-selection-user',
            email='selection@example.com',
        )
        self.client.force_login(self.user)

    def _activate_company(self, issuer):
        self.set_active_company(issuer=issuer)

    def test_switch_company_updates_session(self):
        response = self.client.post(
            reverse('company:switch'),
            data={'company_id': self.issuer_b.company_id, 'next': reverse('invoices:list')},
        )

        self.assertRedirects(response, reverse('invoices:list'))
        self.assertEqual(self.client.session['active_company_id'], self.issuer_b.company_id)

    def test_cross_company_dashboard_route_is_available(self):
        response = self.client.get(reverse('cross_company_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_cross_company_dashboard'])
        self.assertEqual(
            [issuer.pk for issuer in response.context['cross_company_issuers']],
            [self.issuer_a.pk, self.issuer_b.pk],
        )

    def test_company_switcher_menu_includes_cross_company_dashboard_entry(self):
        self._activate_company(self.issuer_a)

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-testid="company-switcher-menu"', html=False)
        self.assertContains(response, f'href="{reverse("cross_company_dashboard")}"', html=False)
        self.assertContains(response, '<span class="company-switcher__option-name">Dashboard</span>', html=True)

    def test_cross_company_dashboard_marks_company_switcher_entry_as_current_page(self):
        self._activate_company(self.issuer_a)

        response = self.client.get(reverse('cross_company_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<span class="company-switcher__name" data-testid="company-switcher-active-name">\n                  Dashboard\n                </span>',
            html=True,
        )
        self.assertContains(response, f'href="{reverse("cross_company_dashboard")}"', html=False)
        self.assertContains(response, 'aria-current="page"', html=False)
        self.assertNotContains(
            response,
            f'data-company-id="{self.issuer_a.company_id}" aria-current="true"',
            html=False,
        )
        self.assertNotContains(
            response,
            f'data-company-id="{self.issuer_b.company_id}" aria-current="true"',
            html=False,
        )
        self.assertNotContains(response, 'company-switcher__check', html=False)

    def test_cross_company_dashboard_hides_company_scoped_sidebar_navigation_and_customers(self):
        self._activate_company(self.issuer_a)

        response = self.client.get(reverse('cross_company_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'class="sidebar__links"', html=False)
        self.assertNotContains(response, f'href="{reverse("customers:list")}"', html=False)
        self.assertNotContains(response, f'href="{reverse("projects:list")}"', html=False)
        self.assertNotContains(response, f'href="{reverse("invoices:list")}"', html=False)
        self.assertNotContains(response, f'href="{reverse("expenses:list")}"', html=False)
        self.assertNotContains(response, 'class="sidebar__customers sidebar__customers--desktop"', html=False)
        self.assertNotContains(response, 'class="sidebar__customers sidebar__customers--mobile"', html=False)
        self.assertNotContains(response, 'Browse customers', html=False)
        self.assertNotContains(response, f'href="{reverse("customers:detail", args=[self.invoice_a.customer_id])}"', html=False)
        self.assertNotContains(response, f'href="{reverse("customers:detail", args=[self.invoice_b.customer_id])}"', html=False)

    def test_company_scoped_dashboard_keeps_selected_company_and_sidebar_content(self):
        self._activate_company(self.issuer_a)

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<span class="company-switcher__name" data-testid="company-switcher-active-name">\n                  Company A\n                </span>',
            html=True,
        )
        self.assertContains(
            response,
            f'data-company-id="{self.issuer_a.company_id}" aria-current="true"',
            html=False,
        )
        self.assertContains(response, 'company-switcher__check', html=False)
        self.assertContains(response, 'class="sidebar__links"', html=False)
        self.assertContains(response, f'href="{reverse("customers:list")}"', html=False)
        self.assertContains(response, f'href="{reverse("projects:list")}"', html=False)
        self.assertContains(response, f'href="{reverse("invoices:list")}"', html=False)
        self.assertContains(response, f'href="{reverse("expenses:list")}"', html=False)
        self.assertContains(response, 'sidebar__customers--desktop', html=False)
        self.assertContains(response, 'sidebar__customers--mobile', html=False)
        self.assertContains(response, 'Browse customers', html=False)
        self.assertContains(
            response,
            f'href="{reverse("customers:detail", args=[self.invoice_a.customer_id])}"',
            html=False,
        )

    def test_cross_company_dashboard_does_not_require_active_company(self):
        session = self.client.session
        session.pop('active_company_id', None)
        session.save()

        response = self.client.get(reverse('cross_company_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_cross_company_dashboard'])

    def test_cross_company_switch_redirect_opens_invoice_detail_in_target_company(self):
        self._activate_company(self.issuer_a)

        response = self.client.get(
            reverse('cross_company_switch_redirect'),
            {
                'company_id': self.issuer_b.company_id,
                'next': reverse('invoices:edit', args=[self.invoice_b.id]),
            },
            follow=True,
        )

        self.assertRedirects(response, reverse('invoices:edit', args=[self.invoice_b.id]))
        self.assertEqual(self.client.session['active_company_id'], self.issuer_b.company_id)
        self.assertEqual(response.context['invoice'].pk, self.invoice_b.pk)

    def test_cross_company_switch_redirect_preserves_customer_detail_querystring(self):
        self._activate_company(self.issuer_a)

        response = self.client.get(
            reverse('cross_company_switch_redirect'),
            {
                'company_id': self.issuer_b.company_id,
                'next': f"{reverse('customers:detail', args=[self.invoice_b.customer_id])}?tab=payments",
            },
            follow=True,
        )

        self.assertRedirects(
            response,
            f"{reverse('customers:detail', args=[self.invoice_b.customer_id])}?tab=payments",
        )
        self.assertEqual(self.client.session['active_company_id'], self.issuer_b.company_id)
        self.assertEqual(response.context['customer'].pk, self.invoice_b.customer_id)
        self.assertEqual(response.context['active_tab'], 'payments')

    def test_cross_company_switch_redirect_opens_project_detail_without_prior_active_company(self):
        session = self.client.session
        session.pop('active_company_id', None)
        session.save()

        response = self.client.get(
            reverse('cross_company_switch_redirect'),
            {
                'company_id': self.issuer_b.company_id,
                'next': reverse('projects:detail', args=[self.project_b.id]),
            },
            follow=True,
        )

        self.assertRedirects(response, reverse('projects:detail', args=[self.project_b.id]))
        self.assertEqual(self.client.session['active_company_id'], self.issuer_b.company_id)
        self.assertEqual(response.context['project'].pk, self.project_b.pk)

    def test_switch_company_from_invoice_detail_redirects_to_invoice_list(self):
        response = self.client.post(
            reverse('company:switch'),
            data={'company_id': self.issuer_b.company_id, 'next': reverse('invoices:edit', args=[self.invoice_a.id])},
        )

        self.assertRedirects(response, reverse('invoices:list'))
        self.assertEqual(self.client.session['active_company_id'], self.issuer_b.company_id)

    def test_switch_company_preserves_invoice_list_filters(self):
        response = self.client.post(
            reverse('company:switch'),
            data={'company_id': self.issuer_b.company_id, 'next': f"{reverse('invoices:list')}?date_range=all&status=draft"},
        )

        self.assertRedirects(response, f"{reverse('invoices:list')}?date_range=all&status=draft")
        self.assertEqual(self.client.session['active_company_id'], self.issuer_b.company_id)

    def test_view_invoices_filters_by_active_company(self):
        self._activate_company(self.issuer_b)

        response = self.client.get(reverse('invoices:list'), {'date_range': 'all'})

        invoices_page = response.context['invoices_list']
        self.assertEqual(invoices_page.paginator.count, 1)
        self.assertEqual(list(invoices_page)[0].issuer, self.issuer_b)

    def test_view_projects_filters_by_active_company(self):
        self._activate_company(self.issuer_b)
        self.invoice_b.status = Invoice.STATUS_INVOICED
        self.invoice_b.total_due = Decimal('100')
        self.invoice_b.amount_due = Decimal('100')
        self.invoice_b.save()

        response = self.client.get(reverse('projects:list'))

        project_list = response.context['project_list']
        self.assertEqual(list(project_list), [self.project_b])
        self.assertEqual(len(response.context['project_rows']), 1)

    def test_view_projects_includes_transactionless_and_date_filtered_projects(self):
        self._activate_company(self.issuer_b)
        self.invoice_b.status = Invoice.STATUS_INVOICED
        self.invoice_b.issued_date = date(2024, 2, 10)
        self.invoice_b.total_due = Decimal('100')
        self.invoice_b.amount_due = Decimal('100')
        self.invoice_b.amount_paid = Decimal('0')
        self.invoice_b.save()
        transactionless_project = Project.objects.create(
            customer=self.customer_b,
            title='Transactionless Project',
            project_code='NOBILL',
        )
        inactive_project = Project.objects.create(
            customer=self.customer_b,
            title='Inactive Transactionless Project',
            project_code='INACTB',
            status=Project.STATUS_INACTIVE,
        )

        response = self.client.get(reverse('projects:list'), {'date_range': 'all'})

        projects_by_id = {project.pk: project for project in response.context['project_list']}
        self.assertIn(self.project_b.pk, projects_by_id)
        self.assertIn(transactionless_project.pk, projects_by_id)
        self.assertNotIn(self.project_a.pk, projects_by_id)
        self.assertNotIn(inactive_project.pk, projects_by_id)
        self.assertEqual(projects_by_id[self.project_b.pk].pending_balance, Decimal('100'))
        self.assertEqual(projects_by_id[transactionless_project.pk].pending_balance, Decimal('0'))
        self.assertEqual(projects_by_id[transactionless_project.pk].paid_total, Decimal('0'))

        date_filtered_response = self.client.get(reverse('projects:list'), {'date_range': 'this_month'})

        date_filtered_projects = {
            project.pk: project for project in date_filtered_response.context['project_list']
        }
        self.assertIn(self.project_b.pk, date_filtered_projects)
        self.assertIn(transactionless_project.pk, date_filtered_projects)
        self.assertEqual(date_filtered_projects[self.project_b.pk].pending_balance, Decimal('0'))

    def test_view_invoices_handles_blank_decimal_values(self):
        self._activate_company(self.issuer_b)

        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE invoices_invoice SET sub_total='' WHERE id=%s",
                [self.invoice_b.id],
            )
        response = self.client.get(reverse('invoices:list'), {'date_range': 'all'})
        self.assertEqual(response.status_code, 200)
        invoices_page = response.context['invoices_list']
        self.assertEqual(list(invoices_page)[0].sub_total, Decimal('0'))

    def test_project_recent_items_endpoint(self):
        self._activate_company(self.issuer_b)

        self.invoice_b.status = Invoice.STATUS_INVOICED
        self.invoice_b.save()

        response = self.client.get(reverse('projects:recent_items', args=[self.project_b.id]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['items']), 1)
        self.assertEqual(data['items'][0]['description'], 'Consulting')

    def test_project_detail_balance_calculations(self):
        self._activate_company(self.issuer_b)

        self.invoice_b.status = Invoice.STATUS_INVOICED
        self.invoice_b.issued_date = date.today() - timedelta(days=2)
        self.invoice_b.due_date = date.today() + timedelta(days=7)
        self.invoice_b.total_due = Decimal('100')
        self.invoice_b.amount_due = Decimal('100')
        self.invoice_b.save()

        overdue_invoice = Invoice.objects.create(
            issuer=self.issuer_b,
            customer=self.invoice_b.customer,
            project=self.project_b,
            status=Invoice.STATUS_INVOICED,
            issued_date=date(2024, 3, 5),
            due_date=date.today() - timedelta(days=1),
            total_due=Decimal('50'),
            amount_due=Decimal('50'),
        )
        OrderLine.objects.create(invoice=overdue_invoice, description='Follow-up', quantity=1, unit_price=Decimal('50'))
        Invoice.objects.filter(pk=overdue_invoice.pk).update(amount_overdue=Decimal('0'))

        response = self.client.get(reverse('projects:detail', args=[self.project_b.id]), {'date_range': 'all'})
        self.assertEqual(response.context['pending_balance'], Decimal('150'))
        self.assertEqual(response.context['overdue_total'], Decimal('50'))

        projects_response = self.client.get(reverse('projects:list'), {'date_range': 'all'})
        project = projects_response.context['project_list'].get(pk=self.project_b.pk)
        self.assertEqual(project.overdue_total, Decimal('50'))

    def test_project_activity_distinguishes_unpaid_and_overdue_amounts(self):
        self._activate_company(self.issuer_b)

        self.invoice_b.status = Invoice.STATUS_INVOICED
        self.invoice_b.issued_date = date.today() - timedelta(days=2)
        self.invoice_b.due_date = date.today() + timedelta(days=7)
        self.invoice_b.total_due = Decimal('100')
        self.invoice_b.amount_due = Decimal('100')
        self.invoice_b.save()

        overdue_invoice = Invoice.objects.create(
            issuer=self.issuer_b,
            customer=self.invoice_b.customer,
            project=self.project_b,
            status=Invoice.STATUS_INVOICED,
            issued_date=date(2024, 3, 5),
            due_date=date.today() - timedelta(days=1),
            total_due=Decimal('50'),
            amount_due=Decimal('50'),
        )
        OrderLine.objects.create(invoice=overdue_invoice, description='Follow-up', quantity=1, unit_price=Decimal('50'))
        Invoice.objects.filter(pk=overdue_invoice.pk).update(amount_overdue=Decimal('0'))

        response = self.client.get(reverse('projects:detail', args=[self.project_b.id]), {'date_range': 'all'})

        self.assertContains(response, 'account-table__amount-note--current', count=1)
        self.assertContains(response, 'account-table__amount-note--danger', count=1)
        self.assertContains(response, '(100.00 €)')
        self.assertContains(response, '(50.00 €)')


class DefaultCompanySelectionTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

        company_a = Company.objects.create(name='Company A', customer_information_file_number='VATA')
        self.issuer_a = Issuer.objects.create(company=company_a)

        company_b = Company.objects.create(name='Company B', customer_information_file_number='VATB')
        self.issuer_b = Issuer.objects.create(company=company_b)

        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username='default-company-user',
            email='user@example.com',
            password=IssuerUserTestMixin.build_test_password(),
        )
        self.issuer_a.users.add(self.user)
        self.issuer_b.users.add(self.user)

        profile = self.user.profile
        profile.default_company = company_b
        profile.save()

    def _build_request(self):
        request = self.factory.get('/invoices/')
        request.user = self.user
        middleware = SessionMiddleware(lambda _request: None)
        middleware.process_request(request)
        request.session.save()
        return request

    def test_uses_profile_default_when_session_empty(self):
        request = self._build_request()

        issuer = get_active_issuer(request)

        self.assertEqual(issuer.pk, self.issuer_b.pk)
        self.assertEqual(request.session.get('active_company_id'), self.issuer_b.company_id)

    def test_session_company_takes_precedence_over_profile_default(self):
        request = self._build_request()
        request.session['active_company_id'] = self.issuer_a.company_id
        request.session.save()

        issuer = get_active_issuer(request)

        self.assertEqual(issuer.pk, self.issuer_a.pk)
