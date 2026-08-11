# Spanish SIF / VERI*FACTU foundation

This app stores SIF compliance settings per issuer. SIF behavior is applicable only when an issuer is explicitly configured with Spain (`ES`) as its tax country, has SIF enabled, has a valid Spanish NIF/NIE/CIF in the issuer company VAT field, and is marked operationally ready.

The foundation supports both SIF modes:

- `VERI_FACTU`: voluntary continuous AEAT remittance.
- `NO_VERI_FACTU`: local SIF preservation mode.

Non-Spanish issuers keep the normal invoice lifecycle and are not forced into Spanish SIF warnings, QR, AEAT XML, AEAT submission, XAdES signing, or Spanish SIF exports.

This issue does not implement downstream fiscal flows. VERI*FACTU AEAT streaming is tracked in issue #155. Non-VERI*FACTU local controls, preservation, and XAdES signing are tracked in issue #158.

For how Spain compares to other EU tax-authority and e-invoice regimes, see [EU e-invoicing and tax-authority reporting](eu-e-invoicing/index.md). SIF and other **2027 pre-live** duties we still implement are listed in [eu-e-invoicing/shared/pre-live-2027.md](eu-e-invoicing/shared/pre-live-2027.md).
