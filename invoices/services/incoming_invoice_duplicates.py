from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from invoices.models import Expense, IncomingInvoiceArtifact, IncomingInvoiceCandidate


@dataclass(frozen=True)
class DuplicateReport:
    is_duplicate: bool
    reasons: list[str] = field(default_factory=list)
    candidate_ids: list[int] = field(default_factory=list)
    expense_ids: list[int] = field(default_factory=list)


def invoice_fingerprint(metadata: dict, fallback_text: str = '') -> str:
    payload = {
        'vendor': metadata.get('vendor') or metadata.get('supplier') or '',
        'invoice_number': metadata.get('invoice_number') or metadata.get('number') or '',
        'issue_date': metadata.get('issue_date') or metadata.get('date') or '',
        'amount': str(metadata.get('amount') or ''),
        'text': fallback_text[:500],
    }
    normalized = json.dumps(payload, sort_keys=True, ensure_ascii=False).casefold()
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def detect_duplicates(candidate: IncomingInvoiceCandidate) -> DuplicateReport:
    reasons: list[str] = []
    candidate_ids: set[int] = set()
    expense_ids: set[int] = set()

    same_message = IncomingInvoiceCandidate.objects.filter(
        source=candidate.source,
        provider_message_id=candidate.provider_message_id,
    ).exclude(pk=candidate.pk)
    if same_message.exists():
        reasons.append('source message id already exists')
        candidate_ids.update(same_message.values_list('id', flat=True))

    hashes = list(candidate.artifacts.values_list('sha256', flat=True))
    if hashes:
        same_hash = IncomingInvoiceArtifact.objects.filter(sha256__in=hashes).exclude(candidate=candidate)
        if same_hash.exists():
            reasons.append('artifact hash already exists')
            candidate_ids.update(same_hash.values_list('candidate_id', flat=True))
        incoming_expenses = Expense.objects.filter(raw_data__incoming_invoice__selected_artifact_sha256__in=hashes)
        if incoming_expenses.exists():
            reasons.append('incoming-created expense uses same artifact hash')
            expense_ids.update(incoming_expenses.values_list('id', flat=True))

    fingerprint = candidate.fingerprint or invoice_fingerprint(candidate.extracted_metadata or {}, candidate.body_text or candidate.subject)
    if fingerprint:
        same_fingerprint = IncomingInvoiceCandidate.objects.filter(fingerprint=fingerprint).exclude(pk=candidate.pk)
        if same_fingerprint.exists():
            reasons.append('invoice fingerprint already exists')
            candidate_ids.update(same_fingerprint.values_list('id', flat=True))
        expenses = Expense.objects.filter(raw_data__incoming_invoice__fingerprint=fingerprint)
        if expenses.exists():
            reasons.append('incoming-created expense uses same invoice fingerprint')
            expense_ids.update(expenses.values_list('id', flat=True))
        if candidate.fingerprint != fingerprint:
            candidate.fingerprint = fingerprint

    report = DuplicateReport(bool(reasons), reasons, sorted(candidate_ids), sorted(expense_ids))
    candidate.duplicate_metadata = {
        'is_duplicate': report.is_duplicate,
        'reasons': report.reasons,
        'candidate_ids': report.candidate_ids,
        'expense_ids': report.expense_ids,
    }
    update_fields = ['duplicate_metadata', 'updated_at']
    if candidate.fingerprint == fingerprint:
        update_fields.append('fingerprint')
    if report.is_duplicate and candidate.status not in {IncomingInvoiceCandidate.STATUS_CONVERTED, IncomingInvoiceCandidate.STATUS_NOT_INVOICE}:
        candidate.status = IncomingInvoiceCandidate.STATUS_DUPLICATE
        update_fields.append('status')
    candidate.save(update_fields=update_fields)
    return report
