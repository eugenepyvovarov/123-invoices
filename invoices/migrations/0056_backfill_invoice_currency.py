from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations
from django.db.models import Q


ZERO = Decimal('0')
ONE = Decimal('1')


def _normalize_decimal(value):
    if value in (None, ''):
        return ZERO
    return Decimal(value)


def backfill_invoice_currency(apps, schema_editor):
    Invoice = apps.get_model('invoices', 'Invoice')

    invoices_to_update = []
    invoices = (
        Invoice.objects
        .filter(currency__isnull=True)
        .filter(
            Q(customer__currency__isnull=False)
            | Q(customer__isnull=True, project__customer__currency__isnull=False)
        )
        .select_related('customer__currency', 'project__customer__currency')
    )

    for invoice in invoices.iterator():
        customer = invoice.customer or getattr(invoice.project, 'customer', None)
        currency = getattr(customer, 'currency', None)

        if not currency:
            continue

        invoice.currency = currency

        if not invoice.exchange_rate or invoice.exchange_rate == ONE:
            invoice.exchange_rate = currency.exchange_rate_to_base

        if (
            invoice.exchange_rate
            and invoice.total_due not in (None, '')
            and (not invoice.base_currency_total or invoice.base_currency_total == ZERO)
        ):
            invoice.base_currency_total = (
                _normalize_decimal(invoice.total_due) * _normalize_decimal(invoice.exchange_rate)
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        invoices_to_update.append(invoice)

    if invoices_to_update:
        Invoice.objects.bulk_update(invoices_to_update, ['currency', 'exchange_rate', 'base_currency_total'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0055_invoice_notes'),
    ]

    operations = [
        migrations.RunPython(backfill_invoice_currency, noop),
    ]
