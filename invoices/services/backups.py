from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
import fcntl
from pathlib import Path
import tempfile
import zipfile

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError
from django.conf import settings
from django.utils import timezone

from invoices.models import BackupConfiguration, BackupRun


@dataclass(frozen=True)
class BackupArtifact:
    file_path: Path
    size_bytes: int


@dataclass(frozen=True)
class BackupRetentionResult:
    kept_run_ids: tuple[int, ...]
    pruned_object_keys: tuple[str, ...]


class BackupDestinationCheckError(Exception):
    """Raised when the configured backup destination cannot be reached."""


def get_backup_execution_lock_path() -> Path:
    return Path(
        getattr(
            settings,
            'BACKUP_EXECUTION_LOCK_PATH',
            settings.BASE_DIR / '.backup-execution.lock',
        )
    )


@contextmanager
def backup_execution_lock():
    lock_file_path = get_backup_execution_lock_path()
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


def _get_sqlite_database_path() -> Path:
    database_settings = settings.DATABASES['default']

    if database_settings.get('ENGINE') != 'django.db.backends.sqlite3':
        raise ValueError('Only SQLite backups are supported.')

    database_name = database_settings.get('NAME')
    if not database_name or database_name == ':memory:' or str(database_name).startswith('file:'):
        raise ValueError('SQLite backups require a file-based database path.')

    return Path(database_name)


