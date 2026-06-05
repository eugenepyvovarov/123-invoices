from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0064_incoming_invoice_inbox'),
    ]

    operations = [
        migrations.AlterField(
            model_name='incominginvoicecandidate',
            name='status',
            field=models.CharField(
                choices=[
                    ('new', 'New'),
                    ('needs_review', 'Needs review'),
                    ('ready', 'Ready'),
                    ('reviewed_unpaid', 'Reviewed/unpaid'),
                    ('converted', 'Converted'),
                    ('rejected', 'Rejected'),
                    ('not_invoice', 'Not an invoice'),
                    ('duplicate', 'Duplicate'),
                    ('needs_fetch', 'Needs manual fetch'),
                    ('error', 'Error'),
                ],
                default='new',
                max_length=32,
            ),
        ),
    ]
