# Shared integration: Italy SdI / FatturaPA

Used by: **[Italy](../italy.md)** only.

## Mandatory?

**Yes.** B2G since 2014/15; B2B and B2C for Italian established operators since **2019-01-01**. Still live in 2026.

**Local copy:** [`../_vendor/italy-sdi/`](../_vendor/italy-sdi/) — SdI 1.8.4 PDF and FatturaPA XSD 1.2.3. SDICoop instruction PDFs were not at a stable public path; get them from the DocumentazioneSDI index if needed.

## Official developer sources

| Resource | URL |
| --- | --- |
| SdI documentation index (valid from **2026-05-15**) | https://www.fatturapa.gov.it/it/norme-e-regole/DocumentazioneSDI/ |
| Technical specs SdI **v1.8.4** (from 2026-05-15) | https://www.fatturapa.gov.it/export/documenti/Specifiche-tecniche-relative-al-Sistema-di-Interscambio-versione-1.8.4.pdf |
| SDICoop Transmit instructions v3.3 | linked from the DocumentazioneSDI page (PDF) |
| SDICoop Receive instructions v3.3 | linked from the DocumentazioneSDI page (PDF) |
| FatturaPA format index | https://www.fatturapa.gov.it/it/norme-e-regole/documentazione-fattura-elettronica/formato-fatturapa/ |
| Schema FatturaPA **1.2.3** (from 2025-04-01) | https://www.fatturapa.gov.it/export/documenti/fatturapa/v1.4/Schema_VFPA12_V1.2.3.xsd |
| Schema Fattura Ordinaria **1.2.3** | https://www.fatturapa.gov.it/export/documenti/fatturapa/v1.4/Schema_VFPR12_v1.2.3.xsd |
| Agenzia delle Entrate (EN) | https://www.agenziaentrate.gov.it/portale/web/english/electronic-invoicing |
| Test SdI (community) | https://github.com/italia/fatturapa-testsdi |

Direct XSD download from older `/export/fatturazione/sdi/...` paths **404** as of 2026-08-11 — use the **formato-fatturapa** index.

## Channels (official)

| Channel | Role | Protocol |
| --- | --- | --- |
| **PEC** | Send XML as certified email attachment | Simple; not suitable as primary automation |
| **SDICoop** | Automated **SOAP** web service | HTTPS TLS 1.2, SOAP + **MTOM**, WSDL, **client certificates** |
| **SdIFtp** | SFTP batch | Dedicated channel agreement |
| **Fatture e Corrispettivi portal** | Manual / small volume | Web |

SDICoop transmit: one file per call (single invoice, lot, or archive), **max ~5 MB** on the SOAP attachment (PEC allows larger multi-attach up to ~30 MB). Receipt of the SOAP response means **file received**, not invoice accepted.

Receive (buyers / intermediaries): expose a SOAP endpoint; SdI retries up to **4 times / every 6 hours**, then “impossibilità di recapito” and the invoice is left in the authenticated area.

SdI→you communications are XML signed **XAdES-BES** enveloped (ETSI TS 101 903 v1.4.1).

## Document types

| Transmission code | Use |
| --- | --- |
| **FPA12** | Public administration (FatturaPA) |
| **FPR12** | Private counterparties (fattura ordinaria) |

Root header/body include `TipoDocumento`, `Divisa`, `Data`, `Numero`, parties, lines, tax summaries. This is **not** UBL/EN 16931 as the native schema (mapping exists; do not send Peppol BIS as-is to SdI).

## Integration steps

1. Obtain a **qualified certificate** and register an SdI channel (SDICoop service agreement + interoperability tests for receive).
2. Generate XML against the current XSD (1.2.3+).
3. Digitally sign the invoice file as required by the current specs.
4. `SDICoop` transmit → store SdI file id.
5. Process async receipts: scarto, consegna, mancata consegna, esito committente (PA), etc.
6. Inbound: implement receive WSDL or poll the cessionario area.

## App mapping

Clearance adapter `IT_SDI`. `authority_document_id` = SdI identifiers. No hash-chain like Spain SIF. No AES session like KSeF.

Do **not** reuse the KSeF REST client or Peppol AP as a substitute for SdI (Peppol may coexist for some cross-border cases; domestic Italian invoices go through SdI).
