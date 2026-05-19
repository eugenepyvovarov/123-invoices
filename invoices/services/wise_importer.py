from __future__ import annotations

from invoices.models import Issuer
from invoices.services.expense_import_mappings import seed_wise_global_mapping
from invoices.services.expense_importer import ExpenseImportError, ExpenseImportResult, GenericExpenseImporter


class WiseImportError(ExpenseImportError):
    """Compatibility error for the legacy Wise import endpoint."""


WiseImportResult = ExpenseImportResult


class WiseStatementImporter:
    """Compatibility adapter around the generic expense CSV importer."""

    def __init__(self, issuer: Issuer) -> None:
        self.issuer = issuer

    def import_files(self, uploads) -> WiseImportResult:
        mapping, _ = seed_wise_global_mapping()
        importer = GenericExpenseImporter(user=None, issuer=self.issuer)
        try:
            return importer.import_files(uploads, mapping=mapping)
        except ExpenseImportError as exc:
            raise WiseImportError(str(exc)) from exc
