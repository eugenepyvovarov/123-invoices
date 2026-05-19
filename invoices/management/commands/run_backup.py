from django.core.management.base import BaseCommand, CommandError

from invoices.models import BackupConfiguration, BackupRun
from invoices.services.backups import execute_backup


class Command(BaseCommand):
    help = 'Run one backup immediately using the configured backup service.'

    def handle(self, *args, **options):
        configuration = BackupConfiguration.load()

        try:
            backup_run = execute_backup(configuration, trigger_source=BackupRun.TRIGGER_SOURCE_MANUAL)
        except Exception as exc:
            raise CommandError(f'Backup failed: {exc}') from exc

        self.stdout.write(
            self.style.SUCCESS(
                f'Backup completed successfully (run #{backup_run.pk}, key: {backup_run.storage_object_key}).'
            )
        )
