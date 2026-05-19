from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("invoices", "0059_backuprun_diagnostics"),
    ]

    operations = [
        migrations.AddField(
            model_name="backuprun",
            name="trigger_source",
            field=models.CharField(
                choices=[("manual", "Manual"), ("scheduled", "Scheduled")],
                default="manual",
                max_length=20,
            ),
            preserve_default=True,
        ),
    ]
