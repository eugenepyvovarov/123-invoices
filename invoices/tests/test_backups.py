from datetime import datetime, time, timedelta, timezone as dt_timezone
from pathlib import Path
from io import StringIO
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4
import zipfile
from zoneinfo import ZoneInfo

from botocore.exceptions import ClientError
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from invoices.forms import BackupConfigurationForm
from invoices.management.commands.run_backup_scheduler import (
    Command as RunBackupSchedulerCommand,
    get_backup_scheduling_timezone,
    get_backup_scheduler_lock_path,
)
from invoices.models import BackupConfiguration, BackupRun, Company, Issuer
from invoices.services.backups import (
    BackupArtifact,
    BackupDestinationCheckError,
    apply_backup_retention,
    append_backup_run_event,
    backup_execution_lock,
    build_backup_storage_object_key,
    build_backup_s3_client,
    classify_backup_runs_for_retention,
    create_backup_artifact,
    execute_backup,
    generate_backup_download_url,
    get_backup_execution_lock_path,
    record_backup_run_failure,
    test_backup_destination,
)
from invoices.views import _next_backup_run_at, _prepare_recent_backup_runs


def example_storage_setting() -> str:
    return uuid4().hex


def example_storage_endpoint_url() -> str:
    return f"https://storage-{uuid4().hex}.invalid"


def example_user_password() -> str:
    return f"pw-{uuid4().hex}"


def example_destination_credentials() -> dict[str, str]:
    return {
        'access_key_id': example_storage_setting(),
        'secret_access_key': example_storage_setting(),
    }


class BackupConfigurationModelTests(TestCase):
    def test_enabled_configuration_requires_destination_credentials(self):
        configuration = BackupConfiguration(is_enabled=True)

        with self.assertRaises(ValidationError) as context:
            configuration.full_clean()

        self.assertEqual(
            set(context.exception.message_dict),
            {'endpoint_url', 'bucket_name', 'region', 'access_key_id', 'secret_access_key'},
        )

    def test_disabled_configuration_allows_blank_destination_credentials(self):
        configuration = BackupConfiguration(is_enabled=False)

        configuration.full_clean()

    def test_load_creates_singleton_configuration(self):
        configuration = BackupConfiguration.load()

        self.assertEqual(configuration.pk, BackupConfiguration.singleton_pk)
        self.assertEqual(BackupConfiguration.objects.count(), 1)

    def test_load_returns_existing_singleton_configuration(self):
        existing_configuration = BackupConfiguration.load()
        existing_configuration.bucket_name = 'daily-backups'
        existing_configuration.save()

        loaded_configuration = BackupConfiguration.load()

        self.assertEqual(loaded_configuration.pk, BackupConfiguration.singleton_pk)
        self.assertEqual(loaded_configuration.bucket_name, 'daily-backups')
        self.assertEqual(BackupConfiguration.objects.count(), 1)

    def test_save_forces_singleton_primary_key(self):
        BackupConfiguration.load()

        configuration = BackupConfiguration(pk=99, bucket_name='replacement-bucket')
        configuration.save()

        self.assertEqual(configuration.pk, BackupConfiguration.singleton_pk)
        self.assertEqual(BackupConfiguration.objects.count(), 1)
        self.assertEqual(BackupConfiguration.load().bucket_name, 'replacement-bucket')


class BackupRunModelTests(TestCase):
    def test_backup_run_defaults_trigger_source_to_manual(self):
        backup_run = BackupRun.objects.create()

        self.assertEqual(backup_run.trigger_source, BackupRun.TRIGGER_SOURCE_MANUAL)

    def test_backup_run_persists_structured_diagnostics_default(self):
        backup_run = BackupRun.objects.create()

        backup_run.refresh_from_db()

        self.assertEqual(
            backup_run.diagnostics,
            {
                'events': [],
                'failure': {
                    'stage': '',
                    'exception_class': '',
                    'message': '',
                    'context': {},
                },
            },
        )

    def test_backup_run_diagnostics_default_is_not_shared_between_instances(self):
        first_backup_run = BackupRun.objects.create()
        second_backup_run = BackupRun.objects.create()

        first_backup_run.diagnostics['events'].append({'stage': 'started'})
        first_backup_run.diagnostics['failure']['stage'] = 'upload'
        first_backup_run.save(update_fields=['diagnostics'])
        second_backup_run.refresh_from_db()

        self.assertEqual(second_backup_run.diagnostics['events'], [])
        self.assertEqual(second_backup_run.diagnostics['failure']['stage'], '')


class MediaServingTests(TestCase):
    def test_media_files_are_served_when_debug_is_disabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            media_root = Path(temp_dir)
            media_file = media_root / 'invoices_pdf' / 'sample.pdf'
            media_file.parent.mkdir(parents=True, exist_ok=True)
            media_file.write_bytes(b'%PDF-1.7\n')

            client = Client()
            with override_settings(DEBUG=False, MEDIA_ROOT=str(media_root)):
                response = client.get('/media/invoices_pdf/sample.pdf')

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b'%PDF-1.7\n')


