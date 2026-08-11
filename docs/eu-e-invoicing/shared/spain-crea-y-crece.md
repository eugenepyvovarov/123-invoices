# Shared integration: Spain Crea y Crece / SPFE (pre-live 2027-10)

Used by: **[Spain](../spain.md)**. **Not** SIF — see [spain-sif-aeat.md](spain-sif-aeat.md).

## Mandatory?

**Pre-live.** RD 238/2026 is in force as regulation; **application** follows the ministerial order (working calendar **2027-10-01** >€8m, **2028-10-01** others).

## Official sources (local)

| Resource | Path |
| --- | --- |
| RD 238/2026 (BOE PDF) | [`../_vendor/spain-crea-y-crece/BOE-A-2026-7295-RD-238-2026.pdf`](../_vendor/spain-crea-y-crece/BOE-A-2026-7295-RD-238-2026.pdf) |
| Consolidated HTML | [`../_vendor/spain-crea-y-crece/BOE-A-2026-7295.html`](../_vendor/spain-crea-y-crece/BOE-A-2026-7295.html) |
| AEAT note | [`../_vendor/spain-crea-y-crece/AEAT-Nota_informativa_RD_Facturacion.pdf`](../_vendor/spain-crea-y-crece/AEAT-Nota_informativa_RD_Facturacion.pdf) |
| BOE | https://www.boe.es/buscar/act.php?id=BOE-A-2026-7295 |

**Not local (not at a stable public file URL):** proyecto de Orden Ministerial SPFE, annex I/II (invoice + status messages), UBL profile, private-platform interconnection spec.

## What the decree already fixes

- Exchange via **private platforms** and/or the **AEAT public solution (SPFE)**.
- Public solution syntax: **UBL**.
- AEAT must publish remaining **technical** elements in the ministerial order: auth, payment-status service, unique e-invoice codes, SPFE↔private platform messaging.

## Ready to implement?

**Legal/calendar:** yes. **SPFE client:** **no** until Hacienda/AEAT publish XSD/OpenAPI. Prepare only the generic `FiscalSnapshot` / submission states from the SIF issuance work.
