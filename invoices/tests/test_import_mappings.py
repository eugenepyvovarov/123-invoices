from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from invoices.models import Company, ImportBatch, ImportMapping, ImportPreviewRow, Issuer
from invoices.services.expense_import_mappings import (
    WISE_MAPPING_NAME,
    WISE_HEADERS,
    seed_wise_global_mapping,
    wise_header_signature,
)


class ImportMappingModelTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='mapping-user', password='pass')
        self.other_user = User.objects.create_user(username='other-mapping-user', password='pass')

    def test_scope_owner_validation(self):
        global_mapping = ImportMapping(
            scope=ImportMapping.SCOPE_GLOBAL,
            owner=self.user,
            name='Invalid global',
            normalized_header_signature=ImportMapping.signature_from_headers(['Date', 'Amount']),
            mapping_json={'paid_date': 'Date', 'amount': 'Amount'},
        )
        with self.assertRaises(ValidationError):
            global_mapping.full_clean()

        user_mapping = ImportMapping(
            scope=ImportMapping.SCOPE_USER,
            name='Invalid user',
            normalized_header_signature=ImportMapping.signature_from_headers(['Date', 'Amount']),
            mapping_json={'paid_date': 'Date', 'amount': 'Amount'},
        )
        with self.assertRaises(ValidationError):
            user_mapping.full_clean()

    def test_global_mappings_are_visible_but_other_users_mappings_are_private(self):
        global_mapping = ImportMapping.objects.create(
            scope=ImportMapping.SCOPE_GLOBAL,
            name='Global card export',
            normalized_header_signature=ImportMapping.signature_from_headers(['Date', 'Amount']),
            mapping_json={'paid_date': 'Date', 'amount': 'Amount'},
        )
        private_mapping = ImportMapping.objects.create(
            scope=ImportMapping.SCOPE_USER,
            owner=self.other_user,
            name='Other user export',
            normalized_header_signature=ImportMapping.signature_from_headers(['Date', 'Total']),
            mapping_json={'paid_date': 'Date', 'amount': 'Total'},
        )

        visible = ImportMapping.objects.visible_to(self.user)

        self.assertIn(global_mapping, visible)
        self.assertNotIn(private_mapping, visible)

    def test_user_mapping_takes_precedence_over_matching_global_mapping(self):
        headers = ['\ufeff Date ', ' AMOUNT', 'Description', 'Ignored Extra Column']
        signature = ImportMapping.signature_from_headers(['Date', 'Amount'])
        ImportMapping.objects.create(
            scope=ImportMapping.SCOPE_GLOBAL,
            name='Global bank export',
            normalized_header_signature=signature,
            mapping_json={'paid_date': 'Date', 'amount': 'Amount'},
        )
        user_mapping = ImportMapping.objects.create(
            scope=ImportMapping.SCOPE_USER,
            owner=self.user,
            name='My bank export',
            normalized_header_signature=signature,
            mapping_json={'paid_date': 'Date', 'amount': 'Amount', 'description': 'Description'},
        )

        best_mapping = ImportMapping.objects.best_for_user_and_headers(self.user, headers)

        self.assertEqual(best_mapping, user_mapping)
        self.assertTrue(user_mapping.matches_headers(headers))

    def test_wise_seed_is_read_only_global_and_idempotent(self):
        mapping, created = seed_wise_global_mapping()
        count_after_first_call = ImportMapping.objects.filter(name=WISE_MAPPING_NAME, scope=ImportMapping.SCOPE_GLOBAL).count()

        seeded_again, created_again = seed_wise_global_mapping()

        self.assertFalse(created)
        self.assertFalse(created_again)
        self.assertEqual(seeded_again.pk, mapping.pk)
        self.assertEqual(count_after_first_call, 1)
        self.assertEqual(
            ImportMapping.objects.filter(name=WISE_MAPPING_NAME, scope=ImportMapping.SCOPE_GLOBAL).count(),
            1,
        )
        self.assertIsNone(mapping.owner)
        self.assertTrue(mapping.read_only)
        self.assertEqual(mapping.normalized_header_signature, wise_header_signature())
        self.assertTrue(mapping.matches_headers(WISE_HEADERS + ['Extra statement column']))

        mapping.name = 'Renamed Wise mapping'
        with self.assertRaises(ValidationError):
            mapping.save()


class ImportBatchPersistenceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='batch-user', password='pass')
        company = Company.objects.create(name='Batch Issuer')
        self.issuer = Issuer.objects.create(company=company)
        self.mapping = ImportMapping.objects.create(
            scope=ImportMapping.SCOPE_USER,
            owner=self.user,
            name='Batch mapping',
            normalized_header_signature=ImportMapping.signature_from_headers(['Date', 'Amount']),
            mapping_json={'paid_date': 'Date', 'amount': 'Amount'},
        )

    def test_import_batch_and_preview_rows_are_scoped_to_user_and_issuer(self):
        batch = ImportBatch.objects.create(
            user=self.user,
            issuer=self.issuer,
            mapping=self.mapping,
            source_filename='expenses.csv',
            raw_headers=['Date', 'Amount'],
            normalized_header_signature=ImportMapping.signature_from_headers(['Date', 'Amount']),
        )
        preview_row = ImportPreviewRow.objects.create(
            batch=batch,
            row_index=1,
            raw_data={'Date': '2026-01-02', 'Amount': '-12.34'},
            mapped_data={'paid_date': '2026-01-02', 'amount': '12.34'},
            default_selected=True,
            selected=False,
            fingerprint='row-fingerprint',
        )

        self.assertEqual(batch.user, self.user)
        self.assertEqual(batch.issuer, self.issuer)
        self.assertEqual(batch.preview_rows.get(), preview_row)
        self.assertFalse(preview_row.selected)
