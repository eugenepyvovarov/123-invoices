from django.db import migrations


def add_reference_to_memo(apps, schema_editor):
    Expense = apps.get_model('invoices', 'Expense')
    updated_ids = []
    batch = []
    qs = Expense.objects.exclude(raw_data={}).exclude(raw_data=None)
    for expense in qs.iterator(chunk_size=500):
        raw = expense.raw_data or {}
        reference = raw.get('Payment Reference') or raw.get('payment_reference')
        if not reference:
            continue
        reference = str(reference).strip()
        if not reference:
            continue
        description = (expense.description or '').strip()
        if description.endswith(reference) or reference in description.split('\n'):
            continue
        lines = [description] if description else []
        lines.append(reference)
        new_description = '\n'.join(lines)
        if new_description == expense.description:
            continue
        expense.description = new_description
        batch.append(expense)
        if len(batch) >= 500:
            Expense.objects.bulk_update(batch, ['description'])
            batch.clear()
    if batch:
        Expense.objects.bulk_update(batch, ['description'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("invoices", "0052_expense_exclude_flag"),
    ]

    operations = [
        migrations.RunPython(add_reference_to_memo, noop),
    ]
