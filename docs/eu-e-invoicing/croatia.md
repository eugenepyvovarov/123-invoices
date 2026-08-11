# Croatia

ISO: `HR` · Research date: 2026-07-24.

## Mandatory status (as of 2026-08-11)

| Obligation | Mandatory now? |
| --- | --- |
| B2G eRačun | **Yes** (since 2019) |
| B2B eRačun + e-reporting | **Yes** since **2026-01-01** (established / PE) |
| Fiscalisation 2.0 | **Yes** (live); **2027** widen is pre-live same stack |

**How to integrate:** structured invoice via Fina / Peppol — [shared/peppol-en16931.md](shared/peppol-en16931.md). Dual-sided e-reporting is national (Porezna/Fina); use their current e-Account docs when coding, do not invent a second REST beside Peppol without Fina’s spec.

## Snapshot

**Fiscalisation 2.0** makes structured **eRačun** plus **e-reporting** mandatory for B2B/B2G from **1 January 2026** (widening in 2027). Croatia already had cash-register fiscalisation and B2G e-invoices via **Fina** / Peppol.

## B2G / B2B / B2C / reporting

| Channel | Status |
| --- | --- |
| B2G | Structured e-invoices since 2019; Fina + Peppol for cross-border suppliers. |
| B2B | **Live 2026-01-01** for established / fixed-establishment businesses (domestic). |
| 2027 | Extends issuance/reporting toward non-VAT entities and public bodies as issuers. |
| Reporting | Issuer **and** recipient e-report the invoice. |

## Technical shape

| Item | Detail |
| --- | --- |
| Operator | **Fina** (financial agency) e-Account / Peppol AP |
| Tax | Porezna uprava |
| Model | Fiscalisation + structured invoice + dual-sided reporting |

## Official sources

- Porezna uprava: [porezna-uprava.hr](https://www.porezna-uprava.hr/)
- Fina: [fina.hr](https://www.fina.hr/)
- Commission factsheet: [eInvoicing in Croatia](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108879/eInvoicing+in+Croatia)

## Fit to our adapter strategy

`HR_ERACUN` sits between **Spain SIF** (fiscalisation mindset) and **Belgium Peppol** (structured exchange). Reporting by **both** parties is a product requirement if we ever issue Croatian invoices.

## Caveats

- Non-established VAT IDs are generally out of the 2026 B2B issue duty — confirm on Porezna pages.
