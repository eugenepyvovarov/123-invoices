# Shared integration: Romania RO e-Factura (ANAF)

Used by: **[Romania](../romania.md)** only.

## Mandatory?

**Yes.** B2B (+ e-reporting) since **2024-01-01** (high-risk sectors 2022-07). B2G earlier. B2C reporting from **2025-01-01** (B2C upload URL mandatory from **2025-03-31**). Still live in 2026.

**Local copy:** [`../_vendor/romania-efactura/`](../_vendor/romania-efactura/) — API presentation, OAuth procedure, Swagger HTML, CIUS-RO 1.0.9 folder, UBL examples.

## Official developer sources

| Resource | URL |
| --- | --- |
| Technical information index | https://mfinante.gov.ro/en/web/efactura/informatii-tehnice |
| Web services presentation (updated 2025-02-13) | https://mfinante.gov.ro/static/10/eFactura/prezentare%20api%20efactura.pdf |
| API rate limits | https://mfinante.gov.ro/static/10/eFactura/limiteApeluriAPI.txt |
| Swagger: upload | https://mfinante.gov.ro/static/10/eFactura/upload.html |
| Swagger: status | https://mfinante.gov.ro/static/10/eFactura/staremesaj.html |
| Swagger: list messages | https://mfinante.gov.ro/static/10/eFactura/listamesaje.html |
| Swagger: download | https://mfinante.gov.ro/static/10/eFactura/descarcare.html |
| Swagger: validate | https://mfinante.gov.ro/static/10/eFactura/validare.html |
| Swagger: signature check | https://mfinante.gov.ro/static/10/eFactura/validaresemnatura.html |
| Swagger: xml-to-pdf | https://mfinante.gov.ro/static/10/eFactura/xmltopdf.html |
| Schematron CIUS-RO 1.0.9 (from 2024-06-05) | https://mfinante.gov.ro/static/10/eFactura/ro16931-ubl-1.0.9.zip |
| UBL examples | https://mfinante.gov.ro/static/10/eFactura/exemple_Invoice_CreditNote.zip |
| ANAF API registration | https://www.anaf.ro/anaf/internet/ANAF/servicii_online/inreg_api |
| ANAF web services list | https://www.anaf.ro/anaf/internet/ANAF/servicii_online/servicii_web_anaf/ |
| OAuth app registration PDF | https://static.anaf.ro/static/10/Anaf/Informatii_R/API/Oauth_procedura_inregistrare_aplicatii_portal_ANAF.pdf |

HTML/PDF fetches from this environment were **reset/403** on 2026-08-11; open the Ministry/ANAF URLs directly when implementing.

## Auth (official OAuth 2.0 + qualified certificate)

1. Register a developer application on ANAF (`inreg_api`) with service **E-Factura**.
2. User (or technical cert flow) authorizes at:

`https://logincert.anaf.ro/anaf-oauth2/v1/authorize?client_id=…&response_type=code&redirect_uri=…&token_content_type=jwt`

3. Exchange code at ANAF token endpoint → JWT **access** (~90 days) + **refresh** (~365 days).
4. Call APIs with `Authorization: Bearer <access_token>`.

SPV (Spațiul Privat Virtual) is the taxpayer’s inbox/outbox.

## HTTP API (FCTEL)

Commonly documented official bases:

| Env | Upload |
| --- | --- |
| Test | `POST https://api.anaf.ro/test/FCTEL/rest/upload` |
| Prod | `POST https://api.anaf.ro/prod/FCTEL/rest/upload` |

- Body: **UBL 2.1 or CII** XML (`Content-Type: application/xml`).
- Response: `index_incarcare` (upload index).
- Then: status (`staremesaj`) → download ANAF response / validation zip (`descarcare`).
- Separate **B2C** upload URL since 2025-03-31 (see Ministry technical page).

Always re-read the **upload Swagger** for the current query params (`standard=UBL|CII`, B2B vs B2C).

## Document contract

| Item | Value |
| --- | --- |
| Syntax | UBL 2.1 Invoice/CreditNote **or** UN/CEFACT CII |
| CIUS | **CIUS-RO** |
| CustomizationID (typical) | `urn:cen.eu:en16931:2017#compliant#urn:efactura.mfinante.ro:CIUS-RO:1.0.1` |
| Validation | Official Schematron `ro16931-ubl-1.0.9` (+ UBL schemas) |
| Legal send window | Short (often **5 working days**) — confirm current law |

This **is** EN 16931 family, but **not** Peppol-as-transport: you upload to **ANAF**, you do not (only) send via a Peppol AP.

## App mapping

Clearance adapter `RO_EFACTURA`. Store `index_incarcare`, ANAF status, downloaded response zip. Inbound: list/download from SPV. Separate later adapters for **SAF-T** and **e-Transport**.
