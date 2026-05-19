from django.db import migrations


def convert_pending_payment(apps, schema_editor):
    Invoice = apps.get_model('invoices', 'Invoice')
    Invoice.objects.filter(status='pending_payment').update(status='invoiced')


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0031_invoice_status'),
    ]

    operations = [
        migrations.RunPython(convert_pending_payment, noop),
    ]
