from __future__ import annotations

import re
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


def _merge_unique(existing, additions: list[str]) -> list[str]:
    values = _as_list(existing)
    seen = {_normalize(value) for value in values}
    for addition in additions:
        value = str(addition or '').strip()
        key = _normalize(value)
        if value and key not in seen:
            values.append(value)
            seen.add(key)
    return values


def _learned_subject_signal(subject: str) -> str:
    """Keep a reusable subject pattern without invoice numbers or month-specific dates."""
    words = re.findall(r'[\w@.+-]+', subject or '')
    reusable = [word for word in words if not any(char.isdigit() for char in word)]
    return ' '.join(reusable[:6]).strip()


def _learned_day_signal(candidate: IncomingInvoiceCandidate) -> str:
    if not candidate.received_at:
        return ''
    return f'day-of-month:{candidate.received_at.day:02d}'


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

    text_parts = [candidate.from_email, candidate.subject, candidate.body_text, candidate.body_html]
    text_parts.extend(candidate.artifacts.values_list('extracted_text', flat=True))
    searchable_text = ' '.join(part or '' for part in text_parts)
    legal_matches = _contains_any(searchable_text, _as_list(rule.legal_names))
    tax_matches = _contains_any(searchable_text, _as_list(rule.tax_identifiers))
    keywords = _as_list(rule.keywords)
    keyword_matches = _contains_any(
        searchable_text,
        [keyword for keyword in keywords if not keyword.startswith('day-of-month:')],
    )
    day_signal = _learned_day_signal(candidate)
    day_matched = day_signal and day_signal in keywords
    if legal_matches:
        score += Decimal('0.30')
        reasons.append('legal company name matched')
    if tax_matches:
        score += Decimal('0.35')
        reasons.append('tax/VAT identifier matched')
    if keyword_matches:
        score += min(Decimal('0.20'), Decimal('0.05') * len(keyword_matches))
        reasons.append('learned sender/subject signal matched')
    if day_matched:
        score += Decimal('0.05')
        reasons.append('learned monthly timing matched')
    if rule.issuer.company_id and rule.issuer.company.name:
        if _normalize(rule.issuer.company.name) in _normalize(searchable_text):
            score += Decimal('0.25')
            reasons.append('issuer company name matched')
    return IssuerScore(rule.issuer, min(score, Decimal('1.00')).quantize(Decimal('0.01')), reasons)


def learn_routing_signals(candidate: IncomingInvoiceCandidate, issuer: Issuer) -> IssuerEmailRoutingRule:
    """Remember reviewer-confirmed routing hints for the next similar invoice email."""
    rule, _ = IssuerEmailRoutingRule.objects.get_or_create(issuer=issuer)
    company = issuer.company
    if company:
        rule.legal_names = _merge_unique(rule.legal_names, [company.name])
        rule.tax_identifiers = _merge_unique(rule.tax_identifiers, [company.customer_information_file_number])
    rule.recipient_aliases = _merge_unique(
        rule.recipient_aliases,
        (candidate.to_addresses or []) + (candidate.cc_addresses or []),
    )
    rule.delivered_to_addresses = _merge_unique(rule.delivered_to_addresses, candidate.delivered_to_addresses or [])
    keyword_additions = [candidate.from_email, _learned_subject_signal(candidate.subject), _learned_day_signal(candidate)]
    rule.keywords = _merge_unique(rule.keywords, keyword_additions)
    rule.save(update_fields=[
        'recipient_aliases',
        'delivered_to_addresses',
        'legal_names',
        'tax_identifiers',
        'keywords',
        'updated_at',
    ])
    return rule


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
