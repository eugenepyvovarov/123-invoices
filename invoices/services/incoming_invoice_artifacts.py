from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from django.core.files.base import ContentFile
from django.utils.text import slugify

from invoices.models import IncomingInvoiceArtifact, IncomingInvoiceCandidate


ALLOWED_ATTACHMENT_CONTENT_TYPES = {
    'application/pdf',
    'image/jpeg',
    'image/png',
    'image/tiff',
    'text/csv',
    'application/csv',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}
ALLOWED_ATTACHMENT_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.tif', '.tiff', '.csv', '.xls', '.xlsx'}
TEXT_CONTENT_TYPES = {'text/plain', 'text/csv', 'application/csv'}
INVOICE_TERMS = ('invoice', 'receipt', 'factuur', 'amount', 'total', 'vat', 'tax')


@dataclass(frozen=True)
class StoredArtifactResult:
    artifact: IncomingInvoiceArtifact
    created: bool


def is_allowed_attachment(filename: str, content_type: str) -> bool:
    suffix = Path(filename or '').suffix.casefold()
    return content_type in ALLOWED_ATTACHMENT_CONTENT_TYPES or suffix in ALLOWED_ATTACHMENT_EXTENSIONS


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def safe_artifact_filename(filename: str, fallback: str = 'attachment') -> str:
    path = Path(filename or fallback)
    suffix = path.suffix.lower()
    stem = slugify(path.stem) or fallback
    return f'{stem[:80]}{suffix[:16]}'


def extract_text_from_bytes(content: bytes, content_type: str, filename: str = '') -> str:
    suffix = Path(filename or '').suffix.casefold()
    if content_type in TEXT_CONTENT_TYPES or suffix in {'.txt', '.csv'}:
        return content.decode('utf-8', errors='replace')[:20000]
    return ''


def invoice_confidence_for_text(*parts: str) -> Decimal:
    text = ' '.join(part or '' for part in parts).casefold()
    if not text.strip():
        return Decimal('0.00')
    matches = sum(1 for term in INVOICE_TERMS if term in text)
    if re.search(r'\b(invoice|factuur|receipt)\b', text) and re.search(r'\b(total|amount|vat|tax|due)\b', text):
        matches += 2
    return Decimal(min(1, matches / 5)).quantize(Decimal('0.01'))


def store_artifact(
    candidate: IncomingInvoiceCandidate,
    *,
    content: bytes,
    filename: str,
    content_type: str,
    kind: str = IncomingInvoiceArtifact.KIND_ATTACHMENT,
    extracted_text: str = '',
) -> StoredArtifactResult:
    digest = sha256_bytes(content)
    existing = candidate.artifacts.filter(sha256=digest).first()
    if existing:
        return StoredArtifactResult(existing, False)

    safe_name = safe_artifact_filename(filename, fallback='email-body' if kind == IncomingInvoiceArtifact.KIND_EMAIL_BODY_PDF else 'attachment')
    extracted = extracted_text or extract_text_from_bytes(content, content_type, safe_name)
    confidence = invoice_confidence_for_text(safe_name, extracted)
    artifact = IncomingInvoiceArtifact(
        candidate=candidate,
        kind=kind,
        original_filename=safe_name,
        content_type=content_type,
        size=len(content),
        sha256=digest,
        extracted_text=extracted,
        is_invoice_like=confidence >= Decimal('0.40'),
        invoice_confidence=confidence,
    )
    artifact.file.save(safe_name, ContentFile(content), save=True)
    return StoredArtifactResult(artifact, True)


def render_email_body_pdf(subject: str, body_text: str = '', body_html: str = '') -> bytes:
    from weasyprint import HTML

    if body_html:
        body = body_html
    else:
        body = '<pre style="white-space: pre-wrap; font-family: sans-serif;">%s</pre>' % html.escape(body_text or '')
    document = f'''
    <!doctype html>
    <html>
      <head><meta charset="utf-8"><title>{html.escape(subject or 'Email body')}</title></head>
      <body>
        <h1>{html.escape(subject or 'Email body')}</h1>
        {body}
      </body>
    </html>
    '''
    return HTML(string=document).write_pdf()


def store_email_body_pdf(candidate: IncomingInvoiceCandidate) -> IncomingInvoiceArtifact | None:
    body_text = (candidate.body_text or '').strip()
    body_html = (candidate.body_html or '').strip()
    if not body_text and not body_html:
        return None
    pdf = render_email_body_pdf(candidate.subject, body_text=body_text, body_html=body_html)
    result = store_artifact(
        candidate,
        content=pdf,
        filename='email-body.pdf',
        content_type='application/pdf',
        kind=IncomingInvoiceArtifact.KIND_EMAIL_BODY_PDF,
        extracted_text=body_text,
    )
    if candidate.generated_body_pdf_artifact_id != result.artifact.pk:
        candidate.generated_body_pdf_artifact = result.artifact
        candidate.save(update_fields=['generated_body_pdf_artifact', 'updated_at'])
    return result.artifact
