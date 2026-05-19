from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0044_alter_company_customer_information_file_number'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='amount_paid',
            field=models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='invoice',
            name='amount_due',
            field=models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='invoice',
            name='amount_overdue',
            field=models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='invoice',
            name='last_payment_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name='invoice',
            index=models.Index(fields=['project', 'status'], name='invoices_in_project_status_idx'),
        ),
        migrations.AddIndex(
            model_name='invoice',
            index=models.Index(fields=['customer', 'status'], name='invoices_in_customer_status_idx'),
        ),
        migrations.AddIndex(
            model_name='invoice',
            index=models.Index(fields=['project', 'issued_date'], name='invoices_in_project_issued_idx'),
        ),
        migrations.AddIndex(
            model_name='invoice',
            index=models.Index(fields=['customer', 'issued_date'], name='invoices_in_customer_issued_idx'),
        ),
    ]

