from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("invoices", "0051_remove_invoice_invoices_in_project_status_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="expense",
            name="exclude_from_reports",
            field=models.BooleanField(default=False),
        ),
    ]
