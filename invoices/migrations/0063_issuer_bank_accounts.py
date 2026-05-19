from django.db import migrations, models
import django.db.models.deletion


def backfill_issuer_bank_accounts(apps, schema_editor):
    Company = apps.get_model('invoices', 'Company')
    Invoice = apps.get_model('invoices', 'Invoice')
    Issuer = apps.get_model('invoices', 'Issuer')
    IssuerBankAccount = apps.get_model('invoices', 'IssuerBankAccount')

    for issuer in Issuer.objects.select_related('company').all():
        company = issuer.company
        if company is None:
            continue

        account_details = (company.bank_account_number or '').strip()
        payment_method = (company.payment_method or '').strip()
        if not account_details and not payment_method:
            continue

        default_account = IssuerBankAccount.objects.filter(
            issuer=issuer,
            is_default=True,
        ).first()
        if default_account is None:
            default_account, _created = IssuerBankAccount.objects.get_or_create(
                issuer=issuer,
                label='Default bank account',
                defaults={
                    'payment_method': payment_method,
                    'account_details': account_details,
                    'is_default': True,
                    'is_active': True,
                    'sort_order': 0,
                },
            )

        Invoice.objects.filter(
            issuer=issuer,
            bank_account__isnull=True,
        ).update(bank_account=default_account)


def clear_backfilled_invoice_accounts(apps, schema_editor):
    Invoice = apps.get_model('invoices', 'Invoice')
    Invoice.objects.update(bank_account=None)


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0062_merge_import_mapping_and_project_scoped_codes'),
    ]

    operations = [
        migrations.CreateModel(
            name='IssuerBankAccount',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(max_length=100)),
                ('payment_method', models.CharField(blank=True, max_length=100, null=True)),
                ('account_details', models.TextField(blank=True)),
                ('is_default', models.BooleanField(default=False)),
                ('is_active', models.BooleanField(default=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('issuer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bank_accounts', to='invoices.issuer')),
            ],
            options={
                'ordering': ['issuer', 'sort_order', 'label', 'id'],
            },
        ),
        migrations.AddField(
            model_name='invoice',
            name='bank_account',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='invoices', to='invoices.issuerbankaccount'),
        ),
        migrations.AddConstraint(
            model_name='issuerbankaccount',
            constraint=models.UniqueConstraint(condition=models.Q(('is_default', True)), fields=('issuer',), name='unique_default_bank_account_per_issuer'),
        ),
        migrations.RunPython(backfill_issuer_bank_accounts, clear_backfilled_invoice_accounts),
    ]
