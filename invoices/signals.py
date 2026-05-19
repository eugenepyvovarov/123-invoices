from __future__ import annotations

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from invoices.models import Invoice, OrderLine, PaymentApplication
from invoices.services.cached_totals import recalc_invoice_amounts


def _on_commit(func, *args, **kwargs):
    try:
        transaction.on_commit(lambda: func(*args, **kwargs))
    except Exception:
        # Fallback if no transaction is active
        func(*args, **kwargs)


@receiver(post_save, sender=OrderLine)
def orderline_saved(sender, instance: OrderLine, **kwargs):
    if instance.invoice_id:
        _on_commit(recalc_invoice_amounts, instance.invoice_id)


@receiver(post_delete, sender=OrderLine)
def orderline_deleted(sender, instance: OrderLine, **kwargs):
    if instance.invoice_id:
        _on_commit(recalc_invoice_amounts, instance.invoice_id)


@receiver(post_save, sender=PaymentApplication)
def payment_application_saved(sender, instance: PaymentApplication, **kwargs):
    if instance.invoice_id:
        _on_commit(recalc_invoice_amounts, instance.invoice_id)


@receiver(post_delete, sender=PaymentApplication)
def payment_application_deleted(sender, instance: PaymentApplication, **kwargs):
    if instance.invoice_id:
        _on_commit(recalc_invoice_amounts, instance.invoice_id)


@receiver(post_save, sender=Invoice)
def invoice_saved(sender, instance: Invoice, **kwargs):
    _on_commit(recalc_invoice_amounts, instance.id)

