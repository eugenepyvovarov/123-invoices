# Italy

ISO: `IT` · Research date: 2026-07-24.

## Mandatory status (as of 2026-08-11)

| Obligation | Mandatory now? |
| --- | --- |
| B2G via SdI | **Yes** |
| B2B via SdI | **Yes** since **2019-01-01** |
| B2C via SdI | **Yes** (established operators) |

**How to integrate:** [shared/italy-sdi.md](shared/italy-sdi.md) (SOAP SDICoop / FatturaPA XSD). Not Peppol-as-substitute.

## Snapshot

Italy is the EU’s longest-running **clearance** regime. Almost all invoices from Italian established operators go through the **Sistema di Interscambio (SdI)** as **FatturaPA** XML. The tax authority is in the delivery path.

## B2G / B2B / B2C / reporting

| Channel | Status |
| --- | --- |
| B2G | Mandatory since 2014/2015 via SdI / FatturaPA. |
| B2B | Mandatory since **1 January 2019** for established operators. |
| B2C | Also through SdI (customer may receive a copy). |
| Non-established | Generally not forced onto SdI for B2G in the same way; paper/e-invoice options exist for non-Italian operators in some B2G cases. |

## Technical shape

| Item | Detail |
| --- | --- |
| Platform | **SdI** (Exchange System), Agenzia delle Entrate |
| Format | FatturaPA XML (mapped toward EN 16931) |
| Transport | SdI channels (web, SFTP, intermediaries, etc.) |
| Success | SdI identifiers / delivery receipts |
| Corrections | Credit notes / variation invoices through SdI |

## Official sources

- FatturaPA / SdI: [fatturapa.gov.it](https://www.fatturapa.gov.it/)
- Agenzia delle Entrate (EN overview): [Electronic invoicing](https://www.agenziaentrate.gov.it/portale/web/english/electronic-invoicing)
- Agenzia delle Entrate home: [agenziaentrate.gov.it](https://www.agenziaentrate.gov.it/)
- Commission factsheet hub: [eInvoicing Country Factsheets](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108874/eInvoicing+Country+Factsheets+for+each+Member+State+and+other+countries)

## Fit to our adapter strategy

`IT_SDI` is another **clearance adapter**, like `PL_KSEF`:

- freeze snapshot → build FatturaPA → submit SdI → persist receipt ids
- no Spanish-style local hash chain as the legal core
- inbound reception is first-class (buyers receive via SdI)

Do **not** implement until Spain issuance exists. Italy is a strong **third** adapter if a customer needs it.

## Caveats

- FatturaPA is a large, opinionated schema. Keep it entirely inside `fiscal/it_sdi/`.
- B2C through SdI is more aggressive than Poland or Spain SIF.
