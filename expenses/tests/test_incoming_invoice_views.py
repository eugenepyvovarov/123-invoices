from datetime import date
from decimal import Decimal

from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone

from invoices.models import Expense, IncomingEmailSource, IncomingInvoiceArtifact, IncomingInvoiceCandidate

from .base import ExpenseViewsTestCase


class IncomingInvoiceViewTests(ExpenseViewsTestCase):
    def setUp(self):
        super().setUp()
        self.source = IncomingEmailSource.objects.create(
            user=self.user,
            issuer=self.issuer,
            display_name='AP inbox',
            email_address='ap@example.com',
            folder='INBOX',
        )
        self.candidate = IncomingInvoiceCandidate.objects.create(
            source=self.source,
            suggested_issuer=self.issuer,
            status=IncomingInvoiceCandidate.STATUS_READY,
            provider_message_id='message-1',
            from_email='vendor@example.com',
            subject='Vendor invoice',
            received_at=timezone.now(),
            extracted_metadata={'vendor': 'Vendor Ltd', 'amount': '42.50', 'currency': 'EUR'},
            detection_metadata={'company_confidence': 0.95, 'reasons': ['alias matched']},
        )
        self.artifact = IncomingInvoiceArtifact.objects.create(
            candidate=self.candidate,
            kind=IncomingInvoiceArtifact.KIND_ATTACHMENT,
            original_filename='invoice.pdf',
            content_type='application/pdf',
            size=7,
            sha256='a' * 64,
            is_invoice_like=True,
            invoice_confidence=Decimal('0.90'),
        )
        self.artifact.file.save('invoice.pdf', ContentFile(b'pdfdata'), save=True)

    def test_inbox_filters_candidates(self):
        response = self.client.get(reverse('expenses:incoming_inbox'), {'status': IncomingInvoiceCandidate.STATUS_READY, 'company': self.issuer.pk, 'confidence': 'high'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Vendor invoice')
        self.assertContains(response, 'AP inbox')

    def test_candidate_detail_saves_company_and_artifact(self):
        response = self.client.post(reverse('expenses:incoming_action', args=[self.candidate.pk]), {
            'action': 'confirm',
            'confirmed_issuer': self.issuer.pk,
            'selected_artifact': self.artifact.pk,
            'vendor': 'Vendor Ltd',
            'description': 'Confirmed vendor invoice',
            'amount': '42.50',
            'currency': 'EUR',
        })

        self.assertRedirects(response, reverse('expenses:incoming_detail', args=[self.candidate.pk]))
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.confirmed_issuer, self.issuer)
        self.assertEqual(self.candidate.selected_artifact, self.artifact)
        self.assertEqual(self.candidate.status, IncomingInvoiceCandidate.STATUS_READY)

    def test_inbox_history_keeps_terminal_review_statuses_visible(self):
        terminal_statuses = [
            IncomingInvoiceCandidate.STATUS_REJECTED,
            IncomingInvoiceCandidate.STATUS_NOT_INVOICE,
            IncomingInvoiceCandidate.STATUS_DUPLICATE,
            IncomingInvoiceCandidate.STATUS_NEEDS_FETCH,
            IncomingInvoiceCandidate.STATUS_CONVERTED,
            IncomingInvoiceCandidate.STATUS_REVIEWED_UNPAID,
        ]
        for index, status in enumerate(terminal_statuses, start=1):
            IncomingInvoiceCandidate.objects.create(
                source=self.source,
                suggested_issuer=self.issuer,
                status=status,
                provider_message_id=f'history-{status}',
                from_email='vendor@example.com',
                subject=f'History {index} {status}',
                received_at=timezone.now(),
            )

        response = self.client.get(reverse('expenses:incoming_inbox'))

        self.assertEqual(response.status_code, 200)
        for index, status in enumerate(terminal_statuses, start=1):
            self.assertContains(response, f'History {index} {status}')

    def test_reject_not_invoice_and_needs_fetch_actions_keep_candidate_in_history(self):
        action_expectations = (
            ('reject', IncomingInvoiceCandidate.STATUS_REJECTED),
            ('not_invoice', IncomingInvoiceCandidate.STATUS_NOT_INVOICE),
            ('needs_fetch', IncomingInvoiceCandidate.STATUS_NEEDS_FETCH),
        )
        for action, expected_status in action_expectations:
            candidate = IncomingInvoiceCandidate.objects.create(
                source=self.source,
                suggested_issuer=self.issuer,
                status=IncomingInvoiceCandidate.STATUS_NEEDS_REVIEW,
                provider_message_id=f'action-{action}',
                from_email='vendor@example.com',
                subject=f'Action {action}',
                received_at=timezone.now(),
            )

            response = self.client.post(reverse('expenses:incoming_action', args=[candidate.pk]), {'action': action})

            self.assertRedirects(response, reverse('expenses:incoming_detail', args=[candidate.pk]))
            candidate.refresh_from_db()
            self.assertEqual(candidate.status, expected_status)
            self.assertContains(self.client.get(reverse('expenses:incoming_inbox')), f'Action {action}')

    def test_reviewed_unpaid_does_not_create_expense(self):
        response = self.client.post(reverse('expenses:incoming_action', args=[self.candidate.pk]), {
            'action': 'reviewed_unpaid',
            'confirmed_issuer': self.issuer.pk,
            'selected_artifact': self.artifact.pk,
            'vendor': 'Vendor Ltd',
            'description': 'Unpaid vendor invoice',
            'amount': '42.50',
            'currency': 'EUR',
        })

        self.assertRedirects(response, reverse('expenses:incoming_detail', args=[self.candidate.pk]))
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, IncomingInvoiceCandidate.STATUS_REVIEWED_UNPAID)
        self.assertIn('no accounting record', self.candidate.conversion_limitation_message)
        self.assertEqual(Expense.objects.filter(raw_data__incoming_invoice__candidate_id=self.candidate.pk).count(), 0)

    def test_conversion_requires_paid_date(self):
        response = self.client.post(reverse('expenses:incoming_convert', args=[self.candidate.pk]), {
            'paid_state': 'paid',
            'confirmed_issuer': self.issuer.pk,
            'selected_artifact': self.artifact.pk,
            'vendor': 'Vendor Ltd',
            'description': 'Paid invoice',
            'amount': '42.50',
            'currency': 'EUR',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Paid date is required')
        self.assertFalse(Expense.objects.filter(raw_data__incoming_invoice__candidate_id=self.candidate.pk).exists())

    def test_paid_conversion_creates_expense_with_provenance(self):
        response = self.client.post(reverse('expenses:incoming_convert', args=[self.candidate.pk]), {
            'paid_state': 'paid',
            'confirmed_issuer': self.issuer.pk,
            'selected_artifact': self.artifact.pk,
            'vendor': 'Vendor Ltd',
            'description': 'Paid invoice',
            'amount': '42.50',
            'currency': 'EUR',
            'paid_date': date.today().isoformat(),
        })

        self.assertEqual(response.status_code, 302)
        self.candidate.refresh_from_db()
        expense = self.candidate.converted_expense
        self.assertIsNotNone(expense)
        self.assertEqual(expense.amount, Decimal('42.50'))
        self.assertTrue(expense.attachment)
        self.assertEqual(expense.raw_data['incoming_invoice']['candidate_id'], self.candidate.pk)
        self.assertEqual(expense.raw_data['incoming_invoice']['source_currency'], 'EUR')

    def test_duplicate_conversion_requires_override(self):
        self.candidate.status = IncomingInvoiceCandidate.STATUS_DUPLICATE
        self.candidate.duplicate_metadata = {'is_duplicate': True, 'reasons': ['artifact hash already exists']}
        self.candidate.save(update_fields=['status', 'duplicate_metadata'])

        response = self.client.post(reverse('expenses:incoming_convert', args=[self.candidate.pk]), {
            'paid_state': 'paid',
            'confirmed_issuer': self.issuer.pk,
            'selected_artifact': self.artifact.pk,
            'vendor': 'Vendor Ltd',
            'description': 'Paid invoice',
            'amount': '42.50',
            'currency': 'EUR',
            'paid_date': date.today().isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Duplicate candidates require explicit override')

    def test_link_existing_marks_duplicate_with_existing_expense_reference(self):
        expense = Expense.objects.create(
            issuer=self.issuer,
            paid_date=date.today(),
            amount=Decimal('42.50'),
            description='Existing paid invoice',
        )

        response = self.client.post(reverse('expenses:incoming_action', args=[self.candidate.pk]), {
            'action': 'link_existing',
            'existing_expense': expense.pk,
        })

        self.assertRedirects(response, reverse('expenses:incoming_detail', args=[self.candidate.pk]))
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, IncomingInvoiceCandidate.STATUS_DUPLICATE)
        self.assertEqual(self.candidate.duplicate_metadata['review_action'], 'linked_existing')
        self.assertEqual(self.candidate.duplicate_metadata['linked_existing_expense_id'], expense.pk)

    def test_artifact_download_is_scoped_to_accessible_candidate(self):
        response = self.client.get(reverse('expenses:incoming_artifact_download', args=[self.candidate.pk, self.artifact.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
