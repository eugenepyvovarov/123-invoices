# Bulgaria

ISO: `BG` · Research date: 2026-07-24.

## Mandatory status (as of 2026-08-11)

| Obligation | Mandatory now? |
| --- | --- |
| B2G receive EN 16931 | **Yes** (Directive 2014/55) |
| B2G / B2B issue | **No** |
| Tax-authority invoice API | **No** |

**How to integrate:** nothing to implement until a law exists. Optional receive-only EN handling via [shared/peppol-en16931.md](shared/peppol-en16931.md) if a public buyer asks.

## Snapshot

No general B2B or B2G **issue** mandate. Public bodies must be able to **receive** EN 16931 invoices (Directive 2014/55). SAF-T and possible future mandates are discussed. ViDA 2030 is the EU floor.

## B2G / B2B / B2C / reporting

| Channel | Status |
| --- | --- |
| B2G | Receive capability; no general supplier mandate. |
| B2B | None. |
| Reporting | SAF-T under development / discussion. |

## Official sources

- National Revenue Agency: [nra.bg](https://nra.bg/)
- Ministry of Finance: [minfin.bg](https://www.minfin.bg/)
- Factsheets hub: [Country Factsheets](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108874/eInvoicing+Country+Factsheets+for+each+Member+State+and+other+countries)
- ViDA: [taxation-customs.ec.europa.eu — ViDA](https://taxation-customs.ec.europa.eu/taxation/vat/vat-digital-age-vida_en)

## Fit to our adapter strategy

No adapter until a law exists. Watch NRA for SAF-T if a Bulgarian issuer appears.

## Caveats

Secondary sources sometimes overstate “plans”; require a published legal act before design work.
