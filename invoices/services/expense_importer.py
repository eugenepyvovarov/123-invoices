from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Sequence

from django.db import transaction

from invoices.models import Currency, Expense, ImportBatch, ImportMapping, ImportPreviewRow, Issuer, normalize_import_header
from invoices.services.expense_import_ai import ExpenseImportAIError
from invoices.services.expense_statement_parsers import ParsedStatementFile, StatementParseError, parse_statement_upload

class ExpenseImportError(Exception):
    """Raised when generic expense statement import cannot continue."""


ParsedExpenseCSV = ParsedStatementFile


@dataclass
class ExpenseImportResult:
    files_processed: int = 0
    rows_processed: int = 0
    created: int = 0
    skipped_existing: int = 0
    skipped_missing_reference: int = 0
    skipped_not_debit: int = 0
    skipped_conversions: int = 0
    skipped_unselected: int = 0
    skipped_invalid: int = 0
    errors: list[str] = field(default_factory=list)
    batch: ImportBatch | None = None
    mapping: ImportMapping | None = None
    mapping_source: str = ''

    def as_dict(self) -> dict[str, object]:
        return {
            'files_processed': self.files_processed,
            'rows_processed': self.rows_processed,
            'created': self.created,
            'skipped_existing': self.skipped_existing,
            'skipped_missing_reference': self.skipped_missing_reference,
            'skipped_not_debit': self.skipped_not_debit,
            'skipped_conversions': self.skipped_conversions,
            'skipped_unselected': self.skipped_unselected,
            'skipped_invalid': self.skipped_invalid,
            'errors': self.errors,
            'mapping_source': self.mapping_source,
        }


