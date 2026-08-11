from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from invoices.models import Issuer


@dataclass(frozen=True)
class FiscalRegimeSpec:
    """Static catalog entry for a live or pre-live national regime."""

    code: str
    country_iso: str
    title: str
    status: str  # live | pre_live | watch | blocked
    implementation_ready: bool
    local_spec_paths: tuple[str, ...]
    notes: str


class FiscalRegimeAdapter(Protocol):
    spec: FiscalRegimeSpec

    def applies(self, issuer: Issuer) -> bool:
        """True when this issuer must run the regime on issue."""
        ...
