import datetime

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("invoices", "0056_backfill_invoice_currency"),
    ]

    operations = [
        migrations.CreateModel(
            name="BackupConfiguration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("endpoint_url", models.URLField(blank=True, max_length=500)),
                ("bucket_name", models.CharField(blank=True, max_length=255)),
                ("region", models.CharField(blank=True, max_length=100)),
                ("object_prefix", models.CharField(blank=True, max_length=255)),
                ("access_key_id", models.CharField(blank=True, max_length=255)),
                ("secret_access_key", models.CharField(blank=True, max_length=255)),
                ("is_enabled", models.BooleanField(default=False)),
                ("daily_run_time", models.TimeField(default=datetime.time(2, 0))),
                ("daily_retention_count", models.PositiveIntegerField(default=14)),
                ("weekly_retention_count", models.PositiveIntegerField(default=26)),
                ("monthly_retention_count", models.PositiveIntegerField(default=36)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Backup configuration",
                "verbose_name_plural": "Backup configuration",
            },
        ),
        migrations.CreateModel(
            name="BackupRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("in_progress", "In progress"), ("succeeded", "Succeeded"), ("failed", "Failed")], default="in_progress", max_length=20)),
                ("started_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("storage_object_key", models.CharField(blank=True, max_length=1024)),
                ("artifact_size_bytes", models.PositiveBigIntegerField(blank=True, null=True)),
                ("error_summary", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-started_at", "-id"],
            },
        ),
    ]
