from django.db import migrations


def normalize_decimal_columns(apps, schema_editor):
    invoice_decimal_fields = [
        'discount_value',
        'discount_amount',
        'sub_total',
        'tax_base',
        'tax_value',
        'tax_amount',
        'total_due',
    ]

    for field in invoice_decimal_fields:
        schema_editor.execute(
            f"""
            UPDATE invoices_invoice
            SET {field} = '0'
            WHERE {field} IS NULL OR trim({field}) = ''
            """
        )

    orderline_decimal_fields = ['quantity', 'unit_price', 'line_total']
    for field in orderline_decimal_fields:
        schema_editor.execute(
            f"""
            UPDATE invoices_orderline
            SET {field} = '0'
            WHERE {field} IS NULL OR trim({field}) = ''
            """
        )

    schema_editor.execute(
        """
        UPDATE invoices_orderline
        SET line_total = CAST(quantity AS NUMERIC) * CAST(unit_price AS NUMERIC)
        """
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0028_remove_orderline_product_orderline_description_and_more'),
    ]

    operations = [
        migrations.RunPython(normalize_decimal_columns, noop),
    ]
