from __future__ import annotations

import email
import imaplib
import re
from dataclasses import dataclass, field
from datetime import datetime
from email.message import Message
from email.policy import default
from email.utils import getaddresses, parsedate_to_datetime, parseaddr
from pathlib import Path
from typing import Iterable

from django.db import IntegrityError, transaction
from django.utils import timezone

from invoices.models import IncomingEmailSource, IncomingInvoiceCandidate
from invoices.services.incoming_invoice_artifacts import (
    invoice_confidence_for_text,
    is_allowed_attachment,
    store_artifact,
    store_email_body_pdf,
)
from invoices.services.incoming_invoice_duplicates import detect_duplicates, invoice_fingerprint
from invoices.services.incoming_invoice_routing import apply_routing


HEADER_ALLOWLIST = {'message-id', 'in-reply-to', 'references', 'date', 'from', 'to', 'cc', 'delivered-to', 'subject'}
PORTAL_LINK_RE = re.compile(r'https?://\S+', re.I)


@dataclass(frozen=True)
class ParsedAttachment:
    filename: str
    content_type: str
    content: bytes
    inline: bool = False


@dataclass(frozen=True)
class ParsedIncomingEmail:
    provider_message_id: str
    provider_thread_id: str
    from_name: str
    from_email: str
    to_addresses: list[str]
    cc_addresses: list[str]
    delivered_to_addresses: list[str]
    subject: str
    received_at: datetime
    body_text: str
    body_html: str
    attachments: list[ParsedAttachment] = field(default_factory=list)
    raw_provider_metadata: dict = field(default_factory=dict)


@dataclass
class IncomingImportResult:
    candidate: IncomingInvoiceCandidate | None
    created: bool
    artifacts_created: int = 0
    duplicate: bool = False


def _clean_header(value: str) -> str:
    return ' '.join((value or '').replace('\x00', '').split())[:1000]


def _addresses(value: str) -> list[str]:
    return [addr.casefold() for _, addr in getaddresses([value or '']) if addr]


