# Slovakia

ISO: `SK` · Research date: 2026-07-24.

## Mandatory status (as of 2026-08-11)

| Obligation | Mandatory now? |
| --- | --- |
| eKasa (retail receipts) | **Yes** (not B2B invoices) |
| General B2B e-invoice | **Pre-live 2027-01-01** (VAT Act amendment / Law 385/2025) — implement EN 16931; reporting API still thin |

**How to integrate:** [shared/slovakia-efaktura.md](shared/slovakia-efaktura.md) + [shared/peppol-en16931.md](shared/peppol-en16931.md). Local architecture PDF in `_vendor/slovakia-2027/`.

## Snapshot

No general B2B e-invoice mandate yet. **eKasa** already fiscalises retail receipts. A **B2B e-invoicing / CTC-style** project has been planned toward **2027**. B2G issue is not a full Italian-style mandate.

## Official sources

- Financial Administration: [financnasprava.sk](https://www.financnasprava.sk/)
- Ministry of Finance: [mfsr.sk](https://www.mfsr.sk/)
- Factsheets hub: [Country Factsheets](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108874/eInvoicing+Country+Factsheets+for+each+Member+State+and+other+countries)

## Fit to our adapter strategy

Watch 2027 legislation. Could become a **clearance or reporting** adapter. Do not start from eKasa (retail, not B2B invoices).

## Caveats

Dates have slipped before; require a published act.
