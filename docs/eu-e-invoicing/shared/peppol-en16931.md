# Shared integration: Peppol + EN 16931

Used by (B2G and/or B2B): **Austria, Belgium, Croatia (Fina AP), Denmark, Estonia, Finland, Germany (also XRechnung), Greece (also myDATA), Latvia, Lithuania, Luxembourg, Netherlands, Slovenia, Sweden**.  
Country pages link here instead of duplicating the network contract.

This is **not** a tax-authority API. You do **not** call a ministry REST endpoint. You become (or use) a **Peppol Access Point** and exchange EN 16931 documents.

## When it is mandatory

See each country page. Common pattern:

- **B2G receive** is an EU duty (Directive 2014/55) almost everywhere.
- **B2G issue** is mandatory in many states (AT federal, BE, DK, EE, FI, DE, HR, LV, LT, LU, NL central, SI, SE, …).
- **B2B issue/receive over Peppol** is already mandatory in **Belgium** (2026-01-01) and used as the rail in **Croatia 2026** / **Greece 2026** alongside national CTC.

**Local copy:** [`../_vendor/peppol/peppol-bis-invoice-3/`](../_vendor/peppol/peppol-bis-invoice-3/) (folder, no git).

## Official documents

| Document | URL |
| --- | --- |
| OpenPeppol | https://peppol.org/ |
| Peppol BIS Billing 3.0 | https://docs.peppol.eu/poacc/billing/3.0/ |
| BIS Billing (current release notes / syntax) | https://docs.peppol.eu/poacc/billing/3.0/bis/ |
| GitHub resources | https://github.com/OpenPEPPOL/peppol-bis-invoice-3 |
| Post-award doc index | https://peppol.org/documentation/technical-documentation/post-award-documentation/ |
| EN 16931 (buy from CEN; Commission overview) | https://ec.europa.eu/digital-building-blocks/sites/display/DIGITAL/EN+16931+compliance+eInvoicing |
| Directive 2014/55/EU | https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32014L0055 |

## Architecture (4-corner)

```text
C1 Seller ERP  →  C2 Seller Access Point  →  Peppol (SML/SMP + AS4)
                                              ↓
C4 Buyer ERP   ←  C3 Buyer Access Point
```

1. Resolve the recipient’s **Peppol participant ID** (often `iso6523-actorid-upis::0088:<GLN>` or a national scheme).
2. Look up the Access Point in the **SMP** (via **SML**).
3. Send the UBL invoice over **AS4** (OASIS ebMS / eDelivery).
4. Optional: Message Level Response, Invoice Response.

This product should **not** implement an Access Point from scratch. Use a certified AP (or become one later). The app’s job is: build valid **UBL Invoice/CreditNote**, hand it to the AP, store the AP message id / evidence.

## Document identifiers (BIS Billing 3.0)

| Field | Value |
| --- | --- |
| `cbc:CustomizationID` (BT-24) | `urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0` |
| `cbc:ProfileID` (BT-23) | `urn:fdc:peppol.eu:2017:poacc:billing:01:1.0` |
| Syntax | UBL 2.1 Invoice / CreditNote |
| Process | Billing profile 01 |

National **CIUS** overlays replace or extend CustomizationID (Germany XRechnung, Romania CIUS-RO, Portugal CIUS-PT). Those countries have extra shared files or country notes.

## Integration steps for this app

1. At issue time, build `FiscalSnapshot`.
2. Map to UBL 2.1 EN 16931 (seller/buyer endpoint IDs, VAT breakdown, payment means).
3. Validate with official Peppol Schematron (from the BIS repo).
4. Submit via Access Point API (vendor-specific; not standardised by OpenPeppol as a single REST).
5. Persist AP transmission id + any MLR.
6. Inbound: poll/webhook from the AP for received invoices (mandatory receive in BE, DE, PL-adjacent, etc.).

## What not to invent

- Do not POST Peppol XML to AEAT/KSeF/SdI.
- Do not treat Peppol as clearance: legal issue is usually **send of a valid structured invoice**, not a ministry UPO (unless the country adds CTC on the side).
