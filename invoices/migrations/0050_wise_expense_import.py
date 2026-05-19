import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("invoices", "0049_wise_import_fields"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="issuer",
            name="wise_api_token",
        ),
        migrations.RemoveField(
            model_name="payment",
            name="raw_data",
        ),
        migrations.AlterField(
            model_name="payment",
            name="customer",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="payments", to="invoices.customer"),
        ),
        migrations.AddField(
            model_name="expense",
            name="external_id",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="expense",
            name="raw_data",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="expense",
            name="exclude_from_reports",
            field=models.BooleanField(default=False),
        ),
    ]
