# Greece

ISO: `EL` · Research date: 2026-07-24.

## Mandatory status (as of 2026-08-11)

| Obligation | Mandatory now? |
| --- | --- |
| myDATA reporting | **Yes** |
| B2G e-invoice | **Yes** (phased; some low-value exclusions) |
| B2B structured e-invoice | **Yes** since **2026-02-01** |

**How to integrate:** [shared/greece-mydata.md](shared/greece-mydata.md) + [shared/peppol-en16931.md](shared/peppol-en16931.md).

## Snapshot

Greece combines **myDATA** real-time digital books with a **B2B structured e-invoice** mandate (from **2026-02-01**) using EN 16931, via myDATA, the **timologio** app, or certified providers / Peppol.

## B2G / B2B / B2C / reporting

| Channel | Status |
| --- | --- |
| B2G | Phased 2023–2025 for general government; low-value (often ≤ EUR 2,500) and some defence contracts excluded. |
| B2B | Mandate approved; **effective 2026-02-01** for established entities (Peppol-like exchange plus myDATA). |
| myDATA | Ongoing **CTC**: income/expense documents reported to AADE. |
| B2C | myDATA reporting still relevant; not the same as B2B e-invoice. |

## Technical shape

| Item | Detail |
| --- | --- |
| Tax authority | Independent Authority for Public Revenue (**AADE**) |
| CTC | **myDATA** |
| E-invoice | EN 16931 / Peppol; timologio; providers |
| National Customs Code (Jul 2025) | Ties B2B invoices to EN 16931 + myDATA/providers |

## Official sources

- AADE: [aade.gr](https://www.aade.gr/)
- myDATA (AADE services — follow current myDATA entry on aade.gr)
- Commission factsheets hub: [Country Factsheets](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108874/eInvoicing+Country+Factsheets+for+each+Member+State+and+other+countries)

## Fit to our adapter strategy

Two adapters if ever needed:

- `EL_MYDATA` — reporting from snapshot (like Hungary NAV / Spain SII)
- `EL_B2B` — structured EN invoice + provider/Peppol

Do not treat myDATA XML as the commercial invoice format.

## Caveats

- myDATA existed **before** the 2026 B2B mandate; implementations must not drop reporting when adding e-invoice.
