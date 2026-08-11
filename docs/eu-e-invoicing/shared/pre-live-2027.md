# Pre-live 2027 (treat as in-scope)

Research date: 2026-08-11.

These regimes are **not fully live for every taxpayer today**, but they have a **2026–2027 hard date** (or a dated draft that is the working calendar). For this product they count as **pre-live: design and implement**, not “wait until 2030”.

ViDA intra-EU (1 July **2030**) is **out of this list** — EU floor, not a 2027 national go-live.

## What “pre-live” means here

| Label | Meaning |
| --- | --- |
| **Live** | Duty already applies to the main population |
| **Pre-live** | Dated 2026–2027 (or remaining 2027 tranche of a live system). Implement now. |
| **Watch** | 2028+ or only a proposal without a stable date |

## 2027 (and late-2026) pre-live register

| When | Country | What becomes mandatory | Adapter | Spec we already have |
| --- | --- | --- | --- | --- |
| **2026-09-01** | France | All must **receive** B2B e-invoices; large/mid **issue**; e-reporting starts for largest | `FR_PDP` (+ existing `FR_CHORUS` B2G) | [france-chorus-pro.md](france-chorus-pro.md) |
| **2027-01-01** | Spain | **SIF / VERI\*FACTU** for **corporate / SL** issuers | `ES_SIF` | [spain-sif-aeat.md](spain-sif-aeat.md), [../sif.md](../../sif.md), `_vendor/spain-sif/` |
| **2027-01-01** | Germany | B2B **issue** for turnover **> EUR 800,000** (receive already live since 2025) | `DE_EN16931` | [germany-xrechnung.md](germany-xrechnung.md), [peppol-en16931.md](peppol-en16931.md) |
| **2027-01-01** | Poland | Remaining **smallest sellers** (≤ PLN 10k/month) must use KSeF (system already live) | `PL_KSEF` | [ksef-2.md](ksef-2.md) |
| **2027-01-01** | Croatia | Fiscalisation 2.0 **widens** (non-VAT entities / public bodies as issuers) | same HR/Peppol + Fina | [peppol-en16931.md](peppol-en16931.md), [../croatia.md](../croatia.md) |
| **2027-07-01** | Spain | **SIF / VERI\*FACTU** for **autónomo / other** covered issuers | `ES_SIF` | same as Spain SIF |
| **2027-09-01** | France | SMEs / micro **issue** B2B e-invoices | `FR_PDP` | [france-chorus-pro.md](france-chorus-pro.md) |
| **2027-10-01** (working calendar) | Spain | **Crea y Crece** B2B e-invoice for turnover **> EUR 8m** (SMEs often **2028-10-01**) | `ES_B2B` / SPFE — **separate from SIF** | [../spain.md](../spain.md); law in `_vendor/spain-crea-y-crece/`; **SPFE API/XSD still await the ministerial order** |
| **2027** (planned) | Estonia | General **B2B** e-invoice | Peppol | [peppol-en16931.md](peppol-en16931.md), [../estonia.md](../estonia.md) |
| **2027** (planned / proposed) | Slovakia | B2B e-invoice / CTC-style | TBD | [../slovakia.md](../slovakia.md) — wait for act before coding |
| **2027-01** (proposal) | Slovenia | B2B e-invoice + e-reporting | Peppol / e-SLOG | [../slovenia.md](../slovenia.md) — wait for enacted law |

## Implementation rule for this app

Treat as **must implement** (same bar as live):

