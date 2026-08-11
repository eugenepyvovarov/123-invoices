# Shared integration: Poland KSeF 2.0 API

Used by: **[Poland](../poland.md)** only.

**Local copies (folders/files, no git):**

- OpenAPI: [`../_vendor/poland-ksef/ksef-2-openapi-prod.json`](../_vendor/poland-ksef/ksef-2-openapi-prod.json)
- Integrator docs: [`../_vendor/poland-ksef/ksef-api-docs/`](../_vendor/poland-ksef/ksef-api-docs/)

## Mandatory?

**Yes, for in-scope domestic B2B** (phased 2026; most VAT businesses already in). See [poland.md](../poland.md) for who/when. This file is **how to integrate** the official API.

## Official developer sources

| Resource | URL |
| --- | --- |
| Integrator support (Ministry) | https://ksef.podatki.gov.pl/ksef-na-okres-obligatoryjny/wsparcie-dla-integratorow/ |
| FA(3) logical structure | https://ksef.podatki.gov.pl/ksef-na-okres-obligatoryjny/struktura-logiczna-fa-3/ |
| Production OpenAPI (downloaded) | https://api.ksef.mf.gov.pl/docs/v2/openapi.json |
| Interactive docs | https://api.ksef.mf.gov.pl/docs/v2/ |
| Production API base | `https://api.ksef.mf.gov.pl/v2` |
| Test OpenAPI | https://api-test.ksef.mf.gov.pl/docs/v2/openapi.json |
| Extended scenarios (auth, sessions) | https://github.com/CIRFMF/ksef-api |
| API changelog | https://github.com/CIRFMF/ksef-api/blob/main/api-changelog.md |

Downloaded contract (2026-08-11): **KSeF API PR v2**, `info.version` **2.6.1** (build `2.7.0-pr-20260806.1`). **59 paths.**

## Auth (from official OpenAPI)

KSeF does **not** use a simple static API key.

1. `POST /auth/challenge` — get a challenge + timestamp.  
2. Authenticate with **one** of:
   - `POST /auth/xades-signature` — XML `AuthTokenRequest` signed **XAdES** (qualified seal/signature). Guide: https://github.com/CIRFMF/ksef-api/blob/main/uwierzytelnianie.md
   - `POST /auth/ksef-token` — encrypt `token|timestamp` (ms since epoch) with the Ministry **public key** (tokens sunset end-2026; certs preferred from 2027).
3. Poll `GET /auth/{referenceNumber}` until success.
4. `POST /auth/token/redeem` — receive **access + refresh tokens once**.
5. `POST /auth/token/refresh` as needed.  
6. `DELETE /auth/sessions/current` to log out.

Public keys: `GET /security/public-key-certificates`.  
Certificates lifecycle: `/certificates/enrollments`, `/certificates/retrieve`, revoke.

## Send an invoice (interactive session)

Encryption is mandatory on the wire: **AES-256-CBC + PKCS#7**, session key wrapped with the MF public key.

1. `POST /sessions/online` (`OpenOnlineSessionRequest`) — declare FA schema form + encryption key material.  
2. `POST /sessions/online/{referenceNumber}/invoices` with `SendInvoiceRequest`:

```json
{
  "invoiceHash": "<SHA-256 of plaintext FA(3) XML, Base64>",
  "invoiceSize": 6480,
  "encryptedInvoiceHash": "<SHA-256 of ciphertext, Base64>",
  "encryptedInvoiceSize": 6496,
  "encryptedInvoiceContent": "<Base64 AES-256-CBC ciphertext>",
  "offlineMode": false
}
```

3. Poll `GET /sessions/{referenceNumber}/invoices/{invoiceReferenceNumber}` for processing status.  
4. `GET /sessions/{referenceNumber}/invoices/{invoiceReferenceNumber}/upo` — official **UPO**.  
5. `GET /invoices/ksef/{ksefNumber}` — fetch by KSeF number.  
6. `POST /sessions/online/{referenceNumber}/close` — close session (starts aggregate UPO).

### Batch

`POST /sessions/batch` → upload parts → `POST /sessions/batch/{referenceNumber}/close`.

### Query / export / inbound

- `POST /invoices/query/metadata`
- `POST /invoices/exports` + `GET /invoices/exports/{referenceNumber}`
- `GET /peppol/query` (Peppol-related lookup on this API)
- Permissions grants under `/permissions/**`

### Limits

`GET /limits/context`, `GET /limits/subject`, `GET /rate-limits`. Invoice max size depends on authenticated context (`invoiceSize` description in OpenAPI).

Errors: set header `X-Error-Format: problem-details` for RFC 7807 `application/problem+json`.

Required permission examples from OpenAPI: `InvoiceWrite`, `PefInvoiceWrite`, `Introspection`.

## Payload (not in OpenAPI)

The API transports an **encrypted FA(3) XML**. The logical structure is a separate Ministry artifact (FA(3) XSD / documentation on podatki.gov.pl). Implement FA(3) in `fiscal/pl_ksef/`, then encrypt as above.

## App mapping

| Generic concept | KSeF |
| --- | --- |
| `issue_invoice` | Build FA(3), open session, send, wait UPO |
| `authority_document_id` | KSeF number |
| `authority_ack_payload` | UPO XML/bytes |
| Offline mode | `offlineMode: true` + later upload (Offline24 rules) |
| Inbound AP | query/export endpoints |

Do **not** share this client with Spain AEAT SOAP or Italy SDICoop.