class GenericExpenseImporter:
    """Parse statement uploads, resolve mappings, preview rows, and create expenses."""

    REQUIRED_TARGETS = {'paid_date', 'amount'}
    COLUMN_TARGETS = {'paid_date', 'amount', 'description', 'transaction_id', 'currency', 'row_type', 'details_type'}
    NON_COLUMN_KEYS = {'date_formats', 'amount_mode'}
    DEFAULT_DATE_FORMATS = [
        '%Y-%m-%d',
        '%d-%m-%Y',
        '%m/%d/%Y',
        '%d/%m/%Y',
        '%Y/%m/%d',
        '%d-%m-%Y %H:%M:%S.%f',
        '%d-%m-%Y %H:%M:%S',
        '%Y-%m-%d %H:%M:%S',
    ]

    def __init__(self, user, issuer: Issuer, ai_client: Any | None = None) -> None:
        self.user = user
        self.issuer = issuer
        self.ai_client = ai_client
        self._currency_cache: dict[str, Currency] = {}

    def import_files(
        self,
        uploads: Sequence[object],
        mapping: ImportMapping | None = None,
        selected_row_indexes: set[int] | None = None,
    ) -> ExpenseImportResult:
        parsed_files = self.parse_uploads(uploads)
        if not parsed_files:
            raise ExpenseImportError('No statement files found in the uploaded files.')

        headers = parsed_files[0].headers
        result = ExpenseImportResult(files_processed=len(parsed_files))
        mapping, mapping_source = self.resolve_mapping(headers, parsed_files[0].rows[:5], mapping=mapping)
        self.validate_mapping(mapping.mapping_json, headers)
        result.mapping = mapping
        result.mapping_source = mapping_source

        rows: list[tuple[str, dict[str, str]]] = []
        for parsed in parsed_files:
            self.validate_mapping(mapping.mapping_json, parsed.headers)
            rows.extend((parsed.source_name, row) for row in parsed.rows)
        result.rows_processed = len(rows)
        if not rows:
            raise ExpenseImportError('No transactions found in the uploaded files.')

        if self.user is None:
            self._import_rows_without_batch(mapping, rows, result)
            return result

        batch = self.create_preview_batch(parsed_files, mapping, rows)
        result.batch = batch
        self.import_selected_preview_rows(batch, result, selected_row_indexes=selected_row_indexes)
        return result

    def parse_uploads(self, uploads: Sequence[object]) -> list[ParsedExpenseCSV]:
        if not uploads:
            raise ExpenseImportError('Upload at least one expense statement file (CSV, XLS, XLSX, or ZIP).')
        parsed: list[ParsedExpenseCSV] = []
        for uploaded in uploads:
            filename = getattr(uploaded, 'name', '') or 'statement'
            data = uploaded.read()
            if not data:
                raise ExpenseImportError(f'{filename}: file is empty.')
            try:
                parsed.extend(parse_statement_upload(data, filename))
            except StatementParseError as exc:
                raise ExpenseImportError(str(exc)) from exc
        return parsed

    def resolve_mapping(
        self,
        headers: list[str],
        sample_rows: list[dict[str, str]],
        mapping: ImportMapping | None = None,
    ) -> tuple[ImportMapping, str]:
        if mapping is not None:
            if not mapping.matches_headers(headers):
                raise ExpenseImportError('Selected mapping does not match the uploaded statement headers.')
            return mapping, 'selected'

        matched = ImportMapping.objects.best_for_user_and_headers(self.user, headers)
        if matched:
            source = 'user' if matched.scope == ImportMapping.SCOPE_USER else 'global'
            return matched, source

        if self.ai_client is None:
            raise ExpenseImportError('No saved mapping matches this statement. Configure AI provider settings to infer a mapping.')
        try:
            inferred_mapping = self.ai_client.infer_mapping(headers, sample_rows[:5])
        except ExpenseImportAIError:
            raise
        except Exception as exc:
            raise ExpenseImportError('Mapping inference provider failed.') from exc
        self.validate_mapping(inferred_mapping, headers)
        ai_mapping = ImportMapping(
            scope=ImportMapping.SCOPE_USER,
            owner=self.user,
            name='AI inferred mapping',
            normalized_header_signature=ImportMapping.signature_from_headers(headers),
            mapping_json=inferred_mapping,
        )
        return ai_mapping, 'ai'

    def validate_mapping(self, mapping_json: dict[str, Any], headers: list[str]) -> None:
        if not isinstance(mapping_json, dict):
            raise ExpenseImportError('Import mapping must be a structured object.')
        missing_targets = self.REQUIRED_TARGETS - set(mapping_json)
        if missing_targets:
            raise ExpenseImportError(f'Import mapping is missing required fields: {", ".join(sorted(missing_targets))}.')
        unsupported = set(mapping_json) - self.COLUMN_TARGETS - self.NON_COLUMN_KEYS
        if unsupported:
            raise ExpenseImportError(f'Import mapping contains unsupported fields: {", ".join(sorted(unsupported))}.')

        normalized_headers = {normalize_import_header(header): header for header in headers}
        for target in self.COLUMN_TARGETS & set(mapping_json):
            for column in self._as_columns(mapping_json[target]):
                if normalize_import_header(column) not in normalized_headers:
                    raise ExpenseImportError(f'Import mapping column "{column}" for {target} is not present in the statement.')

    def create_preview_batch(
        self,
        parsed_files: list[ParsedExpenseCSV],
        mapping: ImportMapping,
        rows: list[tuple[str, dict[str, str]]],
    ) -> ImportBatch:
        first_headers = parsed_files[0].headers
        batch = ImportBatch.objects.create(
            user=self.user,
            issuer=self.issuer,
            mapping=mapping if mapping.pk else None,
            status=ImportBatch.STATUS_MAPPED,
            source_filename=', '.join(parsed.source_name for parsed in parsed_files)[:255],
            normalized_header_signature=ImportMapping.signature_from_headers(first_headers),
            raw_headers=first_headers,
            metadata={'mapping_source': 'saved' if mapping.pk else 'ai'},
        )
        for index, (source_name, row) in enumerate(rows, start=1):
            mapped_data, errors = self.normalize_row(row, mapping.mapping_json, source_name=source_name)
            default_selected, skip_reason = self._default_selected(row, mapping.default_row_selection_rules)
            if skip_reason == 'not_debit':
                mapped_data['skip_reason'] = skip_reason
            elif skip_reason == 'conversion':
                mapped_data['skip_reason'] = skip_reason
            fingerprint = self._row_fingerprint(row, source_name)
            ImportPreviewRow.objects.create(
                batch=batch,
                row_index=index,
                raw_data=row,
                mapped_data=mapped_data,
                default_selected=default_selected,
                selected=default_selected,
                validation_errors=errors,
                fingerprint=fingerprint,
            )
        return batch

    def import_selected_preview_rows(
        self,
        batch: ImportBatch,
        result: ExpenseImportResult | None = None,
        selected_row_indexes: set[int] | None = None,
    ) -> ExpenseImportResult:
        result = result or ExpenseImportResult(batch=batch, mapping=batch.mapping)
        rows = batch.preview_rows.all()
        if selected_row_indexes is not None:
            rows.update(selected=False)
            batch.preview_rows.filter(row_index__in=selected_row_indexes).update(selected=True)
            rows = batch.preview_rows.all()
        for preview in rows:
            skip_reason = preview.mapped_data.get('skip_reason')
            if skip_reason == 'not_debit':
                result.skipped_not_debit += 1
                continue
            if skip_reason == 'conversion':
                result.skipped_conversions += 1
                continue
            if not preview.selected:
                result.skipped_unselected += 1
                continue
            if preview.validation_errors:
                result.skipped_invalid += 1
                result.errors.extend(preview.validation_errors)
                continue
            external_id = (preview.mapped_data.get('transaction_id') or '').strip()
            if not external_id:
                external_id = None
            if self._is_duplicate(external_id, preview.fingerprint):
                result.skipped_existing += 1
                continue
            with transaction.atomic():
                Expense.objects.create(
                    issuer=self.issuer,
                    customer=None,
                    project=None,
                    invoice=None,
                    paid_date=preview.mapped_data['paid_date'],
                    amount=Decimal(preview.mapped_data['amount']),
                    description=(preview.mapped_data.get('description') or '')[:255],
                    external_id=external_id,
                    raw_data={
                        'expense_import': {
                            'batch_id': batch.pk,
                            'row_index': preview.row_index,
                            'fingerprint': preview.fingerprint,
                            'currency': preview.mapped_data.get('currency'),
                        },
                        'row': preview.raw_data,
                    },
                )
            result.created += 1
        batch.status = ImportBatch.STATUS_IMPORTED
        batch.save(update_fields=['status', 'updated_at'])
        return result

    def _import_rows_without_batch(
        self,
        mapping: ImportMapping,
        rows: list[tuple[str, dict[str, str]]],
        result: ExpenseImportResult,
    ) -> None:
        for row_index, (source_name, row) in enumerate(rows, start=1):
            mapped_data, errors = self.normalize_row(row, mapping.mapping_json, source_name=source_name)
            selected, skip_reason = self._default_selected(row, mapping.default_row_selection_rules)
            if skip_reason == 'not_debit':
                result.skipped_not_debit += 1
                continue
            if skip_reason == 'conversion':
                result.skipped_conversions += 1
                continue
            if not selected:
                result.skipped_unselected += 1
                continue
            if errors:
                result.skipped_invalid += 1
                result.errors.extend(errors)
                continue
            external_id = (mapped_data.get('transaction_id') or '').strip() or None
            fingerprint = self._row_fingerprint(row, source_name)
            if self._is_duplicate(external_id, fingerprint):
                result.skipped_existing += 1
                continue
            Expense.objects.create(
                issuer=self.issuer,
                customer=None,
                project=None,
                invoice=None,
                paid_date=mapped_data['paid_date'],
                amount=Decimal(mapped_data['amount']),
                description=(mapped_data.get('description') or '')[:255],
                external_id=external_id,
                raw_data={
                    'expense_import': {
                        'batch_id': None,
                        'row_index': row_index,
                        'fingerprint': fingerprint,
                        'currency': mapped_data.get('currency'),
                    },
                    'row': row,
                },
            )
            result.created += 1

    def normalize_row(self, row: dict[str, str], mapping_json: dict[str, Any], source_name: str = '') -> tuple[dict[str, str], list[str]]:
        errors: list[str] = []
        mapped: dict[str, str] = {}
        transaction_id = self._value_for(row, mapping_json.get('transaction_id'))
        if transaction_id:
            mapped['transaction_id'] = transaction_id.strip()
        amount = self._parse_decimal(self._value_for(row, mapping_json.get('amount')))
        if amount is None:
            errors.append(f'{source_name}: invalid amount.')
        else:
            if mapping_json.get('amount_mode', 'absolute') == 'absolute':
                amount = abs(amount)
            mapped['amount'] = str(amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
        paid_date = self._parse_date(self._value_for(row, mapping_json.get('paid_date')), mapping_json.get('date_formats') or [])
        if paid_date is None:
            errors.append(f'{source_name}: invalid date.')
        else:
            mapped['paid_date'] = paid_date.isoformat()
        description = self._value_for(row, mapping_json.get('description'))
        mapped['description'] = description.strip()
        currency = (self._value_for(row, mapping_json.get('currency')) or 'EUR').strip().upper()
        mapped['currency'] = currency or 'EUR'
        self._get_currency(mapped['currency'])
        return mapped, errors

    def _as_columns(self, value: Any) -> list[str]:
        if value in (None, ''):
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def _value_for(self, row: dict[str, str], columns: Any) -> str:
        values = []
        normalized_row = {normalize_import_header(key): value for key, value in row.items()}
        for column in self._as_columns(columns):
            value = normalized_row.get(normalize_import_header(column), '')
            if value:
                values.append(str(value).strip())
        return '\n'.join(values)

    def _parse_decimal(self, raw: str | None) -> Decimal | None:
        if raw in (None, ''):
            return None
        normalized = str(raw).strip().replace('\u00a0', ' ')
        normalized = re.sub(r'(?i)\b[A-Z]{3}\b', '', normalized)
        normalized = re.sub(r'[^\d,\.\-+ ]', '', normalized).strip()
        normalized = normalized.replace(' ', '')
        if ',' in normalized and '.' in normalized:
            if normalized.rfind(',') > normalized.rfind('.'):
                normalized = normalized.replace('.', '').replace(',', '.')
            else:
                normalized = normalized.replace(',', '')
        elif ',' in normalized:
            whole, fraction = normalized.rsplit(',', 1)
            if len(fraction) == 3 and whole.lstrip('+-').isdigit():
                normalized = whole + fraction
            else:
                normalized = whole + '.' + fraction
        try:
            return Decimal(normalized)
        except (InvalidOperation, ValueError):
            return None

    def _parse_date(self, raw: str | None, formats: list[str]) -> date | None:
        if not raw:
            return None
        raw = raw.strip()
        for pattern in list(formats) + self.DEFAULT_DATE_FORMATS:
            try:
                return datetime.strptime(raw, pattern).date()
            except (ValueError, TypeError):
                continue
        try:
            return datetime.fromisoformat(raw).date()
        except ValueError:
            pass
        try:
            return datetime.strptime(raw.split()[0], '%d/%m/%Y').date()
        except (ValueError, TypeError):
            return None

    def _default_selected(self, row: dict[str, str], rules: dict[str, Any]) -> tuple[bool, str]:
        include_rules = rules.get('include') or []
        exclude_rules = rules.get('exclude') or []
        if include_rules and not all(self._rule_matches(row, rule) for rule in include_rules):
            return False, 'not_debit'
        for rule in exclude_rules:
            if self._rule_matches(row, rule):
                return False, 'conversion'
        return True, ''

    def _rule_matches(self, row: dict[str, str], rule: dict[str, str]) -> bool:
        column = rule.get('column')
        expected = rule.get('equals')
        if not column or expected is None:
            return False
        return self._value_for(row, column).strip().casefold() == str(expected).strip().casefold()

    def _row_fingerprint(self, row: dict[str, str], source_name: str) -> str:
        payload = json.dumps({'source': source_name, 'row': row}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def _is_duplicate(self, external_id: str | None, fingerprint: str) -> bool:
        if external_id and Expense.objects.filter(issuer=self.issuer, external_id=external_id).exists():
            return True
        return Expense.objects.filter(issuer=self.issuer, raw_data__expense_import__fingerprint=fingerprint).exists()

    def _get_currency(self, code: str) -> Currency:
        code = (code or 'EUR').upper()[:3]
        if code in self._currency_cache:
            return self._currency_cache[code]
        currency, _ = Currency.objects.get_or_create(code=code, defaults={'name': code, 'symbol': code})
        self._currency_cache[code] = currency
        return currency
