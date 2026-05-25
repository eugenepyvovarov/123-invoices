from __future__ import annotations

import os
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction

from invoices.models import Expense, IncomingInvoiceArtifact, IncomingInvoiceCandidate, Issuer


UNPAID_LIMITATION_MESSAGE = (
    'Reviewed as unpaid; no accounting record exists yet because expenses require a paid date. '
    'Supplier bill tracking is deferred to a future workflow.'
)


def _metadata_from_cleaned(cleaned_data: dict) -> dict:
    return {
        'vendor': cleaned_data.get('vendor') or '',
        'description': cleaned_data.get('description') or '',
        'amount': str(cleaned_data.get('amount') or ''),
        'currency': cleaned_data.get('currency') or '',
        'paid_date': cleaned_data.get('paid_date').isoformat() if cleaned_data.get('paid_date') else '',
    }


def mark_candidate_confirmed(
    candidate: IncomingInvoiceCandidate,
    *,
    issuer: Issuer,
    artifact: IncomingInvoiceArtifact,
    metadata: dict,
) -> IncomingInvoiceCandidate:
    candidate.confirmed_issuer = issuer
    candidate.selected_artifact = artifact
    candidate.reviewed_metadata = metadata
    if candidate.status not in {IncomingInvoiceCandidate.STATUS_DUPLICATE, IncomingInvoiceCandidate.STATUS_CONVERTED}:
        candidate.status = IncomingInvoiceCandidate.STATUS_READY
    candidate.save(update_fields=['confirmed_issuer', 'selected_artifact', 'reviewed_metadata', 'status', 'updated_at'])
    return candidate


def mark_candidate_reviewed_unpaid(
    candidate: IncomingInvoiceCandidate,
    *,
    issuer: Issuer,
    artifact: IncomingInvoiceArtifact,
    metadata: dict,
) -> IncomingInvoiceCandidate:
    candidate.mark_reviewed_unpaid(issuer, artifact, metadata=metadata, message=UNPAID_LIMITATION_MESSAGE)
    candidate.save(update_fields=[
        'confirmed_issuer',
        'selected_artifact',
        'reviewed_metadata',
        'conversion_limitation_message',
        'status',
        'updated_at',
    ])
    return candidate


def mark_candidate_not_invoice(candidate: IncomingInvoiceCandidate) -> IncomingInvoiceCandidate:
    candidate.status = IncomingInvoiceCandidate.STATUS_NOT_INVOICE
    candidate.save(update_fields=['status', 'updated_at'])
    return candidate


def mark_candidate_rejected(candidate: IncomingInvoiceCandidate) -> IncomingInvoiceCandidate:
    candidate.status = IncomingInvoiceCandidate.STATUS_REJECTED
    candidate.save(update_fields=['status', 'updated_at'])
    return candidate


def mark_candidate_needs_fetch(candidate: IncomingInvoiceCandidate) -> IncomingInvoiceCandidate:
    candidate.status = IncomingInvoiceCandidate.STATUS_NEEDS_FETCH
    candidate.save(update_fields=['status', 'updated_at'])
    return candidate


def mark_candidate_duplicate(candidate: IncomingInvoiceCandidate, *, existing_expense: Expense | None = None) -> IncomingInvoiceCandidate:
    metadata = dict(candidate.duplicate_metadata or {})
    metadata['review_action'] = 'linked_existing' if existing_expense else 'marked_duplicate'
    if existing_expense:
        metadata['linked_existing_expense_id'] = existing_expense.pk
    candidate.duplicate_metadata = metadata
    candidate.status = IncomingInvoiceCandidate.STATUS_DUPLICATE
    candidate.save(update_fields=['duplicate_metadata', 'status', 'updated_at'])
    return candidate


@transaction.atomic
def convert_candidate_to_expense(
    candidate: IncomingInvoiceCandidate,
    *,
    issuer: Issuer,
    artifact: IncomingInvoiceArtifact,
    vendor: str,
    description: str,
    amount: Decimal,
    currency: str,
    paid_date,
    duplicate_override: bool = False,
) -> Expense:
    artifact.file.open('rb')
    try:
        data = artifact.file.read()
    finally:
        artifact.file.close()

    raw_data = {
        'incoming_invoice': {
            'candidate_id': candidate.pk,
            'source_id': candidate.source_id,
            'source_display_name': candidate.source.display_name,
            'provider': candidate.source.provider,
            'provider_message_id': candidate.provider_message_id,
            'provider_thread_id': candidate.provider_thread_id,
            'selected_artifact_id': artifact.pk,
            'selected_artifact_sha256': artifact.sha256,
            'selected_artifact_filename': artifact.original_filename,
            'fingerprint': candidate.fingerprint,
            'from_email': candidate.from_email,
            'subject': candidate.subject,
            'received_at': candidate.received_at.isoformat() if candidate.received_at else '',
            'vendor': vendor,
            'source_amount': str(amount),
            'source_currency': currency or '',
            'duplicate_override': bool(duplicate_override),
        }
    }
    expense = Expense.objects.create(
        issuer=issuer,
        paid_date=paid_date,
        amount=amount,
        description=description or vendor or candidate.display_subject,
        raw_data=raw_data,
    )
    filename = os.path.basename(artifact.file.name or artifact.original_filename or f'incoming-artifact-{artifact.pk}')
    expense.attachment.save(filename, ContentFile(data), save=True)

    candidate.confirmed_issuer = issuer
    candidate.selected_artifact = artifact
    candidate.reviewed_metadata = {
        'vendor': vendor,
        'description': description,
        'amount': str(amount),
        'currency': currency or '',
        'paid_date': paid_date.isoformat() if paid_date else '',
    }
    candidate.converted_expense = expense
    candidate.status = IncomingInvoiceCandidate.STATUS_CONVERTED
    candidate.save(update_fields=[
        'confirmed_issuer',
        'selected_artifact',
        'reviewed_metadata',
        'converted_expense',
        'status',
        'updated_at',
    ])
    from invoices.views import invalidate_dashboard_cache

    invalidate_dashboard_cache(issuer.pk)
    return expense


def review_metadata_from_cleaned(cleaned_data: dict) -> dict:
    return _metadata_from_cleaned(cleaned_data)
