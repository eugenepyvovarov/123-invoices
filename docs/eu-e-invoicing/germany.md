# Germany

ISO: `DE` · Research date: 2026-07-24.

## Mandatory status (as of 2026-08-11)

| Obligation | Mandatory now? |
| --- | --- |
| B2G (federal XRechnung) | **Yes** |
| B2B receive structured invoice | **Yes** since **2025-01-01** |
| B2B issue | **Pre-live** — **2027-01-01** (>€800k) / **2028-01-01** (others) (**implement**) |
| Tax clearance API | **No** |

**How to integrate:** [shared/germany-xrechnung.md](shared/germany-xrechnung.md) and [shared/peppol-en16931.md](shared/peppol-en16931.md).

## Snapshot

Germany made **structured e-invoices the default B2B form** (Growth Opportunities Act). There is **no federal tax-clearance platform**. Exchange is between parties using EN 16931 formats (XRechnung, ZUGFeRD/Factur-X). B2G remains XRechnung, with Länder-specific rules.

## B2G / B2B / B2C / reporting

| Channel | Status |
| --- | --- |
| B2G | Mandatory to federal authorities (from 2020). States differ. |
| B2B receive | **All** domestic B2B recipients must be able to receive e-invoices from **2025-01-01**. |
| B2B issue | Taxpayers above EUR 800k turnover: **2027-01-01**; remaining issuers: **2028-01-01**. |
| B2C | Not the B2B e-invoice mandate. |
| CTC | No Italian/Polish-style clearance. |

## Technical shape

| Item | Detail |
| --- | --- |
| Formats | **XRechnung** (CIUS), **ZUGFeRD / Factur-X** (PDF/A-3 + CII/UBL) |
| Standard | EN 16931 |
| B2G federal | [e-rechnung-bund.de](https://www.e-rechnung-bund.de/) |
| Transport | Email, portal, Peppol — party agreement; no single tax API |

## Official sources

- Federal e-invoice portal: [e-rechnung-bund.de](https://www.e-rechnung-bund.de/)
- Federal Ministry of Finance: [bundesfinanzministerium.de](https://www.bundesfinanzministerium.de/)
- Commission 2025 sheet (context): [Germany eInvoicing Country Sheet](https://ec.europa.eu/digital-building-blocks/sites/x/WACSN)
- Factsheets hub: [Country Factsheets](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108874/eInvoicing+Country+Factsheets+for+each+Member+State+and+other+countries)

## Fit to our adapter strategy

`DE_EN16931` is an **exchange adapter**, not a tax-authority client:

- generate XRechnung or ZUGFeRD from `FiscalSnapshot`
- no `FiscalSubmission` to a ministry API (unless a customer uses Peppol)
- still needs draft vs issued + immutable structured artifact

Lower priority than ES/PL/IT unless a German issuer is active.

## Caveats

- PDF-only invoices lose privileged status after the issue deadlines.
- Sixteen Länder B2G rules are not identical — check the contracting authority.
