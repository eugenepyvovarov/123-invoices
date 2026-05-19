from datetime import date

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from invoices.models import Expense

from .base import ExpenseViewsTestCase


class ExpenseDrawerViewTests(ExpenseViewsTestCase):
    def test_drawer_uses_updated_exclude_from_reports_label(self):
        response = self.client.get(reverse('expenses:drawer_new'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Exclude from reports')
        self.assertNotContains(response, 'Exclude from dashboard')
        self.assertNotContains(response, 'dashboard spending totals')

    def test_drawer_creates_expense_with_project(self):
        response = self.client.post(
            reverse('expenses:drawer_new'),
            data={
                'paid_date': date.today().isoformat(),
                'amount': '150.00',
                'project': str(self.project.id),
                'customer': '',
                'description': 'Design subcontractor',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(Expense.objects.filter(description='Design subcontractor').exists())
        created = Expense.objects.get(description='Design subcontractor')
        self.assertEqual(created.customer, self.customer)

    def test_drawer_async_upload_returns_filtered_expense_list_fragment(self):
        list_url = f'{reverse("expenses:list")}?has_attachment=without&date_range=all&q=Initial'

        response = self.client.post(
            reverse('expenses:drawer', args=[self.expense.pk]),
            data={
                'paid_date': self.expense.paid_date.isoformat(),
                'amount': '300.00',
                'customer': str(self.customer.pk),
                'project': str(self.project.pk),
                'description': 'Initial expense',
                'attachment': SimpleUploadedFile('receipt.pdf', b'receipt', content_type='application/pdf'),
                'current_list_url': list_url,
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['list_url'], list_url)
        self.assertIn('No expenses match the selected filters.', data['list_html'])
        self.assertNotIn('Initial expense', data['list_html'])
        self.assertIn('has_attachment=without', data['list_html'])
        self.expense.refresh_from_db()
        self.assertTrue(self.expense.attachment)

    def test_drawer_async_remove_attachment_returns_filtered_expense_list_fragment(self):
        self.expense.attachment.save('receipt.pdf', ContentFile(b'receipt'), save=True)
        list_url = f'{reverse("expenses:list")}?has_attachment=with&date_range=all&q=Initial'

        response = self.client.post(
            reverse('expenses:drawer', args=[self.expense.pk]),
            data={
                'paid_date': self.expense.paid_date.isoformat(),
                'amount': '300.00',
                'customer': str(self.customer.pk),
                'project': str(self.project.pk),
                'description': 'Initial expense',
                'remove_attachment': 'on',
                'current_list_url': list_url,
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['list_url'], list_url)
        self.assertIn('No expenses match the selected filters.', data['list_html'])
        self.assertNotIn('Initial expense', data['list_html'])
        self.assertIn('has_attachment=with', data['list_html'])
        self.expense.refresh_from_db()
        self.assertFalse(self.expense.attachment)

    def test_drawer_fallback_rejects_unsafe_current_list_url(self):
        response = self.client.post(
            reverse('expenses:drawer', args=[self.expense.pk]),
            data={
                'paid_date': self.expense.paid_date.isoformat(),
                'amount': '300.00',
                'customer': str(self.customer.pk),
                'project': str(self.project.pk),
                'description': 'Initial expense',
                'current_list_url': 'https://example.com/expenses/?has_attachment=without',
            },
        )

        self.assertRedirects(response, reverse('expenses:list'))

    def test_drawer_returns_errors(self):
        response = self.client.post(
            reverse('expenses:drawer_new'),
            data={
                'paid_date': '',
                'amount': '',
            },
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('html', data)
