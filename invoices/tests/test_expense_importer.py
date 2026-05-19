from __future__ import annotations

import csv
import json
import io
import threading
import zipfile
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from invoices.models import Company, Expense, ImportMapping, Issuer
from invoices.services.expense_import_ai import (
    ExpenseImportAIError,
    OpenAICompatibleMappingClient,
    OpenAICompatibleProviderConfig,
)
from invoices.services.expense_import_mappings import seed_wise_global_mapping
from invoices.services.expense_importer import ExpenseImportError, GenericExpenseImporter


FIXTURE_DIR = Path(__file__).resolve().parents[2] / 'tests' / 'e2e' / 'fixtures' / 'expense-import'


class StubMappingClient:
    def __init__(self, mapping=None, exc=None):
        self.mapping = mapping
        self.exc = exc
        self.calls = []

    def infer_mapping(self, headers, sample_rows):
        self.calls.append((headers, sample_rows))
        if self.exc:
            raise self.exc
        return self.mapping


class OpenAICompatibleMappingClientTests(TestCase):
    def _run_fake_provider(self, response_payload=None, status=200):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                requests.append(
                    {
                        'path': self.path,
                        'authorization': self.headers.get('Authorization'),
                        'content_type': self.headers.get('Content-Type'),
                        'payload': json.loads(body.decode('utf-8')),
                    }
                )
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                payload = response_payload or {
                    'choices': [
                        {
                            'message': {
                                'content': json.dumps(
                                    {
                                        'paid_date': 'Date',
                                        'amount': 'Amount',
                                        'description': 'Item',
                                        'currency': 'Currency',
                                    }
                                )
                            }
                        }
                    ]
                }
                self.wfile.write(json.dumps(payload).encode('utf-8'))

            def log_message(self, format, *args):
                return

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server, requests

    def test_fixture_provider_returns_committed_mapping_without_network(self):
        client = OpenAICompatibleMappingClient(
            OpenAICompatibleProviderConfig(
                base_url=OpenAICompatibleMappingClient.FIXTURE_BASE_URL,
                model=OpenAICompatibleMappingClient.FIXTURE_MODEL,
                api_key='sk-fixture',
            )
        )

        mapping = client.infer_mapping(
            ['Txn Date', 'Merchant', 'Card Debit', 'ISO Currency', 'Reference Number'],
            [{'Txn Date': '2025-11-12', 'Merchant': 'Acme Office Supply'}],
        )

        self.assertEqual(mapping['paid_date'], 'Txn Date')
        self.assertEqual(mapping['amount'], 'Card Debit')
        self.assertEqual(mapping['transaction_id'], 'Reference Number')

    def test_fixture_provider_returns_statement_mapping_without_network(self):
        client = OpenAICompatibleMappingClient(
            OpenAICompatibleProviderConfig(
                base_url=OpenAICompatibleMappingClient.FIXTURE_BASE_URL,
                model=OpenAICompatibleMappingClient.FIXTURE_MODEL,
                api_key='sk-fixture',
            )
        )

        mapping = client.infer_mapping(
            ['Value date', 'Date', 'Reason', 'Movement', 'Amount', 'Currency', 'Available', 'Currency 2', 'Comments'],
            [{'Date': '30/04/2026', 'Amount': '-36', 'Reason': 'SANITIZED TELECOM DEBIT'}],
        )

        self.assertEqual(mapping['paid_date'], 'Date')
        self.assertEqual(mapping['amount'], 'Amount')
        self.assertEqual(mapping['description'], ['Reason', 'Movement'])

    def test_openai_compatible_client_posts_expected_chat_completion_request(self):
        server, requests = self._run_fake_provider()
        client = OpenAICompatibleMappingClient(
            OpenAICompatibleProviderConfig(
                base_url=f'http://127.0.0.1:{server.server_port}',
                model='qwen/qwen3.6-27b',
                api_key='test-key',
            ),
            timeout=2,
        )
        sample_rows = [
            {'Date': f'2026-04-{day:02d}', 'Amount': '-12.00', 'Item': f'Sample {day}', 'Currency': 'EUR'}
            for day in range(1, 8)
        ]

        mapping = client.infer_mapping(['Date', 'Amount', 'Item', 'Currency'], sample_rows)

        self.assertEqual(mapping['paid_date'], 'Date')
        self.assertEqual(mapping['amount'], 'Amount')
        self.assertEqual(mapping['description'], 'Item')
        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertEqual(request['path'], '/v1/chat/completions')
        self.assertEqual(request['authorization'], 'Bearer test-key')
        self.assertEqual(request['content_type'], 'application/json')
        payload = request['payload']
        self.assertEqual(payload['model'], 'qwen/qwen3.6-27b')
        self.assertEqual(payload['response_format'], {'type': 'json_schema', 'json_schema': client.RESPONSE_SCHEMA})
        user_content = json.loads(payload['messages'][1]['content'])
        self.assertEqual(user_content['headers'], ['Date', 'Amount', 'Item', 'Currency'])
        self.assertEqual(user_content['sample_rows'], sample_rows[:5])
        self.assertNotIn(sample_rows[5], user_content['sample_rows'])

    def test_openai_compatible_client_rejects_invalid_structured_response(self):
        server, _requests = self._run_fake_provider({'choices': [{'message': {'content': 'not-json'}}]})
        client = OpenAICompatibleMappingClient(
            OpenAICompatibleProviderConfig(
                base_url=f'http://127.0.0.1:{server.server_port}',
                model='qwen/qwen3.6-27b',
                api_key='test-key',
            ),
            timeout=2,
        )

        with self.assertRaisesMessage(ExpenseImportAIError, 'invalid structured output'):
            client.infer_mapping(['Date', 'Amount'], [{'Date': '2026-04-01', 'Amount': '-12.00'}])

    def test_openai_compatible_client_surfaces_provider_failures(self):
        server, _requests = self._run_fake_provider({'error': {'message': 'boom'}}, status=500)
        client = OpenAICompatibleMappingClient(
            OpenAICompatibleProviderConfig(
                base_url=f'http://127.0.0.1:{server.server_port}',
                model='qwen/qwen3.6-27b',
                api_key='test-key',
            ),
            timeout=2,
        )

        with self.assertRaisesMessage(ExpenseImportAIError, 'provider request failed'):
            client.infer_mapping(['Date', 'Amount'], [{'Date': '2026-04-01', 'Amount': '-12.00'}])


class GenericExpenseImporterTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='expense-import-user', password='pass')
        self.other_user = User.objects.create_user(username='other-expense-import-user', password='pass')
        self.company = Company.objects.create(name='Importer Co')
        self.issuer = Issuer.objects.create(company=self.company)

    def _upload(self, name, rows, delimiter=','):
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()), delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)
        return SimpleUploadedFile(name, output.getvalue().encode('utf-8'), content_type='text/csv')

    def _xlsx_upload(self, name='card.xlsx'):
        from openpyxl import Workbook

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(['Preamble', None, None, None, None])
        worksheet.append(['Posted', 'Total', 'Memo', 'Id', 'Currency'])
        worksheet.append(['2026-01-02', -12.0, 'Lunch', 'A-1', 'EUR'])
        buffer = io.BytesIO()
        workbook.save(buffer)
        return SimpleUploadedFile(
            name,
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def _generic_mapping(self, name='Card CSV', owner=None, scope=ImportMapping.SCOPE_USER):
        return ImportMapping.objects.create(
            scope=scope,
            owner=owner if scope == ImportMapping.SCOPE_USER else None,
            name=name,
            normalized_header_signature=ImportMapping.signature_from_headers(['Posted', 'Total', 'Memo', 'Id', 'Currency']),
            mapping_json={
                'paid_date': 'Posted',
                'amount': 'Total',
                'description': 'Memo',
                'transaction_id': 'Id',
                'currency': 'Currency',
            },
        )

    def _mapping_for_headers(self, headers, mapping_json, name='Statement mapping'):
        return ImportMapping.objects.create(
            scope=ImportMapping.SCOPE_USER,
            owner=self.user,
            name=name,
            normalized_header_signature=ImportMapping.signature_from_headers(headers),
            mapping_json=mapping_json,
        )

    def _fixture_upload(self, fixture_name, content_type='application/octet-stream'):
        path = FIXTURE_DIR / fixture_name
        return SimpleUploadedFile(fixture_name, path.read_bytes(), content_type=content_type)

    def test_wise_csv_import_uses_global_mapping_without_ai(self):
        seed_wise_global_mapping()
        rows = [
            {
                'TransferWise ID': 'CARD-001',
                'Date': '07-11-2025',
                'Date Time': '07-11-2025 09:06:18.060',
                'Amount': '-500.00',
                'Currency': 'EUR',
                'Description': 'Invoice 1',
                'Payment Reference': 'Ref 1',
                'Transaction Type': 'DEBIT',
                'Transaction Details Type': 'CARD',
            },
            {
                'TransferWise ID': 'CARD-002',
                'Date': '07-11-2025',
                'Date Time': '07-11-2025 09:06:18.060',
                'Amount': '-10.00',
                'Currency': 'EUR',
                'Description': 'Conversion',
                'Payment Reference': '',
                'Transaction Type': 'DEBIT',
                'Transaction Details Type': 'CONVERSION',
            },
        ]
        ai_client = StubMappingClient({'paid_date': 'Date', 'amount': 'Amount'})

        result = GenericExpenseImporter(self.user, self.issuer, ai_client=ai_client).import_files([self._upload('wise.csv', rows)])

        self.assertEqual(result.mapping_source, 'global')
        self.assertEqual(ai_client.calls, [])
        self.assertEqual(result.created, 1)
        self.assertEqual(result.skipped_conversions, 1)
        expense = Expense.objects.get()
        self.assertEqual(expense.external_id, 'CARD-001')
        self.assertEqual(expense.amount, Decimal('500.00'))
        self.assertEqual(expense.description, 'Invoice 1\nRef 1')

    def test_non_wise_csv_uses_ai_mapping_and_selected_rows(self):
        rows = [
            {'Posted': '2026-01-02', 'Total': '-12.345', 'Memo': 'Lunch', 'Id': 'A-1', 'Currency': 'USD'},
            {'Posted': '2026-01-03', 'Total': '-50.00', 'Memo': 'Hotel', 'Id': 'A-2', 'Currency': 'USD'},
        ]
        ai_client = StubMappingClient(
            {
                'paid_date': 'Posted',
                'amount': 'Total',
                'description': 'Memo',
                'transaction_id': 'Id',
                'currency': 'Currency',
            }
        )

        result = GenericExpenseImporter(self.user, self.issuer, ai_client=ai_client).import_files(
            [self._upload('card.csv', rows, delimiter=';')],
            selected_row_indexes={2},
        )

        self.assertEqual(result.mapping_source, 'ai')
        self.assertEqual(len(ai_client.calls), 1)
        self.assertEqual(result.created, 1)
        self.assertEqual(result.skipped_unselected, 1)
        expense = Expense.objects.get()
        self.assertEqual(expense.external_id, 'A-2')
        self.assertEqual(expense.amount, Decimal('50.00'))
        self.assertEqual(expense.raw_data['expense_import']['currency'], 'USD')

    def test_user_mapping_precedes_global_mapping_and_skips_ai(self):
        self._generic_mapping(name='Global card', scope=ImportMapping.SCOPE_GLOBAL)
        user_mapping = self._generic_mapping(name='My card', owner=self.user)
        ai_client = StubMappingClient({'paid_date': 'Posted', 'amount': 'Total'})

        result = GenericExpenseImporter(self.user, self.issuer, ai_client=ai_client).import_files(
            [self._upload('card.csv', [{'Posted': '2026-01-02', 'Total': '-12.00', 'Memo': 'Lunch', 'Id': 'A-1', 'Currency': 'EUR'}])]
        )

        self.assertEqual(result.mapping, user_mapping)
        self.assertEqual(result.mapping_source, 'user')
        self.assertEqual(ai_client.calls, [])

    def test_invalid_inferred_mapping_is_rejected(self):
        rows = [{'Posted': '2026-01-02', 'Total': '-12.00'}]
        ai_client = StubMappingClient({'paid_date': 'Missing', 'amount': 'Total'})

        with self.assertRaisesMessage(ExpenseImportError, 'Missing'):
            GenericExpenseImporter(self.user, self.issuer, ai_client=ai_client).import_files([self._upload('card.csv', rows)])

        self.assertEqual(Expense.objects.count(), 0)

    def test_provider_errors_do_not_create_expenses(self):
        rows = [{'Posted': '2026-01-02', 'Total': '-12.00'}]
        ai_client = StubMappingClient(exc=RuntimeError('provider down'))

        with self.assertRaisesMessage(ExpenseImportError, 'Mapping inference provider failed'):
            GenericExpenseImporter(self.user, self.issuer, ai_client=ai_client).import_files([self._upload('card.csv', rows)])

        self.assertEqual(Expense.objects.count(), 0)

    def test_duplicate_detection_uses_transaction_id_and_fingerprint(self):
        mapping = self._generic_mapping(owner=self.user)
        rows = [{'Posted': '2026-01-02', 'Total': '-12.00', 'Memo': 'Lunch', 'Id': 'A-1', 'Currency': 'EUR'}]
        importer = GenericExpenseImporter(self.user, self.issuer)

        first = importer.import_files([self._upload('card.csv', rows)], mapping=mapping)
        second = importer.import_files([self._upload('card.csv', rows)], mapping=mapping)

        self.assertEqual(first.created, 1)
        self.assertEqual(second.created, 0)
        self.assertEqual(second.skipped_existing, 1)
        self.assertEqual(Expense.objects.count(), 1)

    def test_zip_upload_parses_csv_members(self):
        mapping = self._generic_mapping(owner=self.user)
        csv_upload = self._upload(
            'card.csv',
            [{'Posted': '2026-01-02', 'Total': '-12.00', 'Memo': 'Lunch', 'Id': 'A-1', 'Currency': 'EUR'}],
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('nested/card.csv', csv_upload.read())
        upload = SimpleUploadedFile('export.zip', buffer.getvalue(), content_type='application/zip')

        result = GenericExpenseImporter(self.user, self.issuer).import_files([upload], mapping=mapping)

        self.assertEqual(result.created, 1)

    def test_xlsx_upload_parses_spreadsheet_before_generic_zip(self):
        mapping = self._generic_mapping(owner=self.user)

        result = GenericExpenseImporter(self.user, self.issuer).import_files([self._xlsx_upload()], mapping=mapping)

        self.assertEqual(result.created, 1)
        expense = Expense.objects.get()
        self.assertEqual(expense.external_id, 'A-1')
        self.assertEqual(expense.amount, Decimal('12.00'))

    def test_xls_upload_parses_legacy_spreadsheet_dates(self):
        mapping = self._generic_mapping(owner=self.user)

        class FakeCell:
            def __init__(self, value, ctype=1):
                self.value = value
                self.ctype = ctype

        class FakeSheet:
            visibility = 0

            def __init__(self, rows):
                self._rows = rows
                self.nrows = len(rows)

            def row(self, index):
                return self._rows[index]

        class FakeWorkbook:
            datemode = 0

            def sheets(self):
                return [
                    FakeSheet(
                        [
                            [FakeCell('Posted'), FakeCell('Total'), FakeCell('Memo'), FakeCell('Id'), FakeCell('Currency')],
                            [FakeCell(46024, ctype=3), FakeCell(-12.0, ctype=2), FakeCell('Lunch'), FakeCell('A-1'), FakeCell('EUR')],
                        ]
                    )
                ]

        upload = SimpleUploadedFile('legacy.xls', b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1fake', content_type='application/vnd.ms-excel')
        with patch('xlrd.open_workbook', return_value=FakeWorkbook()):
            result = GenericExpenseImporter(self.user, self.issuer).import_files([upload], mapping=mapping)

        self.assertEqual(result.created, 1)
        expense = Expense.objects.get()
        self.assertEqual(expense.paid_date.isoformat(), '2026-01-02')

    def test_empty_upload_raises_controlled_error(self):
        upload = SimpleUploadedFile('empty.csv', b'', content_type='text/csv')

        with self.assertRaisesMessage(ExpenseImportError, 'file is empty'):
            GenericExpenseImporter(self.user, self.issuer).import_files([upload])

        self.assertEqual(Expense.objects.count(), 0)

    def test_corrupt_spreadsheet_raises_controlled_error(self):
        upload = SimpleUploadedFile('broken.xlsx', b'not a workbook', content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        with self.assertRaisesMessage(ExpenseImportError, 'invalid or unsupported XLSX file'):
            GenericExpenseImporter(self.user, self.issuer).import_files([upload])

        self.assertEqual(Expense.objects.count(), 0)

    def test_sanitized_attached_xlsx_skips_preamble_and_trailing_rows(self):
        mapping = self._mapping_for_headers(
            ['Value date', 'Date', 'Reason', 'Movement', 'Amount', 'Currency', 'Available', 'Currency 2', 'Comments'],
            {
                'paid_date': 'Date',
                'amount': 'Amount',
                'description': ['Reason', 'Movement'],
                'transaction_id': 'Movement',
                'currency': 'Currency',
            },
            name='Sanitized attached workbook',
        )

        result = GenericExpenseImporter(self.user, self.issuer).import_files(
            [self._fixture_upload('caixabank-attached.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')],
            mapping=mapping,
        )

        self.assertEqual(result.created, 5)
        self.assertEqual(result.skipped_invalid, 0)
        self.assertEqual(Expense.objects.count(), 5)
        self.assertFalse(Expense.objects.filter(description__icontains='End of report').exists())

    def test_semicolon_csv_fixture_normalizes_localized_amounts_and_dates(self):
        mapping = self._mapping_for_headers(
            ['Item', 'Date', 'Amount', 'Balance'],
            {
                'paid_date': 'Date',
                'amount': 'Amount',
                'description': 'Item',
            },
            name='Semicolon bank sample',
        )

        result = GenericExpenseImporter(self.user, self.issuer).import_files(
            [self._fixture_upload('caixabank-semicolon.csv', 'text/csv')],
            mapping=mapping,
        )

        self.assertEqual(result.created, 7)
        self.assertEqual(result.skipped_invalid, 0)
        self.assertEqual(
            list(Expense.objects.order_by('id').values_list('amount', flat=True)),
            [
                Decimal('99.14'),
                Decimal('300.08'),
                Decimal('1815.00'),
                Decimal('173.40'),
                Decimal('340.00'),
                Decimal('21.00'),
                Decimal('21.00'),
            ],
        )
        self.assertEqual(Expense.objects.first().paid_date.isoformat(), '2026-04-20')

    def test_csv_preamble_parse_failure_is_controlled_and_creates_no_expenses(self):
        upload = SimpleUploadedFile(
            'broken-bank.csv',
            b'Bank export\nGenerated for tests\nThis is not a transaction table\n',
            content_type='text/csv',
        )

        with self.assertRaisesMessage(ExpenseImportError, 'missing CSV headers'):
            GenericExpenseImporter(self.user, self.issuer).import_files([upload])

        self.assertEqual(Expense.objects.count(), 0)
