from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from invoices.models import IncomingInvoiceCandidate, Issuer, IssuerEmailRoutingRule


@dataclass(frozen=True)
class IssuerScore:
    issuer: Issuer
    confidence: Decimal
    reasons: list[str] = field(default_factory=list)


def _normalize(value: str) -> str:
    return ' '.join((value or '').casefold().split())


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _contains_any(text: str, needles: list[str]) -> list[str]:
    normalized_text = _normalize(text)
    return [needle for needle in needles if _normalize(needle) and _normalize(needle) in normalized_text]


def score_candidate_for_issuer(candidate: IncomingInvoiceCandidate, rule: IssuerEmailRoutingRule) -> IssuerScore:
    score = Decimal('0.00')
    reasons: list[str] = []
    recipient_addresses = {_normalize(addr) for addr in (candidate.to_addresses or []) + (candidate.cc_addresses or [])}
    delivered_addresses = {_normalize(addr) for addr in candidate.delivered_to_addresses or []}

    aliases = {_normalize(addr) for addr in _as_list(rule.recipient_aliases)}
    delivered = {_normalize(addr) for addr in _as_list(rule.delivered_to_addresses)}
    if recipient_addresses & aliases:
        score += Decimal('0.55')
        reasons.append('recipient alias matched')
    if delivered_addresses & delivered:
        score += Decimal('0.55')
        reasons.append('delivered-to address matched')

    text_parts = [candidate.subject, candidate.body_text, candidate.body_html]
    text_parts.extend(candidate.artifacts.values_list('extracted_text', flat=True))
    searchable_text = ' '.join(part or '' for part in text_parts)
    legal_matches = _contains_any(searchable_text, _as_list(rule.legal_names))
    tax_matches = _contains_any(searchable_text, _as_list(rule.tax_identifiers))
    keyword_matches = _contains_any(searchable_text, _as_list(rule.keywords))
    if legal_matches:
        score += Decimal('0.30')
        reasons.append('legal company name matched')
    if tax_matches:
        score += Decimal('0.35')
        reasons.append('tax/VAT identifier matched')
    if keyword_matches:
        score += min(Decimal('0.20'), Decimal('0.05') * len(keyword_matches))
        reasons.append('keyword matched')
    if rule.issuer.company_id and rule.issuer.company.name:
        if _normalize(rule.issuer.company.name) in _normalize(searchable_text):
            score += Decimal('0.25')
            reasons.append('issuer company name matched')
    return IssuerScore(rule.issuer, min(score, Decimal('1.00')).quantize(Decimal('0.01')), reasons)


def score_candidate(candidate: IncomingInvoiceCandidate) -> list[IssuerScore]:
    rules = IssuerEmailRoutingRule.objects.filter(auto_assign_enabled=True).select_related('issuer__company')
    scores = [score_candidate_for_issuer(candidate, rule) for rule in rules]
    return sorted(scores, key=lambda item: item.confidence, reverse=True)


def apply_routing(candidate: IncomingInvoiceCandidate) -> IncomingInvoiceCandidate:
    scores = score_candidate(candidate)
    eligible = []
    for scored in scores:
        threshold = scored.issuer.incoming_email_routing_rule.confidence_threshold
        if scored.confidence >= threshold:
            eligible.append(scored)
    metadata = {
        'company_scores': [
            {'issuer_id': score.issuer.pk, 'confidence': str(score.confidence), 'reasons': score.reasons}
            for score in scores
        ]
    }
    if len(eligible) == 1:
        candidate.suggested_issuer = eligible[0].issuer
        candidate.status = IncomingInvoiceCandidate.STATUS_READY
        metadata['company_confidence'] = str(eligible[0].confidence)
        metadata['company_reasons'] = eligible[0].reasons
    else:
        candidate.suggested_issuer = None
        if candidate.status in {IncomingInvoiceCandidate.STATUS_NEW, IncomingInvoiceCandidate.STATUS_READY}:
            candidate.status = IncomingInvoiceCandidate.STATUS_NEEDS_REVIEW
        if len(eligible) > 1:
            metadata['company_warning'] = 'multiple issuers matched'
        else:
            metadata['company_warning'] = 'no issuer met confidence threshold'
    current = candidate.detection_metadata or {}
    current.update(metadata)
    candidate.detection_metadata = current
    candidate.save(update_fields=['suggested_issuer', 'status', 'detection_metadata', 'updated_at'])
    return candidate
