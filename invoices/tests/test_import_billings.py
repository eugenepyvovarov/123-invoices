import io
import sqlite3
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase

from invoices.company_deduplication import (
    _normalize_company_contact_email,
    _normalize_company_name,
    _normalize_company_tax_id,
)
from invoices.management.commands.import_billings import BillingsImporter
from invoices.models import Address, Company, Currency, Customer, Issuer, PaymentTerm


class BillingsImportNormalizationTests(SimpleTestCase):
    def test_normalize_company_tax_id_removes_whitespace_and_uppercases(self):
        self.assertEqual(_normalize_company_tax_id("  es  b-123 456  "), "ESB-123456")

    def test_normalize_company_tax_id_returns_blank_for_empty_values(self):
        self.assertEqual(_normalize_company_tax_id("   "), "")
        self.assertEqual(_normalize_company_tax_id(None), "")

    def test_normalize_company_name_collapses_whitespace_and_casefolds(self):
        self.assertEqual(_normalize_company_name("  ACME   Widgets\tLLC  "), "acme widgets llc")

    def test_normalize_company_name_returns_blank_for_empty_values(self):
        self.assertEqual(_normalize_company_name("\n\t"), "")
        self.assertEqual(_normalize_company_name(None), "")

    def test_normalize_company_contact_email_strips_and_lowercases(self):
        self.assertEqual(_normalize_company_contact_email("  Sales@Example.COM  "), "sales@example.com")

    def test_normalize_company_contact_email_returns_blank_for_empty_values(self):
        self.assertEqual(_normalize_company_contact_email("  "), "")
        self.assertEqual(_normalize_company_contact_email(None), "")


class BillingsImportCompanyResolutionTests(SimpleTestCase):
    def setUp(self):
        self.importer = BillingsImporter.__new__(BillingsImporter)

    def test_build_company_name_prefers_company_field(self):
        row = SimpleNamespace(
            company="  ACME Corp  ",
            prefix="",
            firstName="Jane",
            middleName="",
            lastName="Doe",
            suffix="",
            _rowid=7,
        )

        self.assertEqual(self.importer._build_company_name(row.__dict__), "ACME Corp")

    def test_build_company_name_falls_back_to_contact_parts(self):
        row = {
            "company": "",
            "prefix": "Dr.",
            "firstName": "Jane",
            "middleName": "Q.",
            "lastName": "Doe",
            "suffix": "PhD",
            "_rowid": 9,
        }

        self.assertEqual(self.importer._build_company_name(row), "Dr. Jane Q. Doe PhD")

    def test_resolve_company_for_customer_import_reuses_existing_customer_company_and_address(self):
        address = Address(street="123 Main")
        company = Company(name="Existing Co", address=address)
        customer = Customer(company=company)

        resolved_company, resolved_address = self.importer._resolve_company_for_customer_import(
            customer=customer,
            company_name="Replacement Name",
        )

        self.assertIs(resolved_company, company)
        self.assertIs(resolved_address, address)

    def test_resolve_company_for_customer_import_creates_new_unsaved_company_when_missing(self):
        self.importer._find_matching_company_by_tax_id = lambda tax_number: None
        self.importer._find_matching_company_by_name_and_email = lambda company_name, contact_email: None

        resolved_company, resolved_address = self.importer._resolve_company_for_customer_import(
            customer=None,
            company_name="New Co",
        )

        self.assertIsNone(resolved_company.pk)
        self.assertEqual(resolved_company.name, "New Co")
        self.assertIsNone(resolved_address.pk)


class BillingsImportCompanyLookupPriorityTests(TestCase):
    def setUp(self):
        self.importer = BillingsImporter.__new__(BillingsImporter)

    def test_resolve_company_for_customer_import_prefers_tax_id_match_after_customer_lookup_miss(self):
        tax_id_match = Company.objects.create(
            name="Existing Tax Match",
            customer_information_file_number=" ES B-123 456 ",
        )
        Company.objects.create(
            name="Name Email Match",
            contact_email="accounts@example.com",
        )

        resolved_company, resolved_address = self.importer._resolve_company_for_customer_import(
            customer=None,
            company_name="Existing Tax Match",
            tax_number="esb-123456",
            contact_email="accounts@example.com",
        )

        self.assertEqual(resolved_company.pk, tax_id_match.pk)
        self.assertIsNone(resolved_address.pk)

    def test_resolve_company_for_customer_import_falls_back_to_name_and_email_match(self):
        matched_company = Company.objects.create(
            name="  ACME   Studio ",
            contact_email=" Billing@Example.COM ",
        )

        resolved_company, resolved_address = self.importer._resolve_company_for_customer_import(
            customer=None,
            company_name="acme studio",
            tax_number="",
            contact_email="billing@example.com",
        )

        self.assertEqual(resolved_company.pk, matched_company.pk)
        self.assertIsNone(resolved_address.pk)

    def test_resolve_company_for_customer_import_does_not_match_by_name_without_email(self):
        Company.objects.create(name="ACME Studio", contact_email="")

        resolved_company, resolved_address = self.importer._resolve_company_for_customer_import(
            customer=None,
            company_name="ACME Studio",
            tax_number="",
            contact_email="",
        )

        self.assertIsNone(resolved_company.pk)
        self.assertEqual(resolved_company.name, "ACME Studio")
        self.assertIsNone(resolved_address.pk)


