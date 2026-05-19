from invoices.models import Invoice, IssuerBankAccount


def get_default_bank_account(issuer):
    if not issuer:
        return None
    return (
        IssuerBankAccount.objects.filter(issuer=issuer, is_active=True, is_default=True)
        .order_by('sort_order', 'label', 'id')
        .first()
    )


def get_last_used_bank_account(customer, issuer=None, exclude_invoice=None):
    if not customer:
        return None

    qs = (
        Invoice.objects.filter(customer=customer, bank_account__isnull=False, bank_account__is_active=True)
        .select_related('bank_account')
        .order_by('-issued_date', '-created_at', '-pk')
    )
    if issuer:
        qs = qs.filter(issuer=issuer, bank_account__issuer=issuer)
    if exclude_invoice is not None and getattr(exclude_invoice, 'pk', None):
        qs = qs.exclude(pk=exclude_invoice.pk)
    last_invoice = qs.first()
    return last_invoice.bank_account if last_invoice else None


def resolve_invoice_bank_account(issuer, customer=None, project=None, exclude_invoice=None):
    resolved_customer = customer or (project.customer if project else None)
    return get_last_used_bank_account(resolved_customer, issuer=issuer, exclude_invoice=exclude_invoice) or get_default_bank_account(issuer)


def bank_account_for_project(project, issuer=None, exclude_invoice=None):
    if not project:
        return get_default_bank_account(issuer)
    return resolve_invoice_bank_account(
        issuer or project.customer.issuer,
        customer=project.customer,
        project=project,
        exclude_invoice=exclude_invoice,
    )
