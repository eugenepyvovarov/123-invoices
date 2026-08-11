# Poland

ISO: `PL` · Research date: 2026-07-24.

## Mandatory status (as of 2026-08-11)

| Obligation | Mandatory now? |
| --- | --- |
| B2B issue via KSeF (large, then all VAT except tiniest) | **Yes** (2026-02-01 / 2026-04-01) |
| B2B receive via KSeF | **Yes** since **2026-02-01** |
| Smallest sellers (≤ PLN 10k/month) | **Pre-live** — **2027-01-01** (KSeF already built) |
| B2C | **No** (voluntary) |

**How to integrate:** [shared/ksef-2.md](shared/ksef-2.md). Official OpenAPI snapshot: [`_vendor/ksef-2-openapi-prod.json`](_vendor/ksef-2-openapi-prod.json).

## Snapshot

Poland’s **Krajowy System e-Faktur (KSeF)** is a **government clearance platform**. For in-scope domestic B2B, the legal invoice is a structured **FA(3)** XML accepted by KSeF, which returns a **KSeF number** and **UPO** (official acknowledgement).

This is the best **second-country stress test** for the multi-regime design: same `issue_invoice` spine as Spain, completely different payload and transport.

## B2G / B2B / B2C / reporting

| Channel | Status |
| --- | --- |
| B2B issue | Phased mandate: large taxpayers from **2026-02-01**; remaining VAT businesses from **2026-04-01**; smallest sellers (≤ PLN 10k monthly invoiced) until **2026-12-31**, then **2027-01-01**. |
| B2B receive | VAT-registered entities required to receive KSeF invoices from **2026-02-01**. |
| B2C | Not mandatory; voluntary KSeF possible. |
| B2G | Historically **PEF**; from 2026 KSeF integrates / sits beside PEF for public procurement. |
| Penalties | Grace through 2026; enforcement from **2027-01-01**. |

Foreign entities **without** a Polish fixed establishment are generally out of the issue mandate.

## Technical shape

| Item | Detail |
| --- | --- |
| Platform | KSeF 2.0 |
| Format | **FA(3)** logical structure (replaced FA(2)) |
| API | REST, OpenAPI 3 — [api.ksef.mf.gov.pl](https://api.ksef.mf.gov.pl) |
| Auth | KSeF certificates / seals; legacy tokens expire **2026-12-31** |
| Success | KSeF number + UPO |
| Corrections | Corrective FA(3) referencing the original |
| Fallback | Offline24, announced unavailability, emergency, total failure |
| Offline | Local issue + later upload (often next business day for Offline24) + offline QR/cert |

## Official sources

- KSeF home: [ksef.mf.gov.pl](https://ksef.mf.gov.pl/)
- Ministry tax portal: [podatki.gov.pl/ksef](https://www.podatki.gov.pl/ksef/)
- Gov.pl programme page: [Krajowy System e-Faktur](https://www.gov.pl/web/finanse/krajowy-system-e-faktur-ksef-coraz-blizej-przygotuj-swoja-firme-do-e-fakturowania)
- Commission factsheet: [eInvoicing in Poland](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108896/eInvoicing+in+Poland)

## Fit to our adapter strategy

`PL_KSEF` should be a **clearance adapter**:

- `build_registration` → FA(3) XML in `FiscalRegistration.payload`
- `enqueue_or_submit` → KSeF REST session
- store `authority_document_id` = KSeF number and UPO blob
- operating modes: `ONLINE | OFFLINE24 | UNAVAILABILITY | EMERGENCY` (not Spain’s VERI / NO_VERI)
- optional later: **inbound pull** of supplier invoices (already a live obligation in Poland)

**Do not** reuse Spanish hash-chain columns as required fields. Integrity is platform validation + UPO.

## Caveats

- Legal “issued” in online mode is tightly tied to **KSeF acceptance**, unlike Spanish local issue + later remittance.
- Foreign buyers cannot always pull from KSeF — dual delivery may be required.
- Commission factsheets written before/during rollout can lag the live 2026 phases; prefer ksef.mf.gov.pl for dates.
