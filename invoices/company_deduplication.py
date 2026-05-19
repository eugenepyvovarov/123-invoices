import re
from typing import Optional


def _clean_company_identity_value(value: Optional[str]) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_company_tax_id(value: Optional[str]) -> str:
    cleaned = _clean_company_identity_value(value)
    if not cleaned:
        return ""
    return re.sub(r"\s+", "", cleaned).upper()


def _normalize_company_name(value: Optional[str]) -> str:
    cleaned = _clean_company_identity_value(value)
    if not cleaned:
        return ""
    return re.sub(r"\s+", " ", cleaned).casefold()


def _normalize_company_contact_email(value: Optional[str]) -> str:
    cleaned = _clean_company_identity_value(value)
    if not cleaned:
        return ""
    return cleaned.casefold()
