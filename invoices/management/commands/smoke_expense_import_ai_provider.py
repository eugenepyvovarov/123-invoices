from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from invoices.services.expense_import_ai import (
    ExpenseImportAIError,
    OpenAICompatibleMappingClient,
    OpenAICompatibleProviderConfig,
)


class Command(BaseCommand):
    help = 'Run an opt-in smoke test against an OpenAI-compatible expense mapping provider.'

    DEFAULT_BASE_URL = 'http://100.70.58.14:1234'
    DEFAULT_MODEL = 'qwen/qwen3.6-27b'
    DEFAULT_API_KEY = '1111'

    SANITIZED_HEADERS = ['Item', 'Date', 'Amount', 'Balance']
    SANITIZED_SAMPLE_ROWS = [
        {'Item': 'Sample tax payment', 'Date': '20/04/2026', 'Amount': '-99,14EUR', 'Balance': '272,38EUR'},
        {'Item': 'Sample supplier invoice', 'Date': '10/04/2026', 'Amount': '-300,08EUR', 'Balance': '371,52EUR'},
        {'Item': 'Sample deposit maintenance', 'Date': '10/04/2026', 'Amount': '+21,00EUR', 'Balance': '3 000,00EUR'},
    ]

    def add_arguments(self, parser):
        parser.add_argument('--base-url', default=self.DEFAULT_BASE_URL)
        parser.add_argument('--model', default=self.DEFAULT_MODEL)
        parser.add_argument('--api-key', default=self.DEFAULT_API_KEY)
        parser.add_argument('--timeout', type=int, default=30)

    def handle(self, *args, **options):
        client = OpenAICompatibleMappingClient(
            OpenAICompatibleProviderConfig(
                base_url=options['base_url'],
                model=options['model'],
                api_key=options['api_key'],
            ),
            timeout=options['timeout'],
        )
        try:
            mapping = client.infer_mapping(self.SANITIZED_HEADERS, self.SANITIZED_SAMPLE_ROWS)
        except ExpenseImportAIError as exc:
            raise CommandError(str(exc)) from exc

        missing_targets = sorted({'paid_date', 'amount'} - set(mapping))
        if missing_targets:
            raise CommandError(f'Provider response missed required mapping targets: {", ".join(missing_targets)}')

        self.stdout.write(
            self.style.SUCCESS(
                f'OpenAI-compatible mapping smoke passed for {options["base_url"]} using model {options["model"]}.'
            )
        )
