import io
import zipfile
from datetime import date
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from invoices.models import Expense

from .base import ExpenseViewsTestCase


class ExpenseBulkDownloadViewTests(ExpenseViewsTestCase):
    def test_bulk_download_zip_contains_attachment(self):
        file_content = b'%PDF-1.4 test'
        attachment = SimpleUploadedFile('invoice.pdf', file_content, content_type='application/pdf')
        expense_with_file = Expense.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            paid_date=date.today(),
            amount=Decimal('50.00'),
            description='Receipt',
            attachment=attachment,
        )

        response = self.client.post(
            reverse('expenses:bulk_download'),
            data={
                'selected': [expense_with_file.id, self.expense.id],
                'next': reverse('expenses:list'),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')
        buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(buffer) as archive:
            names = archive.namelist()
            self.assertTrue(any(name.endswith('invoice.pdf') for name in names))