def create_backup_artifact(
    database_path: str | Path | None = None,
    media_root: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> BackupArtifact:
    database_path = Path(database_path) if database_path is not None else _get_sqlite_database_path()
    media_root = Path(media_root) if media_root is not None else Path(settings.MEDIA_ROOT)
    output_dir = Path(output_dir) if output_dir is not None else None

    if not database_path.exists():
        raise FileNotFoundError(f'SQLite database file does not exist: {database_path}')

    temp_file = tempfile.NamedTemporaryFile(
        suffix='.zip',
        prefix='backup-',
        dir=output_dir,
        delete=False,
    )
    temp_file.close()

    artifact_path = Path(temp_file.name)

    try:
        with zipfile.ZipFile(artifact_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(database_path, arcname=f'database/{database_path.name}')
            archive.writestr('media/', '')

            if media_root.exists() and media_root.is_dir():
                for file_path in sorted(path for path in media_root.rglob('*') if path.is_file()):
                    archive.write(file_path, arcname=Path('media') / file_path.relative_to(media_root))
    except Exception:
        artifact_path.unlink(missing_ok=True)
        raise

    return BackupArtifact(file_path=artifact_path, size_bytes=artifact_path.stat().st_size)


def build_backup_s3_client(configuration: BackupConfiguration | None = None):
    configuration = configuration or BackupConfiguration.load()

    retry_mode = getattr(settings, 'BACKUP_S3_RETRY_MODE', 'standard')
    max_retries = getattr(settings, 'BACKUP_S3_MAX_RETRIES', 3)
    signature_version = getattr(settings, 'BACKUP_S3_SIGNATURE_VERSION', 's3v4')
    addressing_style = getattr(settings, 'BACKUP_S3_ADDRESSING_STYLE', 'auto')

    return boto3.session.Session().client(
        's3',
        endpoint_url=configuration.endpoint_url or None,
        region_name=configuration.region or None,
        aws_access_key_id=configuration.access_key_id or None,
        aws_secret_access_key=configuration.secret_access_key or None,
        config=Config(
            signature_version=signature_version,
            retries={
                'mode': retry_mode,
                'max_attempts': max_retries,
            },
            s3={
                'addressing_style': addressing_style,
            },
        ),
    )


def build_backup_storage_object_key(
    configuration: BackupConfiguration,
    started_at: datetime | None = None,
) -> str:
    started_at = started_at or timezone.now()
    started_at = started_at.astimezone(dt_timezone.utc)

    filename = f'backup-{started_at.strftime("%Y%m%dT%H%M%SZ")}.zip'
    key_parts = [
        configuration.object_prefix.strip('/'),
        started_at.strftime('%Y'),
        started_at.strftime('%m'),
        started_at.strftime('%d'),
        filename,
    ]
    return '/'.join(part for part in key_parts if part)


def generate_backup_download_url(
    backup_run: BackupRun,
    configuration: BackupConfiguration | None = None,
    *,
    s3_client=None,
) -> str:
    configuration = configuration or BackupConfiguration.load()
    client = s3_client or build_backup_s3_client(configuration)

    return client.generate_presigned_url(
        'get_object',
        Params={
            'Bucket': configuration.bucket_name,
            'Key': backup_run.storage_object_key,
        },
        ExpiresIn=getattr(settings, 'BACKUP_DOWNLOAD_URL_TTL_SECONDS', 300),
    )


def _summarize_backup_destination_check_error(error: Exception) -> str:
    if isinstance(error, EndpointConnectionError):
        return 'Could not reach the S3 endpoint. Check the endpoint URL and try again.'

    if isinstance(error, ClientError):
        error_details = error.response.get('Error', {})
        error_code = str(error_details.get('Code', '')).strip()

        if error_code in {'NoSuchBucket', '404'}:
            return 'Bucket not found. Check the bucket name and try again.'

        if error_code in {'InvalidBucketName'}:
            return 'Bucket name is invalid. Check the bucket name and try again.'

        if error_code in {'PermanentRedirect', 'AuthorizationHeaderMalformed', '301'}:
            return 'Could not verify the bucket in this region. Check the region and try again.'

        if error_code in {'RequestTimeout', 'RequestTimeoutException'}:
            return 'The S3 request timed out. Check the endpoint and try again.'

        if error_code in {'AccessDenied', 'InvalidAccessKeyId', 'SignatureDoesNotMatch', '403'}:
            return 'Could not access the bucket with these credentials. Check the access key, secret key, and bucket permissions.'

        return 'Could not verify the S3 bucket. Check the endpoint, region, bucket, and credentials.'

    if isinstance(error, BotoCoreError):
        return 'Could not connect to the S3 bucket. Check the endpoint, region, bucket, and credentials.'

    return 'Could not verify the S3 bucket. Check the endpoint, region, bucket, and credentials.'


def test_backup_destination(configuration: BackupConfiguration, *, s3_client=None) -> None:
    client = s3_client or build_backup_s3_client(configuration)

    try:
        client.head_bucket(Bucket=configuration.bucket_name)
    except Exception as error:
        raise BackupDestinationCheckError(_summarize_backup_destination_check_error(error)) from error


def _summarize_backup_error(error: Exception) -> str:
    message = str(error).strip()
    summary = f'{type(error).__name__}: {message}' if message else type(error).__name__
    return summary[:500]


def _backup_run_event_timestamp(occurred_at: datetime | None = None) -> str:
    occurred_at = occurred_at or timezone.now()
    return occurred_at.astimezone(dt_timezone.utc).isoformat().replace('+00:00', 'Z')


def append_backup_run_event(
    backup_run: BackupRun,
    *,
    stage: str,
    message: str = '',
    context: dict | None = None,
    occurred_at: datetime | None = None,
) -> dict:
    diagnostics = backup_run.diagnostics if isinstance(backup_run.diagnostics, dict) else {}
    events = diagnostics.get('events') if isinstance(diagnostics.get('events'), list) else []
    failure = diagnostics.get('failure') if isinstance(diagnostics.get('failure'), dict) else {}

    event = {
        'timestamp': _backup_run_event_timestamp(occurred_at),
        'stage': stage,
        'message': message,
        'context': context or {},
    }

    backup_run.diagnostics = {
        'events': [*events, event],
        'failure': {
            'stage': failure.get('stage', ''),
            'exception_class': failure.get('exception_class', ''),
            'message': failure.get('message', ''),
            'context': failure.get('context', {}),
        },
    }
    backup_run.save(update_fields=['diagnostics', 'updated_at'])
    return event


def record_backup_run_failure(
    backup_run: BackupRun,
    *,
    stage: str,
    error: Exception,
    context: dict | None = None,
    occurred_at: datetime | None = None,
) -> dict:
    diagnostics = backup_run.diagnostics if isinstance(backup_run.diagnostics, dict) else {}
    events = diagnostics.get('events') if isinstance(diagnostics.get('events'), list) else []

    failure = {
        'stage': stage,
        'exception_class': type(error).__name__,
        'message': str(error),
        'context': context or {},
    }
    event = {
        'timestamp': _backup_run_event_timestamp(occurred_at),
        'stage': stage,
        'message': 'Backup run failed.',
        'context': failure,
    }

    backup_run.diagnostics = {
        'events': [*events, event],
        'failure': failure,
    }
    backup_run.save(update_fields=['diagnostics', 'updated_at'])
    return event


def _get_backup_run_retention_bucket(
    backup_run: BackupRun,
    *,
    daily_dates: set,
    weekly_periods: set,
    monthly_periods: set,
    configuration: BackupConfiguration,
) -> str:
    started_at = timezone.localtime(backup_run.started_at)
    backup_date = started_at.date()
    backup_week = backup_date.isocalendar()[:2]
    backup_month = (backup_date.year, backup_date.month)

    if (
        configuration.daily_retention_count > 0
        and len(daily_dates) < configuration.daily_retention_count
        and backup_date not in daily_dates
    ):
        daily_dates.add(backup_date)
        return BackupRun.RETENTION_BUCKET_DAILY

    if (
        configuration.weekly_retention_count > 0
        and len(weekly_periods) < configuration.weekly_retention_count
        and backup_week not in weekly_periods
    ):
        weekly_periods.add(backup_week)
        return BackupRun.RETENTION_BUCKET_WEEKLY

    if (
        configuration.monthly_retention_count > 0
        and len(monthly_periods) < configuration.monthly_retention_count
        and backup_month not in monthly_periods
    ):
        monthly_periods.add(backup_month)
        return BackupRun.RETENTION_BUCKET_MONTHLY

    return ''


def classify_backup_runs_for_retention(
    configuration: BackupConfiguration | None = None,
    *,
    backup_runs=None,
) -> dict[int, str]:
    configuration = configuration or BackupConfiguration.load()
    backup_runs = backup_runs or BackupRun.objects.filter(
        status=BackupRun.STATUS_SUCCEEDED,
    ).exclude(
        storage_object_key='',
    )

    daily_dates = set()
    weekly_periods = set()
    monthly_periods = set()
    classifications = {}

    ordered_backup_runs = backup_runs.order_by('-started_at', '-id') if hasattr(backup_runs, 'order_by') else sorted(
        backup_runs,
        key=lambda backup_run: (backup_run.started_at, backup_run.id),
        reverse=True,
    )

    for backup_run in ordered_backup_runs:
        if len(daily_dates) >= configuration.daily_retention_count and len(weekly_periods) >= configuration.weekly_retention_count and len(monthly_periods) >= configuration.monthly_retention_count:
            classifications[backup_run.pk] = ''
            continue

        classifications[backup_run.pk] = _get_backup_run_retention_bucket(
            backup_run,
            daily_dates=daily_dates,
            weekly_periods=weekly_periods,
            monthly_periods=monthly_periods,
            configuration=configuration,
        )

    return classifications


def _delete_pruned_backup_objects(s3_client, bucket_name: str, object_keys: list[str]) -> None:
    if not object_keys:
        return

    if hasattr(s3_client, 'delete_objects'):
        for index in range(0, len(object_keys), 1000):
            batch = object_keys[index:index + 1000]
            response = s3_client.delete_objects(
                Bucket=bucket_name,
                Delete={'Objects': [{'Key': object_key} for object_key in batch]},
            )
            errors = response.get('Errors', []) if response else []
            if errors:
                first_error = errors[0]
                key = first_error.get('Key', '')
                message = first_error.get('Message', 'Remote backup pruning failed.')
                raise RuntimeError(f'Failed to prune backup object {key}: {message}')
        return

    for object_key in object_keys:
        s3_client.delete_object(Bucket=bucket_name, Key=object_key)


def apply_backup_retention(
    configuration: BackupConfiguration | None = None,
    *,
    s3_client=None,
) -> BackupRetentionResult:
    configuration = configuration or BackupConfiguration.load()
    successful_backup_runs = list(
        BackupRun.objects.filter(
            status=BackupRun.STATUS_SUCCEEDED,
        ).exclude(
            storage_object_key='',
        ).order_by('-started_at', '-id')
    )
    classifications = classify_backup_runs_for_retention(configuration, backup_runs=successful_backup_runs)

    pruned_object_keys = [
        backup_run.storage_object_key
        for backup_run in successful_backup_runs
        if not classifications.get(backup_run.pk) and backup_run.storage_object_key
    ]

    if pruned_object_keys:
        client = s3_client or build_backup_s3_client(configuration)
        _delete_pruned_backup_objects(client, configuration.bucket_name, pruned_object_keys)

    updated_at = timezone.now()
    for backup_run in successful_backup_runs:
        backup_run.retention_bucket = classifications.get(backup_run.pk, '')
        backup_run.updated_at = updated_at

    if successful_backup_runs:
        BackupRun.objects.bulk_update(successful_backup_runs, ['retention_bucket', 'updated_at'])

    return BackupRetentionResult(
        kept_run_ids=tuple(run.pk for run in successful_backup_runs if classifications.get(run.pk)),
        pruned_object_keys=tuple(pruned_object_keys),
    )


def execute_backup(
    configuration: BackupConfiguration | None = None,
    *,
    trigger_source: str = BackupRun.TRIGGER_SOURCE_MANUAL,
    s3_client=None,
    database_path: str | Path | None = None,
    media_root: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> BackupRun:
    configuration = configuration or BackupConfiguration.load()
    valid_trigger_sources = {choice for choice, _ in BackupRun.TRIGGER_SOURCE_CHOICES}
    if trigger_source not in valid_trigger_sources:
        raise ValueError(f'Invalid backup trigger source: {trigger_source}')

    with backup_execution_lock() as lock_acquired:
        if not lock_acquired:
            raise BlockingIOError('A backup run is already in progress.')

        started_at = timezone.now()
        storage_object_key = build_backup_storage_object_key(configuration, started_at=started_at)
        backup_run = BackupRun.objects.create(
            status=BackupRun.STATUS_IN_PROGRESS,
            trigger_source=trigger_source,
            started_at=started_at,
            storage_object_key=storage_object_key,
        )

        artifact: BackupArtifact | None = None
        current_stage = 'artifact_creation'
        failure_context: dict[str, str | int] = {
            'object_key': storage_object_key,
        }

        try:
            artifact = create_backup_artifact(
                database_path=database_path,
                media_root=media_root,
                output_dir=output_dir,
            )
            append_backup_run_event(
                backup_run,
                stage='artifact_created',
                message='Backup artifact created.',
                context={
                    'artifact_path': str(artifact.file_path),
                    'size_bytes': artifact.size_bytes,
                },
            )
            current_stage = 'upload'
            failure_context = {
                'bucket_name': configuration.bucket_name,
                'object_key': storage_object_key,
                'size_bytes': artifact.size_bytes,
            }
            client = s3_client or build_backup_s3_client(configuration)
            append_backup_run_event(
                backup_run,
                stage='upload_started',
                message='Uploading backup artifact to object storage.',
                context={
                    'bucket_name': configuration.bucket_name,
                    'object_key': storage_object_key,
                    'size_bytes': artifact.size_bytes,
                },
            )
            client.upload_file(str(artifact.file_path), configuration.bucket_name, storage_object_key)
            append_backup_run_event(
                backup_run,
                stage='upload_finished',
                message='Backup artifact uploaded to object storage.',
                context={
                    'bucket_name': configuration.bucket_name,
                    'object_key': storage_object_key,
                    'size_bytes': artifact.size_bytes,
                },
            )

            backup_run.status = BackupRun.STATUS_SUCCEEDED
            backup_run.finished_at = timezone.now()
            backup_run.artifact_size_bytes = artifact.size_bytes
            backup_run.error_summary = ''
            backup_run.save(update_fields=['status', 'finished_at', 'artifact_size_bytes', 'error_summary', 'updated_at'])
            current_stage = 'retention'
            retention_result = apply_backup_retention(configuration, s3_client=client)
            backup_run.refresh_from_db()
            append_backup_run_event(
                backup_run,
                stage='retention_applied',
                message='Backup retention rules applied.',
                context={
                    'retention_bucket': backup_run.retention_bucket,
                    'kept_run_ids': list(retention_result.kept_run_ids),
                    'pruned_object_keys': list(retention_result.pruned_object_keys),
                },
            )
            backup_run.refresh_from_db()
            return backup_run
        except Exception as error:
            record_backup_run_failure(
                backup_run,
                stage=current_stage,
                error=error,
                context=failure_context,
            )
            backup_run.status = BackupRun.STATUS_FAILED
            backup_run.finished_at = timezone.now()
            backup_run.retention_bucket = ''
            backup_run.error_summary = _summarize_backup_error(error)
            backup_run.save(update_fields=['status', 'finished_at', 'retention_bucket', 'error_summary', 'updated_at'])
            raise
        finally:
            if artifact is not None:
                artifact.file_path.unlink(missing_ok=True)
