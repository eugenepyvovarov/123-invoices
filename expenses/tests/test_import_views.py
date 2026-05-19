import csv
import io
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from invoices.models import Expense, ImportBatch, ImportMapping
from invoices.services.expense_import_mappings import seed_wise_global_mapping

from .base import ExpenseViewsTestCase


class ExpenseImportViewTests(ExpenseViewsTestCase):
    def _upload(self, name, rows):
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        return SimpleUploadedFile(name, buffer.getvalue().encode('utf-8'), content_type='text/csv')

    def test_expense_list_links_to_generic_statement_import(self):
        response = self.client.get(reverse('expenses:list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Import expense statement')
        self.assertContains(response, reverse('expenses:csv_import'))
        self.assertNotContains(response, 'Import from Wise')

    def test_import_page_describes_supported_statement_uploads(self):
        response = self.client.get(reverse('expenses:csv_import'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Import expense statement')
        self.assertContains(response, 'CSV, XLS, XLSX, or ZIP-with-CSV statement')
        self.assertContains(response, 'Statement files (CSV, XLS, XLSX, or ZIP)')
        self.assertContains(response, 'accept=".csv,.xls,.xlsx,.zip"')

    def test_import_batch_is_scoped_to_authenticated_user(self):
        batch = ImportBatch.objects.create(user=self.user, issuer=self.issuer, raw_headers=['When', 'Value'])
        other_issuer = self.create_issuer()
        other_user = self.create_user_with_issuers([other_issuer], username='other-import-user')
        self.login_with_active_company(other_user, issuer=other_issuer)

        response = self.client.post(reverse('expenses:csv_import_confirm', args=[batch.pk]), {'selected_rows': ['1']})

        self.assertEqual(response.status_code, 404)

    def test_upload_validation_error_is_rendered(self):
        response = self.client.post(reverse('expenses:csv_import'), {})

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'Upload at least one expense statement file (CSV, XLS, XLSX, or ZIP).', status_code=400)

    def test_corrupt_spreadsheet_error_is_rendered_without_creating_expenses(self):
        expense_count = Expense.objects.filter(issuer=self.issuer).count()
        upload = SimpleUploadedFile(
            'broken.xlsx',
            b'not a valid workbook',
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

        response = self.client.post(reverse('expenses:csv_import'), {'statements': upload})

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'broken.xlsx: invalid or unsupported XLSX file.', status_code=400)
        self.assertEqual(Expense.objects.filter(issuer=self.issuer).count(), expense_count)

    def test_unmatched_csv_requires_complete_ai_provider_settings(self):
        rows = [{'When': '2026-04-01', 'Value': '-10.00', 'Memo': 'Hosting'}]

        response = self.client.post(reverse('expenses:csv_import'), {'statements': self._upload('card.csv', rows)})

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'No saved mapping matches this statement. Configure AI provider settings to infer a mapping.', status_code=400)

    @patch('expenses.views.OpenAICompatibleMappingClient')
    def test_complete_ai_provider_settings_enable_mapping_inference(self, mock_client_class):
        self.user.profile.expense_ai_provider_base_url = 'https://provider.example'
        self.user.profile.expense_ai_model_name = 'mapping-model'
        self.user.profile.expense_ai_api_key = 'sk-secret'
        self.user.profile.save()
        mock_client = mock_client_class.return_value
        mock_client.infer_mapping.return_value = {
            'paid_date': 'When',
            'amount': 'Value',
            'description': 'Memo',
            'amount_mode': 'absolute',
        }
        rows = [{'When': '2026-04-01', 'Value': '-10.00', 'Memo': 'Hosting'}]

        response = self.client.post(reverse('expenses:csv_import'), {'statements': self._upload('card.csv', rows)})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mapping source: ai')
        mock_client.infer_mapping.assert_called_once()
        batch = ImportBatch.objects.get(user=self.user, issuer=self.issuer)
        self.assertEqual(batch.preview_rows.count(), 1)

    def test_wise_global_mapping_upload_builds_preview(self):
        seed_wise_global_mapping()
        rows = [
            {
                'TransferWise ID': 'CARD-001',
                'Date Time': '01-04-2026 10:00:00.000',
                'Amount': '-12.34',
                'Currency': 'EUR',
                'Description': 'Hosting',
                'Payment Reference': 'April',
                'Transaction Type': 'DEBIT',
                'Transaction Details Type': 'CARD',
            }
        ]

        response = self.client.post(reverse('expenses:csv_import'), {'statements': self._upload('wise.csv', rows)})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mapping source: global')
        self.assertContains(response, 'Select multiple columns to combine them into the expense description.')
        self.assertContains(response, 'value="Description" selected')
        self.assertContains(response, 'value="Payment Reference" selected')
        batch = ImportBatch.objects.get(user=self.user, issuer=self.issuer)
        self.assertEqual(batch.preview_rows.count(), 1)

    def test_saved_user_mapping_can_be_reused_and_confirm_selected_rows(self):
        mapping = ImportMapping.objects.create(
            scope=ImportMapping.SCOPE_USER,
            owner=self.user,
            name='Card export',
            normalized_header_signature=ImportMapping.signature_from_headers(['When', 'Value', 'Memo', 'ID']),
            mapping_json={
                'paid_date': 'When',
                'amount': 'Value',
                'description': 'Memo',
                'transaction_id': 'ID',
                'amount_mode': 'absolute',
            },
        )
        rows = [
            {'When': '2026-04-01', 'Value': '-10.00', 'Memo': 'Selected', 'ID': 'A1'},
            {'When': '2026-04-02', 'Value': '-20.00', 'Memo': 'Skipped', 'ID': 'A2'},
        ]
        upload_response = self.client.post(
            reverse('expenses:csv_import'),
            {'mapping': str(mapping.pk), 'statements': self._upload('card.csv', rows)},
        )
        batch = ImportBatch.objects.get(user=self.user, issuer=self.issuer)

        response = self.client.post(
            reverse('expenses:csv_import_confirm', args=[batch.pk]),
            {'selected_rows': ['1']},
        )

        self.assertEqual(upload_response.status_code, 200)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Created: 1')
        self.assertEqual(Expense.objects.filter(issuer=self.issuer, description='Selected').count(), 1)
        self.assertEqual(Expense.objects.filter(issuer=self.issuer, description='Skipped').count(), 0)

    def test_review_can_save_user_mapping(self):
        seed_wise_global_mapping()
        rows = [{
            'TransferWise ID': 'CARD-002',
            'Date Time': '01-04-2026 10:00:00.000',
            'Amount': '-12.34',
            'Currency': 'EUR',
            'Description': 'Hosting',
            'Payment Reference': 'April',
            'Transaction Type': 'DEBIT',
            'Transaction Details Type': 'CARD',
        }]
        self.client.post(reverse('expenses:csv_import'), {'statements': self._upload('wise.csv', rows)})
        batch = ImportBatch.objects.get(user=self.user, issuer=self.issuer)

        response = self.client.post(reverse('expenses:csv_import_review', args=[batch.pk]), {
            'paid_date': 'Date Time',
            'amount': 'Amount',
            'description': ['Description', 'Payment Reference'],
            'transaction_id': 'TransferWise ID',
            'currency': 'Currency',
            'amount_mode': 'absolute',
            'date_formats': '%d-%m-%Y %H:%M:%S.%f',
            'save_mapping_name': 'My Wise copy',
        })

        self.assertEqual(response.status_code, 200)
        mapping = ImportMapping.objects.get(owner=self.user, name='My Wise copy')
        self.assertEqual(mapping.mapping_json['description'], ['Description', 'Payment Reference'])
        batch.refresh_from_db()
        self.assertEqual(batch.preview_rows.get().mapped_data['description'], 'Hosting\nApril')
