from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Sum, Max

from invoices.models import Invoice, PaymentApplication
from invoices.services.invoice_state import coerce_amount_due, is_invoice_overdue


ZERO = Decimal('0')


def _d(value) -> Decimal:
    return coerce_amount_due(value)


def recalc_invoice_amounts(invoice_id: int) -> None:
    """Recalculate cached amounts for a single invoice and persist changes.

    - amount_invoiced: alias of total_due
    - amount_paid: sum of applications
    - amount_due: max(amount_invoiced - amount_paid, 0)
    - amount_overdue: amount_due if due_date < today and amount_due > 0, else 0
    - last_payment_date: max payment.received_at across applications
    - Normalize status for non-draft invoices based on due/overdue
    """

    invoice = Invoice.objects.filter(pk=invoice_id).first()
    if not invoice:
        return

    # Sum of applied payments
    agg = PaymentApplication.objects.filter(invoice_id=invoice.id).aggregate(
        paid=Sum('amount_applied'),
        last_payment=Max('payment__received_at'),
    )
    amount_paid = _d(agg['paid'])
    amount_invoiced = _d(invoice.total_due)
    amount_due = amount_invoiced - amount_paid
    if amount_due < ZERO:
        amount_due = ZERO

    today = date.today()
    is_overdue = is_invoice_overdue(due_date=invoice.due_date, amount_due=amount_due, today=today)
    amount_overdue = amount_due if is_overdue else ZERO
    last_payment_date = agg['last_payment']

    updates = {}
    if _d(invoice.amount_paid) != amount_paid:
        updates['amount_paid'] = amount_paid
    if _d(invoice.amount_due) != amount_due:
        updates['amount_due'] = amount_due
    if _d(invoice.amount_overdue) != amount_overdue:
        updates['amount_overdue'] = amount_overdue
    if invoice.last_payment_date != last_payment_date:
        updates['last_payment_date'] = last_payment_date

    # Normalize status for non-draft invoices only
    desired_status = None
    if invoice.status != Invoice.STATUS_DRAFT:
        if amount_due == ZERO and amount_invoiced > ZERO:
            desired_status = Invoice.STATUS_PAID
        elif is_overdue:
            desired_status = Invoice.STATUS_OVERDUE
        else:
            desired_status = Invoice.STATUS_INVOICED

    if desired_status and desired_status != invoice.status:
        updates['status'] = desired_status

    if updates:
        for k, v in updates.items():
            setattr(invoice, k, v)
        invoice.save(update_fields=list(updates.keys()))
