from django.core.management.base import BaseCommand, CommandError

from accounts.models import ApiToken


class Command(BaseCommand):
    help = 'Revoke an API token by id or prefix.'

    def add_arguments(self, parser):
        parser.add_argument('token', help='API token id or prefix')

    def handle(self, *args, **options):
        token_ref = options['token']
        queryset = ApiToken.objects.all()
        api_token = queryset.filter(pk=token_ref).first() if token_ref.isdigit() else None
        api_token = api_token or queryset.filter(prefix=token_ref).first()
        if api_token is None:
            raise CommandError(f'API token not found: {token_ref}')

        api_token.revoke()
        self.stdout.write(self.style.SUCCESS(f'Revoked API token {api_token.pk} ({api_token.prefix})'))