class BillingsImportCustomerUpsertTests(TestCase):
    def setUp(self):
        self.issuer_company = Company.objects.create(name="Issuer Co")
        self.issuer = Issuer.objects.create(company=self.issuer_company)
        self.currency = Currency.objects.create(code="USD", name="US Dollar", symbol="$", is_base=True)
        self.payment_term = PaymentTerm.objects.create(name="Net 30", days=30)
        self.importer = BillingsImporter.__new__(BillingsImporter)
        self.importer.issuer = self.issuer
        self.importer.customer_by_rowid = {}

    def test_upsert_customer_for_import_updates_existing_customer_fields(self):
        self.importer.update_existing = True
        original_company = Company.objects.create(name="Original Co")
        resolved_company = Company.objects.create(name="Resolved Co", contact_name="Resolved Billing")
        customer = Customer.objects.create(
            issuer=self.issuer,
            company=original_company,
            external_id="123",
            currency=self.currency,
            payment_term=self.payment_term,
            billing_email="keep@example.com",
            billing_contact_name="Original Billing",
            is_active=True,
        )

        updated_customer = self.importer._upsert_customer_for_import(
            rowid=123,
            external_id="123",
            customer=customer,
            company=resolved_company,
            currency=None,
            payment_term=self.payment_term,
            company_name="Resolved Co",
            is_active=False,
        )

        customer.refresh_from_db()

        self.assertEqual(updated_customer.pk, customer.pk)
        self.assertEqual(customer.company_id, resolved_company.id)
        self.assertIsNone(customer.currency)
        self.assertEqual(customer.payment_term_id, self.payment_term.id)
        self.assertEqual(customer.billing_email, "keep@example.com")
        self.assertEqual(customer.billing_contact_name, "Resolved Billing")
        self.assertFalse(customer.is_active)
        self.assertEqual(self.importer.customer_by_rowid[123].pk, customer.pk)

    def test_upsert_customer_for_import_creates_customer_for_resolved_company(self):
        self.importer.update_existing = False
        resolved_company = Company.objects.create(
            name="Resolved Co",
            contact_name="Resolved Billing",
            contact_email="billing@example.com",
        )

        customer = self.importer._upsert_customer_for_import(
            rowid=456,
            external_id="456",
            customer=None,
            company=resolved_company,
            currency=self.currency,
            payment_term=self.payment_term,
            company_name="Resolved Co",
            is_active=True,
        )

        self.assertEqual(customer.company_id, resolved_company.id)
        self.assertEqual(customer.external_id, "456")
        self.assertEqual(customer.billing_email, "billing@example.com")
        self.assertEqual(customer.billing_contact_name, "Resolved Billing")
        self.assertTrue(customer.is_active)
        self.assertEqual(self.importer.customer_by_rowid[456].pk, customer.pk)


