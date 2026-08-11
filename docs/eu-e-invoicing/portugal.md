# Portugal

ISO: `PT` · Research date: 2026-07-24.

## Mandatory status (as of 2026-08-11)

| Obligation | Mandatory now? |
| --- | --- |
| Certified software + ATCUD + QR | **Yes** |
| SAF-T / e-Fatura reporting | **Yes** |
| B2G structured invoice | **Yes** |
| General B2B clearance e-invoice | **No** |

**How to integrate:** [shared/portugal-atcud.md](shared/portugal-atcud.md); B2G also [shared/peppol-en16931.md](shared/peppol-en16931.md) + CIUS-PT.

## Snapshot

Portugal does **not** run a general B2B clearance platform. It runs a **certified invoicing software** regime: every invoice (paper, PDF, or XML) must come from **AT-certified software**, carry **ATCUD** and a **QR code**, and feed **SAF-T (PT)**. B2G uses structured CIUS-PT e-invoices.

This is the closest cousin to **Spain SIF** in the “software integrity + codes on the document” family.

## B2G / B2B / B2C / reporting

| Channel | Status |
| --- | --- |
| B2G | Mandatory (large 2021; SME/micro later; CIUS-PT). |
| B2B structured | Optional; paper/PDF still allowed if other rules are met. |
| PDF 2026 | Commission factsheet: PDFs need a **qualified electronic signature** from **2026-01-01**; ATCUD on those PDFs described as optional in that note — **confirm on Portal das Finanças** (other guides still treat ATCUD as general). |
| Reporting | Monthly SAF-T / e-Fatura ecosystem. |

## Technical shape

| Item | Detail |
| --- | --- |
| Authority | Autoridade Tributária e Aduaneira (**AT**) |
| Software | Certification via Modelo 24 |
| ATCUD | Unique document identifier (series validation code + number) |
| QR | AT specification on the invoice |
| SAF-T PT | Periodic extract of invoicing data |

## Official sources

- Portal das Finanças: [portaldasfinancas.gov.pt](https://www.portaldasfinancas.gov.pt/)
- Commission factsheet: [eInvoicing in Portugal](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108897/eInvoicing+in+Portugal)
- Factsheets hub: [Country Factsheets](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108874/eInvoicing+Country+Factsheets+for+each+Member+State+and+other+countries)

## Fit to our adapter strategy

`PT_ATCUD` is a **certified-software adapter**:

- series registration with AT
- ATCUD + QR on PDF
- SAF-T export job
- **no** KSeF-like submit-for-legal-force (unless B2G CIUS-PT)

Reusable patterns with `ES_SIF`: QR generation, software identity metadata, immutable artifact after issue.

## Caveats

- ATCUD vs QES-on-PDF details differ between the 2026 Commission sheet and practitioner guides — implement only from AT documentation.
- Certified software obligation can apply to **non-established** VAT-registered businesses.
