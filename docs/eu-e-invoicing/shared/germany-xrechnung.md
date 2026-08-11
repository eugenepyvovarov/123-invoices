# Shared integration: Germany XRechnung / ZUGFeRD

Used by: **[Germany](../germany.md)**. Transport may still be [Peppol](peppol-en16931.md).

## Mandatory?

| Rule | Mandatory now? |
| --- | --- |
| B2G XRechnung to federal authorities | **Yes** (from 2020) |
| B2B **receive** structured e-invoice | **Yes** since **2025-01-01** |
| B2B **issue** | **Not yet** for everyone: > EUR 800k from **2027-01-01**; others **2028-01-01** |
| Tax-authority clearance API | **No** |

**Local copy:** [`../_vendor/germany-xrechnung/`](../_vendor/germany-xrechnung/)

- `301-XRechnung-2023-09-22.pdf` — CIUS/Extension specification
- `validator-configuration-3.0.2/` — KoSIT release **xrechnung-3.0.2** (2026-01-31): XSD + Schematron + `scenarios.xml`

CustomizationID: `urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0`

## Official developer sources

| Resource | URL |
| --- | --- |
| Federal e-invoice | https://www.e-rechnung-bund.de/ |
| XRechnung (KoSIT) | https://xeinkauf.de/xrechnung/ (KoSIT / xeinkauf — current spec index) |
| Peppol BIS Billing | https://docs.peppol.eu/poacc/billing/3.0/ |
| Factur-X / ZUGFeRD | https://fnfe-mpe.org/factur-x/ (Factur-X) / FeRD for ZUGFeRD |

## Integration shape

- Produce **XRechnung** (UBL or CII CIUS) or **ZUGFeRD/Factur-X** (PDF/A-3 + embedded XML).
- Validate with official XRechnung Schematron.
- Deliver by Peppol, email, or buyer portal — **no Ministry REST**.
- Inbound receive path is already mandatory for German B2B.

App: EN snapshot → XRechnung/ZUGFeRD writer → optional Peppol AP. Reuse Peppol shared file for routing.
