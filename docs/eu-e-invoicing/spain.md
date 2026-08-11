# Spain

ISO: `ES` · Research date: 2026-07-24.

## Mandatory status (as of 2026-08-11)

| Obligation | Mandatory now? |
| --- | --- |
| B2G (FACe / Facturae) | **Yes** (since 2015) |
| SIF / VERI\*FACTU | **Pre-live** — **2027-01-01** corporate / **2027-07-01** others (**implement**) |
| Crea y Crece B2B e-invoice | **Pre-live** — working calendar **2027-10-01** (>€8m) / **2028-10-01** others (**implement**, not SIF) |
| SII (in-scope taxpayers) | **Yes** |

**How to integrate:** [shared/spain-sif-aeat.md](shared/spain-sif-aeat.md). FACe is a separate B2G sender. 2027 calendar: [shared/pre-live-2027.md](shared/pre-live-2027.md). Do not use KSeF/Peppol as SIF.

## Snapshot

Spain is a **hybrid** regime and the first adapter for this product.

There are **two different Spanish tracks**:

1. **SIF / VERI\*FACTU** (RD 1007/2023, Orden HAC/1177/2024) — invoicing **software** must keep inalterable fiscal records, hash/chain them, and either remit continuously to AEAT (**VERI\*FACTU**) or preserve locally with XAdES (**NO_VERI\*FACTU**). Deadlines: corporate taxpayers **2027-01-01**, others **2027-07-01**.
2. **Crea y Crece B2B e-invoice** (Law 18/2022) — structured **business-to-business** electronic invoices. The duty is enacted, but the **start clock depends on the pending technical regulation**. Commission factsheets still describe a one- or two-year phase-in after that regulation.

Do not collapse these into one “Spain e-invoice” feature. SIF is a **CTC / software-integrity** adapter. Crea y Crece is a future **exchange** adapter.

## B2G / B2B / B2C / reporting

| Channel | Status |
| --- | --- |
| B2G | Mandatory since 2015 via **FACe** / FACeB2B for public-sector invoices. |
| B2B structured invoice | Approved in law; timetable waits on implementing regulation (often discussed as 2027). |
| B2C | Not the Crea y Crece mandate. SIF still applies to invoicing software used for Spanish issuers. |
| Immediate Supply of Information (**SII**) | Existing VAT books reporting for larger taxpayers — a **reporting** feed, not SIF. |
| SIF / VERI\*FACTU | Per Spanish issuer/establishment. Optional VERI\*FACTU remittance; both modes are SIF. |

## Technical shape

| Item | Detail |
| --- | --- |
| Tax authority | [Agencia Estatal de Administración Tributaria (AEAT)](https://sede.agenciatributaria.gob.es/) |
| SIF records | `RegistroAlta` / `RegistroAnulacion`, SHA-256 hash chain, QR on the invoice |
| VERI\*FACTU transport | AEAT SOAP (`tikeV1.0` WSDL/XSD) |
| NO_VERI\*FACTU | Local preservation + XAdES; AEAT-on-request export |
| B2G format | Facturae via FACe |
| Future B2B | Expected EN 16931-aligned structured formats (regulation pending) |

Repo status: issuer settings foundation is implemented (`IssuerSifSettings`, `docs/sif.md`). Issuance, records, hash, XML, AEAT client are **not** implemented yet (Gitea #149–#158).

## Official sources

- AEAT SIF / VERI\*FACTU portal: [Sistemas Informáticos de Facturación y VERI\*FACTU](https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu.html)
- AEAT technical index: [Información técnica](https://sede.agenciatributaria.gob.es/Sede/iva/sistemas-informaticos-facturacion-verifactu/informacion-tecnica.html)
- [Real Decreto 1007/2023](https://www.boe.es/buscar/act.php?id=BOE-A-2023-24840)
- [Orden HAC/1177/2024](https://www.boe.es/buscar/act.php?id=BOE-A-2024-22138)
- Law 18/2022 (Crea y Crece): [BOE-A-2022-15818](https://www.boe.es/buscar/act.php?id=BOE-A-2022-15818)
- FACe (B2G): [face.gob.es](https://face.gob.es/)
- Commission factsheet: [eInvoicing in Spain](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108901/eInvoicing+in+Spain)
- In-repo: [Spanish SIF foundation](../sif.md)

## Fit to our adapter strategy

| Proposed code | Role |
| --- | --- |
| `ES_SIF` | First `FiscalRegimeAdapter`. Issue/freeze/hash/XML/AEAT or XAdES. |
| `ES_SII` | Optional later **reporting** adapter for taxpayers already in SII. |
| `ES_B2B` | Crea y Crece / SPFE — **pre-live 2027-10**. RD 238/2026 is local in `_vendor/spain-crea-y-crece/`. Do not code the AEAT public platform client until the ministerial order + XSD/OpenAPI exist. |

Spain confirms: **do not put AEAT fields on `Invoice`**. Keep a mutable invoice row and an append-only fiscal registration.

## Caveats

- VERI\*FACTU is **optional**. The app must support **NO_VERI\*FACTU**.
- Applicability is **issuer tax country = ES**, not customer country.
- QR / “Factura verificable…” wording applies only when SIF (and VERI\*FACTU wording only when actually in that mode).
