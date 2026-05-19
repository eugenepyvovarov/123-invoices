from django.db import connection


INVOICE_DECIMAL_COLUMNS = [
    'discount_value',
    'discount_amount',
    'sub_total',
    'tax_base',
    'tax_value',
    'tax_amount',
    'total_due',
]

ORDERLINE_DECIMAL_COLUMNS = ['quantity', 'unit_price', 'line_total']


def sanitize_decimal_columns():
    with connection.cursor() as cursor:
        for column in INVOICE_DECIMAL_COLUMNS:
            cursor.execute(
                f"""
                UPDATE invoices_invoice
                SET {column} = '0'
                WHERE {column} IS NULL OR trim({column}) = ''
                """
            )

        for column in ORDERLINE_DECIMAL_COLUMNS:
            cursor.execute(
                f"""
                UPDATE invoices_orderline
                SET {column} = '0'
                WHERE {column} IS NULL OR trim({column}) = ''
                """
            )

        cursor.execute(
            """
            UPDATE invoices_orderline
            SET line_total = CAST(quantity AS NUMERIC) * CAST(unit_price AS NUMERIC)
            """
        )
