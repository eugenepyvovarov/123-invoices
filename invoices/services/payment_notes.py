def resolve_invoice_payment_notes(invoice):
    """Return customer payment notes with issuer-company fallback."""
    customer_notes = getattr(getattr(invoice, 'customer', None), 'payment_notes', '') or ''
    if customer_notes.strip():
        return customer_notes

    issuer_company = getattr(getattr(invoice, 'issuer', None), 'company', None)
    company_notes = getattr(issuer_company, 'payment_terms', '') or ''
    if company_notes.strip():
        return company_notes

    return ''
