# Local official specs (no nested git)

Downloaded **2026-08-11**. Layout is **folders and files only** — no `.git`, no leftover zips.

If an official site updates a spec, replace the files here and bump this date. Live URLs still win if they disagree.

| Folder | What | Source |
| --- | --- | --- |
| `peppol/peppol-bis-invoice-3/` | Peppol BIS Billing 3.0 (guide, rules, syntax, Schematron) | OpenPEPPOL source snapshot (extracted, no git) |
| `poland-ksef/ksef-api-docs/` | Official integrator scenarios (auth, sessions, UPO, QR) | CIRFMF/ksef-api snapshot (extracted, no git) |
| `poland-ksef/ksef-2-openapi-*.json` | Live OpenAPI 2.6.1 prod + test | `api.ksef.mf.gov.pl` / `api-test.ksef.mf.gov.pl` |
| `spain-sif/` | VERI\*FACTU PDFs + `tikeV1.0` WSDL/XSD | AEAT |
| `italy-sdi/` | SdI specs 1.8.4 PDF + FatturaPA XSD 1.2.3 | fatturapa.gov.it |
| `romania-efactura/` | API PDF, OAuth PDF, Swagger HTML, CIUS-RO 1.0.9, UBL examples | mfinante.gov.ro / ANAF |
| `hungary-nav/Online-Invoice/` | NAV Online Számla interface spec PDFs (latest EN/HU 2026-02-12) | nav-gov-hu snapshot (docs only; sample PDFs dropped) |
| `france-pdp/` | Official AIFE/DGFiP **spécifications externes v3.2** (dossier, XSD, Swagger, annexes) + practical guide | [impots.gouv.fr specs](https://www.impots.gouv.fr/specifications-externes-b2b) |
| `germany-xrechnung/` | XRechnung 3.0.2 spec PDF + KoSIT validator config (XSD/Schematron) release 2026-01-31 | xeinkauf / KoSIT GitHub *release zip* (no git) |
| `spain-crea-y-crece/` | RD 238/2026 BOE PDF + AEAT note | BOE / AEAT |
| `slovakia-2027/` | FS e-invoicing pages + **Solution Architecture PDF** (30 Mar 2026) | financnasprava.sk |

## Not downloaded (blocked or no stable file URL)

| Missing | Why | Get it from |
| --- | --- | --- |
| Greece myDATA ERP/Provider PDFs | `aade.gr` returned HTTP 403 | [AADE technical specs](https://www.aade.gr/en/mydata/technical-specifications-versions-mydata) |
| Italy SDICoop instruction PDFs v3.3 | Direct `/export/documenti/...` 404 | [Documentazione SdI](https://www.fatturapa.gov.it/it/norme-e-regole/DocumentazioneSDI/) |
| Poland FA(3) XSD as a single file | No public direct XSD URL found | [FA(3) page](https://ksef.podatki.gov.pl/ksef-na-okres-obligatoryjny/struktura-logiczna-fa-3/) + schemas under `poland-ksef/ksef-api-docs/faktury/schemy/` |
| France Chorus Pro OpenAPI | Behind PISTE login | [developer.aife.economie.gouv.fr](https://developer.aife.economie.gouv.fr/) |
| NAV XSD tree | Not in the published GitHub `docs/` snapshot we kept | [github.com/nav-gov-hu/Online-Invoice](https://github.com/nav-gov-hu/Online-Invoice) `src/schemas` (download files, do not clone into this repo) |

Human-readable how-to stays in `../shared/`. Those notes now point at these folders.

## Rules for this folder

- Do **not** `git clone` anything under `_vendor/`.
- If you need a GitHub tree: download the zipball, **unzip into a folder**, delete the zip, delete any `.git`.
- Do not commit `.git` directories here.
