from __future__ import annotations

from invoices.models import Issuer
from invoices.services.fiscal.base import FiscalRegimeAdapter, FiscalRegimeSpec
from invoices.services.sif import is_sif_effectively_active


REGIME_CATALOG: tuple[FiscalRegimeSpec, ...] = (
    FiscalRegimeSpec(
        code='ES_SIF',
        country_iso='ES',
        title='Spain SIF / VERI*FACTU',
        status='pre_live',
        implementation_ready=True,
        local_spec_paths=(
            'docs/eu-e-invoicing/_vendor/spain-sif/',
            'docs/eu-e-invoicing/shared/spain-sif-aeat.md',
        ),
        notes='Corporate 2027-01-01, other 2027-07-01. WSDL/XSD local.',
    ),
    FiscalRegimeSpec(
        code='ES_B2B',
        country_iso='ES',
        title='Spain Crea y Crece / SPFE',
        status='blocked',
        implementation_ready=False,
        local_spec_paths=(
            'docs/eu-e-invoicing/_vendor/spain-crea-y-crece/',
            'docs/eu-e-invoicing/shared/pre-live-2027.md',
        ),
        notes='RD 238/2026 stored. SPFE API/XSD await ministerial order.',
    ),
    FiscalRegimeSpec(
        code='FR_PDP',
        country_iso='FR',
        title='France B2B PDP / e-reporting',
        status='pre_live',
        implementation_ready=True,
        local_spec_paths=(
            'docs/eu-e-invoicing/_vendor/france-pdp/',
            'docs/eu-e-invoicing/shared/france-chorus-pro.md',
        ),
        notes='Specs v3.2 local. Still pick one accredited PDP for transport.',
    ),
    FiscalRegimeSpec(
        code='DE_EN16931',
        country_iso='DE',
        title='Germany XRechnung / Peppol issue',
        status='pre_live',
        implementation_ready=True,
        local_spec_paths=(
            'docs/eu-e-invoicing/_vendor/germany-xrechnung/',
            'docs/eu-e-invoicing/shared/germany-xrechnung.md',
        ),
        notes='Issue duty 2027-01-01 for >EUR 800k. Receive already live.',
    ),
    FiscalRegimeSpec(
        code='PL_KSEF',
        country_iso='PL',
        title='Poland KSeF 2.0',
        status='live',
        implementation_ready=True,
        local_spec_paths=(
            'docs/eu-e-invoicing/_vendor/poland-ksef/',
            'docs/eu-e-invoicing/shared/ksef-2.md',
        ),
        notes='Live for most VAT issuers. 2027-01-01 last small-seller tranche.',
    ),
    FiscalRegimeSpec(
        code='PEPPOL_BIS',
        country_iso='',
        title='Peppol BIS Billing 3.0',
        status='live',
        implementation_ready=True,
        local_spec_paths=(
            'docs/eu-e-invoicing/_vendor/peppol/',
            'docs/eu-e-invoicing/shared/peppol-en16931.md',
        ),
        notes='Shared rail for BE/HR/DE/Nordics/SK/EE/SI B2G or B2B.',
    ),
    FiscalRegimeSpec(
        code='SK_EFAKTURA',
        country_iso='SK',
        title='Slovakia eFaktúra 2027',
        status='pre_live',
        implementation_ready=False,
        local_spec_paths=(
            'docs/eu-e-invoicing/_vendor/slovakia-2027/',
            'docs/eu-e-invoicing/shared/slovakia-efaktura.md',
        ),
        notes='Law/date + solution architecture PDF. No FS reporting API pack.',
    ),
)


class _EsSifAdapter:
    spec = next(item for item in REGIME_CATALOG if item.code == 'ES_SIF')

    def applies(self, issuer: Issuer) -> bool:
        return is_sif_effectively_active(issuer)


_ADAPTERS: tuple[FiscalRegimeAdapter, ...] = (_EsSifAdapter(),)


def get_regime(code: str) -> FiscalRegimeSpec:
    for spec in REGIME_CATALOG:
        if spec.code == code:
            return spec
    raise KeyError(code)


def get_applicable_adapters(issuer: Issuer) -> tuple[FiscalRegimeAdapter, ...]:
    return tuple(adapter for adapter in _ADAPTERS if adapter.applies(issuer))


def get_implementation_inventory() -> tuple[FiscalRegimeSpec, ...]:
    return REGIME_CATALOG
