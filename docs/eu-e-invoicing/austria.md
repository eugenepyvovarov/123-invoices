# Austria

ISO: `AT` · Research date: 2026-07-24.

## Mandatory status (as of 2026-08-11)

| Obligation | Mandatory now? |
| --- | --- |
| B2G issue (federal) | **Yes** |
| B2B structured e-invoice | **No** (voluntary) |
| Tax-authority API / CTC | **No** |

**How to integrate:** [shared/peppol-en16931.md](shared/peppol-en16931.md) (federal eRechnung / Peppol). No national tax REST API.

## Snapshot

Austria has mature **B2G** e-invoicing to the federal government (**eRechnung.gv.at** / Peppol). **B2B is voluntary**. No general tax-clearance or SIF-style software law.

## B2G / B2B / B2C / reporting

| Channel | Status |
| --- | --- |
| B2G | Mandatory for suppliers to **federal** agencies since 2014 (including many foreign PE suppliers “to the extent technically possible”). |
| B2B | Allowed, not mandated. |
| B2C | No mandate. |

## Technical shape

EN 16931 via the federal e-invoice portal / Peppol. Länder and other public bodies may differ.

## Official sources

- Federal e-invoice: [erechnung.gv.at](https://www.erechnung.gv.at/)
- Federal Ministry of Finance: [bmf.gv.at](https://www.bmf.gv.at/)
- Factsheets hub: [Country Factsheets](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108874/eInvoicing+Country+Factsheets+for+each+Member+State+and+other+countries)

## Fit to our adapter strategy

No dedicated tax adapter. Optional later **Peppol B2G** send if an issuer invoices Austrian federal bodies. ViDA 2030 is the likely B2B driver.

## Caveats

Federal vs state buyers are not the same obligation.
