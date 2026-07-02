from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from accounts.models import ApiToken


class Command(BaseCommand):
    help = 'List API tokens without exposing plaintext secrets.'

    def add_arguments(self, parser):
        parser.add_argument('--user', help='Optional username or email address filter')

    def handle(self, *args, **options):
        queryset = ApiToken.objects.select_related('owner').all()
        if options.get('user'):
            user_ref = options['user']
            User = get_user_model()
            user = User.objects.filter(username=user_ref).first() or User.objects.filter(email=user_ref).first()
            if user is None:
                raise CommandError(f'User not found: {user_ref}')
            queryset = queryset.filter(owner=user)

        for token in queryset:
            status = 'revoked' if token.is_revoked else 'expired' if token.is_expired else 'active'
            self.stdout.write(
                f'{token.pk}\t{token.owner}\t{token.name}\t{token.prefix}\t{status}\t{token.expires_at or ""}'
            )