class BackupConfigurationFormTests(TestCase):
    def _form_data(self, **overrides):
        data = {
            'endpoint_url': '',
            'bucket_name': '',
            'region': '',
            'object_prefix': '',
            'access_key_id': '',
            'secret_access_key': '',
            'is_enabled': 'on',
            'daily_run_time': '03:30',
            'daily_retention_count': 14,
            'weekly_retention_count': 26,
            'monthly_retention_count': 36,
        }
        data.update(overrides)
        return {f'backup_settings-{key}': value for key, value in data.items()}

    def test_enabled_form_requires_destination_credentials(self):
        form = BackupConfigurationForm(
            data=self._form_data(),
            instance=BackupConfiguration.load(),
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(
            set(form.errors),
            {'endpoint_url', 'bucket_name', 'region', 'access_key_id', 'secret_access_key'},
        )

    def test_valid_form_updates_backup_configuration(self):
        configuration = BackupConfiguration.load()
        destination_credentials = example_destination_credentials()
        endpoint_url = example_storage_endpoint_url()
        form = BackupConfigurationForm(
            data=self._form_data(
                endpoint_url=endpoint_url,
                bucket_name='invoice-backups',
                region='nyc3',
                object_prefix='daily-snapshots',
                **destination_credentials,
            ),
            instance=configuration,
        )

        self.assertTrue(form.is_valid(), form.errors)

        saved_configuration = form.save()
        saved_configuration.refresh_from_db()

        self.assertEqual(saved_configuration.endpoint_url, endpoint_url)
        self.assertEqual(saved_configuration.bucket_name, 'invoice-backups')
        self.assertEqual(saved_configuration.region, 'nyc3')
        self.assertEqual(saved_configuration.object_prefix, 'daily-snapshots')
        self.assertEqual(saved_configuration.access_key_id, destination_credentials['access_key_id'])
        self.assertEqual(saved_configuration.secret_access_key, destination_credentials['secret_access_key'])
        self.assertTrue(saved_configuration.is_enabled)
        self.assertEqual(saved_configuration.daily_run_time, time(hour=3, minute=30))
        self.assertEqual(saved_configuration.daily_retention_count, 14)
        self.assertEqual(saved_configuration.weekly_retention_count, 26)
        self.assertEqual(saved_configuration.monthly_retention_count, 36)

    def test_form_uses_backup_specific_widgets(self):
        form = BackupConfigurationForm(instance=BackupConfiguration.load())

        self.assertEqual(form.prefix, 'backup_settings')
        self.assertEqual(form.fields['daily_run_time'].widget.input_type, 'time')
        self.assertEqual(form.fields['secret_access_key'].widget.input_type, 'password')
        self.assertEqual(form.fields['daily_retention_count'].widget.attrs['min'], 0)


class SeedE2ESmokeCommandTests(TestCase):
    def test_seed_e2e_smoke_creates_recent_backup_rows_for_success_and_failure_evidence(self):
        stdout = StringIO()

        call_command('seed_e2e_smoke', stdout=stdout)

        seeded_runs = list(BackupRun.objects.order_by('-started_at'))

        self.assertGreaterEqual(len(seeded_runs), 5)
        self.assertEqual(seeded_runs[0].status, BackupRun.STATUS_SUCCEEDED)
        self.assertEqual(seeded_runs[1].status, BackupRun.STATUS_FAILED)
        self.assertTrue(any(run.storage_object_key and run.artifact_size_bytes for run in seeded_runs))
        self.assertEqual(seeded_runs[1].error_summary, 'RuntimeError: upload failed')
        self.assertEqual(seeded_runs[1].diagnostics['failure']['stage'], 'upload')
        self.assertEqual(seeded_runs[1].diagnostics['failure']['exception_class'], 'RuntimeError')
        self.assertIn('Seeded deterministic E2E smoke data.', stdout.getvalue())


class BackupSettingsViewTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.url = reverse('backup_settings')
        self.dashboard_url = reverse('dashboard')
        self.company = Company.objects.create(name='Admin Company')
        self.issuer = Issuer.objects.create(company=self.company)

    def _activate_company(self):
        session = self.client.session
        session['active_company_id'] = self.company.id
        session.save()

    def _post_data(self, **overrides):
        destination_credentials = example_destination_credentials()
        data = {
            'backup_settings-endpoint_url': example_storage_endpoint_url(),
            'backup_settings-bucket_name': 'invoice-backups',
            'backup_settings-region': 'us-east-1',
            'backup_settings-object_prefix': 'daily',
            'backup_settings-access_key_id': destination_credentials['access_key_id'],
            'backup_settings-secret_access_key': destination_credentials['secret_access_key'],
            'backup_settings-is_enabled': 'on',
            'backup_settings-daily_run_time': '04:45',
            'backup_settings-daily_retention_count': 14,
            'backup_settings-weekly_retention_count': 26,
            'backup_settings-monthly_retention_count': 36,
        }
        data.update(overrides)
        return data

    def _ajax_post(self, data):
        return self.client.post(
            self.url,
            data=data,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

    def _assert_settings_panel_form_sections(self, response):
        self.assertContains(response, 'id="backup-settings-panel"')
        self.assertContains(response, 'data-backup-settings-destination-section')
        self.assertContains(response, 'data-backup-settings-schedule-section')
        self.assertContains(response, 'data-backup-settings-test-feedback')
        self.assertContains(response, 'data-backup-settings-save-feedback')
        self.assertContains(response, 'data-backup-settings-actions')
        self.assertContains(response, 'name="action" value="test_s3_connection"')
        self.assertContains(response, 'name="action" value="save"')

    def _assert_test_button_is_inside_connection_box(self, response):
        html = response.content.decode()
        destination_section_start = html.index('data-backup-settings-destination-section')
        destination_section_end = html.index('</section>', destination_section_start)
        test_button_index = html.index('name="action" value="test_s3_connection"')
        actions_footer_index = html.index('data-backup-settings-actions')

        self.assertGreater(test_button_index, destination_section_start)
        self.assertLess(test_button_index, destination_section_end)
        self.assertLess(test_button_index, actions_footer_index)

    def _assert_backup_settings_tab_is_active(self, response):
        self.assertEqual(response.context['backup_tab'], 'settings')
        self.assertContains(response, 'href="#backup-settings-panel" class="tab-nav__link is-active"')
        self.assertContains(response, 'class="tab-panel backup-settings-tab-panel is-active" id="backup-settings-panel"')
        self.assertNotContains(response, 'href="#recent-backups-panel" class="tab-nav__link is-active"')

    def test_superuser_can_open_backup_settings_view(self):
        password = example_user_password()
        superuser = self.user_model.objects.create_superuser(
            username='backup-admin',
            email='backup-admin@example.com',
            password=password,
        )
        configuration = BackupConfiguration.load()
        configuration.is_enabled = True
        configuration.save()
        downloadable_run = BackupRun.objects.create(
            status=BackupRun.STATUS_SUCCEEDED,
            trigger_source=BackupRun.TRIGGER_SOURCE_MANUAL,
            started_at=timezone.make_aware(datetime(2026, 4, 18, 2, 0)),
            finished_at=timezone.make_aware(datetime(2026, 4, 18, 2, 5)),
            storage_object_key='backups/run-1.zip',
            artifact_size_bytes=4096,
        )
        BackupRun.objects.create(
            status=BackupRun.STATUS_FAILED,
            trigger_source=BackupRun.TRIGGER_SOURCE_SCHEDULED,
            started_at=timezone.make_aware(datetime(2025, 12, 31, 23, 0)),
            finished_at=None,
            storage_object_key='',
            artifact_size_bytes=None,
            error_summary='RuntimeError: upload failed',
        )

        self.client.force_login(superuser)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'invoices/backup_settings.html')
        self.assertIsInstance(response.context['backup_form'], BackupConfigurationForm)
        self.assertEqual(response.context['backup_configuration'].pk, BackupConfiguration.singleton_pk)
        self.assertIsNotNone(response.context['next_backup_run_at'])
        self.assertEqual(list(response.context['recent_backup_runs']), list(BackupRun.objects.all()[:10]))
        self.assertContains(response, 'Recent backups')
        self.assertContains(response, 'Backup settings')
        self.assertContains(response, 'href="#recent-backups-panel"')
        self.assertContains(response, 'href="#backup-settings-panel"')
        self.assertContains(response, 'id="recent-backups-panel"')
        self.assertContains(response, 'id="backup-settings-panel"')
        self.assertContains(response, 'data-backup-settings-destination-section')
        self.assertContains(response, 'S3 connection')
        self.assertContains(response, 'name="backup_settings-endpoint_url"')
        self.assertContains(response, 'name="backup_settings-bucket_name"')
        self.assertContains(response, 'name="backup_settings-region"')
        self.assertContains(response, 'name="backup_settings-object_prefix"')
        self.assertContains(response, 'name="backup_settings-access_key_id"')
        self.assertContains(response, 'name="backup_settings-secret_access_key"')
        self.assertContains(response, 'data-backup-settings-schedule-section')
        self.assertContains(response, 'data-backup-settings-status-badge-container')
        self.assertContains(response, 'data-backup-settings-status-badge')
        self.assertContains(response, 'name="backup_settings-is_enabled"')
        self.assertContains(response, 'name="backup_settings-daily_run_time"')
        self.assertContains(response, 'name="backup_settings-daily_retention_count"')
        self.assertContains(response, 'name="backup_settings-weekly_retention_count"')
        self.assertContains(response, 'name="backup_settings-monthly_retention_count"')
        self.assertContains(response, 'data-backup-settings-actions')
        self.assertContains(response, 'name="action" value="test_s3_connection"')
        self.assertContains(response, 'name="action" value="save"')
        self.assertNotContains(response, 'Next scheduled backup')
        self.assertNotContains(response, 'This runs immediately using the latest saved backup settings.')
        self.assertNotContains(response, 'Does not save form edits.')
        self.assertContains(response, 'Run backup now')
        self.assertContains(response, reverse('backup_run_now'))
        self.assertContains(response, 'method="post" action="/backup-settings/run-now/" class="mb-0"')
        self.assertContains(response, 'The daily run time is interpreted in UTC.')
        self.assertContains(response, 'Save changes')
        self.assertContains(response, 'Recent backups')
        self.assertContains(response, 'Source')
        self.assertContains(response, 'class="table-scroll"', html=False)
        self.assertContains(response, 'class="data-table"', html=False)
        self.assertContains(response, 'class="stack-gap-md backup-settings-tabs"', html=False)
        self.assertContains(response, 'class="tab-nav backup-settings-tab-nav"', html=False)
        self.assertContains(response, 'class="tab-container tab-panels stack-gap-md backup-settings-tab-container"', html=False)
        self.assertContains(response, 'class="tab-panel backup-settings-tab-panel is-active" id="recent-backups-panel"', html=False)
        self.assertContains(response, 'class="tab-panel backup-settings-tab-panel" id="backup-settings-panel"', html=False)
        self.assertContains(response, 'Manual')
        self.assertContains(response, 'Apr 18, 2026, 02:00')
        self.assertContains(response, 'Apr 18, 2026, 02:05')
        self.assertContains(response, 'Dec 31, 2025, 23:00')
        self.assertContains(response, '<th scope="col">Status</th>', html=True)
        self.assertNotContains(response, '<th scope="col">Error</th>', html=True)
        self.assertNotContains(response, 'data-label="Error"', html=False)
        self.assertNotContains(response, 'Object key')
        self.assertNotContains(response, 'backups/run-1.zip')
        self.assertNotContains(response, 'RuntimeError: upload failed')
        self.assertContains(response, 'backup-status-indicator backup-status-indicator--success', count=1)
        self.assertContains(response, 'backup-status-indicator backup-status-indicator--danger', count=1)
        self.assertContains(response, 'icon-tabler-circle-check', count=1)
        self.assertContains(response, 'icon-tabler-circle-x', count=1)
        self.assertContains(response, '<span class="visually-hidden">Succeeded</span>', html=True)
        self.assertContains(response, '<span class="visually-hidden">Failed</span>', html=True)
        self.assertContains(response, f'href="{reverse("backup_run_download", args=[downloadable_run.id])}"')
        self.assertContains(response, 'target="_blank"')
        self.assertContains(response, 'rel="noopener"')
        self.assertContains(response, '4.0')
        self.assertContains(response, 'KB')
        self.assertContains(response, 'data-label="Size"><span class="text-muted">—</span></td>', html=False)
        self.assertContains(
            response,
            f'<a href="{reverse("backup_run_detail", args=[downloadable_run.id])}" class="btn btn-sm btn-outline-secondary">View details</a>',
            html=True,
        )
        self.assertContains(response, 'class="text-end table-actions-cell"', html=False)
        self.assertContains(response, 'Test S3 connection')
        self._assert_test_button_is_inside_connection_box(response)

    @override_settings(TIME_ZONE='UTC', BACKUP_SCHEDULING_TIMEZONE='Europe/Madrid')
    def test_backup_settings_view_references_explicit_scheduling_timezone(self):
        superuser = self.user_model.objects.create_superuser(
            username='backup-timezone-admin',
            email='backup-timezone-admin@example.com',
            password=example_user_password(),
        )
        configuration = BackupConfiguration.load()
        configuration.is_enabled = True
        configuration.daily_run_time = time(hour=4, minute=45)
        configuration.save()

        self.client.force_login(superuser)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['backup_scheduling_timezone'], 'Europe/Madrid')
        self.assertContains(response, 'Recent backups')
        self.assertContains(response, 'Backup settings')
        self.assertNotContains(response, 'Backups will run daily at 04:45 in Europe/Madrid.')
        self.assertContains(response, 'The daily run time is interpreted in Europe/Madrid.')

    def test_superuser_sees_run_backup_now_action_without_old_summary_copy(self):
        superuser = self.user_model.objects.create_superuser(
            username='run-backup-visibility-admin',
            email='run-backup-visibility-admin@example.com',
            password=example_user_password(),
        )

        self.client.force_login(superuser)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Recent backups')
        self.assertContains(response, 'Backup settings')
        self.assertContains(response, 'method="post" action="/backup-settings/run-now/" class="mb-0"')
        self.assertContains(response, '<button type="submit" class="btn btn-outline-danger">Run backup now</button>', html=True)
        self.assertNotContains(response, 'This runs immediately using the latest saved backup settings.')
        self.assertNotContains(response, 'Does not save form edits.')

    def test_superuser_sees_backup_link_in_sidebar(self):
        superuser = self.user_model.objects.create_superuser(
            username='sidebar-admin',
            email='sidebar-admin@example.com',
            password=example_user_password(),
        )

        self.client.force_login(superuser)
        self._activate_company()
        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{self.url}"')
        self.assertContains(response, 'Backups')
        self.assertContains(response, 'class="btn btn-outline-secondary w-100 mb-2 sidebar__account-action"')
        self.assertContains(response, 'class="btn btn-outline-secondary w-100 sidebar__account-action"')
        self.assertContains(response, 'class="sidebar__account-action-content"', count=2)
        self.assertContains(response, 'class="sidebar__account-action-icon" aria-hidden="true"', count=2)
        self.assertContains(response, 'class="sidebar__account-action-label">Backups</span>', html=False)
        self.assertContains(response, 'class="sidebar__account-action-label">Logout</span>', html=False)
        self.assertContains(
            response,
            '<svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-database-export" width="18" height="18" viewBox="0 0 24 24" stroke-width="1.5"',
            html=False,
        )
        self.assertContains(response, f'method="post" action="{reverse("accounts:logout")}"')
        self.assertContains(
            response,
            '<svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-logout" width="18" height="18" viewBox="0 0 24 24" stroke-width="1.5"',
            html=False,
        )
        self.assertContains(response, 'type="submit"')

    def test_non_superuser_does_not_see_backup_link_in_sidebar(self):
        user = self.user_model.objects.create_user(
            username='sidebar-user',
            email='sidebar-user@example.com',
            password=example_user_password(),
        )
        self.issuer.users.add(user)

        self.client.force_login(user)
        self._activate_company()
        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'href="/backup-settings/"')

    def test_non_superuser_cannot_open_backup_settings_view(self):
        password = example_user_password()
        user = self.user_model.objects.create_user(
            username='backup-user',
            email='backup-user@example.com',
            password=password,
        )

        self.client.force_login(user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)
        self.assertNotContains(response, 'Run backup now', status_code=403)

    def test_superuser_can_open_backup_run_detail_view(self):
        superuser = self.user_model.objects.create_superuser(
            username='backup-run-admin',
            email='backup-run-admin@example.com',
            password=example_user_password(),
        )
        backup_run = BackupRun.objects.create(status=BackupRun.STATUS_SUCCEEDED)

        self.client.force_login(superuser)
        response = self.client.get(reverse('backup_run_detail', args=[backup_run.id]))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'invoices/backup_run_detail.html')
        self.assertEqual(response.context['backup_run'], backup_run)

    def test_non_superuser_cannot_open_backup_run_detail_view(self):
        user = self.user_model.objects.create_user(
            username='backup-run-user',
            email='backup-run-user@example.com',
            password=example_user_password(),
        )
        backup_run = BackupRun.objects.create(status=BackupRun.STATUS_SUCCEEDED)

        self.client.force_login(user)
        response = self.client.get(reverse('backup_run_detail', args=[backup_run.id]))

        self.assertEqual(response.status_code, 403)

    @override_settings(TIME_ZONE='UTC')
    def test_prepare_recent_backup_runs_adds_compact_datetime_displays_with_year_suppression(self):
        recent_runs = [
            BackupRun(
                id=1,
                status=BackupRun.STATUS_SUCCEEDED,
                started_at=datetime(2026, 4, 18, 2, 0, tzinfo=dt_timezone.utc),
                finished_at=datetime(2026, 4, 18, 2, 5, tzinfo=dt_timezone.utc),
                storage_object_key='daily/2026/04/18/run-1.zip',
            ),
            BackupRun(
                id=2,
                status=BackupRun.STATUS_FAILED,
                started_at=datetime(2026, 4, 17, 2, 0, tzinfo=dt_timezone.utc),
                finished_at=datetime(2025, 12, 31, 23, 55, tzinfo=dt_timezone.utc),
                storage_object_key='daily/2026/04/17/run-2.zip',
            ),
            BackupRun(
                id=3,
                status=BackupRun.STATUS_IN_PROGRESS,
                started_at=datetime(2025, 12, 31, 23, 0, tzinfo=dt_timezone.utc),
                finished_at=None,
                storage_object_key='',
            ),
        ]

        prepared_runs = _prepare_recent_backup_runs(recent_runs)

        self.assertEqual(prepared_runs[0].started_at_display, 'Apr 18, 2026, 02:00')
        self.assertFalse(prepared_runs[1].started_at_shows_year)
        self.assertEqual(prepared_runs[1].started_at_display, 'Apr 17, 02:00')
        self.assertTrue(prepared_runs[2].started_at_shows_year)
        self.assertEqual(prepared_runs[2].started_at_display, 'Dec 31, 2025, 23:00')
        self.assertEqual(prepared_runs[0].finished_at_display, 'Apr 18, 2026, 02:05')
        self.assertTrue(prepared_runs[1].finished_at_shows_year)
        self.assertEqual(prepared_runs[1].finished_at_display, 'Dec 31, 2025, 23:55')
        self.assertEqual(prepared_runs[2].finished_at_display, '')
        self.assertEqual(
            prepared_runs[0].status_indicator,
            {'icon': 'circle-check', 'variant': 'success', 'label': 'Succeeded'},
        )
        self.assertEqual(
            prepared_runs[1].status_indicator,
            {'icon': 'circle-x', 'variant': 'danger', 'label': 'Failed'},
        )
        self.assertEqual(
            prepared_runs[2].status_indicator,
            {'icon': 'progress', 'variant': 'muted', 'label': 'In progress'},
        )
        self.assertEqual(prepared_runs[0].download_url, reverse('backup_run_download', args=[1]))
        self.assertEqual(prepared_runs[2].download_url, '')

    @override_settings(TIME_ZONE='Europe/Madrid')
    def test_prepare_recent_backup_runs_formats_in_local_timezone(self):
        recent_run = BackupRun(
            id=1,
            started_at=datetime(2026, 4, 18, 0, 0, tzinfo=dt_timezone.utc),
            finished_at=datetime(2026, 4, 18, 0, 5, tzinfo=dt_timezone.utc),
            storage_object_key='daily/2026/04/18/run-1.zip',
        )

        prepared_run = _prepare_recent_backup_runs([recent_run])[0]

        self.assertEqual(prepared_run.started_at_display, 'Apr 18, 2026, 02:00')
        self.assertEqual(prepared_run.finished_at_display, 'Apr 18, 2026, 02:05')

    def test_backup_run_detail_renders_successful_run_summary_and_events(self):
        superuser = self.user_model.objects.create_superuser(
            username='backup-run-success-admin',
            email='backup-run-success-admin@example.com',
            password=example_user_password(),
        )
        backup_run = BackupRun.objects.create(
            status=BackupRun.STATUS_SUCCEEDED,
            trigger_source=BackupRun.TRIGGER_SOURCE_SCHEDULED,
            started_at=timezone.make_aware(datetime(2026, 3, 30, 2, 15)),
            finished_at=timezone.make_aware(datetime(2026, 3, 30, 2, 20)),
            storage_object_key='daily/2026/03/30/backup-20260330T021500Z.zip',
            artifact_size_bytes=4096,
            retention_bucket=BackupRun.RETENTION_BUCKET_DAILY,
            diagnostics={
                'events': [
                    {
                        'timestamp': '2026-03-30T02:15:01Z',
                        'stage': 'artifact_created',
                        'message': 'Backup artifact created.',
                        'context': {'size_bytes': 4096},
                    },
                    {
                        'timestamp': '2026-03-30T02:15:05Z',
                        'stage': 'retention_applied',
                        'message': 'Backup retention applied.',
                        'context': {'retention_bucket': BackupRun.RETENTION_BUCKET_DAILY},
                    },
                ],
                'failure': {
                    'stage': '',
                    'exception_class': '',
                    'message': '',
                    'context': {},
                },
            },
        )

        self.client.force_login(superuser)
        response = self.client.get(reverse('backup_run_detail', args=[backup_run.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'Backup run #{backup_run.id}')
        self.assertContains(response, 'Succeeded')
        self.assertContains(response, 'Source')
        self.assertContains(response, 'Scheduled')
        self.assertContains(response, 'daily/2026/03/30/backup-20260330T021500Z.zip')
        self.assertContains(response, '4.0')
        self.assertContains(response, '4,096 bytes')
        self.assertContains(response, 'Daily')
        self.assertContains(response, 'No failure diagnostics were recorded for this run.')
        self.assertContains(response, 'artifact_created')
        self.assertContains(response, 'Backup artifact created.')
        self.assertContains(response, 'retention_applied')
        self.assertContains(response, '2026-03-30T02:15:05Z')

    def test_backup_run_detail_renders_failed_run_error_summary_and_failure_diagnostics(self):
        superuser = self.user_model.objects.create_superuser(
            username='backup-run-failure-admin',
            email='backup-run-failure-admin@example.com',
            password=example_user_password(),
        )
        backup_run = BackupRun.objects.create(
            status=BackupRun.STATUS_FAILED,
            trigger_source=BackupRun.TRIGGER_SOURCE_MANUAL,
            started_at=timezone.make_aware(datetime(2026, 3, 30, 2, 15)),
            finished_at=timezone.make_aware(datetime(2026, 3, 30, 2, 16)),
            storage_object_key='daily/2026/03/30/backup-20260330T021500Z.zip',
            error_summary='RuntimeError: upload failed',
            diagnostics={
                'events': [
                    {
                        'timestamp': '2026-03-30T02:15:02Z',
                        'stage': 'upload',
                        'message': 'Backup run failed.',
                        'context': {
                            'stage': 'upload',
                            'exception_class': 'RuntimeError',
                            'message': 'upload failed',
                            'context': {'object_key': 'daily/2026/03/30/backup-20260330T021500Z.zip'},
                        },
                    }
                ],
                'failure': {
                    'stage': 'upload',
                    'exception_class': 'RuntimeError',
                    'message': 'upload failed',
                    'context': {
                        'bucket_name': 'invoice-backups',
                        'object_key': 'daily/2026/03/30/backup-20260330T021500Z.zip',
                    },
                },
            },
        )

        self.client.force_login(superuser)
        response = self.client.get(reverse('backup_run_detail', args=[backup_run.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Failed')
        self.assertContains(response, 'Source')
        self.assertContains(response, 'Manual')
        self.assertContains(response, 'RuntimeError: upload failed')
        self.assertContains(response, 'upload')
        self.assertContains(response, 'RuntimeError')
        self.assertContains(response, 'bucket_name')
        self.assertContains(response, 'invoice-backups')
        self.assertContains(response, 'object_key')
        self.assertContains(response, 'upload failed')
        self.assertContains(response, '2026-03-30T02:15:02Z')

    @patch('invoices.views.test_backup_destination')
    def test_superuser_can_submit_backup_settings_form(self, test_backup_destination_mock):
        password = example_user_password()
        superuser = self.user_model.objects.create_superuser(
            username='backup-admin',
            email='backup-admin@example.com',
            password=password,
        )
        submitted_data = self._post_data()

        self.client.force_login(superuser)
        response = self.client.post(self.url, data=submitted_data, follow=True)

        configuration = BackupConfiguration.load()

        self.assertRedirects(response, self.url)
        self.assertTemplateUsed(response, 'invoices/backup_settings.html')
        self.assertContains(response, 'Backup settings saved successfully.')
        self.assertContains(response, 'Enabled')
        self.assertContains(response, 'Recent backups')
        self.assertContains(response, 'Backup settings')
        self.assertContains(response, 'The daily run time is interpreted in UTC.')
        self.assertNotContains(response, 'Backups will run daily at 04:45 in UTC.')
        self._assert_settings_panel_form_sections(response)
        self.assertEqual(configuration.endpoint_url, submitted_data['backup_settings-endpoint_url'])
        self.assertEqual(configuration.bucket_name, 'invoice-backups')
        self.assertEqual(configuration.region, 'us-east-1')
        self.assertEqual(configuration.object_prefix, 'daily')
        self.assertEqual(configuration.access_key_id, submitted_data['backup_settings-access_key_id'])
        self.assertEqual(configuration.secret_access_key, submitted_data['backup_settings-secret_access_key'])
        self.assertTrue(configuration.is_enabled)
        self.assertEqual(configuration.daily_run_time, time(hour=4, minute=45))
        self.assertEqual(configuration.daily_retention_count, 14)
        self.assertEqual(configuration.weekly_retention_count, 26)
        self.assertEqual(configuration.monthly_retention_count, 36)
        test_backup_destination_mock.assert_not_called()

    @patch('invoices.views.test_backup_destination')
    def test_superuser_can_test_s3_connection_successfully(self, test_backup_destination_mock):
        superuser = self.user_model.objects.create_superuser(
            username='backup-test-success-admin',
            email='backup-test-success-admin@example.com',
            password=example_user_password(),
        )

        self.client.force_login(superuser)
        response = self.client.post(
            self.url,
            data=self._post_data(action='test_s3_connection'),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'S3 connection test succeeded.')
        self._assert_settings_panel_form_sections(response)
        self._assert_backup_settings_tab_is_active(response)
        test_backup_destination_mock.assert_called_once()
        self.assertFalse(BackupRun.objects.exists())

    @patch('invoices.services.backups.execute_backup')
    @patch('invoices.services.backups.create_backup_artifact')
    @patch('invoices.views.test_backup_destination')
    def test_test_action_does_not_invoke_backup_execution_or_artifact_creation(
        self,
        test_backup_destination_mock,
        create_backup_artifact_mock,
        execute_backup_mock,
    ):
        superuser = self.user_model.objects.create_superuser(
            username='backup-test-no-side-effects-admin',
            email='backup-test-no-side-effects-admin@example.com',
            password=example_user_password(),
        )

        self.client.force_login(superuser)
        response = self.client.post(
            self.url,
            data=self._post_data(action='test_s3_connection'),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'S3 connection test succeeded.')
        self._assert_settings_panel_form_sections(response)
        self._assert_backup_settings_tab_is_active(response)
        test_backup_destination_mock.assert_called_once()
        create_backup_artifact_mock.assert_not_called()
        execute_backup_mock.assert_not_called()

    @patch('invoices.views.test_backup_destination')
    def test_superuser_sees_test_s3_connection_failure_message(self, test_backup_destination_mock):
        superuser = self.user_model.objects.create_superuser(
            username='backup-test-failure-admin',
            email='backup-test-failure-admin@example.com',
            password=example_user_password(),
        )
        test_backup_destination_mock.side_effect = BackupDestinationCheckError(
            'Could not access the bucket with these credentials. Check the access key, secret key, and bucket permissions.'
        )

        self.client.force_login(superuser)
        response = self.client.post(
            self.url,
            data=self._post_data(action='test_s3_connection'),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'Could not access the bucket with these credentials. Check the access key, secret key, and bucket permissions.',
        )
        self._assert_settings_panel_form_sections(response)
        self._assert_backup_settings_tab_is_active(response)
        test_backup_destination_mock.assert_called_once()

    @patch('invoices.views.test_backup_destination')
    def test_non_superuser_cannot_trigger_test_s3_connection(self, test_backup_destination_mock):
        user = self.user_model.objects.create_user(
            username='backup-test-user',
            email='backup-test-user@example.com',
            password=example_user_password(),
        )

        self.client.force_login(user)
        response = self.client.post(
            self.url,
            data=self._post_data(action='test_s3_connection'),
        )

        self.assertEqual(response.status_code, 403)
        test_backup_destination_mock.assert_not_called()

    @patch('invoices.views.test_backup_destination')
    def test_test_action_uses_bound_form_data_without_persisting_changes(self, test_backup_destination_mock):
        superuser = self.user_model.objects.create_superuser(
            username='backup-test-admin',
            email='backup-test-admin@example.com',
            password=example_user_password(),
        )
        configuration = BackupConfiguration.load()
        configuration.endpoint_url = 'https://saved-storage.example.com'
        configuration.bucket_name = 'saved-bucket'
        configuration.region = 'saved-region'
        configuration.object_prefix = 'saved-prefix'
        saved_credentials = example_destination_credentials()
        configuration.access_key_id = saved_credentials['access_key_id']
        configuration.secret_access_key = saved_credentials['secret_access_key']
        configuration.is_enabled = False
        configuration.save()

        submitted_data = self._post_data(
            action='test_s3_connection',
            **{
                'backup_settings-endpoint_url': 'https://submitted-storage.example.com',
                'backup_settings-bucket_name': 'submitted-bucket',
                'backup_settings-region': 'submitted-region',
                'backup_settings-object_prefix': 'submitted-prefix',
                **{
                    f'backup_settings-{key}': value
                    for key, value in example_destination_credentials().items()
                },
                'backup_settings-daily_run_time': '06:15',
            },
        )

        self.client.force_login(superuser)
        response = self.client.post(self.url, data=submitted_data)

        configuration.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'S3 connection test succeeded.')
        self._assert_settings_panel_form_sections(response)
        self._assert_backup_settings_tab_is_active(response)
        self.assertTrue(response.context['backup_form'].is_bound)
        self.assertFalse(response.context['backup_form'].errors)
        self.assertEqual(response.context['backup_configuration'].endpoint_url, 'https://submitted-storage.example.com')
        self.assertEqual(response.context['backup_configuration'].bucket_name, 'submitted-bucket')
        self.assertEqual(response.context['backup_configuration'].daily_run_time, time(hour=6, minute=15))
        self.assertEqual(configuration.endpoint_url, 'https://saved-storage.example.com')
        self.assertEqual(configuration.bucket_name, 'saved-bucket')
        self.assertEqual(configuration.region, 'saved-region')
        self.assertEqual(configuration.object_prefix, 'saved-prefix')
        self.assertEqual(configuration.access_key_id, saved_credentials['access_key_id'])
        self.assertEqual(configuration.secret_access_key, saved_credentials['secret_access_key'])
        self.assertFalse(configuration.is_enabled)
        test_backup_destination_mock.assert_called_once()
        tested_configuration = test_backup_destination_mock.call_args.args[0]
        self.assertEqual(tested_configuration.endpoint_url, 'https://submitted-storage.example.com')
        self.assertEqual(tested_configuration.bucket_name, 'submitted-bucket')
        self.assertEqual(tested_configuration.region, 'submitted-region')
        self.assertEqual(tested_configuration.object_prefix, 'submitted-prefix')
        self.assertEqual(
            tested_configuration.access_key_id,
            submitted_data['backup_settings-access_key_id'],
        )
        self.assertEqual(
            tested_configuration.secret_access_key,
            submitted_data['backup_settings-secret_access_key'],
        )
        self.assertTrue(tested_configuration.is_enabled)
        self.assertEqual(tested_configuration.daily_run_time, time(hour=6, minute=15))

    @patch('invoices.views.test_backup_destination')
    def test_test_action_shows_bound_form_errors_without_persisting_changes(self, test_backup_destination_mock):
        superuser = self.user_model.objects.create_superuser(
            username='backup-invalid-admin',
            email='backup-invalid-admin@example.com',
            password=example_user_password(),
        )
        configuration = BackupConfiguration.load()
        configuration.endpoint_url = 'https://saved-storage.example.com'
        configuration.bucket_name = 'saved-bucket'
        configuration.region = 'saved-region'
        saved_credentials = example_destination_credentials()
        configuration.access_key_id = saved_credentials['access_key_id']
        configuration.secret_access_key = saved_credentials['secret_access_key']
        configuration.is_enabled = False
        configuration.save()

        submitted_data = self._post_data(
            action='test_s3_connection',
            **{
                'backup_settings-endpoint_url': '',
                'backup_settings-bucket_name': '',
                'backup_settings-region': '',
                'backup_settings-access_key_id': '',
                'backup_settings-secret_access_key': '',
            },
        )

        self.client.force_login(superuser)
        response = self.client.post(self.url, data=submitted_data)

        configuration.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self._assert_settings_panel_form_sections(response)
        self._assert_backup_settings_tab_is_active(response)
        self.assertTrue(response.context['backup_form'].is_bound)
        self.assertFormError(response.context['backup_form'], 'endpoint_url', 'This field is required when backups are enabled.')
        self.assertFormError(response.context['backup_form'], 'bucket_name', 'This field is required when backups are enabled.')
        self.assertEqual(configuration.endpoint_url, 'https://saved-storage.example.com')
        self.assertEqual(configuration.bucket_name, 'saved-bucket')
        self.assertEqual(configuration.region, 'saved-region')
        self.assertEqual(configuration.access_key_id, saved_credentials['access_key_id'])
        self.assertEqual(configuration.secret_access_key, saved_credentials['secret_access_key'])
        self.assertFalse(configuration.is_enabled)
        test_backup_destination_mock.assert_not_called()

    @patch('invoices.views.test_backup_destination')
    def test_invalid_save_keeps_backup_settings_tab_active(self, test_backup_destination_mock):
        superuser = self.user_model.objects.create_superuser(
            username='backup-invalid-save-admin',
            email='backup-invalid-save-admin@example.com',
            password=example_user_password(),
        )

        self.client.force_login(superuser)
        response = self.client.post(
            self.url,
            data=self._post_data(
                action='save',
                **{
                    'backup_settings-endpoint_url': '',
                    'backup_settings-bucket_name': '',
                    'backup_settings-region': '',
                    'backup_settings-access_key_id': '',
                    'backup_settings-secret_access_key': '',
                },
            ),
        )

        self.assertEqual(response.status_code, 200)
        self._assert_settings_panel_form_sections(response)
        self._assert_backup_settings_tab_is_active(response)
        self.assertFormError(response.context['backup_form'], 'endpoint_url', 'This field is required when backups are enabled.')
        self.assertFormError(response.context['backup_form'], 'bucket_name', 'This field is required when backups are enabled.')
        test_backup_destination_mock.assert_not_called()

    def test_superuser_can_save_backup_settings_via_ajax(self):
        superuser = self.user_model.objects.create_superuser(
            username='backup-ajax-save-admin',
            email='backup-ajax-save-admin@example.com',
            password=example_user_password(),
        )

        self.client.force_login(superuser)
        response = self._ajax_post(self._post_data(action='save'))

        configuration = BackupConfiguration.load()
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['active_tab'], 'backup-settings-panel')
        self.assertIn('Backup settings saved successfully.', payload['fragments']['settings_panel'])
        self.assertIn('data-backup-settings-form', payload['fragments']['settings_panel'])
        self.assertIn('Enabled', payload['fragments']['status_badge'])
        self.assertEqual(configuration.bucket_name, 'invoice-backups')
        self.assertEqual(configuration.object_prefix, 'daily')
        self.assertTrue(configuration.is_enabled)

    @patch('invoices.views.test_backup_destination')
    def test_ajax_test_uses_connection_validation_only(self, test_backup_destination_mock):
        superuser = self.user_model.objects.create_superuser(
            username='backup-ajax-test-connection-only-admin',
            email='backup-ajax-test-connection-only-admin@example.com',
            password=example_user_password(),
        )

        self.client.force_login(superuser)
        response = self._ajax_post(
            self._post_data(
                action='test_s3_connection',
                **{
                    'backup_settings-daily_run_time': 'not-a-time',
                    'backup_settings-daily_retention_count': 'not-a-number',
                },
            )
        )

        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        self.assertIn('S3 connection test succeeded.', payload['fragments']['settings_panel'])
        self.assertNotIn('Enter a valid time.', payload['fragments']['settings_panel'])
        self.assertNotIn('Enter a whole number.', payload['fragments']['settings_panel'])
        test_backup_destination_mock.assert_called_once()

    @patch('invoices.views.test_backup_destination')
    def test_ajax_test_validation_errors_do_not_persist_changes(self, test_backup_destination_mock):
        superuser = self.user_model.objects.create_superuser(
            username='backup-ajax-test-invalid-admin',
            email='backup-ajax-test-invalid-admin@example.com',
            password=example_user_password(),
        )
        configuration = BackupConfiguration.load()
        configuration.bucket_name = 'saved-bucket'
        configuration.object_prefix = 'saved-prefix'
        configuration.save()

        self.client.force_login(superuser)
        response = self._ajax_post(
            self._post_data(
                action='test_s3_connection',
                **{
                    'backup_settings-endpoint_url': '',
                    'backup_settings-bucket_name': '',
                    'backup_settings-region': '',
                    'backup_settings-access_key_id': '',
                    'backup_settings-secret_access_key': '',
                    'backup_settings-object_prefix': 'unsaved-prefix',
                },
            )
        )

        configuration.refresh_from_db()
        payload = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload['success'])
        self.assertIn('This field is required when backups are enabled.', payload['fragments']['settings_panel'])
        self.assertIn('data-backup-settings-test-feedback', payload['fragments']['settings_panel'])
        self.assertEqual(configuration.bucket_name, 'saved-bucket')
        self.assertEqual(configuration.object_prefix, 'saved-prefix')
        test_backup_destination_mock.assert_not_called()

    @patch('invoices.views.test_backup_destination')
    def test_ajax_test_does_not_persist_configuration_changes(self, test_backup_destination_mock):
        superuser = self.user_model.objects.create_superuser(
            username='backup-ajax-test-no-persist-admin',
            email='backup-ajax-test-no-persist-admin@example.com',
            password=example_user_password(),
        )
        configuration = BackupConfiguration.load()
        configuration.bucket_name = 'saved-bucket'
        configuration.object_prefix = 'saved-prefix'
        configuration.is_enabled = False
        configuration.save()

        self.client.force_login(superuser)
        response = self._ajax_post(
            self._post_data(
                action='test_s3_connection',
                **{
                    'backup_settings-bucket_name': 'submitted-bucket',
                    'backup_settings-object_prefix': 'submitted-prefix',
                },
            )
        )

        configuration.refresh_from_db()
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload['success'])
        self.assertIn('S3 connection test succeeded.', payload['fragments']['settings_panel'])
        self.assertIn('Disabled', payload['fragments']['status_badge'])
        self.assertEqual(configuration.bucket_name, 'saved-bucket')
        self.assertEqual(configuration.object_prefix, 'saved-prefix')
        test_backup_destination_mock.assert_called_once()
        tested_configuration = test_backup_destination_mock.call_args.args[0]
        self.assertEqual(tested_configuration.bucket_name, 'submitted-bucket')
        self.assertEqual(tested_configuration.object_prefix, 'submitted-prefix')

    @patch('invoices.views.test_backup_destination')
    def test_non_superuser_cannot_use_backup_settings_ajax(self, test_backup_destination_mock):
        user = self.user_model.objects.create_user(
            username='backup-ajax-user',
            email='backup-ajax-user@example.com',
            password=example_user_password(),
        )

        self.client.force_login(user)
        response = self._ajax_post(self._post_data(action='test_s3_connection'))

        self.assertEqual(response.status_code, 403)
        test_backup_destination_mock.assert_not_called()


class RunBackupNowViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_model = get_user_model()
        self.url = reverse('backup_run_now')

    def _login_superuser(self):
        superuser = self.user_model.objects.create_superuser(
            username=f'run-backup-admin-{uuid4().hex}',
            email=f'run-backup-admin-{uuid4().hex}@example.com',
            password=example_user_password(),
        )
        self.client.force_login(superuser)
        return superuser

    def test_superuser_post_uses_saved_backup_configuration(self):
        configuration = BackupConfiguration.load()
        self._login_superuser()

        with patch('invoices.views.execute_backup') as execute_backup_mock:
            response = self.client.post(self.url)

        execute_backup_mock.assert_called_once_with(
            configuration,
            trigger_source=BackupRun.TRIGGER_SOURCE_MANUAL,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('backup_settings'))

    def test_superuser_post_ignores_unsaved_backup_settings_form_edits(self):
        saved_configuration = BackupConfiguration.load()
        saved_configuration.endpoint_url = example_storage_endpoint_url()
        saved_configuration.bucket_name = 'saved-invoice-backups'
        saved_configuration.region = 'us-east-1'
        saved_configuration.object_prefix = 'saved-prefix'
        saved_configuration.access_key_id = example_storage_setting()
        saved_configuration.secret_access_key = example_storage_setting()
        saved_configuration.save()
        self._login_superuser()

        with patch('invoices.views.execute_backup') as execute_backup_mock:
            response = self.client.post(
                self.url,
                data={
                    'backup_settings-endpoint_url': example_storage_endpoint_url(),
                    'backup_settings-bucket_name': 'unsaved-invoice-backups',
                    'backup_settings-region': 'eu-west-1',
                    'backup_settings-object_prefix': 'unsaved-prefix',
                    'backup_settings-access_key_id': example_storage_setting(),
                    'backup_settings-secret_access_key': example_storage_setting(),
                    'backup_settings-daily_run_time': '09:15',
                },
            )

        execute_backup_mock.assert_called_once()
        configuration = execute_backup_mock.call_args.args[0]
        self.assertEqual(configuration.pk, saved_configuration.pk)
        self.assertEqual(configuration.endpoint_url, saved_configuration.endpoint_url)
        self.assertEqual(configuration.bucket_name, 'saved-invoice-backups')
        self.assertEqual(configuration.region, 'us-east-1')
        self.assertEqual(configuration.object_prefix, 'saved-prefix')
        self.assertEqual(configuration.access_key_id, saved_configuration.access_key_id)
        self.assertEqual(configuration.secret_access_key, saved_configuration.secret_access_key)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('backup_settings'))

        saved_configuration.refresh_from_db()
        self.assertEqual(saved_configuration.bucket_name, 'saved-invoice-backups')
        self.assertEqual(saved_configuration.region, 'us-east-1')
        self.assertEqual(saved_configuration.object_prefix, 'saved-prefix')

    def test_successful_manual_backup_redirects_with_success_message(self):
        self._login_superuser()

        backup_run = BackupRun.objects.create(
            status=BackupRun.STATUS_SUCCEEDED,
            finished_at=timezone.now(),
            storage_object_key='backups/manual-success.zip',
            artifact_size_bytes=1024,
        )

        with patch('invoices.views.execute_backup') as execute_backup_mock:
            execute_backup_mock.return_value = backup_run
            response = self.client.post(self.url, follow=True)

        execute_backup_mock.assert_called_once_with(
            BackupConfiguration.load(),
            trigger_source=BackupRun.TRIGGER_SOURCE_MANUAL,
        )
        self.assertRedirects(response, reverse('backup_settings'))
        self.assertContains(response, 'Backup run completed successfully.')
        self.assertContains(response, f'href="{reverse("backup_run_download", args=[backup_run.id])}"')
        self.assertNotContains(response, 'backups/manual-success.zip')
        self.assertContains(response, 'Succeeded')
        self.assertIn(backup_run, response.context['recent_backup_runs'])

    def test_failed_manual_backup_redirects_with_error_message(self):
        self._login_superuser()
        failure_summary = 'RuntimeError: upload failed'
        failed_run = BackupRun.objects.create(
            status=BackupRun.STATUS_FAILED,
            finished_at=timezone.now(),
            storage_object_key='backups/manual-failure.zip',
            error_summary=failure_summary,
        )

        with patch('invoices.views.execute_backup', side_effect=RuntimeError('upload failed')):
            response = self.client.post(self.url, follow=True)

        self.assertRedirects(response, reverse('backup_settings'))
        self.assertContains(response, 'Backup run failed. Check recent runs for details.')
        self.assertContains(response, 'Failed')
        self.assertNotContains(response, 'backups/manual-failure.zip')
        self.assertNotContains(response, failure_summary)
        self.assertContains(response, f'href="{reverse("backup_run_detail", args=[failed_run.id])}"')
        self.assertIn(failed_run, response.context['recent_backup_runs'])

    def test_already_running_manual_backup_redirects_with_warning_message(self):
        self._login_superuser()

        with patch('invoices.views.execute_backup', side_effect=BlockingIOError):
            response = self.client.post(self.url, follow=True)

        self.assertRedirects(response, reverse('backup_settings'))
        self.assertContains(response, 'A backup run is already in progress.')

    def test_already_running_manual_backup_warning_renders_in_shared_layout_after_redirect(self):
        self._login_superuser()

        with patch('invoices.views.execute_backup', side_effect=BlockingIOError):
            response = self.client.post(self.url, follow=True)

        self.assertRedirects(response, reverse('backup_settings'))
        self.assertTemplateUsed(response, 'invoices/backup_settings.html')
        self.assertTemplateUsed(response, 'invoices/partials/messages.html')
        self.assertContains(response, 'data-testid="django-messages"', count=1)
        self.assertContains(response, 'A backup run is already in progress.', count=1)

    def test_manual_backup_run_is_blocked_when_shared_execution_lock_is_held(self):
        self._login_superuser()

        with tempfile.TemporaryDirectory() as temp_dir:
            lock_file_path = Path(temp_dir) / 'backup-execution.lock'

            with override_settings(BACKUP_EXECUTION_LOCK_PATH=lock_file_path):
                with backup_execution_lock() as lock_acquired:
                    self.assertTrue(lock_acquired)

                    response = self.client.post(self.url, follow=True)

        self.assertRedirects(response, reverse('backup_settings'))
        self.assertContains(response, 'A backup run is already in progress.')
        self.assertEqual(BackupRun.objects.count(), 0)

    def test_non_superuser_cannot_post_manual_backup_run(self):
        user = self.user_model.objects.create_user(
            username='run-backup-user',
            email='run-backup-user@example.com',
            password=example_user_password(),
        )
        self.client.force_login(user)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(BackupRun.objects.count(), 0)


class BackupRunDownloadViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_model = get_user_model()
        self.url_name = 'backup_run_download'

    def _login_superuser(self):
        superuser = self.user_model.objects.create_superuser(
            username=f'backup-download-admin-{uuid4().hex}',
            email=f'backup-download-admin-{uuid4().hex}@example.com',
            password=example_user_password(),
        )
        self.client.force_login(superuser)
        return superuser

    @patch('invoices.views.generate_backup_download_url')
    def test_superuser_is_redirected_to_fresh_download_target(self, generate_backup_download_url_mock):
        self._login_superuser()
        backup_run = BackupRun.objects.create(
            status=BackupRun.STATUS_SUCCEEDED,
            storage_object_key='daily/2026/04/18/backup-20260418T020000Z.zip',
        )
        generate_backup_download_url_mock.return_value = 'https://downloads.example.com/backups/run-1.zip?signature=fresh'

        response = self.client.get(reverse(self.url_name, args=[backup_run.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response['Location'],
            'https://downloads.example.com/backups/run-1.zip?signature=fresh',
        )
        generate_backup_download_url_mock.assert_called_once_with(backup_run)

    @patch('invoices.views.generate_backup_download_url')
    def test_non_superuser_cannot_download_backup_run(self, generate_backup_download_url_mock):
        user = self.user_model.objects.create_user(
            username='backup-download-user',
            email='backup-download-user@example.com',
            password=example_user_password(),
        )
        backup_run = BackupRun.objects.create(
            status=BackupRun.STATUS_SUCCEEDED,
            storage_object_key='daily/2026/04/18/backup-20260418T020000Z.zip',
        )
        self.client.force_login(user)

        response = self.client.get(reverse(self.url_name, args=[backup_run.id]))

        self.assertEqual(response.status_code, 403)
        generate_backup_download_url_mock.assert_not_called()

    @patch('invoices.views.generate_backup_download_url')
    def test_download_view_rejects_runs_without_storage_object_key(self, generate_backup_download_url_mock):
        self._login_superuser()
        backup_run = BackupRun.objects.create(status=BackupRun.STATUS_SUCCEEDED, storage_object_key='')

        response = self.client.get(reverse(self.url_name, args=[backup_run.id]))

        self.assertEqual(response.status_code, 403)
        generate_backup_download_url_mock.assert_not_called()


class BackupS3ClientTests(TestCase):
    @override_settings(
        BACKUP_S3_SIGNATURE_VERSION='s3v4',
        BACKUP_S3_ADDRESSING_STYLE='path',
        BACKUP_S3_RETRY_MODE='adaptive',
        BACKUP_S3_MAX_RETRIES=5,
    )
    @patch('invoices.services.backups.boto3.session.Session')
    def test_build_backup_s3_client_uses_configuration_and_settings(self, session_class):
        destination_credentials = example_destination_credentials()
        endpoint_url = example_storage_endpoint_url()
        configuration = BackupConfiguration(
            endpoint_url=endpoint_url,
            bucket_name='invoice-backups',
            region='nyc3',
            **destination_credentials,
        )
        client = object()
        session_class.return_value.client.return_value = client

        result = build_backup_s3_client(configuration)

        self.assertIs(result, client)
        session_class.return_value.client.assert_called_once()
        _, kwargs = session_class.return_value.client.call_args
        self.assertEqual(kwargs['endpoint_url'], endpoint_url)
        self.assertEqual(kwargs['region_name'], 'nyc3')
        self.assertEqual(kwargs['aws_access_key_id'], destination_credentials['access_key_id'])
        self.assertEqual(kwargs['aws_secret_access_key'], destination_credentials['secret_access_key'])
        self.assertEqual(kwargs['config'].signature_version, 's3v4')
        self.assertEqual(kwargs['config'].retries, {'mode': 'adaptive', 'max_attempts': 5})
        self.assertEqual(kwargs['config'].s3, {'addressing_style': 'path'})

    @patch('invoices.services.backups.boto3.session.Session')
    def test_build_backup_s3_client_loads_singleton_configuration_by_default(self, session_class):
        destination_credentials = example_destination_credentials()
        endpoint_url = example_storage_endpoint_url()
        configuration = BackupConfiguration.load()
        configuration.endpoint_url = endpoint_url
        configuration.region = 'us-east-1'
        configuration.access_key_id = destination_credentials['access_key_id']
        configuration.secret_access_key = destination_credentials['secret_access_key']
        configuration.save()

        build_backup_s3_client()

        _, kwargs = session_class.return_value.client.call_args
        self.assertEqual(kwargs['endpoint_url'], endpoint_url)
        self.assertEqual(kwargs['region_name'], 'us-east-1')
        self.assertEqual(kwargs['aws_access_key_id'], destination_credentials['access_key_id'])
        self.assertEqual(kwargs['aws_secret_access_key'], destination_credentials['secret_access_key'])

    @patch('invoices.services.backups.build_backup_s3_client')
    def test_generate_backup_download_url_uses_presigned_get_object_request(self, build_backup_s3_client_mock):
        configuration = BackupConfiguration.load()
        configuration.bucket_name = 'invoice-backups'
        configuration.save()
        backup_run = BackupRun(
            id=123,
            storage_object_key='daily/2026/04/18/backup-20260418T020000Z.zip',
        )
        client = Mock()
        client.generate_presigned_url.return_value = 'https://downloads.example.com/backups/run-123.zip?signature=fresh'
        build_backup_s3_client_mock.return_value = client

        result = generate_backup_download_url(backup_run, configuration)

        self.assertEqual(
            result,
            'https://downloads.example.com/backups/run-123.zip?signature=fresh',
        )
        build_backup_s3_client_mock.assert_called_once_with(configuration)
        client.generate_presigned_url.assert_called_once_with(
            'get_object',
            Params={
                'Bucket': 'invoice-backups',
                'Key': 'daily/2026/04/18/backup-20260418T020000Z.zip',
            },
            ExpiresIn=300,
        )


class BackupDestinationTests(TestCase):
    def setUp(self):
        self.configuration = BackupConfiguration(bucket_name='invoice-backups')

    @patch('invoices.services.backups.build_backup_s3_client')
    def test_test_backup_destination_builds_client_and_checks_bucket_access(self, build_backup_s3_client_mock):
        client = SimpleNamespace(head_bucket=Mock(return_value={}))
        build_backup_s3_client_mock.return_value = client

        test_backup_destination(self.configuration)

        build_backup_s3_client_mock.assert_called_once_with(self.configuration)
        client.head_bucket.assert_called_once_with(Bucket='invoice-backups')

    def test_test_backup_destination_checks_bucket_access_without_uploading_data(self):
        client = SimpleNamespace(head_bucket=Mock(return_value={}))

        test_backup_destination(self.configuration, s3_client=client)

        client.head_bucket.assert_called_once_with(Bucket='invoice-backups')

    def test_test_backup_destination_raises_concise_bucket_not_found_error(self):
        client = SimpleNamespace(
            head_bucket=Mock(
                side_effect=ClientError(
                    error_response={
                        'Error': {
                            'Code': 'NoSuchBucket',
                            'Message': 'The specified bucket does not exist.',
                        }
                    },
                    operation_name='HeadBucket',
                )
            )
        )

        with self.assertRaisesMessage(
            BackupDestinationCheckError,
            'Bucket not found. Check the bucket name and try again.',
        ):
            test_backup_destination(self.configuration, s3_client=client)

    def test_test_backup_destination_raises_concise_bucket_access_error(self):
        client = SimpleNamespace(
            head_bucket=Mock(
                side_effect=ClientError(
                    error_response={
                        'Error': {
                            'Code': 'AccessDenied',
                            'Message': 'Access Denied',
                        }
                    },
                    operation_name='HeadBucket',
                )
            )
        )

        with self.assertRaisesMessage(
            BackupDestinationCheckError,
            'Could not access the bucket with these credentials. Check the access key, secret key, and bucket permissions.',
        ):
            test_backup_destination(self.configuration, s3_client=client)

    def test_test_backup_destination_raises_concise_region_error(self):
        client = SimpleNamespace(
            head_bucket=Mock(
                side_effect=ClientError(
                    error_response={
                        'Error': {
                            'Code': 'PermanentRedirect',
                            'Message': 'The bucket is in a different region.',
                        }
                    },
                    operation_name='HeadBucket',
                )
            )
        )

        with self.assertRaisesMessage(
            BackupDestinationCheckError,
            'Could not verify the bucket in this region. Check the region and try again.',
        ):
            test_backup_destination(self.configuration, s3_client=client)

    def test_test_backup_destination_raises_concise_invalid_bucket_name_error(self):
        client = SimpleNamespace(
            head_bucket=Mock(
                side_effect=ClientError(
                    error_response={
                        'Error': {
                            'Code': 'InvalidBucketName',
                            'Message': 'The specified bucket is not valid.',
                        }
                    },
                    operation_name='HeadBucket',
                )
            )
        )

        with self.assertRaisesMessage(
            BackupDestinationCheckError,
            'Bucket name is invalid. Check the bucket name and try again.',
        ):
            test_backup_destination(self.configuration, s3_client=client)


class BackupStorageObjectKeyTests(TestCase):
    def test_build_backup_storage_object_key_is_deterministic_from_prefix_and_timestamp(self):
        configuration = BackupConfiguration(object_prefix='daily')
        started_at = timezone.make_aware(datetime(2026, 3, 30, 2, 15))

        object_key = build_backup_storage_object_key(configuration, started_at=started_at)

        self.assertEqual(object_key, 'daily/2026/03/30/backup-20260330T021500Z.zip')

    def test_build_backup_storage_object_key_omits_blank_prefix(self):
        configuration = BackupConfiguration(object_prefix='')
        started_at = timezone.make_aware(datetime(2026, 3, 30, 2, 15))

        object_key = build_backup_storage_object_key(configuration, started_at=started_at)

        self.assertEqual(object_key, '2026/03/30/backup-20260330T021500Z.zip')


class BackupArtifactTests(TestCase):
    def test_create_backup_artifact_includes_database_and_media_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / 'db.sqlite3'
            database_path.write_bytes(b'sqlite database bytes')
            media_root = Path(temp_dir) / 'media'
            nested_media_dir = media_root / 'uploads'
            nested_media_dir.mkdir(parents=True)
            media_file = nested_media_dir / 'invoice.txt'
            media_file.write_text('invoice attachment', encoding='utf-8')

            with override_settings(MEDIA_ROOT=media_root):
                artifact = create_backup_artifact(database_path=database_path, output_dir=temp_dir)

            self.addCleanup(artifact.file_path.unlink, missing_ok=True)

            self.assertTrue(artifact.file_path.exists())
            self.assertGreater(artifact.size_bytes, 0)

            with zipfile.ZipFile(artifact.file_path) as archive:
                names = archive.namelist()
                self.assertIn(f'database/{database_path.name}', names)
                self.assertIn('media/', names)
                self.assertIn('media/uploads/invoice.txt', names)
                self.assertEqual(archive.read(f'database/{database_path.name}'), b'sqlite database bytes')
                self.assertEqual(archive.read('media/uploads/invoice.txt').decode('utf-8'), 'invoice attachment')

    def test_create_backup_artifact_allows_missing_media_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / 'db.sqlite3'
            database_path.write_bytes(b'sqlite database bytes')
            missing_media_root = Path(temp_dir) / 'missing-media'

            with override_settings(MEDIA_ROOT=missing_media_root):
                artifact = create_backup_artifact(database_path=database_path, output_dir=temp_dir)

            self.addCleanup(artifact.file_path.unlink, missing_ok=True)

            with zipfile.ZipFile(artifact.file_path) as archive:
                self.assertIn('media/', archive.namelist())


class BackupExecutionTests(TestCase):
    def setUp(self):
        self.configuration = BackupConfiguration.load()
        self.configuration.bucket_name = 'invoice-backups'
        self.configuration.object_prefix = 'daily'
        self.configuration.save()

    def test_execute_backup_uses_execution_lock_even_while_scheduler_lock_is_held(self):
        command = RunBackupSchedulerCommand()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            database_path = temp_path / 'db.sqlite3'
            database_path.write_bytes(b'sqlite database bytes')
            media_root = temp_path / 'media'
            media_root.mkdir()
            scheduler_lock_path = temp_path / 'backup-scheduler.lock'
            execution_lock_path = temp_path / 'backup-execution.lock'
            command._get_scheduler_lock_file_path = lambda: scheduler_lock_path
            client = SimpleNamespace(upload_file=Mock())

            with override_settings(BACKUP_EXECUTION_LOCK_PATH=execution_lock_path):
                with command._scheduler_lock() as lock_acquired:
                    self.assertTrue(lock_acquired)

                    backup_run = execute_backup(
                        self.configuration,
                        s3_client=client,
                        database_path=database_path,
                        media_root=media_root,
                        output_dir=temp_dir,
                    )

                self.assertTrue(scheduler_lock_path.exists())
                self.assertTrue(execution_lock_path.exists())

        backup_run.refresh_from_db()

        self.assertEqual(backup_run.status, BackupRun.STATUS_SUCCEEDED)
        client.upload_file.assert_called_once()

    def test_execute_backup_logs_successful_run_around_upload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / 'db.sqlite3'
            database_path.write_bytes(b'sqlite database bytes')
            media_root = Path(temp_dir) / 'media'
            media_root.mkdir()

            upload_calls = []

            def upload_file(filename, bucket_name, object_key):
                upload_calls.append((filename, bucket_name, object_key, BackupRun.objects.get().status))
                self.assertTrue(Path(filename).exists())

            client = SimpleNamespace(upload_file=upload_file)

            backup_run = execute_backup(
                self.configuration,
                s3_client=client,
                database_path=database_path,
                media_root=media_root,
                output_dir=temp_dir,
            )

            uploaded_filename = upload_calls[0][0]

        backup_run.refresh_from_db()

        self.assertEqual(backup_run.status, BackupRun.STATUS_SUCCEEDED)
        self.assertIsNotNone(backup_run.finished_at)
        self.assertGreater(backup_run.artifact_size_bytes, 0)
        self.assertEqual(backup_run.error_summary, '')
        self.assertEqual(len(upload_calls), 1)
        self.assertEqual(
            backup_run.diagnostics['failure'],
            {
                'stage': '',
                'exception_class': '',
                'message': '',
                'context': {},
            },
        )

        _, bucket_name, object_key, status_during_upload = upload_calls[0]
        self.assertEqual(bucket_name, 'invoice-backups')
        self.assertEqual(status_during_upload, BackupRun.STATUS_IN_PROGRESS)
        self.assertEqual(backup_run.storage_object_key, object_key)
        self.assertTrue(object_key.startswith('daily/'))
        self.assertEqual(backup_run.retention_bucket, BackupRun.RETENTION_BUCKET_DAILY)
        self.assertEqual(
            [event['stage'] for event in backup_run.diagnostics['events']],
            ['artifact_created', 'upload_started', 'upload_finished', 'retention_applied'],
        )
        self.assertEqual(
            backup_run.diagnostics['events'][0]['context']['size_bytes'],
            backup_run.artifact_size_bytes,
        )
        self.assertEqual(
            backup_run.diagnostics['events'][1]['context'],
            {
                'bucket_name': 'invoice-backups',
                'object_key': backup_run.storage_object_key,
                'size_bytes': backup_run.artifact_size_bytes,
            },
        )
        self.assertEqual(
            backup_run.diagnostics['events'][2]['context'],
            {
                'bucket_name': 'invoice-backups',
                'object_key': backup_run.storage_object_key,
                'size_bytes': backup_run.artifact_size_bytes,
            },
        )
        self.assertEqual(
            backup_run.diagnostics['events'][3]['context'],
            {
                'retention_bucket': BackupRun.RETENTION_BUCKET_DAILY,
                'kept_run_ids': [backup_run.pk],
                'pruned_object_keys': [],
            },
        )
        self.assertFalse(Path(uploaded_filename).exists())
        self.assertEqual(backup_run.trigger_source, BackupRun.TRIGGER_SOURCE_MANUAL)

    def test_execute_backup_persists_explicit_trigger_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / 'db.sqlite3'
            database_path.write_bytes(b'sqlite database bytes')
            media_root = Path(temp_dir) / 'media'
            media_root.mkdir()
            client = SimpleNamespace(upload_file=Mock())

            backup_run = execute_backup(
                self.configuration,
                trigger_source=BackupRun.TRIGGER_SOURCE_SCHEDULED,
                s3_client=client,
                database_path=database_path,
                media_root=media_root,
                output_dir=temp_dir,
            )

        backup_run.refresh_from_db()

        self.assertEqual(backup_run.trigger_source, BackupRun.TRIGGER_SOURCE_SCHEDULED)

    def test_execute_backup_rejects_invalid_trigger_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / 'db.sqlite3'
            database_path.write_bytes(b'sqlite database bytes')
            media_root = Path(temp_dir) / 'media'
            media_root.mkdir()
            client = SimpleNamespace(upload_file=Mock())

            with self.assertRaisesMessage(ValueError, 'Invalid backup trigger source: invalid'):
                execute_backup(
                    self.configuration,
                    trigger_source='invalid',
                    s3_client=client,
                    database_path=database_path,
                    media_root=media_root,
                    output_dir=temp_dir,
                )

        self.assertEqual(BackupRun.objects.count(), 0)
        client.upload_file.assert_not_called()

    @patch('invoices.services.backups.apply_backup_retention')
    @patch('invoices.services.backups.build_backup_s3_client')
    def test_execute_backup_builds_default_s3_client_for_upload(self, build_backup_s3_client, apply_backup_retention):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / 'db.sqlite3'
            database_path.write_bytes(b'sqlite database bytes')
            media_root = Path(temp_dir) / 'media'
            media_root.mkdir()

            client = SimpleNamespace(upload_file=Mock())
            build_backup_s3_client.return_value = client
            apply_backup_retention.return_value = SimpleNamespace(kept_run_ids=(), pruned_object_keys=())

            backup_run = execute_backup(
                self.configuration,
                database_path=database_path,
                media_root=media_root,
                output_dir=temp_dir,
            )

        backup_run.refresh_from_db()

        build_backup_s3_client.assert_called_once_with(self.configuration)
        client.upload_file.assert_called_once()
        _, bucket_name, object_key = client.upload_file.call_args.args
        self.assertEqual(bucket_name, 'invoice-backups')
        self.assertEqual(object_key, backup_run.storage_object_key)
        apply_backup_retention.assert_called_once_with(self.configuration, s3_client=client)
        self.assertEqual(
            [event['stage'] for event in backup_run.diagnostics['events']],
            ['artifact_created', 'upload_started', 'upload_finished', 'retention_applied'],
        )

    @patch('invoices.services.backups.apply_backup_retention')
    def test_execute_backup_logs_failed_run_when_retention_fails(self, apply_backup_retention):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / 'db.sqlite3'
            database_path.write_bytes(b'sqlite database bytes')
            media_root = Path(temp_dir) / 'media'
            media_root.mkdir()

            client = SimpleNamespace(upload_file=Mock())
            apply_backup_retention.side_effect = RuntimeError('retention failed')

            with self.assertRaisesMessage(RuntimeError, 'retention failed'):
                execute_backup(
                    self.configuration,
                    s3_client=client,
                    database_path=database_path,
                    media_root=media_root,
                    output_dir=temp_dir,
                )

            backup_run = BackupRun.objects.get()
            uploaded_file = next(Path(temp_dir).glob('backup-*.zip'), None)

        backup_run.refresh_from_db()

        self.assertEqual(backup_run.status, BackupRun.STATUS_FAILED)
        self.assertIsNotNone(backup_run.finished_at)
        self.assertEqual(backup_run.error_summary, 'RuntimeError: retention failed')
        self.assertGreater(backup_run.artifact_size_bytes, 0)
        self.assertEqual(backup_run.retention_bucket, '')
        self.assertIsNone(uploaded_file)
        client.upload_file.assert_called_once()
        self.assertEqual(
            [event['stage'] for event in backup_run.diagnostics['events']],
            ['artifact_created', 'upload_started', 'upload_finished', 'retention'],
        )
        self.assertEqual(
            backup_run.diagnostics['failure'],
            {
                'stage': 'retention',
                'exception_class': 'RuntimeError',
                'message': 'retention failed',
                'context': {
                    'bucket_name': 'invoice-backups',
                    'object_key': backup_run.storage_object_key,
                    'size_bytes': backup_run.artifact_size_bytes,
                },
            },
        )

    def test_execute_backup_logs_failed_run_when_artifact_creation_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_database_path = Path(temp_dir) / 'missing.sqlite3'
            media_root = Path(temp_dir) / 'media'
            media_root.mkdir()
            client = SimpleNamespace(upload_file=Mock())

            with self.assertRaises(FileNotFoundError):
                execute_backup(
                    self.configuration,
                    s3_client=client,
                    database_path=missing_database_path,
                    media_root=media_root,
                    output_dir=temp_dir,
                )

            backup_run = BackupRun.objects.get()

        backup_run.refresh_from_db()

        self.assertEqual(backup_run.status, BackupRun.STATUS_FAILED)
        self.assertIsNotNone(backup_run.finished_at)
        self.assertEqual(
            backup_run.error_summary,
            f'FileNotFoundError: SQLite database file does not exist: {missing_database_path}',
        )
        self.assertIsNone(backup_run.artifact_size_bytes)
        client.upload_file.assert_not_called()
        self.assertEqual(
            [event['stage'] for event in backup_run.diagnostics['events']],
            ['artifact_creation'],
        )
        self.assertEqual(
            backup_run.diagnostics['failure'],
            {
                'stage': 'artifact_creation',
                'exception_class': 'FileNotFoundError',
                'message': f'SQLite database file does not exist: {missing_database_path}',
                'context': {
                    'object_key': backup_run.storage_object_key,
                },
            },
        )

    def test_execute_backup_logs_failed_run_when_upload_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / 'db.sqlite3'
            database_path.write_bytes(b'sqlite database bytes')
            media_root = Path(temp_dir) / 'media'
            media_root.mkdir()

            def upload_file(filename, bucket_name, object_key):
                self.assertEqual(BackupRun.objects.get().status, BackupRun.STATUS_IN_PROGRESS)
                self.assertTrue(Path(filename).exists())
                raise RuntimeError('upload failed')

            client = SimpleNamespace(upload_file=upload_file)

            with self.assertRaisesMessage(RuntimeError, 'upload failed'):
                execute_backup(
                    self.configuration,
                    s3_client=client,
                    database_path=database_path,
                    media_root=media_root,
                    output_dir=temp_dir,
                )

            backup_run = BackupRun.objects.get()
            uploaded_file = next(Path(temp_dir).glob('backup-*.zip'), None)

        self.assertEqual(backup_run.status, BackupRun.STATUS_FAILED)
        self.assertIsNotNone(backup_run.finished_at)
        self.assertEqual(backup_run.error_summary, 'RuntimeError: upload failed')
        self.assertIsNone(backup_run.artifact_size_bytes)
        self.assertIsNone(uploaded_file)
        self.assertEqual(
            [event['stage'] for event in backup_run.diagnostics['events']],
            ['artifact_created', 'upload_started', 'upload'],
        )
        self.assertEqual(
            backup_run.diagnostics['failure'],
            {
                'stage': 'upload',
                'exception_class': 'RuntimeError',
                'message': 'upload failed',
                'context': {
                    'bucket_name': 'invoice-backups',
                    'object_key': backup_run.storage_object_key,
                    'size_bytes': backup_run.diagnostics['events'][0]['context']['size_bytes'],
                },
            },
        )


class BackupRunEventHelpersTests(TestCase):
    def setUp(self):
        self.configuration = BackupConfiguration.load()
        self.configuration.bucket_name = 'invoice-backups'
        self.configuration.object_prefix = 'daily'
        self.configuration.save()

    def test_append_backup_run_event_persists_timestamped_event(self):
        backup_run = BackupRun.objects.create()
        occurred_at = datetime(2026, 3, 30, 2, 15, tzinfo=dt_timezone.utc)

        event = append_backup_run_event(
            backup_run,
            stage='artifact_created',
            message='Backup artifact created.',
            context={'size_bytes': 123},
            occurred_at=occurred_at,
        )

        backup_run.refresh_from_db()

        self.assertEqual(
            event,
            {
                'timestamp': '2026-03-30T02:15:00Z',
                'stage': 'artifact_created',
                'message': 'Backup artifact created.',
                'context': {'size_bytes': 123},
            },
        )
        self.assertEqual(backup_run.diagnostics['events'], [event])
        self.assertEqual(backup_run.diagnostics['failure'], {
            'stage': '',
            'exception_class': '',
            'message': '',
            'context': {},
        })

    def test_append_backup_run_event_preserves_existing_failure_metadata(self):
        backup_run = BackupRun.objects.create(
            diagnostics={
                'events': [{'timestamp': '2026-03-30T02:00:00Z', 'stage': 'started', 'message': '', 'context': {}}],
                'failure': {
                    'stage': 'upload',
                    'exception_class': 'RuntimeError',
                    'message': 'upload failed',
                    'context': {'object_key': 'daily/example.zip'},
                },
            }
        )

        append_backup_run_event(backup_run, stage='finished', message='Backup run finished.')

        backup_run.refresh_from_db()

        self.assertEqual(len(backup_run.diagnostics['events']), 2)
        self.assertEqual(backup_run.diagnostics['events'][0]['stage'], 'started')
        self.assertEqual(backup_run.diagnostics['events'][1]['stage'], 'finished')
        self.assertEqual(
            backup_run.diagnostics['failure'],
            {
                'stage': 'upload',
                'exception_class': 'RuntimeError',
                'message': 'upload failed',
                'context': {'object_key': 'daily/example.zip'},
            },
        )

    def test_record_backup_run_failure_persists_failure_metadata_and_event(self):
        backup_run = BackupRun.objects.create(
            diagnostics={
                'events': [{'timestamp': '2026-03-30T02:00:00Z', 'stage': 'started', 'message': '', 'context': {}}],
                'failure': {
                    'stage': '',
                    'exception_class': '',
                    'message': '',
                    'context': {},
                },
            }
        )
        occurred_at = datetime(2026, 3, 30, 2, 30, tzinfo=dt_timezone.utc)

        event = record_backup_run_failure(
            backup_run,
            stage='upload',
            error=RuntimeError('upload failed'),
            context={'object_key': 'daily/example.zip'},
            occurred_at=occurred_at,
        )

        backup_run.refresh_from_db()

        self.assertEqual(
            event,
            {
                'timestamp': '2026-03-30T02:30:00Z',
                'stage': 'upload',
                'message': 'Backup run failed.',
                'context': {
                    'stage': 'upload',
                    'exception_class': 'RuntimeError',
                    'message': 'upload failed',
                    'context': {'object_key': 'daily/example.zip'},
                },
            },
        )
        self.assertEqual(len(backup_run.diagnostics['events']), 2)
        self.assertEqual(backup_run.diagnostics['events'][1], event)
        self.assertEqual(backup_run.diagnostics['failure'], event['context'])

    def test_execute_backup_raises_blocking_io_error_when_execution_lock_is_held(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / 'db.sqlite3'
            database_path.write_bytes(b'sqlite database bytes')
            media_root = Path(temp_dir) / 'media'
            media_root.mkdir()
            client = SimpleNamespace(upload_file=Mock())
            lock_file_path = Path(temp_dir) / 'backup-execution.lock'

            with override_settings(BACKUP_EXECUTION_LOCK_PATH=lock_file_path):
                with backup_execution_lock() as lock_acquired:
                    self.assertTrue(lock_acquired)

                    with self.assertRaisesMessage(BlockingIOError, 'A backup run is already in progress.'):
                        execute_backup(
                            self.configuration,
                            s3_client=client,
                            database_path=database_path,
                            media_root=media_root,
                            output_dir=temp_dir,
                        )

        self.assertEqual(BackupRun.objects.count(), 0)
        client.upload_file.assert_not_called()


class BackupRetentionTests(TestCase):
    def setUp(self):
        self.configuration = BackupConfiguration.load()
        self.configuration.bucket_name = 'invoice-backups'
        self.configuration.daily_retention_count = 2
        self.configuration.weekly_retention_count = 2
        self.configuration.monthly_retention_count = 2
        self.configuration.save()

    def _create_backup_run(self, *, days_ago: int, key_suffix: str) -> BackupRun:
        started_at = timezone.now() - timedelta(days=days_ago)
        return BackupRun.objects.create(
            status=BackupRun.STATUS_SUCCEEDED,
            started_at=started_at,
            finished_at=started_at + timedelta(minutes=5),
            storage_object_key=f'daily/{key_suffix}.zip',
        )

    def test_classify_backup_runs_assigns_daily_weekly_and_monthly_windows(self):
        daily_newest = self._create_backup_run(days_ago=0, key_suffix='daily-newest')
        daily_second = self._create_backup_run(days_ago=1, key_suffix='daily-second')
        weekly_recent = self._create_backup_run(days_ago=7, key_suffix='weekly-recent')
        weekly_older = self._create_backup_run(days_ago=14, key_suffix='weekly-older')
        monthly_recent = self._create_backup_run(days_ago=35, key_suffix='monthly-recent')
        monthly_older = self._create_backup_run(days_ago=70, key_suffix='monthly-older')
        pruned = self._create_backup_run(days_ago=120, key_suffix='pruned')

        classifications = classify_backup_runs_for_retention(self.configuration)

        self.assertEqual(classifications[daily_newest.pk], BackupRun.RETENTION_BUCKET_DAILY)
        self.assertEqual(classifications[daily_second.pk], BackupRun.RETENTION_BUCKET_DAILY)
        self.assertEqual(classifications[weekly_recent.pk], BackupRun.RETENTION_BUCKET_WEEKLY)
        self.assertEqual(classifications[weekly_older.pk], BackupRun.RETENTION_BUCKET_WEEKLY)
        self.assertEqual(classifications[monthly_recent.pk], BackupRun.RETENTION_BUCKET_MONTHLY)
        self.assertEqual(classifications[monthly_older.pk], BackupRun.RETENTION_BUCKET_MONTHLY)
        self.assertEqual(classifications[pruned.pk], '')

    def test_apply_backup_retention_updates_classification_and_prunes_remote_objects(self):
        kept_daily = self._create_backup_run(days_ago=0, key_suffix='kept-daily')
        kept_weekly = self._create_backup_run(days_ago=7, key_suffix='kept-weekly')
        kept_monthly = self._create_backup_run(days_ago=35, key_suffix='kept-monthly')
        pruned = self._create_backup_run(days_ago=120, key_suffix='pruned')

        self.configuration.daily_retention_count = 1
        self.configuration.weekly_retention_count = 1
        self.configuration.monthly_retention_count = 1
        self.configuration.save()

        deleted_batches = []

        def delete_objects(*, Bucket, Delete):
            deleted_batches.append((Bucket, Delete))
            return {'Deleted': Delete['Objects']}

        client = SimpleNamespace(delete_objects=delete_objects)

        result = apply_backup_retention(self.configuration, s3_client=client)

        kept_daily.refresh_from_db()
        kept_weekly.refresh_from_db()
        kept_monthly.refresh_from_db()
        pruned.refresh_from_db()

        self.assertEqual(kept_daily.retention_bucket, BackupRun.RETENTION_BUCKET_DAILY)
        self.assertEqual(kept_weekly.retention_bucket, BackupRun.RETENTION_BUCKET_WEEKLY)
        self.assertEqual(kept_monthly.retention_bucket, BackupRun.RETENTION_BUCKET_MONTHLY)
        self.assertEqual(pruned.retention_bucket, '')
        self.assertEqual(result.kept_run_ids, (kept_daily.pk, kept_weekly.pk, kept_monthly.pk))
        self.assertEqual(result.pruned_object_keys, (pruned.storage_object_key,))
        self.assertEqual(
            deleted_batches,
            [
                (
                    'invoice-backups',
                    {'Objects': [{'Key': pruned.storage_object_key}]},
                )
            ],
        )

    def test_apply_backup_retention_raises_when_remote_pruning_reports_errors(self):
        kept_daily = self._create_backup_run(days_ago=0, key_suffix='kept-daily')
        pruned = self._create_backup_run(days_ago=120, key_suffix='pruned')

        self.configuration.daily_retention_count = 1
        self.configuration.weekly_retention_count = 0
        self.configuration.monthly_retention_count = 0
        self.configuration.save()

        client = SimpleNamespace(
            delete_objects=Mock(
                return_value={
                    'Errors': [
                        {
                            'Key': pruned.storage_object_key,
                            'Message': 'Access denied',
                        }
                    ]
                }
            )
        )

        with self.assertRaisesMessage(
            RuntimeError,
            f'Failed to prune backup object {pruned.storage_object_key}: Access denied',
        ):
            apply_backup_retention(self.configuration, s3_client=client)

        kept_daily.refresh_from_db()
        pruned.refresh_from_db()

        self.assertEqual(kept_daily.retention_bucket, '')
        self.assertEqual(pruned.retention_bucket, '')


class RunBackupCommandTests(TestCase):
    @patch('invoices.management.commands.run_backup.execute_backup')
    def test_run_backup_command_executes_backup_with_loaded_configuration(self, execute_backup_mock):
        configuration = BackupConfiguration.load()
        configuration.bucket_name = 'invoice-backups'
        configuration.save()
        backup_run = BackupRun.objects.create(
            status=BackupRun.STATUS_SUCCEEDED,
            storage_object_key='daily/2026/03/30/backup-20260330T020000Z.zip',
        )
        execute_backup_mock.return_value = backup_run
        stdout = StringIO()

        call_command('run_backup', stdout=stdout)

        execute_backup_mock.assert_called_once_with(
            configuration,
            trigger_source=BackupRun.TRIGGER_SOURCE_MANUAL,
        )
        self.assertIn(
            f'Backup completed successfully (run #{backup_run.pk}, key: {backup_run.storage_object_key}).',
            stdout.getvalue(),
        )

    @patch('invoices.management.commands.run_backup.execute_backup')
    def test_run_backup_command_raises_command_error_when_backup_fails(self, execute_backup_mock):
        execute_backup_mock.side_effect = RuntimeError('upload failed')

        with self.assertRaisesMessage(CommandError, 'Backup failed: upload failed'):
            call_command('run_backup')


class RunBackupSchedulerCommandTests(TestCase):
    def setUp(self):
        self.command = RunBackupSchedulerCommand()
        self.lock_dir = tempfile.TemporaryDirectory()
        self.command._get_scheduler_lock_file_path = lambda: Path(self.lock_dir.name) / 'backup-scheduler.lock'
        self.command.stdout = StringIO()
        self.configuration = BackupConfiguration.load()
        self.configuration.is_enabled = True
        self.configuration.daily_run_time = time(hour=2, minute=0)
        self.configuration.bucket_name = 'invoice-backups'
        self.configuration.object_prefix = 'daily'
        self.configuration.save()

    def tearDown(self):
        self.lock_dir.cleanup()
        super().tearDown()

    def _aware_datetime(self, year, month, day, hour, minute=0):
        return timezone.make_aware(datetime(year, month, day, hour, minute))

    def test_scheduler_tick_and_execution_locks_use_distinct_default_paths(self):
        self.assertEqual(get_backup_scheduler_lock_path(), settings.BASE_DIR / '.backup-scheduler.lock')
        self.assertEqual(get_backup_execution_lock_path(), settings.BASE_DIR / '.backup-execution.lock')
        self.assertNotEqual(get_backup_scheduler_lock_path(), get_backup_execution_lock_path())

    def test_get_due_run_at_returns_scheduled_boundary_once_daily_run_time_arrives(self):
        now = self._aware_datetime(2026, 3, 30, 2, 0)

        due_run_at = self.command._get_due_run_at(self.configuration, now=now)

        self.assertEqual(due_run_at, now)

    @override_settings(TIME_ZONE='Europe/Madrid')
    def test_backup_scheduling_timezone_defaults_to_time_zone_setting(self):
        self.assertEqual(get_backup_scheduling_timezone(), ZoneInfo('Europe/Madrid'))

    @override_settings(TIME_ZONE='UTC', BACKUP_SCHEDULING_TIMEZONE='Europe/Madrid')
    def test_get_due_run_at_uses_explicit_backup_scheduling_timezone(self):
        now = datetime(2026, 3, 30, 1, 5, tzinfo=dt_timezone.utc)

        due_run_at = self.command._get_due_run_at(self.configuration, now=now)

        self.assertEqual(due_run_at, datetime(2026, 3, 30, 2, 0, tzinfo=ZoneInfo('Europe/Madrid')))

    @override_settings(TIME_ZONE='UTC', BACKUP_SCHEDULING_TIMEZONE='Europe/Madrid')
    def test_get_due_run_at_uses_local_scheduling_day_when_utc_date_differs(self):
        self.configuration.daily_run_time = time(hour=0, minute=30)
        self.configuration.save()
        now = datetime(2026, 3, 29, 22, 45, tzinfo=dt_timezone.utc)

        due_run_at = self.command._get_due_run_at(self.configuration, now=now)

        self.assertEqual(due_run_at, datetime(2026, 3, 30, 0, 30, tzinfo=ZoneInfo('Europe/Madrid')))

    @override_settings(TIME_ZONE='UTC', BACKUP_SCHEDULING_TIMEZONE='Europe/Madrid')
    def test_next_backup_run_at_uses_explicit_backup_scheduling_timezone(self):
        now = datetime(2026, 3, 30, 1, 5, tzinfo=dt_timezone.utc)

        next_run_at = _next_backup_run_at(self.configuration, now=now)

        self.assertEqual(next_run_at, datetime(2026, 3, 31, 2, 0, tzinfo=ZoneInfo('Europe/Madrid')))

    @patch('invoices.management.commands.run_backup_scheduler.execute_backup')
    def test_run_scheduler_tick_skips_when_backups_are_disabled(self, execute_backup_mock):
        self.configuration.is_enabled = False
        self.configuration.save()

        result = self.command.run_scheduler_tick(now=self._aware_datetime(2026, 3, 30, 3, 0))

        self.assertIsNone(result)
        execute_backup_mock.assert_not_called()

    @patch('invoices.management.commands.run_backup_scheduler.execute_backup')
    def test_run_scheduler_tick_skips_when_backup_is_not_due_yet(self, execute_backup_mock):
        result = self.command.run_scheduler_tick(now=self._aware_datetime(2026, 3, 30, 1, 0))

        self.assertIsNone(result)
        execute_backup_mock.assert_not_called()

    @patch('invoices.management.commands.run_backup_scheduler.execute_backup')
    def test_run_scheduler_tick_executes_due_backup_once_daily_run_time_has_passed(self, execute_backup_mock):
        backup_run = BackupRun.objects.create(
            status=BackupRun.STATUS_SUCCEEDED,
            started_at=self._aware_datetime(2026, 3, 29, 2, 5),
            storage_object_key='daily/2026/03/30/backup-20260330T020000Z.zip',
        )
        execute_backup_mock.return_value = backup_run

        result = self.command.run_scheduler_tick(now=self._aware_datetime(2026, 3, 30, 3, 0))

        execute_backup_mock.assert_called_once_with(
            self.configuration,
            trigger_source=BackupRun.TRIGGER_SOURCE_SCHEDULED,
        )
        self.assertEqual(result, backup_run)

    @patch('invoices.management.commands.run_backup_scheduler.execute_backup')
    def test_run_scheduler_tick_skips_when_backup_already_started_in_current_daily_window(self, execute_backup_mock):
        backup_run = BackupRun.objects.create(
            status=BackupRun.STATUS_SUCCEEDED,
            started_at=self._aware_datetime(2026, 3, 30, 2, 15),
            storage_object_key='daily/2026/03/30/backup-20260330T021500Z.zip',
            trigger_source=BackupRun.TRIGGER_SOURCE_SCHEDULED,
        )

        result = self.command.run_scheduler_tick(now=self._aware_datetime(2026, 3, 30, 3, 0))

        self.assertEqual(result, backup_run)
        execute_backup_mock.assert_not_called()

    @patch('invoices.management.commands.run_backup_scheduler.execute_backup')
    def test_run_scheduler_tick_does_not_count_manual_backup_for_current_daily_window(self, execute_backup_mock):
        BackupRun.objects.create(
            status=BackupRun.STATUS_SUCCEEDED,
            started_at=self._aware_datetime(2026, 3, 30, 2, 15),
            storage_object_key='daily/2026/03/30/manual-backup-20260330T021500Z.zip',
            trigger_source=BackupRun.TRIGGER_SOURCE_MANUAL,
        )
        scheduled_backup_run = BackupRun.objects.create(
            status=BackupRun.STATUS_SUCCEEDED,
            started_at=self._aware_datetime(2026, 3, 29, 2, 15),
            storage_object_key='daily/2026/03/29/backup-20260329T021500Z.zip',
            trigger_source=BackupRun.TRIGGER_SOURCE_SCHEDULED,
        )
        execute_backup_mock.return_value = scheduled_backup_run

        result = self.command.run_scheduler_tick(now=self._aware_datetime(2026, 3, 30, 3, 0))

        self.assertEqual(result, scheduled_backup_run)
        execute_backup_mock.assert_called_once_with(
            self.configuration,
            trigger_source=BackupRun.TRIGGER_SOURCE_SCHEDULED,
        )

    @patch('invoices.management.commands.run_backup_scheduler.execute_backup')
    def test_run_scheduler_tick_prefers_scheduled_run_when_manual_and_scheduled_runs_share_window(self, execute_backup_mock):
        scheduled_backup_run = BackupRun.objects.create(
            status=BackupRun.STATUS_SUCCEEDED,
            started_at=self._aware_datetime(2026, 3, 30, 2, 5),
            storage_object_key='daily/2026/03/30/backup-20260330T020500Z.zip',
            trigger_source=BackupRun.TRIGGER_SOURCE_SCHEDULED,
        )
        BackupRun.objects.create(
            status=BackupRun.STATUS_SUCCEEDED,
            started_at=self._aware_datetime(2026, 3, 30, 2, 25),
            storage_object_key='daily/2026/03/30/manual-backup-20260330T022500Z.zip',
            trigger_source=BackupRun.TRIGGER_SOURCE_MANUAL,
        )

        result = self.command.run_scheduler_tick(now=self._aware_datetime(2026, 3, 30, 3, 0))

        self.assertEqual(result, scheduled_backup_run)
        execute_backup_mock.assert_not_called()

    @patch('invoices.management.commands.run_backup_scheduler.execute_backup')
    def test_run_scheduler_tick_skips_when_in_progress_backup_exists_in_current_daily_window(self, execute_backup_mock):
        backup_run = BackupRun.objects.create(
            status=BackupRun.STATUS_IN_PROGRESS,
            started_at=self._aware_datetime(2026, 3, 30, 2, 1),
            storage_object_key='daily/2026/03/30/backup-20260330T020100Z.zip',
            trigger_source=BackupRun.TRIGGER_SOURCE_SCHEDULED,
        )

        result = self.command.run_scheduler_tick(now=self._aware_datetime(2026, 3, 30, 3, 0))

        self.assertEqual(result, backup_run)
        execute_backup_mock.assert_not_called()

    @patch('invoices.management.commands.run_backup_scheduler.execute_backup')
    def test_run_scheduler_tick_skips_when_another_scheduler_tick_holds_the_lock(self, execute_backup_mock):
        with self.command._scheduler_lock() as lock_acquired:
            self.assertTrue(lock_acquired)

            result = self.command.run_scheduler_tick(now=self._aware_datetime(2026, 3, 30, 3, 0))

        self.assertIsNone(result)
        execute_backup_mock.assert_not_called()

    @patch('invoices.management.commands.run_backup_scheduler.execute_backup')
    def test_run_scheduler_tick_skips_when_backup_execution_is_already_in_progress(self, execute_backup_mock):
        execute_backup_mock.side_effect = BlockingIOError('A backup run is already in progress.')

        result = self.command.run_scheduler_tick(now=self._aware_datetime(2026, 3, 30, 3, 0))

        self.assertIsNone(result)
        execute_backup_mock.assert_called_once_with(
            self.configuration,
            trigger_source=BackupRun.TRIGGER_SOURCE_SCHEDULED,
        )

    @patch('invoices.services.backups.create_backup_artifact')
    @patch('invoices.services.backups.build_backup_s3_client')
    def test_run_scheduler_tick_executes_backup_without_self_blocking_on_scheduler_lock(self, build_backup_s3_client_mock, create_backup_artifact_mock):
        build_backup_s3_client_mock.return_value = SimpleNamespace(upload_file=Mock())
        execution_lock_path = Path(self.lock_dir.name) / 'backup-execution.lock'
        artifact_path = Path(self.lock_dir.name) / 'backup-artifact.zip'
        artifact_path.write_bytes(b'backup bytes')
        create_backup_artifact_mock.return_value = BackupArtifact(file_path=artifact_path, size_bytes=artifact_path.stat().st_size)

        with override_settings(BACKUP_EXECUTION_LOCK_PATH=execution_lock_path):
            backup_run = self.command.run_scheduler_tick(now=self._aware_datetime(2026, 3, 30, 3, 0))

        backup_run.refresh_from_db()

        self.assertEqual(backup_run.status, BackupRun.STATUS_SUCCEEDED)
        self.assertEqual(backup_run.trigger_source, BackupRun.TRIGGER_SOURCE_SCHEDULED)
        self.assertTrue(self.command._get_scheduler_lock_file_path().exists())
        self.assertTrue(execution_lock_path.exists())
        self.assertNotIn('Another backup run is already in progress', self.command.stdout.getvalue())
        build_backup_s3_client_mock.return_value.upload_file.assert_called_once()

    def test_run_scheduler_tick_skips_when_shared_execution_lock_is_held(self):
        lock_file_path = Path(self.lock_dir.name) / 'backup-execution.lock'

        with override_settings(BACKUP_EXECUTION_LOCK_PATH=lock_file_path):
            with backup_execution_lock() as lock_acquired:
                self.assertTrue(lock_acquired)

                result = self.command.run_scheduler_tick(now=self._aware_datetime(2026, 3, 30, 3, 0))

        self.assertIsNone(result)
        self.assertEqual(BackupRun.objects.count(), 0)
        self.assertIn('Another backup run is already in progress; skipping scheduler tick.', self.command.stdout.getvalue())
