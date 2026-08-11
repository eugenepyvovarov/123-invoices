# Denmark

ISO: `DK` · Research date: 2026-07-24.

## Mandatory status (as of 2026-08-11)

| Obligation | Mandatory now? |
| --- | --- |
| B2G issue (NemHandel / Peppol) | **Yes** (since 2005) |
| B2B e-invoice | **No** |
| Bookkeeping systems must *support* e-invoices | **Yes** (digital bookkeeping act, in-scope entities) |

**How to integrate:** [shared/peppol-en16931.md](shared/peppol-en16931.md) + [NemHandel](https://nemhandel.dk/). No SKAT clearance API.

## Snapshot

Denmark pioneered **B2G** e-invoicing (since 2005) via **NemHandel** (now Peppol-aligned). There is **no general B2B e-invoice mandate**. Digital bookkeeping law requires in-scope systems to be **able** to issue, receive, and store e-invoices.

## B2G / B2B / B2C / reporting

| Channel | Status |
| --- | --- |
| B2G | Mandatory for suppliers to public authorities (UBL / NemHandel). |
| B2B | Voluntary; bookkeeping systems must support e-invoices. |
| B2C | No mandate. |

## Official sources

- NemHandel: [nemhandel.dk](https://nemhandel.dk/)
- Danish Business Authority / Erhvervsstyrelsen: [erhvervsstyrelsen.dk](https://erhvervsstyrelsen.dk/)
- SKAT: [skat.dk](https://skat.dk/)
- Factsheets hub: [Country Factsheets](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108874/eInvoicing+Country+Factsheets+for+each+Member+State+and+other+countries)

## Fit to our adapter strategy

Optional **Peppol/NemHandel B2G** send. No tax-clearance adapter. Digital bookkeeping “capability” is a product checkbox, not an AEAT-like client.

## Caveats

Bookkeeping-act scope (turnover thresholds) is separate from VAT e-invoice law.
