import django.db.models.deletion
import invoices.models
from django.db import migrations, models


def assign_customers_from_projects(apps, schema_editor):
    Expense = apps.get_model('invoices', 'Expense')

    expenses_to_update = []
    for expense in Expense.objects.select_related('project__customer').filter(project__isnull=False, customer__isnull=True):
        project = expense.project
        if project and project.customer_id:
            expense.customer_id = project.customer_id
            expenses_to_update.append(expense)

    if expenses_to_update:
        Expense.objects.bulk_update(expenses_to_update, ['customer'])


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0047_invoice_payment_term'),
    ]

    operations = [
        migrations.RenameField(
            model_name='expense',
            old_name='date',
            new_name='paid_date',
        ),
        migrations.RemoveField(
            model_name='expense',
            name='category',
        ),
        migrations.AddField(
            model_name='expense',
            name='attachment',
            field=models.FileField(blank=True, null=True, upload_to=invoices.models.expense_attachment_upload_path),
        ),
        migrations.AddField(
            model_name='expense',
            name='customer',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='expenses', to='invoices.customer'),
        ),
        migrations.RunPython(assign_customers_from_projects, migrations.RunPython.noop),
    ]
