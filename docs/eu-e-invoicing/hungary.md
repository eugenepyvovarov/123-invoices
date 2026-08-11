# Hungary

ISO: `HU` · Research date: 2026-07-24.

## Mandatory status (as of 2026-08-11)

| Obligation | Mandatory now? |
| --- | --- |
| NAV Online Számla (RTIR) | **Yes** |
| General B2B e-invoice | **No** (energy sector e-invoice yes since 2025-07) |
| B2G issue | **No** (receive only) |

**How to integrate:** [shared/hungary-nav.md](shared/hungary-nav.md). Official OpenAPI-equivalent is NAV XSD 3.0 on GitHub, not REST OpenAPI.

## Snapshot

Hungary’s core duty is **real-time invoice reporting** to **NAV Online Számla** (RTIR), not a general B2B structured-invoice mandate. Electricity/gas wholesale got a sector e-invoice duty from July 2025. Broader EN 16931 B2B e-invoicing has been discussed for **~2028**.

## B2G / B2B / B2C / reporting

| Channel | Status |
| --- | --- |
| B2G | Public bodies must **accept** EN invoices; no general supplier mandate. |
| B2B e-invoice | No general mandate (energy sector exception). |
| RTIR | **Live**: invoice data (B2B/B2C and more) to NAV shortly after issue. |
| Future | NAV communications about phased domestic e-invoicing from 2028. |

## Technical shape

| Item | Detail |
| --- | --- |
| Portal | [NAV Online Számla](https://onlineszamla.nav.gov.hu/home) |
| Transport | NAV XML / API |
| Authority | National Tax and Customs Administration (NAV) |

## Official sources

- NAV Online Számla: [onlineszamla.nav.gov.hu](https://onlineszamla.nav.gov.hu/home)
- NAV: [nav.gov.hu](https://nav.gov.hu/)
- Factsheets hub: [Country Factsheets](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108874/eInvoicing+Country+Factsheets+for+each+Member+State+and+other+countries)

## Fit to our adapter strategy

`HU_NAV` is a **reporting adapter** (like Spain SII / Greece myDATA):

- fire XML from `FiscalSnapshot` after issue
- do **not** wait for NAV to “clear” the commercial invoice
- keep invoice numbering/PDF in the core product

## Caveats

- RTIR validation rules change often; treat NAV XSD as the contract.
- Energy-sector e-invoice is not a reason to build a full Hungarian clearance client.
