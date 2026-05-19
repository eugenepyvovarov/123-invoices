from datetime import date
from decimal import Decimal

from django.db import migrations, models


def backfill(apps, schema_editor):
    Invoice = apps.get_model('invoices', 'Invoice')
    PaymentApplication = apps.get_model('invoices', 'PaymentApplication')

    ZERO = Decimal('0')
    today = date.today()

    batch = []
    for inv in Invoice.objects.all().only('id', 'total_due', 'due_date', 'status'):
        paid = (
            PaymentApplication.objects.filter(invoice_id=inv.id)
            .aggregate(total=models.Sum('amount_applied'))
            .get('total')
            or ZERO
        )
        amount_invoiced = inv.total_due or ZERO
        amount_due = amount_invoiced - paid
        if amount_due < ZERO:
            amount_due = ZERO
        is_overdue = bool(inv.due_date and inv.due_date < today and amount_due > ZERO)
        amount_overdue = amount_due if is_overdue else ZERO
        last_payment = (
            PaymentApplication.objects.filter(invoice_id=inv.id)
            .aggregate(dt=models.Max('payment__received_at'))
            .get('dt')
        )
        batch.append(
            Invoice(id=inv.id, amount_paid=paid, amount_due=amount_due, amount_overdue=amount_overdue, last_payment_date=last_payment)
        )

    if batch:
        Invoice.objects.bulk_update(batch, ['amount_paid', 'amount_due', 'amount_overdue', 'last_payment_date'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0045_invoice_cached_amounts'),
    ]

    operations = [
        migrations.RunPython(backfill, noop),
    ]
