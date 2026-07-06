from datetime import datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import ApiToken


class Command(BaseCommand):
    help = 'Issue an account-owned API bearer token. The plaintext token is shown once.'

    def add_arguments(self, parser):
        parser.add_argument('user', help='Username or email address for the token owner')
        parser.add_argument('--name', default='API token', help='Human-readable token name')
        parser.add_argument('--expires-at', help='ISO-8601 expiry datetime')

    def handle(self, *args, **options):
        user_ref = options['user']
        User = get_user_model()
        user = User.objects.filter(username=user_ref).first() or User.objects.filter(email=user_ref).first()
        if user is None:
            raise CommandError(f'User not found: {user_ref}')

        expires_at = None
        if options.get('expires_at'):
            expires_at = datetime.fromisoformat(options['expires_at'])
            if timezone.is_naive(expires_at):
                expires_at = timezone.make_aware(expires_at, timezone.get_current_timezone())

        api_token, plaintext = ApiToken.issue(owner=user, name=options['name'], expires_at=expires_at)
        self.stdout.write(self.style.SUCCESS(f'Issued API token {api_token.pk} for {user}'))
        self.stdout.write(plaintext)
