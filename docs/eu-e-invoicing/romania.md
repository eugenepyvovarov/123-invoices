# Romania

ISO: `RO` · Research date: 2026-07-24.

## Mandatory status (as of 2026-08-11)

| Obligation | Mandatory now? |
| --- | --- |
| B2B RO e-Factura | **Yes** since **2024-01-01** |
| B2G | **Yes** |
| B2C reporting / e-Factura | **Yes** since **2025-01-01** |

**How to integrate:** [shared/romania-efactura.md](shared/romania-efactura.md) (ANAF OAuth + FCTEL REST + CIUS-RO). Related EN mapping only — not Peppol-as-ANAF-replacement.

## Snapshot

Romania runs **RO e-Factura**, a **clearance / central platform** under **ANAF**. General B2B e-invoicing and e-reporting have been mandatory since **January 2024** (high-risk sectors earlier, from July 2022). B2C reporting/e-invoice rules expanded from 2025, with 2026 simplifications (Law 88/2026).

## B2G / B2B / B2C / reporting

| Channel | Status |
| --- | --- |
| B2G | Mandatory since ~2020 via the national platform. |
| B2B | **Live** for domestic transactions, including many foreign VAT-registered parties for **e-reporting**. |
| B2C | Resident issuers: e-report / RO e-Factura duties from 2025; 2026 law eases some B2C admin. |
| Other | **SAF-T** and **e-Transport** are separate obligations. |

## Technical shape

| Item | Detail |
| --- | --- |
| Platform | RO e-Factura (ANAF / Ministry of Finance) |
| Format | UBL 2.1 / RO CIUS (EN 16931 family) |
| Deadline | Typically a short window (often **5 working days**) to send to the platform |
| Tax authority | [ANAF](https://www.anaf.ro/) |

## Official sources

- Ministry of Finance e-Factura: [mfinante.gov.ro e-Factura](https://mfinante.gov.ro/en/web/efactura)
- ANAF: [anaf.ro](https://www.anaf.ro/)
- Commission factsheets hub: [Country Factsheets](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108874/eInvoicing+Country+Factsheets+for+each+Member+State+and+other+countries)

## Fit to our adapter strategy

`RO_EFACTURA` is a **clearance adapter** next to Italy and Poland:

- snapshot → UBL CIUS → ANAF platform → store index/ack
- inbound reception for buyers
- do not mix with SAF-T (periodic file) or e-Transport

## Caveats

- Foreign VAT IDs can be in **reporting** scope even when not “Romanian established”.
- Penalty and B2C rules moved during 2024–2026 — re-read ANAF before coding.
