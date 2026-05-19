from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("invoices", "0057_backup_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="backuprun",
            name="retention_bucket",
            field=models.CharField(
                blank=True,
                choices=[("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly")],
                max_length=20,
            ),
        ),
    ]
