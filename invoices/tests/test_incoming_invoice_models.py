from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from invoices.admin import IncomingInvoiceCandidateAdmin, IssuerEmailRoutingRuleAdmin
from invoices.models import (
    Company,
    IncomingEmailSource,
    IncomingInvoiceArtifact,
    IncomingInvoiceCandidate,
    Issuer,
    IssuerEmailRoutingRule,
    incoming_invoice_artifact_upload_path,
)


class IncomingInvoiceModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='incoming-admin', password='test-pass')
        self.issuer = Issuer.objects.create(company=Company.objects.create(name='Example BV'))
        self.source = IncomingEmailSource.objects.create(
            issuer=self.issuer,
            user=self.user,
            display_name='Invoice mailbox',
            email_address='invoices@example.test',
            folder='INBOX/Invoices',
            polling_query='UNSEEN',
            credential_reference='secret://incoming/invoices',
        )

    def make_candidate(self, **overrides):
        values = {
            'source': self.source,
            'provider_message_id': 'message-1',
            'provider_thread_id': 'thread-1',
            'from_name': 'Supplier',
            'from_email': 'billing@supplier.test',
            'to_addresses': ['invoices@example.test'],
            'delivered_to_addresses': ['ap@example.test'],
            'subject': 'Invoice 1001',
            'received_at': timezone.datetime(2026, 5, 25, 10, 30, tzinfo=timezone.get_current_timezone()),
            'extracted_metadata': {'invoice_number': '1001', 'amount': '42.00'},
            'detection_metadata': {'invoice_confidence': 0.91, 'company_reasons': ['recipient alias']},
            'fingerprint': 'supplier-1001-42',
        }
        values.update(overrides)
        return IncomingInvoiceCandidate.objects.create(**values)

    def make_artifact(self, candidate=None, **overrides):
        values = {
            'candidate': candidate or self.make_candidate(provider_message_id='message-artifact'),
            'kind': IncomingInvoiceArtifact.KIND_ATTACHMENT,
            'original_filename': 'supplier-invoice.pdf',
            'content_type': 'application/pdf',
            'size': 128,
            'sha256': 'a' * 64,
            'file': 'incoming-invoices/2026/05/source-1/candidate-1/supplier-invoice.pdf',
            'is_invoice_like': True,
            'invoice_confidence': Decimal('0.95'),
        }
        values.update(overrides)
        return IncomingInvoiceArtifact.objects.create(**values)

    def test_source_defaults_to_imap_and_rejects_future_provider_values(self):
        self.assertEqual(self.source.provider, IncomingEmailSource.PROVIDER_IMAP)

        self.source.provider = 'gmail'
        with self.assertRaises(ValidationError):
            self.source.full_clean()

    def test_routing_rule_stores_company_detection_settings(self):
        rule = IssuerEmailRoutingRule.objects.create(
            issuer=self.issuer,
            recipient_aliases=['invoices@example.test'],
            delivered_to_addresses=['ap@example.test'],
            legal_names=['Example BV'],
            tax_identifiers=['NL123456789B01'],
            keywords=['consulting'],
            confidence_threshold=Decimal('0.75'),
        )

        self.assertEqual(str(rule), f'Incoming routing for {self.issuer}')
        self.assertEqual(rule.recipient_aliases, ['invoices@example.test'])
        self.assertTrue(rule.auto_assign_enabled)

    def test_candidate_is_unique_per_source_and_provider_message_id(self):
        self.make_candidate(provider_message_id='same-message')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_candidate(provider_message_id='same-message')

    def test_artifact_hash_is_unique_per_candidate_but_allowed_across_candidates(self):
        first = self.make_candidate(provider_message_id='candidate-a')
        second = self.make_candidate(provider_message_id='candidate-b')
        self.make_artifact(candidate=first, sha256='b' * 64)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_artifact(candidate=first, sha256='b' * 64, original_filename='copy.pdf')

        duplicate_file_on_other_message = self.make_artifact(candidate=second, sha256='b' * 64)
        self.assertEqual(duplicate_file_on_other_message.sha256, 'b' * 64)

    def test_reviewed_unpaid_state_records_confirmed_issuer_artifact_and_limitation(self):
        candidate = self.make_candidate(status=IncomingInvoiceCandidate.STATUS_NEEDS_REVIEW)
        artifact = self.make_artifact(candidate=candidate)

        candidate.mark_reviewed_unpaid(
            issuer=self.issuer,
            artifact=artifact,
            metadata={'vendor': 'Supplier', 'source_currency': 'EUR'},
        )
        candidate.save()

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, IncomingInvoiceCandidate.STATUS_REVIEWED_UNPAID)
        self.assertEqual(candidate.confirmed_issuer, self.issuer)
        self.assertEqual(candidate.selected_artifact, artifact)
        self.assertIn('no accounting record exists yet', candidate.conversion_limitation_message)
        self.assertTrue(candidate.is_terminal)

    def test_candidate_relationship_and_display_helpers(self):
        candidate = self.make_candidate(
            suggested_issuer=self.issuer,
            subject='',
            provider_message_id='display-message',
        )
        artifact = self.make_artifact(candidate=candidate, original_filename='')

        self.assertEqual(str(candidate), 'Incoming message display-message')
        self.assertEqual(candidate.display_subject, 'Incoming message display-message')
        self.assertEqual(candidate.issuer_for_review, self.issuer)
        self.assertEqual(str(artifact), artifact.get_kind_display())
        self.assertEqual(candidate.artifacts.count(), 1)

    def test_incoming_artifact_upload_path_uses_media_relative_incoming_invoice_tree(self):
        candidate = self.make_candidate(provider_message_id='path-message')
        artifact = IncomingInvoiceArtifact(candidate=candidate, original_filename='Supplier Invoice.PDF')

        path = incoming_invoice_artifact_upload_path(artifact, 'Supplier Invoice.PDF')

        self.assertTrue(path.startswith(f'incoming-invoices/2026/05/source-{self.source.pk}/candidate-{candidate.pk}/'))
        self.assertTrue(path.endswith('/supplier-invoice.pdf'))

    def test_admin_display_helpers_summarize_artifacts_and_routing_fields(self):
        candidate = self.make_candidate(provider_message_id='admin-message')
        self.make_artifact(candidate=candidate)
        candidate_admin = IncomingInvoiceCandidateAdmin(IncomingInvoiceCandidate, admin.site)

        rule = IssuerEmailRoutingRule.objects.create(
            issuer=self.issuer,
            recipient_aliases=['invoices@example.test'],
            delivered_to_addresses=['ap@example.test'],
            keywords=['invoice', 'vat'],
        )
        rule_admin = IssuerEmailRoutingRuleAdmin(IssuerEmailRoutingRule, admin.site)

        self.assertEqual(candidate_admin.artifact_count(candidate), 1)
        self.assertEqual(rule_admin.alias_count(rule), 2)
        self.assertEqual(rule_admin.keyword_count(rule), 2)
