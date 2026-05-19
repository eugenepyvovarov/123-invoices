from datetime import date

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models import ProtectedError
from django.test import TestCase, TransactionTestCase

from invoices.models import Company, Customer, Invoice, Issuer, IssuerBankAccount, Project
from tests.support import IssuerUserTestMixin


class IssuerBankAccountModelTests(IssuerUserTestMixin, TestCase):
    def setUp(self):
        self.issuer = self.create_issuer(
            company=Company.objects.create(name='Issuer Co', customer_information_file_number='VATISS')
        )
        self.other_issuer = self.create_issuer(
            company=Company.objects.create(name='Other Issuer', customer_information_file_number='VATOTH')
        )

    def test_enforces_one_default_per_issuer(self):
        IssuerBankAccount.objects.create(
            issuer=self.issuer,
            label='Primary',
            account_details='ES12 0000 0000 0000',
            is_default=True,
        )
        duplicate = IssuerBankAccount(
            issuer=self.issuer,
            label='Secondary',
            account_details='ES34 0000 0000 0000',
            is_default=True,
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                duplicate.save()

    def test_allows_one_default_for_each_issuer(self):
        first = IssuerBankAccount.objects.create(
            issuer=self.issuer,
            label='Primary',
            account_details='ES12 0000 0000 0000',
            is_default=True,
        )
        second = IssuerBankAccount.objects.create(
            issuer=self.other_issuer,
            label='Primary',
            account_details='BE68 0000 0000 0000',
            is_default=True,
        )

        self.assertNotEqual(first.issuer_id, second.issuer_id)

    def test_rejects_default_inactive_account(self):
        account = IssuerBankAccount(
            issuer=self.issuer,
            label='Inactive default',
            account_details='ES12 0000 0000 0000',
            is_default=True,
            is_active=False,
        )

        with self.assertRaises(ValidationError):
            account.full_clean()

    def test_invoice_bank_account_must_belong_to_invoice_issuer(self):
        account = IssuerBankAccount.objects.create(
            issuer=self.other_issuer,
            label='Other default',
            account_details='BE68 0000 0000 0000',
            is_default=True,
        )
        customer = Customer.objects.create(
            issuer=self.issuer,
            company=Company.objects.create(name='Client', customer_information_file_number='VATCLI'),
        )
        project = Project.objects.create(customer=customer, title='Client project', project_code='CLI')
        invoice = Invoice(
            issuer=self.issuer,
            customer=customer,
            project=project,
            bank_account=account,
            issued_date=date(2026, 1, 1),
        )

        with self.assertRaises(ValidationError):
            invoice.full_clean()

    def test_inactive_linked_account_remains_valid_and_protected(self):
        account = IssuerBankAccount.objects.create(
            issuer=self.issuer,
            label='Archived',
            account_details='ES12 0000 0000 0000',
            is_active=False,
        )
        customer = Customer.objects.create(
            issuer=self.issuer,
            company=Company.objects.create(name='Client', customer_information_file_number='VATCLI'),
        )
        project = Project.objects.create(customer=customer, title='Client project', project_code='CLI')
        invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=customer,
            project=project,
            bank_account=account,
            issued_date=date(2026, 1, 1),
        )

        invoice.full_clean(exclude=['pdf_document'])
        with self.assertRaises(ProtectedError):
            account.delete()


class IssuerBankAccountAdminTests(TestCase):
    def test_bank_account_admin_is_registered(self):
        model_admin = admin.site._registry[IssuerBankAccount]

        self.assertIn('is_default', model_admin.list_display)
        self.assertIn('is_active', model_admin.list_display)
        self.assertIn('issuer', model_admin.list_filter)


class IssuerBankAccountBackfillMigrationTests(TransactionTestCase):
    migrate_from = [('invoices', '0062_merge_import_mapping_and_project_scoped_codes')]
    migrate_to = [('invoices', '0063_issuer_bank_accounts')]

    def _migrate_with_setup(self, setup_data):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        state = setup_data(old_apps)

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        return new_apps, state

    def test_backfills_default_account_and_existing_invoices(self):
        def setup_data(old_apps):
            CompanyModel = old_apps.get_model('invoices', 'Company')
            CustomerModel = old_apps.get_model('invoices', 'Customer')
            InvoiceModel = old_apps.get_model('invoices', 'Invoice')
            IssuerModel = old_apps.get_model('invoices', 'Issuer')
            ProjectModel = old_apps.get_model('invoices', 'Project')

            issuer_company = CompanyModel.objects.create(
                name='Issuer',
                customer_information_file_number='VATISS',
                bank_account_number='ES12 3456 7890 1234',
                payment_method='Bank transfer',
            )
            customer_company = CompanyModel.objects.create(name='Client', customer_information_file_number='VATCLI')
            issuer = IssuerModel.objects.create(company=issuer_company)
            customer = CustomerModel.objects.create(issuer=issuer, company=customer_company)
            project = ProjectModel.objects.create(customer=customer, title='Project', project_code='PRJ')
            invoice = InvoiceModel.objects.create(
                issuer=issuer,
                customer=customer,
                project=project,
                issued_date=date(2026, 1, 1),
                status='draft',
            )
            return {'issuer_id': issuer.pk, 'invoice_id': invoice.pk}

        new_apps, state = self._migrate_with_setup(setup_data)
        InvoiceModel = new_apps.get_model('invoices', 'Invoice')
        IssuerBankAccountModel = new_apps.get_model('invoices', 'IssuerBankAccount')

        account = IssuerBankAccountModel.objects.get(issuer_id=state['issuer_id'])
        invoice = InvoiceModel.objects.get(pk=state['invoice_id'])

        self.assertEqual(account.label, 'Default bank account')
        self.assertEqual(account.payment_method, 'Bank transfer')
        self.assertEqual(account.account_details, 'ES12 3456 7890 1234')
        self.assertTrue(account.is_default)
        self.assertTrue(account.is_active)
        self.assertEqual(invoice.bank_account_id, account.pk)

    def test_backfill_skips_blank_existing_bank_details(self):
        def setup_data(old_apps):
            CompanyModel = old_apps.get_model('invoices', 'Company')
            IssuerModel = old_apps.get_model('invoices', 'Issuer')

            issuer_company = CompanyModel.objects.create(name='Issuer', customer_information_file_number='VATISS')
            issuer = IssuerModel.objects.create(company=issuer_company)
            return {'issuer_id': issuer.pk}

        new_apps, state = self._migrate_with_setup(setup_data)
        IssuerBankAccountModel = new_apps.get_model('invoices', 'IssuerBankAccount')

        self.assertFalse(IssuerBankAccountModel.objects.filter(issuer_id=state['issuer_id']).exists())
