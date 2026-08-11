# EU e-invoicing and tax-authority reporting

Research date: 2026-07-24; mandatory-status and API notes refreshed **2026-08-11**.

This folder maps **how EU member states require invoicing software to talk to tax authorities or structured-invoice networks**. It is a product-planning source for the invoices app’s multi-regime fiscal strategy (Spain SIF first; other countries as later adapters).

It is **not legal advice**. National rules change quickly. Prefer the official links on each country page before implementing.

## What this is (and is not)

European rules mix several different jobs:

| Job | Meaning | Example |
| --- | --- | --- |
| **B2G e-invoicing** | Structured invoice to a public buyer | Almost all EU states after Directive 2014/55/EU |
| **B2B e-invoicing** | Structured invoice between businesses | Italy SdI, Poland KSeF, Belgium Peppol, France 2026–27 |
| **Clearance** | Authority/platform must accept the invoice (or a registration) before or as it becomes legal | Italy, Poland, Romania |
| **Continuous transaction control (CTC) / real-time reporting** | Invoice *data* is sent to the tax authority, even if the commercial invoice is separate | Hungary NAV, Spain SII, Greece myDATA, Spain SIF/VERI*FACTU |
| **Certified invoicing software** | Software must be certified and/or produce QR/codes/SAF-T | Portugal ATCUD, Spain SIF, Croatia fiscalisation |
| **Peppol / EN 16931 exchange** | Interoperable structured invoices over a network, often without a tax-clearance step | Belgium, Germany, Nordics, Baltics |

Spain’s **SIF / VERI\*FACTU** is mainly a **software-integrity + fiscal-record** regime (with optional continuous AEAT remittance). Poland’s **KSeF** is a **clearance e-invoice** platform. Both hang off the same product spine (`issue_invoice` → snapshot → registration → submission), but they are different adapters.

## EU-wide legal frame

### Directive 2014/55/EU (B2G)

Since April 2020, public administrations must be able to **receive** electronic invoices that comply with the European standard **EN 16931** for contracts above EU public-procurement thresholds.

