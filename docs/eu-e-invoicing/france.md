# France

ISO: `FR` · Research date: 2026-07-24.

## Mandatory status (as of 2026-08-11)

| Obligation | Mandatory now? |
| --- | --- |
| B2G (Chorus Pro) | **Yes** |
| B2B receive | **Pre-live** — **2026-09-01** (**implement now**) |
| B2B issue (large / mid) | **Pre-live** — **2026-09-01** (**implement now**) |
| B2B issue (SME / micro) | **Pre-live** — **2027-09-01** (**implement**) |
| e-reporting | Same calendar as B2B reform |

**How to integrate:** B2G now → [shared/france-chorus-pro.md](shared/france-chorus-pro.md). B2B from Sept 2026 → PDP (same file, second section). Do not use KSeF/SdI clients.

## Snapshot

France is moving from **B2G Chorus Pro** to a domestic **B2B e-invoicing + e-reporting** reform. Invoices between VAT-liable French businesses must travel via **approved partner platforms (PDP)**. Ordinary PDF/email stops being enough.

## B2G / B2B / B2C / reporting

| Channel | Status |
| --- | --- |
| B2G | Mandatory (phased 2017–2020) via **Chorus Pro**. |
| B2B receive | **All** businesses must be able to receive e-invoices from **2026-09-01**. |
| B2B issue | Large and mid-size from **2026-09-01**; SMEs/micro from **2027-09-01**. |
| e-reporting | Transaction data (B2C and some cross-border) to the tax authority on the same calendar, starting with the largest firms. |
| Scope | Issuing duty aimed at **French-established** businesses; non-established VAT-registered parties may still face **e-reporting**. |

## Technical shape

| Item | Detail |
| --- | --- |
| Tax authority | DGFiP / [impots.gouv.fr](https://www.impots.gouv.fr/) |
| B2G | Chorus Pro |
| B2B | Partner Dematerialisation Platforms (PDP); public billing portal remains in the architecture discussion |
| Formats | UBL, CII, Factur-X (EN 16931 family) |

## Official sources

- “Je passe à la facturation électronique”: [impots.gouv.fr professionnel](https://www.impots.gouv.fr/professionnel/je-passe-la-facturation-electronique)
- English explainer: [I want to understand electronic invoicing](https://www.impots.gouv.fr/internationalenbusiness/i-want-understand-electronic-invoicing)
- Service-public entreprises: [Electronic invoicing: it's coming soon](https://entreprendre.service-public.gouv.fr/actualites/A15683?lang=en)
- Commission factsheet: [eInvoicing in France](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108885/eInvoicing+in+France)

## Fit to our adapter strategy

`FR_EINVOICE` is a **platform-mediated exchange + reporting** adapter:

- not AEAT SOAP and not KSeF REST
- submit/receive via a **certified PDP** (or a later public hub)
- e-reporting is a sibling feed from the same snapshot

Build only if a French issuer is in scope. The generic snapshot + submission states still apply (`SUBMITTED_PENDING_AUTHORITY` / platform accepted).

## Caveats

- Calendar has slipped before; confirm impots.gouv.fr before coding.
- Choosing a PDP is an **operations** decision, not just a code format decision.