class BillingsImportCustomerImportRegressionTests(TestCase):
    def setUp(self):
        self.issuer_company = Company.objects.create(name="Issuer Co")
        self.issuer = Issuer.objects.create(company=self.issuer_company)
        self.payment_term = PaymentTerm.objects.create(name="Net 30", days=30)
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.addCleanup(self.connection.close)
        self._create_billings_tables()

    def _create_billings_tables(self):
        self.connection.execute(
            """
            CREATE TABLE Client (
                _rowid INTEGER PRIMARY KEY,
                company TEXT,
                prefix TEXT,
                firstName TEXT,
                middleName TEXT,
                lastName TEXT,
                suffix TEXT,
                taxNumber TEXT,
                addressFormatted TEXT,
                clientCategoryID INTEGER,
                email TEXT,
                addressStreet TEXT,
                addressCity TEXT,
                addressState TEXT,
                addressZIP TEXT,
                addressCountry TEXT,
                currentCurrencyID INTEGER,
                nickName TEXT
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE Invoice (
                _rowid INTEGER PRIMARY KEY,
                clientID INTEGER,
                invoiceDate REAL,
                dueDate REAL
            )
            """
        )

    def _insert_client(self, rowid=101, *, tax_number="", company="ACME Studio", email="billing@example.com"):
        self.connection.execute(
            """
            INSERT INTO Client (
                _rowid, company, prefix, firstName, middleName, lastName, suffix,
                taxNumber, addressFormatted, clientCategoryID, email, addressStreet,
                addressCity, addressState, addressZIP, addressCountry, currentCurrencyID,
                nickName
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rowid,
                company,
                "",
                "",
                "",
                "",
                "",
                tax_number,
                "123 Main St\nSpringfield, IL 62701",
                None,
                email,
                "123 Main St",
                "Springfield",
                "IL",
                "62701",
                "US",
                None,
                "Billing Team",
            ),
        )
        self.connection.commit()

    def _build_importer(self, *, update_existing):
        importer = BillingsImporter.__new__(BillingsImporter)
        importer.connection = self.connection
        importer.issuer = self.issuer
        importer.dry_run = False
        importer.update_existing = update_existing
        importer.stdout = io.StringIO()
        importer.style = SimpleNamespace(WARNING=lambda value: value, SUCCESS=lambda value: value)
        importer.currency_by_rowid = {}
        importer.payment_term_by_days = {}
        importer.customer_by_rowid = {}
        importer.customer_total = 0
        importer.customer_status_counts = {"active": 0, "inactive": 0}
        importer.placeholder_pdf = BillingsImporter.PLACEHOLDER_PDF_NAME
        importer._ensure_placeholder_pdf = lambda: BillingsImporter.PLACEHOLDER_PDF_NAME
        importer._derive_payment_term_for_client = lambda client_rowid: self.payment_term
        return importer

    def test_import_customers_repeated_import_reuses_same_company_row(self):
        self._insert_client()

        first_importer = self._build_importer(update_existing=True)
        first_importer._import_customers()

        customer = Customer.objects.get(external_id="101")
        original_company_id = customer.company_id

        second_importer = self._build_importer(update_existing=True)
        second_importer._import_customers()

        customer.refresh_from_db()

        self.assertEqual(Company.objects.count(), 2)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(customer.company_id, original_company_id)
        self.assertEqual(customer.company.name, "ACME Studio")

    def test_import_customers_external_id_churn_reuses_existing_company_by_tax_id(self):
        existing_company = Company.objects.create(
            name="ACME Studio",
            customer_information_file_number=" ES B-123 456 ",
            contact_name="Billing Team",
            contact_email="billing@example.com",
        )
        Customer.objects.create(
            issuer=self.issuer,
            company=existing_company,
            external_id="999",
            payment_term=self.payment_term,
            billing_email="billing@example.com",
            billing_contact_name="Billing Team",
            is_active=True,
        )
        self._insert_client(rowid=101, tax_number="esb-123456")

        importer = self._build_importer(update_existing=True)
        importer._import_customers()

        imported_customer = Customer.objects.get(external_id="101")

        self.assertEqual(Company.objects.count(), 2)
        self.assertEqual(Customer.objects.count(), 2)
        self.assertEqual(imported_customer.company_id, existing_company.id)
        self.assertEqual(imported_customer.company.customer_information_file_number, "esb-123456")

    def test_import_customers_external_id_churn_reuses_existing_company_by_normalized_name_and_email(self):
        existing_company = Company.objects.create(
            name="  ACME   Studio  ",
            contact_name="Billing Team",
            contact_email=" Billing@Example.COM ",
        )
        Customer.objects.create(
            issuer=self.issuer,
            company=existing_company,
            external_id="999",
            payment_term=self.payment_term,
            billing_email="billing@example.com",
            billing_contact_name="Billing Team",
            is_active=True,
        )
        self._insert_client(rowid=101, company="acme studio", email="billing@example.com")

        importer = self._build_importer(update_existing=True)
        importer._import_customers()

        imported_customer = Customer.objects.get(external_id="101")

        self.assertEqual(Company.objects.count(), 2)
        self.assertEqual(Customer.objects.count(), 2)
        self.assertEqual(imported_customer.company_id, existing_company.id)
        self.assertEqual(imported_customer.company.contact_email, "billing@example.com")

    def test_import_customers_external_id_churn_does_not_match_by_name_only(self):
        existing_company = Company.objects.create(
            name="ACME Studio",
            contact_name="Billing Team",
            contact_email="",
        )
        Customer.objects.create(
            issuer=self.issuer,
            company=existing_company,
            external_id="999",
            payment_term=self.payment_term,
            billing_email="",
            billing_contact_name="Billing Team",
            is_active=True,
        )
        self._insert_client(rowid=101, company=" ACME   Studio ", email="")

        importer = self._build_importer(update_existing=True)
        importer._import_customers()

        imported_customer = Customer.objects.get(external_id="101")

        self.assertEqual(Company.objects.count(), 3)
        self.assertEqual(Customer.objects.count(), 2)
        self.assertNotEqual(imported_customer.company_id, existing_company.id)
        self.assertEqual(imported_customer.company.name, "ACME   Studio")