1. **`ES_SIF`** — 2027-01 / 2027-07. Already the current epic (#148–#158).  
2. **`FR_PDP`** — receive wall is **2026-09-01** (weeks away). B2G Chorus is already live.  
3. **`DE_EN16931` issue path** — receive is live; **issue** for larger DE taxpayers is **2027-01-01**. Same XRechnung/Peppol writer.  
4. **`PL_KSEF`** — already live; 2027 is only the last SME tranche.  
5. **`ES_B2B` (Crea y Crece / SPFE)** — pre-live **2027-10-01** for large issuers. **Do not merge with SIF.** Different ministry/platform. Start after SIF issuance exists, but keep the generic snapshot/submission spine so SPFE can plug in.

Treat as **watch, do not schedule a dedicated adapter yet**:

- Estonia / Slovakia / Slovenia 2027 — reuse Peppol if the law lands; no unique API today.  
- Croatia 2027 widen — same Fina/Peppol stack as 2026.  
- Latvia B2B **2028**, Hungary broader e-invoice **~2028**, Belgium reporting **~2028**.  
- ViDA **2030**.

## Spain: two 2027 clocks (do not confuse)

| Clock | Law | Job | Date |
| --- | --- | --- | --- |
| SIF / VERI\*FACTU | RD 1007/2023 | Software integrity + AEAT record/remittance | 2027-01-01 SL / 2027-07-01 others |
| Crea y Crece B2B | Law 18/2022 + RD 238/2026 + ministerial order | Structured **exchange** between companies (public SPFE / private platforms) | Working calendar **2027-10-01** (>€8m), **2028-10-01** others |

Both are pre-live. **SIF is first** for this repo (issuers already on the app). Crea y Crece is the second Spanish adapter.

## France 2026–27 (pre-live, almost live)

| Date | Who | Duty |
| --- | --- | --- |
| 2026-09-01 | Everyone | **Receive** structured B2B |
| 2026-09-01 | Large + mid-size | **Issue** + e-reporting (largest) |
| 2027-09-01 | SME / micro | **Issue** |

Integration is PDP, not Chorus Pro, for B2B. See [france-chorus-pro.md](france-chorus-pro.md).

## Germany 2027–28

| Date | Who | Duty |
| --- | --- | --- |
| 2025-01-01 | All | **Receive** e-invoice (already live) |
| **2027-01-01** | Turnover > EUR 800k | **Issue** XRechnung / ZUGFeRD / Peppol |
| 2028-01-01 | Remaining issuers | **Issue** |

No tax-clearance API. Same files as live receive.

## Official starting points + local packs

- Spain SIF: [`../_vendor/spain-sif/`](../_vendor/spain-sif/)
- Spain Crea y Crece: [`../_vendor/spain-crea-y-crece/`](../_vendor/spain-crea-y-crece/) (RD 238/2026 + AEAT note). SPFE OpenAPI **not published** until the ministerial order is final.
- France PDP/B2B: [`../_vendor/france-pdp/`](../_vendor/france-pdp/) (specs v3.2 + XSD + Swagger)
- Germany XRechnung: [`../_vendor/germany-xrechnung/`](../_vendor/germany-xrechnung/)
- Poland KSeF: [`../_vendor/poland-ksef/`](../_vendor/poland-ksef/)
- Slovakia 2027: [`../_vendor/slovakia-2027/`](../_vendor/slovakia-2027/) (authority page; no API pack yet)
- Peppol (HR/EE/SI): [`../_vendor/peppol/`](../_vendor/peppol/)

## Implementation-readiness check (2026-08-11)

| Pre-live item | How-to note | Local technical pack | Ready to implement? |
| --- | --- | --- | --- |
| Spain SIF 2027-01/07 | [spain-sif-aeat.md](spain-sif-aeat.md) | **Yes** WSDL/XSD/PDFs | **Yes** (product epic #149–#158) |
| France B2B/PDP 2026-09 / 2027-09 | this file + [france-chorus-pro.md](france-chorus-pro.md) | **Yes** official v3.2 dossier/XSD/Swagger | **Yes for formats + directory + e-reporting.** Still need to pick **one accredited PDP** and use *its* send/receive API (not in the state zip). |
| Germany issue 2027-01 | [germany-xrechnung.md](germany-xrechnung.md) | **Yes** spec + Schematron 3.0.2 | **Yes** (same as live receive; add issue writer + Peppol/AP) |
| Poland KSeF last tranche 2027-01 | [ksef-2.md](ksef-2.md) | **Yes** OpenAPI + integrator docs | **Yes** (already the live adapter) |
| Croatia 2027 widen | [peppol-en16931.md](peppol-en16931.md) | **Yes** Peppol BIS | **Yes** for structured invoice; Fina extras if they publish more |
| Spain Crea y Crece / SPFE 2027-10 | [../spain.md](../spain.md) | **Law + AEAT note only** | **Not yet** — no final SPFE WSDL/XSD/OpenAPI in `_vendor`. Cannot code the public platform client until the ministerial order + AEAT technical pack land. Spine (`FiscalSnapshot` / submission) can be ready. |
| Slovakia 2027-01 | [../slovakia.md](../slovakia.md) | Authority HTML only | **Partial** — law/date firm (EN 16931 + reporting). **No official API/XSD pack** downloaded. Use Peppol/EN until FS publishes the 5-corner / digital-postman API. |
| Estonia ~2027 | Peppol | Peppol pack | **Watch** — reuse Peppol when the act is final |
| Slovenia ~2027 proposal | Peppol | Peppol pack | **Watch** — not enacted as a hard unique API |

**Verdict:** we now have **implementation-grade local specs** for SIF, France v3.2, XRechnung, KSeF, and Peppol. We do **not** yet have everything for **Spain SPFE** or **Slovakia’s reporting API**. Those two cannot be fully coded against a frozen official interface today.
