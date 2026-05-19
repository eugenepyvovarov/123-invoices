from django.core.files.base import ContentFile
from django.urls import reverse

from invoices.models import Expense

from .base import ExpenseViewsTestCase


class ExpenseListViewTests(ExpenseViewsTestCase):
    def test_expense_index_renders_table(self):
        response = self.client.get(reverse('expenses:list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'#{self.expense.id}')
        self.assertEqual(response.context['expenses_page'].paginator.count, 1)
        self.assertContains(response, 'Do not count')
        self.assertContains(response, reverse('expenses:reporting_visibility', args=[self.expense.pk]))
        self.assertContains(response, f'aria-label="Do not count expense #{self.expense.pk} in reports"')

    def test_expense_index_marks_excluded_expense_toggle_checked(self):
        excluded = Expense.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            paid_date=self.expense.paid_date,
            amount=self.expense.amount,
            description='Excluded expense',
            exclude_from_reports=True,
        )

        response = self.client.get(reverse('expenses:list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'#{excluded.id}')
        self.assertContains(response, f'data-testid="expense-report-toggle-{excluded.id}"')
        self.assertContains(response, 'checked')

    def test_expense_index_filters_by_search_query(self):
        Expense.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            paid_date=self.expense.paid_date,
            amount=self.expense.amount,
            description='Payment to John Smith consulting',
        )
        other_customer = self.customer.__class__.objects.create(
            issuer=self.issuer,
            company=self.customer.company.__class__.objects.create(
                name='Other Vendor Ltd',
                customer_information_file_number='VATOTHER',
            ),
            is_active=True,
        )
        Expense.objects.create(
            issuer=self.issuer,
            customer=other_customer,
            paid_date=self.expense.paid_date,
            amount=self.expense.amount,
            description='Hosting subscription',
        )

        response = self.client.get(reverse('expenses:list'), {'q': 'John Smith'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Payment to John Smith consulting')
        self.assertNotContains(response, 'Hosting subscription')

    def test_expense_index_filters_by_customer_company_name(self):
        self.expense.description = 'General expense'
        self.expense.save(update_fields=['description'])

        response = self.client.get(reverse('expenses:list'), {'q': 'Client Co'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'#{self.expense.id}')

    def test_expense_list_fragment_filters_without_attachment_after_availability_changes(self):
        attached = Expense.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            paid_date=self.expense.paid_date,
            amount=self.expense.amount,
            description='Attached expense',
        )
        attached.attachment.save('receipt.txt', ContentFile(b'receipt'), save=True)

        response = self.client.get(
            reverse('expenses:list'),
            {'has_attachment': 'without', 'q': 'expense', 'date_range': 'all', 'order': 'id_asc'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['availability_filter'], 'without')
        self.assertContains(response, 'Initial expense')
        self.assertNotContains(response, 'Attached expense')
        self.assertContains(
            response,
            f'name="next" value="{reverse("expenses:list")}?has_attachment=without&amp;q=expense&amp;date_range=all&amp;order=id_asc"',
            html=False,
        )

        self.expense.attachment.save('uploaded.txt', ContentFile(b'uploaded'), save=True)
        response = self.client.get(
            reverse('expenses:list'),
            {'has_attachment': 'without', 'q': 'expense', 'date_range': 'all', 'order': 'id_asc'},
        )

        self.assertEqual(response.context['expenses_page'].paginator.count, 0)
        self.assertContains(response, 'No expenses match the selected filters.')
        self.assertNotContains(response, 'Initial expense')

    def test_expense_list_fragment_filters_with_attachment_after_availability_changes(self):
        self.expense.attachment.save('receipt.txt', ContentFile(b'receipt'), save=True)

        response = self.client.get(
            reverse('expenses:list'),
            {'has_attachment': 'with', 'date_range': 'all', 'page': '1'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['availability_filter'], 'with')
        self.assertContains(response, 'Initial expense')
        self.assertContains(
            response,
            f'name="next" value="{reverse("expenses:list")}?has_attachment=with&amp;date_range=all&amp;page=1"',
            html=False,
        )

        self.expense.attachment.delete(save=True)
        response = self.client.get(
            reverse('expenses:list'),
            {'has_attachment': 'with', 'date_range': 'all', 'page': '1'},
        )

        self.assertEqual(response.context['expenses_page'].paginator.count, 0)
        self.assertContains(response, 'No expenses match the selected filters.')
        self.assertNotContains(response, 'Initial expense')

    def test_reporting_visibility_toggle_can_exclude_expense(self):
        response = self.client.post(
            reverse('expenses:reporting_visibility', args=[self.expense.pk]),
            {
                'exclude_from_reports': '1',
                'next': f"{reverse('expenses:list')}?date_range=all&page=2",
            },
        )

        self.assertRedirects(response, f"{reverse('expenses:list')}?date_range=all&page=2")
        self.expense.refresh_from_db()
        self.assertTrue(self.expense.exclude_from_reports)

    def test_reporting_visibility_toggle_can_include_expense(self):
        self.expense.exclude_from_reports = True
        self.expense.save(update_fields=['exclude_from_reports'])

        response = self.client.post(
            reverse('expenses:reporting_visibility', args=[self.expense.pk]),
            {
                'exclude_from_reports': '0',
                'next': 'https://example.com/not-allowed',
            },
        )

        self.assertRedirects(response, reverse('expenses:list'))
        self.expense.refresh_from_db()
        self.assertFalse(self.expense.exclude_from_reports)

    def test_reporting_visibility_toggle_returns_json_for_async_requests(self):
        response = self.client.post(
            reverse('expenses:reporting_visibility', args=[self.expense.pk]),
            {'exclude_from_reports': '1'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {'success': True, 'exclude_from_reports': True})
        self.expense.refresh_from_db()
        self.assertTrue(self.expense.exclude_from_reports)

    def test_expense_delete_async_returns_filtered_expense_list_fragment(self):
        list_url = f'{reverse("expenses:list")}?has_attachment=without&date_range=all&q=Initial'

        response = self.client.post(
            reverse('expenses:delete', args=[self.expense.pk]),
            {'current_list_url': list_url},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['list_url'], list_url)
        self.assertIn('No expenses match the selected filters.', data['list_html'])
        self.assertIn('has_attachment=without', data['list_html'])
        self.assertFalse(Expense.objects.filter(pk=self.expense.pk).exists())

    def test_expense_delete_redirects_to_safe_filtered_next_url(self):
        list_url = f'{reverse("expenses:list")}?has_attachment=with&date_range=all&page=2'

        response = self.client.post(
            reverse('expenses:delete', args=[self.expense.pk]),
            {'current_list_url': list_url},
        )

        self.assertRedirects(response, list_url)
        self.assertFalse(Expense.objects.filter(pk=self.expense.pk).exists())

    def test_expense_delete_rejects_unsafe_next_url(self):
        response = self.client.post(
            reverse('expenses:delete', args=[self.expense.pk]),
            {'current_list_url': 'https://example.com/expenses/?has_attachment=with'},
        )

        self.assertRedirects(response, reverse('expenses:list'))
        self.assertFalse(Expense.objects.filter(pk=self.expense.pk).exists())
