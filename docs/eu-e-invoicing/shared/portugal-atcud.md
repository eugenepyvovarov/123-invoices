# Shared integration: Portugal AT certified software / ATCUD / QR / SAF-T

Used by: **[Portugal](../portugal.md)**.

## Mandatory?

| Rule | Mandatory now? |
| --- | --- |
| AT-certified invoicing software | **Yes** (includes many non-established VAT IDs) |
| ATCUD + QR on invoices | **Yes** (QR since 2022, ATCUD since 2023 — confirm any 2026 PDF/QES nuance on Portal das Finanças) |
| SAF-T (PT) / e-Fatura reporting | **Yes** (periodic) |
| B2G structured CIUS-PT | **Yes** for public suppliers |
| General B2B clearance e-invoice | **No** |

## Official developer sources

| Resource | URL |
| --- | --- |
| Portal das Finanças | https://www.portaldasfinancas.gov.pt/ |
| Commission factsheet (QES on PDF 2026) | https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108897/eInvoicing+in+Portugal |

Implement only from AT documentation (software certification / Modelo 24, ATCUD series, QR technical note, SAF-T XSD). Those files sit behind authenticated Portal das Finanças areas — download at implementation time.

## Integration shape

1. Certify the product (or run as a certified instance).
2. Register invoice **series** with AT; receive validation code.
3. ATCUD = `ValidationCode-DocumentNumber`.
4. Render AT QR on the PDF (field encoding per AT spec).
5. From 2026-01-01, Commission sheet: PDFs need a **qualified electronic signature** — verify current AT text.
6. Export SAF-T monthly / as required.
7. B2G: produce CIUS-PT EN 16931 and send via the public e-invoice channel (often Peppol-compatible). See [peppol-en16931.md](peppol-en16931.md) plus PT CIUS.

Closest product cousin: **Spain SIF** (software identity + QR), not KSeF.
