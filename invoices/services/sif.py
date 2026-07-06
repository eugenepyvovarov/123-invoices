import re
from dataclasses import dataclass

from invoices.models import Issuer, IssuerSifSettings


SPANISH_TAX_ID_RE = re.compile(r'^[A-Z0-9]+$')
NIF_LETTERS = 'TRWAGMYFPDXBNJZSQVHLCKE'
CIF_LETTERS = set('ABCDEFGHJNPQRSUVW')
CIF_CONTROL_LETTER_PREFIXES = set('KPQS')
CIF_CONTROL_DIGIT_PREFIXES = set('ABEH')
NIE_PREFIX_VALUES = {'X': '0', 'Y': '1', 'Z': '2'}


@dataclass(frozen=True)
class SifReadiness:
    settings: IssuerSifSettings
    normalized_tax_id: str
    is_spanish_issuer: bool
    has_valid_tax_id: bool
    is_operationally_ready: bool
    effective_activation: bool
    deadline: object
    missing_prerequisites: tuple[str, ...]


def get_sif_settings(issuer: Issuer) -> IssuerSifSettings:
    settings, _ = IssuerSifSettings.objects.get_or_create(issuer=issuer)
    return settings


def normalize_spanish_tax_id(value: str | None) -> str:
    return re.sub(r'[^A-Z0-9]', '', (value or '').upper())


def is_valid_spanish_tax_id(value: str | None) -> bool:
    tax_id = normalize_spanish_tax_id(value)
    if not SPANISH_TAX_ID_RE.match(tax_id):
        return False
    return _is_valid_nif(tax_id) or _is_valid_nie(tax_id) or _is_valid_cif(tax_id)


def get_informational_deadline(settings: IssuerSifSettings):
    return settings.informational_deadline


def get_sif_readiness(issuer: Issuer) -> SifReadiness:
    settings = get_sif_settings(issuer)
    tax_id = ''
    if issuer.company:
        tax_id = normalize_spanish_tax_id(issuer.company.customer_information_file_number)

    is_spanish = settings.tax_country == IssuerSifSettings.TaxCountry.SPAIN
    has_valid_tax_id = is_valid_spanish_tax_id(tax_id)
    is_ready = settings.operational_status == IssuerSifSettings.OperationalStatus.READY
    missing = []
    if settings.enabled:
        if not is_spanish:
            missing.append('spanish_tax_country')
        if is_spanish and not has_valid_tax_id:
            missing.append('valid_spanish_tax_id')
        if not is_ready:
            missing.append('operational_ready_status')

    return SifReadiness(
        settings=settings,
        normalized_tax_id=tax_id,
        is_spanish_issuer=is_spanish,
        has_valid_tax_id=has_valid_tax_id,
        is_operationally_ready=is_ready,
        effective_activation=settings.enabled and is_spanish and has_valid_tax_id and is_ready,
        deadline=get_informational_deadline(settings),
        missing_prerequisites=tuple(missing),
    )


def is_sif_effectively_active(issuer: Issuer) -> bool:
    return get_sif_readiness(issuer).effective_activation


def _is_valid_nif(tax_id: str) -> bool:
    if len(tax_id) != 9 or not tax_id[:8].isdigit() or not tax_id[-1].isalpha():
        return False
    return NIF_LETTERS[int(tax_id[:8]) % 23] == tax_id[-1]


def _is_valid_nie(tax_id: str) -> bool:
    if len(tax_id) != 9 or tax_id[0] not in NIE_PREFIX_VALUES:
        return False
    numeric = NIE_PREFIX_VALUES[tax_id[0]] + tax_id[1:8]
    return tax_id[1:8].isdigit() and tax_id[-1].isalpha() and NIF_LETTERS[int(numeric) % 23] == tax_id[-1]


def _is_valid_cif(tax_id: str) -> bool:
    if len(tax_id) != 9 or tax_id[0] not in CIF_LETTERS or not tax_id[1:8].isdigit():
        return False

    total = 0
    for index, digit_text in enumerate(tax_id[1:8], start=1):
        digit = int(digit_text)
        if index % 2:
            doubled = digit * 2
            total += doubled // 10 + doubled % 10
        else:
            total += digit

    control_digit = (10 - (total % 10)) % 10
    control_letter = 'JABCDEFGHI'[control_digit]
    control = tax_id[-1]
    if tax_id[0] in CIF_CONTROL_LETTER_PREFIXES:
        return control == control_letter
    if tax_id[0] in CIF_CONTROL_DIGIT_PREFIXES:
        return control == str(control_digit)
    return control in {str(control_digit), control_letter}
