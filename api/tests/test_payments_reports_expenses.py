import tempfile
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import ApiToken
from invoices.models import Company, Customer, Expense, Invoice, Issuer, Payment, PaymentApplication, Project


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ApiPaymentsReportsExpensesTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='api-chunk-user')
        self.other_user = User.objects.create_user(username='api-chunk-other')
        self.issuer = self._issuer('Alpha API Ltd', self.user)
        self.second_issuer = self._issuer('Beta API Ltd', self.user)
        self.other_issuer = self._issuer('Hidden API Ltd', self.other_user)
        self.customer = self._customer(self.issuer, 'Alpha Customer')
        self.second_customer = self._customer(self.second_issuer, 'Beta Customer')
        self.other_customer = self._customer(self.other_issuer, 'Hidden Customer')
        self.project = Project.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            title='Alpha Project',
            project_code='ALPHA-API',
        )
        self.invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            status=Invoice.STATUS_INVOICED,
            issued_date=date(2026, 7, 1),
            due_date=date(2026, 7, 31),
            total_due=Decimal('100.00'),
            amount_due=Decimal('100.00'),
        )
        self.second_invoice = Invoice.objects.create(
            issuer=self.second_issuer,
            customer=self.second_customer,
            status=Invoice.STATUS_INVOICED,
            issued_date=date(2026, 7, 2),
            total_due=Decimal('50.00'),
            amount_due=Decimal('50.00'),
        )
        self.other_invoice = Invoice.objects.create(
            issuer=self.other_issuer,
            customer=self.other_customer,
            status=Invoice.STATUS_INVOICED,
            issued_date=date(2026, 7, 3),
            total_due=Decimal('900.00'),
            amount_due=Decimal('900.00'),
        )
        _, self.token = ApiToken.issue(owner=self.user, name='Chunk token')
        _, self.other_token = ApiToken.issue(owner=self.other_user, name='Other chunk token')

    def _issuer(self, company_name, user):
        issuer = Issuer.objects.create(company=Company.objects.create(name=company_name))
        issuer.users.add(user)
        return issuer

    def _customer(self, issuer, company_name):
        return Customer.objects.create(issuer=issuer, company=Company.objects.create(name=company_name))

    def auth(self, token=None):
        return {'HTTP_AUTHORIZATION': f'Bearer {token or self.token}'}

    def test_payment_application_recalculates_invoice_amounts_and_status(self):
        payment_response = self.client.post(
            reverse('api:payment-list'),
            {
                'issuer': self.issuer.pk,
                'customer': self.customer.pk,
                'project': self.project.pk,
                'external_id': 'pay-api-1',
                'amount': '100.00',
                'received_at': '2026-07-10',
                'memo': 'Paid by bank transfer',
            },
            content_type='application/json',
            **self.auth(),
        )
        self.assertEqual(payment_response.status_code, 201)

        application_response = self.client.post(
            reverse('api:paymentapplication-list'),
            {
                'payment': payment_response.json()['id'],
                'invoice': self.invoice.pk,
                'amount_applied': '100.00',
                'external_id': 'app-api-1',
            },
            content_type='application/json',
            **self.auth(),
        )

        self.assertEqual(application_response.status_code, 201)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal('100.00'))
        self.assertEqual(self.invoice.amount_due, Decimal('0.00'))
        self.assertEqual(self.invoice.status, Invoice.STATUS_PAID)

    def test_payment_application_rejects_cross_account_invoice(self):
        payment = Payment.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            amount=Decimal('10.00'),
            received_at=date(2026, 7, 10),
        )

        response = self.client.post(
            reverse('api:paymentapplication-list'),
            {'payment': payment.pk, 'invoice': self.other_invoice.pk, 'amount_applied': '10.00'},
            content_type='application/json',
            **self.auth(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('invoice', response.json()['error']['details'])

    def test_dashboard_report_supports_account_level_and_issuer_filtered_totals(self):
        payment = Payment.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            amount=Decimal('25.00'),
            received_at=date(2026, 7, 11),
        )
        PaymentApplication.objects.create(payment=payment, invoice=self.invoice, amount_applied=Decimal('25.00'))
        Expense.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            paid_date=date(2026, 7, 12),
            amount=Decimal('15.00'),
            description='Alpha expense',
        )
        Expense.objects.create(
            issuer=self.second_issuer,
            customer=self.second_customer,
            paid_date=date(2026, 7, 12),
            amount=Decimal('5.00'),
            description='Beta expense',
        )
        Expense.objects.create(
            issuer=self.other_issuer,
            customer=self.other_customer,
            paid_date=date(2026, 7, 12),
            amount=Decimal('500.00'),
            description='Hidden expense',
        )

        account_response = self.client.get(reverse('api:report-dashboard'), **self.auth())
        filtered_response = self.client.get(
            reverse('api:report-dashboard'), {'issuer': self.issuer.pk}, **self.auth()
        )

        self.assertEqual(account_response.status_code, 200)
        self.assertEqual(account_response.json()['totals']['invoice_total'], '150.00')
        self.assertEqual(account_response.json()['totals']['expense_total'], '20.00')
        self.assertEqual(filtered_response.status_code, 200)
        self.assertEqual(filtered_response.json()['issuer_ids'], [self.issuer.pk])
        self.assertEqual(filtered_response.json()['totals']['invoice_total'], '100.00')
        self.assertEqual(filtered_response.json()['totals']['expense_total'], '15.00')
        self.assertEqual(filtered_response.json()['monthly_revenue'][0]['month'], '2026-07-01')

    def test_expense_create_update_attachment_download_and_permissions(self):
        upload = SimpleUploadedFile('receipt.pdf', b'%PDF-1.4\nreceipt', content_type='application/pdf')
        create_response = self.client.post(
            reverse('api:expense-list'),
            {
                'issuer': self.issuer.pk,
                'customer': self.customer.pk,
                'project': self.project.pk,
                'paid_date': '2026-07-12',
                'amount': '42.50',
                'description': 'Receipt upload',
                'attachment': upload,
            },
            **self.auth(),
        )
        self.assertEqual(create_response.status_code, 201)
        payload = create_response.json()
        self.assertTrue(payload['has_attachment'])
        self.assertTrue(payload['attachment_url'].endswith(f"/api/expenses/{payload['id']}/download-attachment/"))

        download_response = self.client.get(reverse('api:expense-download-attachment', args=[payload['id']]), **self.auth())
        self.assertEqual(download_response.status_code, 200)
        self.assertIn(b'%PDF-1.4', b''.join(download_response.streaming_content))

        blocked_response = self.client.get(
            reverse('api:expense-download-attachment', args=[payload['id']]),
            **self.auth(self.other_token),
        )
        self.assertEqual(blocked_response.status_code, 404)

        update_response = self.client.patch(
            reverse('api:expense-detail', args=[payload['id']]),
            {'description': 'Updated receipt', 'remove_attachment': True},
            content_type='application/json',
            **self.auth(),
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertFalse(update_response.json()['has_attachment'])

    def test_expense_upload_rejects_invalid_attachment_type(self):
        upload = SimpleUploadedFile('receipt.exe', b'not allowed', content_type='application/octet-stream')
        response = self.client.post(
            reverse('api:expense-list'),
            {
                'issuer': self.issuer.pk,
                'paid_date': '2026-07-12',
                'amount': '42.50',
                'attachment': upload,
            },
            **self.auth(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('attachment', response.json()['error']['details'])
