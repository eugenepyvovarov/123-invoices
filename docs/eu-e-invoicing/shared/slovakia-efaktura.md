# Shared integration: Slovakia eFaktúra (2027-01-01)

Used by: **[Slovakia](../slovakia.md)**.

## Mandatory?

**Pre-live.** Domestic B2B (and B2G) structured e-invoice + reporting from **2027-01-01** (Law 385/2025 / VAT Act amendment). Voluntary use from Q2 2026.

## Official sources (local)

| Resource | Path / URL |
| --- | --- |
| Solution architecture v1.2 (30 Mar 2026) | [`../_vendor/slovakia-2027/2026.03.30_Slov_Solution_Architect2.pdf`](../_vendor/slovakia-2027/2026.03.30_Slov_Solution_Architect2.pdf) |
| FS e-invoicing (EN) | [`../_vendor/slovakia-2027/e-invoicing.html`](../_vendor/slovakia-2027/e-invoicing.html) · https://www.financnasprava.sk/en/businesses/taxes-businesses/value-added-tax/e-invoicing |
| FS eFaktúra (SK) | [`../_vendor/slovakia-2027/e-faktura-sk.html`](../_vendor/slovakia-2027/e-faktura-sk.html) |
| Law 385/2025 | https://www.slov-lex.sk/ezbierky/pravne-predpisy/SK/ZZ/2025/385/20270101.html |
| Peppol BIS (format) | [`../_vendor/peppol/`](../_vendor/peppol/) |

## How it works

5-corner / **Digital Postman** model: you do **not** call a Slovak tax REST API like KSeF.

1. Build EN 16931 / Peppol BIS (+ Slovak CIUS when published).
2. Send via a **certified Digital Postman** (Peppol Access Point on the FS list).
3. The postman validates and the tax data document (TDD) is reported to FS.

Vendor integration point = **Peppol AP**, same as Belgium.

## Ready to implement?

**Formats:** yes (Peppol pack). **Architecture:** yes (50-page FS PDF). **FS machine API / TDD XSD:** not in a downloadable pack here. Implement Peppol send when a SK issuer exists; add TDD when FS publishes the schema zip.
