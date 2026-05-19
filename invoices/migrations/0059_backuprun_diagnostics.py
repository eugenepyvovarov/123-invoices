from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("invoices", "0058_backuprun_retention_bucket"),
    ]

    operations = [
        migrations.AddField(
            model_name="backuprun",
            name="diagnostics",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
