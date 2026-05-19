from __future__ import annotations

import json
from pathlib import Path
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from invoices.models import normalize_import_header


class ExpenseImportAIError(Exception):
    """Raised when mapping inference cannot be completed."""


@dataclass(frozen=True)
class OpenAICompatibleProviderConfig:
    base_url: str
    model: str
    api_key: str


class OpenAICompatibleMappingClient:
    """Small OpenAI-compatible structured-output client for CSV mapping inference."""

    FIXTURE_BASE_URL = 'https://expense-import-ai-fixture.local'
    FIXTURE_MODEL = 'expense-import-card-mapping-fixture'

    RESPONSE_SCHEMA = {
        'name': 'expense_csv_mapping',
        'schema': {
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'paid_date': {'type': 'string'},
                'amount': {'type': 'string'},
                'description': {
                    'oneOf': [
                        {'type': 'string'},
                        {'type': 'array', 'items': {'type': 'string'}},
                    ],
                },
                'transaction_id': {'type': 'string'},
                'currency': {'type': 'string'},
                'date_formats': {'type': 'array', 'items': {'type': 'string'}},
                'amount_mode': {'type': 'string', 'enum': ['absolute', 'signed']},
            },
            'required': ['paid_date', 'amount'],
        },
        'strict': True,
    }

    def __init__(self, config: OpenAICompatibleProviderConfig, timeout: int = 30) -> None:
        self.config = config
        self.timeout = timeout

    def infer_mapping(self, headers: list[str], sample_rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.config.base_url or not self.config.model or not self.config.api_key:
            raise ExpenseImportAIError('OpenAI-compatible provider settings are incomplete.')

        if (
            self.config.base_url.rstrip('/') == self.FIXTURE_BASE_URL
            and self.config.model == self.FIXTURE_MODEL
        ):
            return self._fixture_mapping(headers)

        payload = {
            'model': self.config.model,
            'messages': [
                {
                    'role': 'system',
                    'content': (
                        'Map parsed expense statement headers to an expense import schema. Return only columns that exist in the '
                        'provided headers. Required targets are paid_date and amount.'
                    ),
                },
                {
                    'role': 'user',
                    'content': json.dumps({'headers': headers, 'sample_rows': sample_rows[:5]}, ensure_ascii=False),
                },
            ],
            'response_format': {'type': 'json_schema', 'json_schema': self.RESPONSE_SCHEMA},
        }
        url = self.config.base_url.rstrip('/') + '/v1/chat/completions'
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Authorization': f'Bearer {self.config.api_key}',
                'Content-Type': 'application/json',
            },
            method='POST',
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response_payload = json.loads(response.read().decode('utf-8'))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ExpenseImportAIError('Mapping inference provider request failed.') from exc

        try:
            content = response_payload['choices'][0]['message']['content']
            mapping = json.loads(content) if isinstance(content, str) else content
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ExpenseImportAIError('Mapping inference provider returned invalid structured output.') from exc
        if not isinstance(mapping, dict):
            raise ExpenseImportAIError('Mapping inference provider returned invalid structured output.')
        return mapping

    def _fixture_mapping(self, headers: list[str]) -> dict[str, Any]:
        normalized_headers = {normalize_import_header(header) for header in headers}
        if {'item', 'date', 'amount'}.issubset(normalized_headers):
            return {
                'paid_date': 'Date',
                'amount': 'Amount',
                'description': 'Item',
                'date_formats': ['%d/%m/%Y'],
                'amount_mode': 'absolute',
            }
        if {'date', 'reason', 'movement', 'amount'}.issubset(normalized_headers):
            return {
                'paid_date': 'Date',
                'amount': 'Amount',
                'description': ['Reason', 'Movement'],
                'currency': 'Currency',
                'date_formats': ['%d/%m/%Y'],
                'amount_mode': 'absolute',
            }
        fixture_path = Path(settings.BASE_DIR) / 'tests' / 'e2e' / 'fixtures' / 'expense-import' / 'card-mapping.json'
        try:
            mapping = json.loads(fixture_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise ExpenseImportAIError('Mapping inference fixture is unavailable.') from exc
        if not isinstance(mapping, dict):
            raise ExpenseImportAIError('Mapping inference fixture is invalid.')
        return mapping
