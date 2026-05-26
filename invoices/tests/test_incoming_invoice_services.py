from __future__ import annotations

import tempfile
from decimal import Decimal
from email.message import EmailMessage
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone

from invoices.models import (
    Company,
    Expense,
    IncomingEmailSource,
    IncomingInvoiceArtifact,
    IncomingInvoiceCandidate,
    Issuer,
    IssuerEmailRoutingRule,
)
from invoices.services.incoming_email import fetch_imap_messages, import_eml_fixture, parse_email_message
from invoices.services.incoming_invoice_conversion import (
    convert_candidate_to_expense,
    mark_candidate_confirmed,
)
from invoices.services.incoming_invoice_duplicates import detect_duplicates
from invoices.services.incoming_invoice_routing import apply_routing


class IncomingInvoiceServiceTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(self.media_root.cleanup)

        self.user = get_user_model().objects.create_user(username='incoming-service')
        self.issuer = Issuer.objects.create(company=Company.objects.create(name='Example BV'))
        self.source = IncomingEmailSource.objects.create(
            issuer=None,
            user=self.user,
            display_name='Invoice mailbox',
            email_address='invoices@example.test',
            folder='Invoices',
            polling_query='SUBJECT Invoice',
            credential_reference='env:INCOMING_IMAP_TEST_CREDENTIAL_REF',
        )
        IssuerEmailRoutingRule.objects.create(
            issuer=self.issuer,
            recipient_aliases=['invoices@example.test'],
            delivered_to_addresses=['ap@example.test'],
            legal_names=['Example BV'],
            tax_identifiers=['NL123456789B01'],
            keywords=['consulting'],
            confidence_threshold=Decimal('0.70'),
        )

    def make_message(self, *, message_id='<invoice-1@example.test>', to='Invoices <invoices@example.test>', subject='Invoice 1001', body='Invoice 1001 for Example BV. VAT NL123456789B01. Total 42.00'):
        message = EmailMessage()
        message['Message-ID'] = message_id
        message['Date'] = 'Mon, 25 May 2026 10:30:00 +0000'
        message['From'] = 'Supplier Billing <billing@supplier.test>'
        message['To'] = to
        message['Cc'] = 'Accounts <accounts@example.test>'
        message['Delivered-To'] = 'ap@example.test'
        message['Subject'] = subject
        message.set_content(body)
        return message

    def test_parse_email_sanitizes_headers_and_keeps_allowed_attachments(self):
        message = self.make_message(subject='Invoice 1001')
        message.add_attachment(b'%PDF-1.4 synthetic invoice', maintype='application', subtype='pdf', filename='Supplier Invoice.PDF')
        message.add_attachment(b'not allowed', maintype='application', subtype='octet-stream', filename='blocked.exe')

        parsed = parse_email_message(message.as_bytes())

        self.assertEqual(parsed.provider_message_id, '<invoice-1@example.test>')
        self.assertEqual(parsed.to_addresses, ['invoices@example.test'])
        self.assertEqual(parsed.delivered_to_addresses, ['ap@example.test'])
        self.assertEqual(parsed.subject, 'Invoice 1001')
        self.assertEqual(len(parsed.attachments), 1)
        self.assertEqual(parsed.attachments[0].content_type, 'application/pdf')
        self.assertIn('headers', parsed.raw_provider_metadata)

    def test_fixture_import_creates_candidate_artifacts_body_pdf_and_company_suggestion_idempotently(self):
        message = self.make_message()
        message.add_attachment(b'%PDF-1.4 synthetic invoice', maintype='application', subtype='pdf', filename='invoice-1001.pdf')
        fixture = Path(self.media_root.name) / 'invoice.eml'
        fixture.write_bytes(message.as_bytes())

        first = import_eml_fixture(self.source, fixture)
        second = import_eml_fixture(self.source, fixture)

        candidate = first.candidate
        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertTrue(second.duplicate)
        self.assertEqual(IncomingInvoiceCandidate.objects.count(), 1)
        self.assertEqual(candidate.status, IncomingInvoiceCandidate.STATUS_READY)
        self.assertEqual(candidate.suggested_issuer, self.issuer)
        self.assertEqual(candidate.artifacts.filter(kind=IncomingInvoiceArtifact.KIND_ATTACHMENT).count(), 1)
        body_pdf = candidate.generated_body_pdf_artifact
        self.assertIsNotNone(body_pdf)
        self.assertEqual(body_pdf.kind, IncomingInvoiceArtifact.KIND_EMAIL_BODY_PDF)
        with body_pdf.file.open('rb') as stored:
            self.assertTrue(stored.read(4).startswith(b'%PDF'))

    def test_ambiguous_company_match_stays_needs_review(self):
        other = Issuer.objects.create(company=Company.objects.create(name='Other BV'))
        IssuerEmailRoutingRule.objects.create(
            issuer=other,
            recipient_aliases=['invoices@example.test'],
            confidence_threshold=Decimal('0.50'),
        )
        result = import_eml_fixture(self.source, self._write_message(self.make_message(message_id='<ambiguous@example.test>')))

        self.assertEqual(result.candidate.status, IncomingInvoiceCandidate.STATUS_NEEDS_REVIEW)
        self.assertIsNone(result.candidate.suggested_issuer)
        self.assertEqual(result.candidate.detection_metadata['company_warning'], 'multiple issuers matched')

    def test_portal_link_only_email_is_marked_needs_fetch(self):
        message = self.make_message(message_id='<portal@example.test>', subject='Your bill is ready', body='Download it at https://portal.example.test/invoices/1')

        result = import_eml_fixture(self.source, self._write_message(message))

        self.assertEqual(result.candidate.status, IncomingInvoiceCandidate.STATUS_NEEDS_FETCH)

    def test_duplicate_detection_flags_artifact_hash_fingerprint_and_expense_provenance(self):
        first = import_eml_fixture(self.source, self._write_message(self.make_message(message_id='<dup-a@example.test>'))).candidate
        second = import_eml_fixture(self.source, self._write_message(self.make_message(message_id='<dup-b@example.test>'))).candidate
        artifact = first.artifacts.first()
        Expense.objects.create(
            issuer=self.issuer,
            paid_date=timezone.localdate(),
            amount=Decimal('42.00'),
            description='Incoming invoice',
            raw_data={'incoming_invoice': {'selected_artifact_sha256': artifact.sha256, 'fingerprint': first.fingerprint}},
        )

        report = detect_duplicates(second)

        self.assertTrue(report.is_duplicate)
        self.assertIn('invoice fingerprint already exists', report.reasons)
        self.assertIn('incoming-created expense uses same invoice fingerprint', report.reasons)
        second.refresh_from_db()
        self.assertEqual(second.status, IncomingInvoiceCandidate.STATUS_DUPLICATE)

    def test_imap_fetch_uses_readonly_select_and_body_peek(self):
        client = mock.MagicMock()
        client.__enter__.return_value = client
        client.search.return_value = ('OK', [b'1 2'])
        client.fetch.side_effect = [('OK', [(b'1 (BODY[])', b'raw-one')]), ('OK', [(b'2 (BODY[])', b'raw-two')])]

        runtime_only_value = '-'.join(['runtime', 'only'])
        with mock.patch('invoices.services.incoming_email.imaplib.IMAP4_SSL', return_value=client):
            messages = fetch_imap_messages(
                self.source,
                host='imap.example.test',
                username='user',
                password=runtime_only_value,
                limit=1,
            )

        client.select.assert_called_once_with('Invoices', readonly=True)
        client.search.assert_called_once_with(None, 'SUBJECT', 'Invoice')
        client.fetch.assert_called_once_with(b'1', '(BODY.PEEK[])')
        self.assertEqual(messages, [b'raw-one'])

    def test_paid_conversion_invalidates_dashboard_cache(self):
        candidate = import_eml_fixture(
            self.source,
            self._write_message(self.make_message(message_id='<convert-cache@example.test>')),
        ).candidate
        artifact = candidate.artifacts.first()
        artifact.file.save('convert-cache.pdf', ContentFile(b'%PDF-1.4 cache test'), save=True)

        with mock.patch('invoices.views.invalidate_dashboard_cache') as invalidate_cache:
            expense = convert_candidate_to_expense(
                candidate,
                issuer=self.issuer,
                artifact=artifact,
                vendor='Supplier',
                description='Converted incoming invoice',
                amount=Decimal('42.00'),
                currency='EUR',
                paid_date=timezone.localdate(),
            )

        self.assertEqual(expense.issuer, self.issuer)
        invalidate_cache.assert_called_once_with(self.issuer.pk)

    def test_confirmed_review_learns_routing_signals_for_later_messages(self):
        IssuerEmailRoutingRule.objects.filter(issuer=self.issuer).delete()
        first = IncomingInvoiceCandidate.objects.create(
            source=self.source,
            status=IncomingInvoiceCandidate.STATUS_NEEDS_REVIEW,
            provider_message_id='learned-first',
            from_email='billing@repeat-vendor.test',
            to_addresses=['ap-confirm@example.test'],
            delivered_to_addresses=['invoices-confirm@example.test'],
            subject='Invoice 1001 May 2026',
            received_at=timezone.now(),
        )
        artifact = IncomingInvoiceArtifact.objects.create(
            candidate=first,
            kind=IncomingInvoiceArtifact.KIND_ATTACHMENT,
            original_filename='learned.pdf',
            content_type='application/pdf',
            size=7,
            sha256='b' * 64,
        )

        mark_candidate_confirmed(first, issuer=self.issuer, artifact=artifact, metadata={'vendor': 'Repeat Vendor'})

        rule = self.issuer.incoming_email_routing_rule
        self.assertIn('ap-confirm@example.test', rule.recipient_aliases)
        self.assertIn('invoices-confirm@example.test', rule.delivered_to_addresses)
        self.assertIn('billing@repeat-vendor.test', rule.keywords)
        self.assertTrue(any(keyword.startswith('day-of-month:') for keyword in rule.keywords))

        second = IncomingInvoiceCandidate.objects.create(
            source=self.source,
            status=IncomingInvoiceCandidate.STATUS_NEW,
            provider_message_id='learned-second',
            from_email='billing@repeat-vendor.test',
            to_addresses=['ap-confirm@example.test'],
            delivered_to_addresses=['invoices-confirm@example.test'],
            subject='Invoice 1002 June 2026',
            received_at=timezone.now(),
        )

        apply_routing(second)

        second.refresh_from_db()
        self.assertEqual(second.suggested_issuer, self.issuer)
        self.assertEqual(second.status, IncomingInvoiceCandidate.STATUS_READY)

    def _write_message(self, message):
        path = Path(self.media_root.name) / f'{message["Message-ID"].strip("<>")}.eml'
        path.write_bytes(message.as_bytes())
        return path