def _payload_text(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        raw = part.get_payload()
        return raw if isinstance(raw, str) else ''
    charset = part.get_content_charset() or 'utf-8'
    return payload.decode(charset, errors='replace')


def parse_email_message(raw_message: bytes | str, fallback_message_id: str = '') -> ParsedIncomingEmail:
    message = email.message_from_bytes(raw_message, policy=default) if isinstance(raw_message, bytes) else email.message_from_string(raw_message, policy=default)
    message_id = _clean_header(message.get('Message-ID') or fallback_message_id)
    if not message_id:
        raise ValueError('Email message is missing Message-ID.')
    from_name, from_email = parseaddr(message.get('From', ''))
    received_at = parsedate_to_datetime(message.get('Date')) if message.get('Date') else timezone.now()
    if timezone.is_naive(received_at):
        received_at = timezone.make_aware(received_at, timezone.get_current_timezone())
    body_text = ''
    body_html = ''
    attachments: list[ParsedAttachment] = []
    parts: Iterable[Message] = message.walk() if message.is_multipart() else [message]
    for part in parts:
        if part.is_multipart():
            continue
        disposition = (part.get_content_disposition() or '').casefold()
        content_type = part.get_content_type()
        filename = part.get_filename() or ''
        payload = part.get_payload(decode=True) or b''
        if filename or disposition in {'attachment', 'inline'}:
            if payload and is_allowed_attachment(filename, content_type):
                attachments.append(ParsedAttachment(filename or 'attachment', content_type, payload, inline=disposition == 'inline'))
            continue
        if content_type == 'text/plain':
            body_text += ('\n' if body_text else '') + _payload_text(part)
        elif content_type == 'text/html':
            body_html += ('\n' if body_html else '') + _payload_text(part)
    sanitized_headers = {key: _clean_header(message.get(key, '')) for key in HEADER_ALLOWLIST if message.get(key)}
    return ParsedIncomingEmail(
        provider_message_id=message_id[:255],
        provider_thread_id=_clean_header(message.get('References') or message.get('In-Reply-To') or '')[:255],
        from_name=_clean_header(from_name)[:255],
        from_email=(from_email or '').casefold()[:254],
        to_addresses=_addresses(message.get('To', '')),
        cc_addresses=_addresses(message.get('Cc', '')),
        delivered_to_addresses=_addresses(message.get('Delivered-To', '')),
        subject=_clean_header(message.get('Subject', ''))[:500],
        received_at=received_at,
        body_text=body_text[:50000],
        body_html=body_html[:50000],
        attachments=attachments,
        raw_provider_metadata={'headers': sanitized_headers},
    )


def import_parsed_email(source: IncomingEmailSource, parsed: ParsedIncomingEmail) -> IncomingImportResult:
    invoice_confidence = invoice_confidence_for_text(parsed.subject, parsed.body_text, parsed.body_html)
    fingerprint = invoice_fingerprint(
        {'vendor': parsed.from_email, 'invoice_number': parsed.subject},
        parsed.body_text or parsed.subject,
    )
    try:
        with transaction.atomic():
            candidate = IncomingInvoiceCandidate.objects.create(
                source=source,
                provider_message_id=parsed.provider_message_id,
                provider_thread_id=parsed.provider_thread_id,
                from_name=parsed.from_name,
                from_email=parsed.from_email,
                to_addresses=parsed.to_addresses,
                cc_addresses=parsed.cc_addresses,
                delivered_to_addresses=parsed.delivered_to_addresses,
                subject=parsed.subject,
                received_at=parsed.received_at,
                body_text=parsed.body_text,
                body_html=parsed.body_html,
                raw_provider_metadata=parsed.raw_provider_metadata,
                detection_metadata={'invoice_confidence': str(invoice_confidence)},
                fingerprint=fingerprint,
            )
    except IntegrityError:
        return IncomingImportResult(
            candidate=IncomingInvoiceCandidate.objects.filter(source=source, provider_message_id=parsed.provider_message_id).first(),
            created=False,
            duplicate=True,
        )

    artifacts_created = 0
    for attachment in parsed.attachments:
        result = store_artifact(
            candidate,
            content=attachment.content,
            filename=attachment.filename,
            content_type=attachment.content_type,
        )
        artifacts_created += int(result.created)
    if parsed.body_text.strip() or parsed.body_html.strip():
        artifact = store_email_body_pdf(candidate)
        artifacts_created += int(bool(artifact))
    text_for_portal = ' '.join([parsed.subject, parsed.body_text, parsed.body_html])
    if not parsed.attachments and invoice_confidence < 0.40 and PORTAL_LINK_RE.search(text_for_portal):
        candidate.status = IncomingInvoiceCandidate.STATUS_NEEDS_FETCH
        candidate.save(update_fields=['status', 'updated_at'])
    else:
        apply_routing(candidate)
    detect_duplicates(candidate)
    if source.last_seen_message_at is None or parsed.received_at > source.last_seen_message_at:
        source.last_seen_message_at = parsed.received_at
        source.save(update_fields=['last_seen_message_at', 'updated_at'])
    return IncomingImportResult(candidate=candidate, created=True, artifacts_created=artifacts_created)


def import_eml_bytes(source: IncomingEmailSource, raw_message: bytes | str, fallback_message_id: str = '') -> IncomingImportResult:
    return import_parsed_email(source, parse_email_message(raw_message, fallback_message_id=fallback_message_id))


def import_eml_fixture(source: IncomingEmailSource, path: str | Path) -> IncomingImportResult:
    fixture_path = Path(path)
    return import_eml_bytes(source, fixture_path.read_bytes(), fallback_message_id=fixture_path.name)


def fetch_imap_messages(source: IncomingEmailSource, *, host: str, username: str, password: str, port: int = 993, limit: int | None = None) -> list[bytes]:
    if source.provider != IncomingEmailSource.PROVIDER_IMAP:
        raise ValueError('Only IMAP sources are supported.')
    query = source.polling_query or 'ALL'
    messages: list[bytes] = []
    with imaplib.IMAP4_SSL(host, port) as client:
        client.login(username, password)
        client.select(source.folder or 'INBOX', readonly=True)
        status, data = client.search(None, *query.split())
        if status != 'OK':
            raise RuntimeError('IMAP search failed.')
        ids = (data[0] or b'').split()
        if limit is not None:
            ids = ids[:limit]
        for message_id in ids:
            status, fetched = client.fetch(message_id, '(BODY.PEEK[])')
            if status != 'OK':
                continue
            for item in fetched:
                if isinstance(item, tuple) and item[1]:
                    messages.append(item[1])
        client.close()
        client.logout()
    return messages


def poll_imap_source(source: IncomingEmailSource, *, host: str, username: str, password: str, port: int = 993, limit: int | None = None) -> list[IncomingImportResult]:
    return [import_eml_bytes(source, raw) for raw in fetch_imap_messages(source, host=host, username=username, password=password, port=port, limit=limit)]