- Legal text: [Directive 2014/55/EU](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32014L0055)
- Standard: [CEN EN 16931](https://ec.europa.eu/digital-building-blocks/sites/display/DIGITAL/EN+16931+compliance+eInvoicing)
- Commission country factsheets (2025/2026, includes B2B sections): [eInvoicing Country Factsheets](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108874/eInvoicing+Country+Factsheets+for+each+Member+State+and+other+countries)

### VAT in the Digital Age (ViDA)

ViDA was adopted on 11 March 2025 and published in the Official Journal on 25 March 2025.

Official overview: [VAT in the Digital Age (ViDA)](https://taxation-customs.ec.europa.eu/taxation/vat/vat-digital-age-vida_en)

| Date | Effect |
| --- | --- |
| 14 April 2025 (entry into force) | Member States may introduce **mandatory e-invoicing** under EU conditions (the old “buyer consent” barrier is gone). |
| 1 January 2027 | Smaller OSS/IOSS clarifications. |
| 1 July 2028 | Platform “deemed supplier” rules (can be delayed to 2030); Single VAT Registration elements. |
| **1 July 2030** | **Intra-EU B2B e-invoicing + digital reporting (DRR)** for cross-border supplies. |
| **1 January 2035** | Domestic real-time reporting systems must **align with the EU model**. |

So: **2030 is the EU floor for cross-border B2B**. Many states already go further on **domestic** B2B or CTC. Those national systems are what this folder documents.

### Peppol

[OpenPeppol](https://peppol.org/) is the usual cross-border **transport** for EN 16931 invoices. Several states (Belgium, Nordics, Baltics, Netherlands, Luxembourg) use Peppol as the national B2G or B2B rail. Peppol is **not** a tax authority. In our architecture it is a **transport adapter**, reusable by more than one country.

## How this maps to the invoices app

Recommended shape (see the SIF design discussion):

```text
issue_invoice()
  → FiscalSnapshot
  → for each applicable FiscalRegimeAdapter:
       build registration → integrity → artifacts → submit/queue
```

| Adapter class | Typical countries | What the adapter owns |
| --- | --- | --- |
| **SIF / certified software** | Spain (SIF), Portugal (ATCUD/QR), Croatia (fiscalisation) | Local integrity, codes, optional remittance |
| **Clearance platform** | Italy, Poland, Romania | XML schema + authority session + acceptance id |
| **Peppol / EN exchange** | Belgium, Germany, Nordics, Baltics | Access point, BIS Billing, no tax-clearance loop |
| **Real-time reporting** | Hungary NAV, Greece myDATA, Spain SII | Parallel data feed, not a replacement invoice |
| **B2G only** | Most remaining states | Optional later; not a product priority |

**Build now:** Spain SIF (`ES_SIF`).  
**Pre-live 2027 (also implement):** France PDP, Germany issue, Spain Crea y Crece, remaining PL KSeF tranche — see [shared/pre-live-2027.md](shared/pre-live-2027.md).  
**Best second live stress-test:** Poland KSeF (`PL_KSEF`).  
**Do not** put AEAT SOAP fields or KSeF FA(3) columns on `Invoice`.

## Is it mandatory *today*?

Read the **Mandatory status** table at the top of each country page. Summary:

| Already mandatory (do not treat as “future”) | **Pre-live 2026–27 (implement)** | Watch later |
| --- | --- | --- |
| **B2B structured invoice live:** Belgium, Croatia, Greece, Italy, Poland (most VAT issuers), Romania | **France** B2B receive/issue 2026-09 / SME 2027-09; **Germany** issue 2027-01; **Spain SIF** 2027-01/07; **Spain Crea y Crece** ~2027-10; **PL** last KSeF tranche 2027-01; **HR** 2027 widen | EE/SK/SI 2027 *plans*; LV/HU ~2028; ViDA 2030 |
| **B2B *receive* live:** also Germany (2025) | |
| **Tax feed live without full e-invoice:** Hungary NAV, Spain SII (in-scope), Greece myDATA, Portugal ATCUD/QR/SAF-T | |
| **B2G issue live:** most of the EU (Peppol / national portal) | BG, CY, CZ, IE, MT (receive-only); SK weak |

## Shared integration specs (do not copy per country)

Same rail → **one file**, countries only link to it.

| Shared file | What it is | Official contract | Countries |
| --- | --- | --- | --- |
| [shared/peppol-en16931.md](shared/peppol-en16931.md) | Peppol AP + EN 16931 / BIS Billing 3.0 | [docs.peppol.eu](https://docs.peppol.eu/poacc/billing/3.0/) | AT, BE, HR, DK, EE, FI, DE (plus XRechnung), EL (plus myDATA), LV, LT, LU, NL, SI, SE, PT B2G |
| [shared/ksef-2.md](shared/ksef-2.md) | Poland KSeF 2 REST | Downloaded OpenAPI in [`_vendor/`](_vendor/README.md) | PL only |
| [shared/italy-sdi.md](shared/italy-sdi.md) | SdI SOAP / FatturaPA XSD | [fatturapa.gov.it DocumentazioneSDI](https://www.fatturapa.gov.it/it/norme-e-regole/DocumentazioneSDI/) | IT only |
| [shared/romania-efactura.md](shared/romania-efactura.md) | ANAF OAuth + FCTEL REST + CIUS-RO | [mfinante technical page](https://mfinante.gov.ro/en/web/efactura/informatii-tehnice) | RO only |
| [shared/hungary-nav.md](shared/hungary-nav.md) | NAV Online Számla XSD 3.0 | [nav-gov-hu/Online-Invoice](https://github.com/nav-gov-hu/Online-Invoice) | HU only |
| [shared/greece-mydata.md](shared/greece-mydata.md) | AADE myDATA REST XML | [AADE technical specs](https://www.aade.gr/en/mydata/technical-specifications-versions-mydata) | EL |
| [shared/france-chorus-pro.md](shared/france-chorus-pro.md) | Chorus Pro / PISTE OAuth (B2G) + PDP note | [PISTE / AIFE](https://developer.aife.economie.gouv.fr/) | FR |
| [shared/spain-sif-aeat.md](shared/spain-sif-aeat.md) | SIF SOAP `tikeV1.0` + FACe/SII pointers | [AEAT technical index](https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu/informacion-tecnica.html) | ES |
| [shared/portugal-atcud.md](shared/portugal-atcud.md) | Certified software, ATCUD, QR, SAF-T | Portal das Finanças | PT |
| [shared/germany-xrechnung.md](shared/germany-xrechnung.md) | XRechnung / ZUGFeRD (no tax API) | [e-rechnung-bund.de](https://www.e-rechnung-bund.de/) | DE |
| [shared/pre-live-2027.md](shared/pre-live-2027.md) | Dated 2026–27 duties + readiness check | National calendars + `_vendor` packs | ES, FR, DE, PL, HR, SK, EE/SI |
| [shared/spain-crea-y-crece.md](shared/spain-crea-y-crece.md) | Crea y Crece / SPFE (not SIF) | RD 238/2026 in `_vendor/spain-crea-y-crece/` | ES |
| [shared/slovakia-efaktura.md](shared/slovakia-efaktura.md) | SK Digital Postman / Peppol | Architecture PDF in `_vendor/slovakia-2027/` | SK |

Vendor snapshots actually downloaded (KSeF OpenAPI, NAV README): [`_vendor/README.md`](_vendor/README.md).

## Comparison table (27 EU members)

Status as of 2026-08-11. “B2B structured mandate” means domestic B2B structured e-invoice is **live**, not merely planned.

| Country | ISO | Mandatory *now*? | Integration spec | Detail |
| --- | --- | --- | --- | --- |
| Austria | AT | B2G **yes**; B2B **no** | [Peppol](shared/peppol-en16931.md) | [austria.md](austria.md) |
| Belgium | BE | B2G **yes**; B2B **yes** (2026-01-01) | [Peppol](shared/peppol-en16931.md) | [belgium.md](belgium.md) |
| Bulgaria | BG | Receive only | — | [bulgaria.md](bulgaria.md) |
| Croatia | HR | B2G+B2B **yes** (2026-01-01) | [Peppol](shared/peppol-en16931.md) + Fina | [croatia.md](croatia.md) |
| Cyprus | CY | Receive only | — | [cyprus.md](cyprus.md) |
| Czechia | CZ | Receive only | — | [czechia.md](czechia.md) |
| Denmark | DK | B2G **yes**; B2B **no** | [Peppol](shared/peppol-en16931.md) | [denmark.md](denmark.md) |
| Estonia | EE | B2G **yes**; B2B **pre-live ~2027** | [Peppol](shared/peppol-en16931.md) | [estonia.md](estonia.md) |
| Finland | FI | B2G **yes**; B2B **no** | [Peppol](shared/peppol-en16931.md) | [finland.md](finland.md) |
| France | FR | B2G **yes**; B2B **pre-live 2026-09 / 2027-09** | [Chorus Pro / PDP](shared/france-chorus-pro.md) | [france.md](france.md) |
| Germany | DE | B2G **yes**; B2B receive **yes**; issue **pre-live 2027-01** | [XRechnung](shared/germany-xrechnung.md) + [Peppol](shared/peppol-en16931.md) | [germany.md](germany.md) |
| Greece | EL | myDATA **yes**; B2B **yes** (2026-02-01) | [myDATA](shared/greece-mydata.md) + [Peppol](shared/peppol-en16931.md) | [greece.md](greece.md) |
| Hungary | HU | NAV RTIR **yes**; B2B e-invoice **no** | [NAV](shared/hungary-nav.md) | [hungary.md](hungary.md) |
| Ireland | IE | Receive only | — | [ireland.md](ireland.md) |
| Italy | IT | B2G+B2B+B2C **yes** | [SdI](shared/italy-sdi.md) | [italy.md](italy.md) |
| Latvia | LV | B2G **yes**; B2B **no** | [Peppol](shared/peppol-en16931.md) | [latvia.md](latvia.md) |
| Lithuania | LT | B2G **yes**; B2B **no** | [Peppol](shared/peppol-en16931.md) | [lithuania.md](lithuania.md) |
| Luxembourg | LU | B2G **yes**; B2B **no** | [Peppol](shared/peppol-en16931.md) | [luxembourg.md](luxembourg.md) |
| Malta | MT | Receive only | — | [malta.md](malta.md) |
| Netherlands | NL | B2G central **yes**; B2B **no** | [Peppol](shared/peppol-en16931.md) | [netherlands.md](netherlands.md) |
| Poland | PL | KSeF **yes** (most); last tranche **pre-live 2027-01** | [KSeF 2 OpenAPI](shared/ksef-2.md) | [poland.md](poland.md) |
| Portugal | PT | ATCUD/QR/SAF-T **yes**; B2B clearance **no** | [ATCUD](shared/portugal-atcud.md) | [portugal.md](portugal.md) |
| Romania | RO | RO e-Factura **yes** | [ANAF](shared/romania-efactura.md) | [romania.md](romania.md) |
| Slovakia | SK | eKasa **yes**; B2B **pre-live ~2027 (watch)** | — | [slovakia.md](slovakia.md) |
| Slovenia | SI | B2G **yes**; B2B **pre-live ~2027 (proposal)** | [Peppol](shared/peppol-en16931.md) | [slovenia.md](slovenia.md) |
| Spain | ES | FACe/SII **yes**; SIF + Crea y Crece **pre-live 2027** | [SIF/AEAT](shared/spain-sif-aeat.md) · [2027 list](shared/pre-live-2027.md) | [spain.md](spain.md) |
| Sweden | SE | B2G **yes**; B2B **no** | [Peppol](shared/peppol-en16931.md) | [sweden.md](sweden.md) |

## Priority for this product

1. **Spain SIF (`ES_SIF`)** — pre-live **2027-01 / 2027-07**; epic #148–#158.
2. **France PDP (`FR_PDP`)** — pre-live **2026-09-01** receive (then 2027-09 SME issue).
3. **Germany issue (`DE_EN16931`)** — pre-live **2027-01-01** for >€800k (receive already live).
4. **Spain Crea y Crece (`ES_B2B`)** — pre-live **2027-10-01** large issuers; **not** the same as SIF.
5. **Poland KSeF** — already live; 2027 is only the last small-seller tranche.
6. Live cousins if a customer needs them: Italy SdI, Romania e-Factura, Belgium Peppol.
7. EE/SK/SI 2027: reuse Peppol when the act is final; do not invent APIs yet.

Full calendar: [shared/pre-live-2027.md](shared/pre-live-2027.md).

## Document conventions

Each country page uses the same sections:

1. Snapshot  
2. B2G / B2B / B2C / reporting  
3. Technical shape  
4. Official sources  
5. Fit to our adapter strategy  
6. Open caveats  

Cross-links: [Spanish SIF foundation in this repo](../sif.md). Broader Spanish legal source maps live outside this checkout under `Projects/esp/` (`sif-requirements-2027.md`, `sif-technical-implementation-docs.md`).

## Maintenance

Re-check official factsheets and national tax sites when implementing an adapter. Update the country page and this table in the same change. Do not treat vendor blogs as the source of truth when an official page exists.
