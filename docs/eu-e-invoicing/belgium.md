# Belgium

ISO: `BE` · Research date: 2026-07-24.

## Mandatory status (as of 2026-08-11)

| Obligation | Mandatory now? |
| --- | --- |
| B2G issue | **Yes** |
| B2B structured e-invoice | **Yes** since **2026-01-01** (established / PE) |
| Tax-authority CTC | **No** (reporting discussed ~2028) |

**How to integrate:** [shared/peppol-en16931.md](shared/peppol-en16931.md) only. There is no FPS Finance invoice-clearance API.

## Snapshot

Belgium switched domestic **B2B** to **structured e-invoices over Peppol** from **1 January 2026** for VAT-liable businesses established (or with a PE) in Belgium. This is an **exchange mandate**, not a KSeF-style tax clearance. Real-time tax reporting is discussed for later (often 2028).

## B2G / B2B / B2C / reporting

| Channel | Status |
| --- | --- |
| B2G | Mandatory, phased by region then nationwide contract-value steps (2022–2023). Contracts under EUR 3,000 typically exempt. |
| B2B | **Live since 2026-01-01** for established / PE businesses. Foreign VAT IDs without PE generally out of scope. |
| B2C | Not this mandate. |
| Reporting | Expected later (around 2028), separate from Peppol exchange. |

## Technical shape

| Item | Detail |
| --- | --- |
| Network | **Peppol** BIS Billing / EN 16931 |
| Authority (tax) | FPS Finance — [finance.belgium.be](https://finance.belgium.be/en) |
| B2G / e-invoice info | Regional and federal public-sector Peppol receiving |

## Official sources

- FPS Finance: [finance.belgium.be](https://finance.belgium.be/en)
- Commission factsheet: [eInvoicing in Belgium](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108877/eInvoicing+in+Belgium)
- Peppol: [peppol.org](https://peppol.org/)
- Factsheets hub: [Country Factsheets](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108874/eInvoicing+Country+Factsheets+for+each+Member+State+and+other+countries)

## Fit to our adapter strategy

`BE_PEPPOL` is a **Peppol transport adapter**:

- issue structured EN 16931
- send/receive via an access point
- no AEAT/KSeF client
- a later `BE_REPORTING` adapter if 2028 CTC appears

Reusable Peppol code would also serve LU/NL/Nordics/Baltics B2G.

## Caveats

- Confirm PE vs non-established VAT ID scope on FPS pages before treating a Belgian VAT number as in-mandate.
