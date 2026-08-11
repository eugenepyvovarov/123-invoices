"""Country-agnostic fiscal-regime registry.

Issuance still lives on Invoice.save(); adapters hang off this package when
#149+ lands. get_applicable_adapters() is the only entry future views should use.
"""

from invoices.services.fiscal.registry import (
    REGIME_CATALOG,
    get_applicable_adapters,
    get_implementation_inventory,
    get_regime,
)

__all__ = [
    'REGIME_CATALOG',
    'get_applicable_adapters',
    'get_implementation_inventory',
    'get_regime',
]
