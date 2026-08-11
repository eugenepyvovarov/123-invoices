# Shared integration: Greece AADE myDATA

Used by: **[Greece](../greece.md)** (CTC). B2B structured invoices also use [Peppol / EN 16931](peppol-en16931.md).

## Mandatory?

**Yes — myDATA reporting** has been live for years (income/expense classifications).  
**Yes — B2B structured e-invoice** from **2026-02-01** (EN 16931 via myDATA, timologio, or certified providers / Peppol).

These are **two integrations**: reporting REST XML to AADE, plus an EN invoice for the counterparty.

## Official developer sources

| Resource | URL |
| --- | --- |
| myDATA home | https://www.aade.gr/mydata |
| Technical specifications / versions | https://www.aade.gr/en/mydata/technical-specifications-versions-mydata |
| ERP REST API PDF v2.0.1 (2026-03) | https://www.aade.gr/sites/default/files/2026-03/myDATA%20API%20Documentation%20v2.0.1_official_erp.pdf |
| Provider REST API PDF v2.0.1 | https://www.aade.gr/sites/default/files/2026-03/myDATA%20API%20Documentation_Providers_v2%200%201_official.pdf |
| Delivery-note / goods movement API v2.0.1 | https://www.aade.gr/sites/default/files/2026-03/myDATA%20API%20Documentation_DeliveryNote_v2.0.1_official.pdf |
| AADE | https://www.aade.gr/ |

The ERP PDF returned **HTTP 403** from this environment (2026-08-11). Download it from the official technical-specifications page when implementing.

## Integration shape (ERP channel)

Official model (ERP documentation family):

- REST over HTTPS
- XML bodies for invoices (`SendInvoices`), classifications, cancel, request docs
- Separate **provider** API if the app is a licensed e-invoicing provider
- Test vs production bases are published inside the PDF (do not hardcode from blogs)

Typical ERP operations described in AADE docs: send invoices, send income/expense classification, cancel invoice, request documents, request income/expense info.

2026 B2B mandate additionally requires the **European invoice standard** on the commercial document and transmission via myDATA / timologio / certified provider.

## App mapping

- `EL_MYDATA` — reporting adapter (like NAV).
- `EL_B2B` — EN 16931 / Peppol or provider channel.

Do not treat myDATA XML as a drop-in Peppol BIS document.
