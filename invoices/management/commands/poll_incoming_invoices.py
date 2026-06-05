import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from invoices.models import IncomingEmailSource
from invoices.services.incoming_email import import_eml_fixture, poll_imap_source


class Command(BaseCommand):
    help = 'Manually poll an IMAP incoming invoice source or import synthetic .eml fixtures.'

    def add_arguments(self, parser):
        parser.add_argument('--source-id', type=int, required=True, help='IncomingEmailSource id to poll/import into.')
        parser.add_argument('--fixture', action='append', default=[], help='Path to a sanitized .eml fixture. May be repeated.')
        parser.add_argument('--fixture-dir', help='Directory of sanitized .eml fixtures to import.')
        parser.add_argument('--host', help='IMAP host. Defaults to INCOMING_IMAP_HOST.')
        parser.add_argument('--username', help='IMAP username. Defaults to INCOMING_IMAP_USERNAME.')
        parser.add_argument('--password-env', default='INCOMING_IMAP_PASSWORD', help='Environment variable containing the IMAP password.')
        parser.add_argument('--port', type=int, default=993, help='IMAP SSL port.')
        parser.add_argument('--limit', type=int, help='Maximum IMAP messages to fetch.')

    def handle(self, *args, **options):
        try:
            source = IncomingEmailSource.objects.get(pk=options['source_id'])
        except IncomingEmailSource.DoesNotExist as exc:
            raise CommandError('Incoming email source not found.') from exc

        fixtures = [Path(value) for value in options['fixture']]
        if options.get('fixture_dir'):
            fixtures.extend(sorted(Path(options['fixture_dir']).glob('*.eml')))

        if fixtures:
            created = 0
            for fixture in fixtures:
                result = import_eml_fixture(source, fixture)
                created += int(result.created)
                self.stdout.write(f'imported {fixture}: created={result.created} artifacts={result.artifacts_created}')
            self.stdout.write(self.style.SUCCESS(f'Imported {len(fixtures)} fixture(s); {created} new candidate(s).'))
            return

        host = options.get('host') or os.environ.get('INCOMING_IMAP_HOST')
        username = options.get('username') or os.environ.get('INCOMING_IMAP_USERNAME')
        password = os.environ.get(options['password_env'])
        if not host or not username or not password:
            raise CommandError('IMAP host, username, and password environment variable are required when not importing fixtures.')

        results = poll_imap_source(
            source,
            host=host,
            username=username,
            password=password,
            port=options['port'],
            limit=options.get('limit'),
        )
        self.stdout.write(self.style.SUCCESS(f'Polled {len(results)} message(s); {sum(1 for item in results if item.created)} new candidate(s).'))
