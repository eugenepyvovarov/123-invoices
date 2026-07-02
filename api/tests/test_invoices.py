import tempfile
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import ApiToken
from invoices.models import Company, Customer, Invoice, Issuer, IssuerBankAccount, OrderLine, Project


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ApiInvoiceEndpointTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='invoice-api-user', password='test-password')
        self.other_user = User.objects.create_user(username='invoice-api-other', password='test-password')
        self.issuer = self._issuer('API Issuer', self.user)
        self.other_issuer = self._issuer('Other Issuer', self.other_user)
        self.bank_account = IssuerBankAccount.objects.create(
            issuer=self.issuer,
            label='Main account',
            payment_method='Bank transfer',
            account_details='IBAN API',
            is_default=True,
        )
        self.customer = Customer.objects.create(
            issuer=self.issuer,
            company=Company.objects.create(name='API Customer'),
        )
        self.project = Project.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            title='API Project',
            project_code='API-1',
        )
        self.other_customer = Customer.objects.create(
            issuer=self.other_issuer,
            company=Company.objects.create(name='Hidden Customer'),
        )
        _, self.token = ApiToken.issue(owner=self.user, name='Invoice token')
        _, self.other_token = ApiToken.issue(owner=self.other_user, name='Other invoice token')

    def _issuer(self, company_name, user):
        issuer = Issuer.objects.create(company=Company.objects.create(name=company_name))
        issuer.users.add(user)
        return issuer

    def auth(self, token=None):
        return {'HTTP_AUTHORIZATION': f'Bearer {token or self.token}'}

    def test_create_update_finalize_invoice_with_nested_order_lines(self):
        create_response = self.client.post(
            reverse('api:invoice-list'),
            {
                'issuer': self.issuer.pk,
                'customer': self.customer.pk,
                'project': self.project.pk,
                'bank_account': self.bank_account.pk,
                'external_id': 'invoice-api-1',
                'issued_date': '2026-07-02',
                'tax_value': '20.00',
                'order_lines': [
                    {
                        'external_id': 'line-api-1',
                        'description': 'Consulting',
                        'quantity': '2.000',
                        'unit_price': '100.00',
                    },
                    {
                        'description': 'Expense recharge',
                        'line_type': OrderLine.LINE_TYPE_EXPENSE,
                        'manual_total': True,
                        'line_total': '25.00',
                    },
                ],
            },
            content_type='application/json',
            **self.auth(),
        )

        self.assertEqual(create_response.status_code, 201)
        payload = create_response.json()
        self.assertEqual(payload['status'], Invoice.STATUS_DRAFT)
        self.assertEqual(Decimal(payload['sub_total']), Decimal('225.00'))
        self.assertEqual(Decimal(payload['total_due']), Decimal('270.00'))
        self.assertEqual(len(payload['order_lines']), 2)

        invoice_id = payload['id']
        retained_line_id = payload['order_lines'][0]['id']
        update_response = self.client.patch(
            reverse('api:invoice-detail', args=[invoice_id]),
            {
                'notes': 'Updated draft notes',
                'order_lines': [
                    {
                        'id': retained_line_id,
                        'description': 'Consulting updated',
                        'quantity': '3.000',
                        'unit_price': '100.00',
                    }
                ],
            },
            content_type='application/json',
            **self.auth(),
        )

        self.assertEqual(update_response.status_code, 200)
        updated = update_response.json()
        self.assertEqual(updated['notes'], 'Updated draft notes')
        self.assertEqual(len(updated['order_lines']), 1)
        self.assertEqual(Decimal(updated['sub_total']), Decimal('300.00'))
        self.assertEqual(Decimal(updated['total_due']), Decimal('360.00'))

        finalize_response = self.client.post(
            reverse('api:invoice-finalize', args=[invoice_id]),
            **self.auth(),
        )

        self.assertEqual(finalize_response.status_code, 200)
        self.assertEqual(finalize_response.json()['status'], Invoice.STATUS_INVOICED)

    def test_finalized_invoice_cannot_be_updated_or_deleted(self):
        invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            status=Invoice.STATUS_INVOICED,
            issued_date=date(2026, 7, 2),
            total_due=Decimal('50.00'),
        )

        update_response = self.client.patch(
            reverse('api:invoice-detail', args=[invoice.pk]),
            {'notes': 'blocked'},
            content_type='application/json',
            **self.auth(),
        )
        delete_response = self.client.delete(reverse('api:invoice-detail', args=[invoice.pk]), **self.auth())

        self.assertEqual(update_response.status_code, 400)
        self.assertEqual(delete_response.status_code, 400)
        invoice.refresh_from_db()
        self.assertNotEqual(invoice.notes, 'blocked')

    def test_pdf_generation_and_authenticated_download_are_account_scoped(self):
        invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            issued_date=date(2026, 7, 2),
        )
        OrderLine.objects.create(invoice=invoice, description='PDF line', quantity=1, unit_price=Decimal('10.00'))

        def fake_save_pdf(request, invoice_id):
            pdf_invoice = Invoice.objects.get(pk=invoice_id)
            pdf_invoice.pdf_document.save('api-invoice.pdf', ContentFile(b'%PDF-1.4\napi test\n'))
            return True

        with patch('api.views.save_invoice_pdf', side_effect=fake_save_pdf):
            generate_response = self.client.post(
                reverse('api:invoice-generate-pdf', args=[invoice.pk]),
                **self.auth(),
            )

        self.assertEqual(generate_response.status_code, 200)
        self.assertTrue(generate_response.json()['has_pdf'])

        download_response = self.client.get(reverse('api:invoice-download-pdf', args=[invoice.pk]), **self.auth())
        self.assertEqual(download_response.status_code, 200)
        self.assertEqual(download_response['Content-Type'], 'application/pdf')
        self.assertIn(b'%PDF-1.4', b''.join(download_response.streaming_content))

        blocked_response = self.client.get(
            reverse('api:invoice-download-pdf', args=[invoice.pk]),
            **self.auth(self.other_token),
        )
        self.assertEqual(blocked_response.status_code, 404)

    def test_invoice_create_rejects_cross_account_customer(self):
        response = self.client.post(
            reverse('api:invoice-list'),
            {
                'issuer': self.issuer.pk,
                'customer': self.other_customer.pk,
                'order_lines': [{'description': 'Blocked', 'quantity': '1.000', 'unit_price': '10.00'}],
            },
            content_type='application/json',
            **self.auth(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('customer', response.json()['error']['details'])
