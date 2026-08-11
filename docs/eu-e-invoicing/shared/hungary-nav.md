# Shared integration: Hungary NAV Online Számla (RTIR)

Used by: **[Hungary](../hungary.md)** only.

## Mandatory?

**Yes — real-time invoice data reporting** for essentially all issued invoices (B2B/B2C and more) via NAV Online Számla.  
**No** general mandatory structured B2B e-invoice (except energy-sector e-invoices from 2025-07).

The commercial invoice can still be PDF; the **XML report to NAV** is the legal feed.

## Official developer sources

| Resource | URL |
| --- | --- |
| Developer docs portal | https://onlineszamla.nav.gov.hu/dokumentaciok |
| Developer diary | https://onlineszamla.nav.gov.hu/fejlesztoi_naplo |
| Official GitHub (XSD, examples) | https://github.com/nav-gov-hu/Online-Invoice |
| API spec (HU) | https://github.com/nav-gov-hu/Online-Invoice/tree/master/docs/API%20docs/hu |
| Production UI | https://onlineszamla.nav.gov.hu/ |
| Production API | `https://api.onlineszamla.nav.gov.hu/` |
| Test UI | https://onlineszamla-test.nav.gov.hu/ |
| Test API | `https://api-test.onlineszamla.nav.gov.hu/` |

**Local copy:** [`../_vendor/hungary-nav/Online-Invoice/docs/API docs/`](../_vendor/hungary-nav/Online-Invoice/docs/API%20docs/) (latest EN/HU interface PDFs, 2026-02-12). Folder snapshot, no git.

Current public interface family: **OSA 3.0** XML.

- API namespace: `http://schemas.nav.gov.hu/OSA/3.0/api`
- Common: `http://schemas.nav.gov.hu/NTCA/1.0/common`
- Invoice data / annulment sibling schemas under the same GitHub tree
- Password hash: **SHA-512** with `cryptoType="SHA-512"`
- URL version segment: `/v3/` (not `/v2/`)

## Typical M2M flow (from official interface model)

1. Create a **technical user** on Online Számla; store XML signing key + exchange key.
2. `POST …/tokenExchange` (or current token operation in the v3 spec) — signed XML request, receive a short-lived exchange token.
3. `manageInvoice` — upload one or more invoice XML reports (base64 inner invoice + electronic signature / request signature as specified).
4. Poll `queryTransactionStatus` / query digest / `queryInvoiceData`.
5. `queryTaxpayer` for buyer VAT checks.
6. `manageAnnulment` for technical annulment (not a substitute for a corrective invoice).

Exact operation names and XSD live in the GitHub `invoiceApi.xsd` — implement against that file, not against blog copies.

## App mapping

Reporting adapter `HU_NAV`. Fire **after** `issue_invoice`. Do not block PDF issue on NAV acceptance (unless product policy wants a hard fail). Store NAV transaction id + validation result.

Do **not** reuse KSeF encryption or SdI SOAP.
