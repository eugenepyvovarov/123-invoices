import fcntl
import time as time_module
from contextlib import contextmanager
from pathlib import Path
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone

from invoices.models import BackupConfiguration, BackupRun
from invoices.services.backups import execute_backup


def get_backup_scheduler_lock_path() -> Path:
    return Path(getattr(settings, 'BACKUP_SCHEDULER_LOCK_PATH', settings.BASE_DIR / '.backup-scheduler.lock'))


def get_backup_scheduling_timezone() -> ZoneInfo:
    return ZoneInfo(getattr(settings, 'BACKUP_SCHEDULING_TIMEZONE', None) or settings.TIME_ZONE)


class Command(BaseCommand):
    help = 'Run the backup scheduler loop and trigger due daily backups.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--poll-interval',
            type=int,
            default=60,
            help='Seconds to wait between scheduler ticks.',
        )

    def handle(self, *args, **options):
        poll_interval = options['poll_interval']

        try:
            while True:
                self.run_scheduler_tick()
                time_module.sleep(poll_interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('Backup scheduler stopped.'))

    def run_scheduler_tick(self, *, now=None):
        with self._scheduler_lock() as lock_acquired:
            if not lock_acquired:
                self.stdout.write('Another backup scheduler tick is already running; skipping scheduler tick.')
                return None

            configuration = BackupConfiguration.load()

            if not configuration.is_enabled:
                self.stdout.write('Backups are disabled; skipping scheduler tick.')
                return None

            due_run_at = self._get_due_run_at(configuration, now=now)
            if due_run_at is None:
                self.stdout.write('Backup is not due yet; skipping scheduler tick.')
                return None

            existing_run = BackupRun.objects.filter(
                started_at__gte=due_run_at,
                trigger_source=BackupRun.TRIGGER_SOURCE_SCHEDULED,
            ).order_by(
                '-started_at',
                '-id',
            ).first()
            if existing_run is not None:
                self.stdout.write(
                    'Backup already processed for the current daily window; skipping scheduler tick.'
                )
                return existing_run

            try:
                backup_run = execute_backup(
                    configuration,
                    trigger_source=BackupRun.TRIGGER_SOURCE_SCHEDULED,
                )
            except BlockingIOError:
                self.stdout.write('Another backup run is already in progress; skipping scheduler tick.')
                return None
            except Exception as exc:
                raise CommandError(f'Backup scheduler run failed: {exc}') from exc

            self.stdout.write(
                self.style.SUCCESS(
                    f'Backup completed successfully (run #{backup_run.pk}, key: {backup_run.storage_object_key}).'
                )
            )
            return backup_run

    def _get_due_run_at(self, configuration, *, now=None):
        current_time = timezone.localtime(now or timezone.now(), get_backup_scheduling_timezone())
        due_run_at = current_time.replace(
            hour=configuration.daily_run_time.hour,
            minute=configuration.daily_run_time.minute,
            second=0,
            microsecond=0,
        )

        if due_run_at > current_time:
            return None

        return due_run_at

    def _get_scheduler_lock_file_path(self):
        return get_backup_scheduler_lock_path()

    @contextmanager
    def _scheduler_lock(self):
        lock_file_path = self._get_scheduler_lock_file_path()
        lock_file_path.parent.mkdir(parents=True, exist_ok=True)

        with lock_file_path.open('a+') as lock_file:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return

            try:
                yield True
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
