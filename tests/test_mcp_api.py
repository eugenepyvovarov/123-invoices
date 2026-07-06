from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from invoices.models import Company, Customer, Invoice, Issuer, IssuerBankAccount, OrderLine, Project
from tests.support import IssuerUserTestMixin


class InvoicesMCPAPITests(IssuerUserTestMixin, TestCase):
    def setUp(self):
        self.issuer = self.create_issuer(company=Company.objects.create(name='Issuer Co', customer_information_file_number='ES12345678Z'))
        self.other_issuer = self.create_issuer(company=Company.objects.create(name='Other Co'))
        self.customer = Customer.objects.create(
            issuer=self.issuer,
            company=Company.objects.create(name='Acme Client'),
            billing_email='billing@example.test',
        )
        self.project = Project.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            title='Retainer',
            project_code='RET',
        )
        self.bank_account = IssuerBankAccount.objects.create(
            issuer=self.issuer,
            label='Main',
            payment_method='Bank transfer',
            is_default=True,
        )
        self.user = self.create_user_with_issuers(issuers=[self.issuer])
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

    def test_api_requires_token_authentication(self):
        response = APIClient().get('/api/invoices/')

        self.assertEqual(response.status_code, 401)

    def test_reference_routes_are_issuer_scoped_for_token_user(self):
        Customer.objects.create(issuer=self.other_issuer, company=Company.objects.create(name='Hidden Client'))

        issuers = self.client.get('/api/issuers/')
        customers = self.client.get('/api/customers/', {'search': 'Client'})
        projects = self.client.get('/api/projects/', {'customer': self.customer.id})
        bank_accounts = self.client.get('/api/bank-accounts/', {'issuer': self.issuer.id})

        self.assertEqual(issuers.status_code, 200)
        self.assertEqual([item['id'] for item in issuers.json()['results']], [self.issuer.id])
        self.assertEqual(customers.json()['results'][0]['id'], self.customer.id)
        self.assertEqual(projects.json()['results'][0]['id'], self.project.id)
        self.assertEqual(bank_accounts.json()['results'][0]['id'], self.bank_account.id)

    def test_create_update_and_finalize_draft_invoice_through_api(self):
        create_response = self.client.post(
            '/api/invoices/',
            {
                'issuer': self.issuer.id,
                'project': self.project.id,
                'bank_account': self.bank_account.id,
                'issued_date': '2026-07-06',
                'status': 'draft',
                'lines': [
                    {'description': 'Strategy work', 'quantity': '2', 'unit_price': '100.00'},
                ],
            },
            format='json',
        )

        self.assertEqual(create_response.status_code, 201)
        invoice_id = create_response.json()['id']
        self.assertEqual(create_response.json()['status'], Invoice.STATUS_DRAFT)
        self.assertEqual(create_response.json()['totals']['total'], '200.00')

        update_response = self.client.patch(
            f'/api/invoices/{invoice_id}/',
            {'lines': [{'description': 'Strategy work', 'quantity': '3', 'unit_price': '100.00'}]},
            format='json',
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()['totals']['total'], '300.00')

        missing_confirm = self.client.post(f'/api/invoices/{invoice_id}/finalize/', {'confirm': False}, format='json')
        finalized = self.client.post(f'/api/invoices/{invoice_id}/finalize/', {'confirm': True}, format='json')
        rejected_update = self.client.patch(f'/api/invoices/{invoice_id}/', {'notes': 'late change'}, format='json')

        self.assertEqual(missing_confirm.status_code, 400)
        self.assertEqual(finalized.status_code, 200)
        self.assertEqual(finalized.json()['status'], Invoice.STATUS_INVOICED)
        self.assertEqual(rejected_update.status_code, 409)

    def test_create_draft_rejects_non_draft_status_and_unsupported_fields(self):
        non_draft = self.client.post(
            '/api/invoices/',
            {'issuer': self.issuer.id, 'project': self.project.id, 'status': 'paid'},
            format='json',
        )
        unsupported = self.client.post(
            '/api/invoices/',
            {'issuer': self.issuer.id, 'project': self.project.id, 'filesystem_path': '/tmp/invoice.pdf'},
            format='json',
        )

        self.assertEqual(non_draft.status_code, 400)
        self.assertEqual(unsupported.status_code, 400)

    def test_invoice_search_detail_suggestions_and_pdf_metadata_routes_exist(self):
        invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            bank_account=self.bank_account,
            issued_date=date(2026, 7, 6),
            status=Invoice.STATUS_DRAFT,
            total_due=Decimal('100.00'),
        )
        OrderLine.objects.create(invoice=invoice, description='Consulting', quantity=1, unit_price=100)

        search = self.client.get('/api/invoices/', {'search': 'Acme'})
        detail = self.client.get(f'/api/invoices/{invoice.id}/')
        suggestions = self.client.get('/api/invoice-line-suggestions/', {'search': 'Consulting'})
        pdf_metadata = self.client.get(f'/api/invoices/{invoice.id}/pdf/', {'mode': 'metadata'})

        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.json()['results'][0]['id'], invoice.id)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(suggestions.status_code, 200)
        self.assertEqual(suggestions.json()['results'][0]['description'], 'Consulting')
        self.assertEqual(pdf_metadata.status_code, 200)
        self.assertFalse(pdf_metadata.json()['pdf']['available'])

    def test_generate_pdf_uses_api_checked_invoice_scope(self):
        invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            issued_date=date(2026, 7, 6),
            status=Invoice.STATUS_DRAFT,
        )

        with mock.patch('api.views.save_invoice_pdf') as save_pdf:
            response = self.client.post(f'/api/invoices/{invoice.id}/generate-pdf/')

        self.assertEqual(response.status_code, 200)
        save_pdf.assert_called_once()

    def test_api_token_user_cannot_access_other_issuer_invoice(self):
        hidden_customer = Customer.objects.create(issuer=self.other_issuer, company=Company.objects.create(name='Hidden Client'))
        hidden_project = Project.objects.create(issuer=self.other_issuer, customer=hidden_customer, title='Hidden', project_code='HID')
        hidden_invoice = Invoice.objects.create(
            issuer=self.other_issuer,
            customer=hidden_customer,
            project=hidden_project,
            issued_date=date(2026, 7, 6),
            status=Invoice.STATUS_DRAFT,
        )

        response = self.client.get(f'/api/invoices/{hidden_invoice.id}/')

        self.assertEqual(response.status_code, 404)
