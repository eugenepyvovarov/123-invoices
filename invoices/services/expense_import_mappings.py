from __future__ import annotations

from invoices.models import ImportMapping


WISE_MAPPING_NAME = 'Wise CSV expense import'
WISE_HEADERS = [
    'TransferWise ID',
    'Date Time',
    'Amount',
    'Currency',
    'Description',
    'Payment Reference',
    'Transaction Type',
    'Transaction Details Type',
]
WISE_MAPPING_JSON = {
    'transaction_id': 'TransferWise ID',
    'paid_date': 'Date Time',
    'amount': 'Amount',
    'currency': 'Currency',
    'description': ['Description', 'Payment Reference'],
    'row_type': 'Transaction Type',
    'details_type': 'Transaction Details Type',
    'date_formats': ['%d-%m-%Y %H:%M:%S.%f', '%d-%m-%Y %H:%M:%S'],
    'amount_mode': 'absolute',
}
WISE_DEFAULT_ROW_SELECTION_RULES = {
    'include': [{'column': 'Transaction Type', 'equals': 'DEBIT'}],
    'exclude': [{'column': 'Transaction Details Type', 'equals': 'CONVERSION'}],
}


def wise_header_signature() -> str:
    return ImportMapping.signature_from_headers(WISE_HEADERS)


def seed_wise_global_mapping() -> tuple[ImportMapping, bool]:
    defaults = {
        'scope': ImportMapping.SCOPE_GLOBAL,
        'owner': None,
        'normalized_header_signature': wise_header_signature(),
        'mapping_json': WISE_MAPPING_JSON,
        'default_row_selection_rules': WISE_DEFAULT_ROW_SELECTION_RULES,
        'read_only': True,
    }
    mapping, created = ImportMapping.objects.get_or_create(
        name=WISE_MAPPING_NAME,
        scope=ImportMapping.SCOPE_GLOBAL,
        defaults=defaults,
    )
    update_fields = []
    for field, value in defaults.items():
        if getattr(mapping, field) != value:
            setattr(mapping, field, value)
            update_fields.append(field)
    if update_fields and not created:
        ImportMapping.objects.filter(pk=mapping.pk).update(**{field: getattr(mapping, field) for field in update_fields})
        mapping.refresh_from_db()
    return mapping, created
