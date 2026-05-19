import sqlite3
from collections import defaultdict
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, List, Optional

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from invoices.company_deduplication import (
    _normalize_company_contact_email,
    _normalize_company_name,
    _normalize_company_tax_id,
)
from invoices.models import (
    Address,
    Company,
    Currency,
    Customer,
    Invoice,
    Issuer,
    OrderLine,
    Payment,
    PaymentApplication,
    PaymentTerm,
    Project,
    Statement,
)
from invoices.services.bank_accounts import get_default_bank_account


class DryRunRollback(Exception):
    """Internal exception used to abort transactions during dry-run."""


class Command(BaseCommand):
    help = (
        "Import data from a Billings Pro SQLite export into the Django models "
        "for a specific company."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "sqlite_path",
            type=str,
            help="Path to the Billings Pro sqlite database (billingspro.sqlite).",
        )
        parser.add_argument(
            "--company-id",
            type=int,
            required=True,
            help="Company ID that should own the imported records.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run the import inside a rollback-only transaction.",
        )
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help=(
                "Update existing records that match by external_id. By default, existing "
                "records are skipped to make the import idempotent."
            ),
        )

    def handle(self, *args, **options):
        sqlite_path = Path(options["sqlite_path"]).expanduser().resolve()
        company_id = options["company_id"]
        dry_run = options["dry_run"]
        update_existing = options["update_existing"]

        if not sqlite_path.exists():
            raise CommandError(f"SQLite export not found: {sqlite_path}")

        try:
            company = Company.objects.get(pk=company_id)
        except Company.DoesNotExist as exc:
            raise CommandError(f"Company {company_id} does not exist") from exc

        issuer = getattr(company, "issuer_profile", None)
        if not issuer:
            issuer = Issuer.objects.create(company=company)
            self.stdout.write(self.style.WARNING(f"Created issuer {issuer.id} for company {company.id}"))

        self.stdout.write(
            f"Importing Billings data from {sqlite_path} for company {company.id} / issuer {issuer.id}"
        )

        connection = sqlite3.connect(str(sqlite_path))
        connection.row_factory = sqlite3.Row

        try:
            if dry_run:
                try:
                    with transaction.atomic():
                        self._run_import(connection, issuer, dry_run=True, update_existing=update_existing)
                        raise DryRunRollback()
                except DryRunRollback:
                    self.stdout.write(self.style.WARNING("Dry-run complete; no changes were saved."))
            else:
                with transaction.atomic():
                    self._run_import(connection, issuer, dry_run=False, update_existing=update_existing)
        finally:
            connection.close()

    def _run_import(self, connection: sqlite3.Connection, issuer: Issuer, dry_run: bool, update_existing: bool) -> None:
        """Core import routine coordinating the Billings import."""
        importer = BillingsImporter(command=self, connection=connection, issuer=issuer, dry_run=dry_run, update_existing=update_existing)
        importer.run()


class BillingsImporter:
    """High-level importer that reads Billings Pro data and persists Django models."""

    PLACEHOLDER_PDF_NAME = "invoices_pdf/billings-placeholder.pdf"

    def __init__(self, command: Command, connection: sqlite3.Connection, issuer: Issuer, dry_run: bool, update_existing: bool) -> None:
        self.command = command
        self.connection = connection
        self.issuer = issuer
        self.dry_run = dry_run
        self.update_existing = update_existing
        self.stdout = command.stdout
        self.style = command.style

        self.currency_by_rowid: Dict[int, Currency] = {}
        self.payment_term_by_days: Dict[int, PaymentTerm] = {}
        self.customer_by_rowid: Dict[int, Customer] = {}
        self.project_by_rowid: Dict[int, Project] = {}
        self.invoice_by_rowid: Dict[int, Invoice] = {}
        self.invoice_state_by_rowid: Dict[int, Optional[int]] = {}
        self.invoice_lines: Dict[int, List[OrderLine]] = defaultdict(list)
        self.payment_by_rowid: Dict[int, Payment] = {}
        self.payment_applications_map: Dict[int, List[PaymentApplication]] = defaultdict(list)
        self.time_entries_by_slip: Dict[int, List[sqlite3.Row]] = defaultdict(list)
        self.applied_amounts_by_invoice: Dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
        self.placeholder_pdf = self.PLACEHOLDER_PDF_NAME
        self.client_category_map: Dict[int, str] = {}
        self.payment_method_labels: Dict[int, str] = {}
        self.customer_total = 0
        self.customer_status_counts = {"active": 0, "inactive": 0}
        self.project_total = 0
        self.project_created = 0
        self.project_updated = 0
        self.project_skipped_missing_customer = 0
        self.projects_before = Project.objects.filter(customer__issuer=issuer).count()
        self.invoice_total = 0
        self.invoice_with_project_direct = 0
        self.invoice_with_project_inferred = 0
        self.invoice_missing_project = 0

        self.now_date = timezone.now().date()
        self._load_time_entries()
        self._load_client_categories()
        self._load_payment_method_labels()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self) -> None:
        self.stdout.write("Importing reference data (currencies and payment terms)...")
        self._import_currencies()
        self._prepare_default_payment_terms()

        self.stdout.write("Importing customers...")
        self._import_customers()

        self.stdout.write("Importing projects...")
        self._import_projects()

        self.stdout.write("Importing invoices...")
        self._import_invoices()

        self.stdout.write("Importing invoice line items...")
        self._import_time_slips()
        self._finalize_invoice_totals()

        self.stdout.write("Importing payments and applications...")
        self._import_payments()
        self._import_payment_applications()
        # Ensure payment statuses reflect actual applications after linking.
        self._finalize_payment_statuses()
        self._finalize_invoice_statuses()

        self.stdout.write("Importing statements...")
        self._import_statements()

        self.stdout.write(self.style.SUCCESS("Billings import completed successfully."))

    # ------------------------------------------------------------------
    # Helpers shared across import routines
    # ------------------------------------------------------------------

    def _load_time_entries(self) -> None:
        cursor = self.connection.execute(
            "SELECT timeSlipID, uuid, comment FROM TimeEntry WHERE timeSlipID IS NOT NULL"
        )
        for row in cursor.fetchall():
            time_slip_id = row["timeSlipID"]
            if time_slip_id is None:
                continue
            self.time_entries_by_slip[int(time_slip_id)].append(row)

    def _load_client_categories(self) -> None:
        cursor = self.connection.execute("SELECT _rowid, name FROM ClientCategory")
        for row in cursor.fetchall():
            try:
                self.client_category_map[int(row["_rowid"])] = self._clean_str(row["name"])
            except (TypeError, ValueError):
                continue

    def _load_payment_method_labels(self) -> None:
        cursor = self.connection.execute(
            "SELECT _rowid, name FROM PaymentMethodType WHERE name IS NOT NULL AND name <> ''"
        )
        for row in cursor.fetchall():
            try:
                self.payment_method_labels[int(row["_rowid"])] = self._clean_str(row["name"])
            except (TypeError, ValueError):
                continue

    @staticmethod
    def _clean_str(value: Optional[str]) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _epoch_to_datetime(value: Optional[float]) -> Optional[datetime]:
        if value in (None, "", 0):
            return None
        try:
            timestamp = float(value)
        except (TypeError, ValueError):
            return None
        return datetime.fromtimestamp(timestamp, tz=dt_timezone.utc)

    def _epoch_to_date(self, value: Optional[float]) -> Optional[datetime.date]:
        dt = self._epoch_to_datetime(value)
        if dt is None:
            return None
        return dt.date()

    @staticmethod
    def _decimal(value) -> Decimal:
        if value in (None, ""):
            return Decimal("0")
        return Decimal(str(value))

    def _determine_customer_is_active(self, category_id: Optional[int]) -> bool:
        if not category_id:
            return True
        try:
            category_name = self.client_category_map.get(int(category_id), "")
        except (TypeError, ValueError):
            category_name = ""
        normalized = category_name.strip().lower()
        if not normalized:
            return True
        if "past" in normalized or "inactive" in normalized or "former" in normalized:
            return False
        if "current" in normalized or "active" in normalized:
            return True
        return True

    def _get_payment_term(self, days: Optional[int]) -> PaymentTerm:
        normalized_days = days if isinstance(days, int) and days > 0 else 30
        if normalized_days not in self.payment_term_by_days:
            name = f"Net {normalized_days}"
            term, _ = PaymentTerm.objects.get_or_create(
                days=normalized_days,
                defaults={"name": name, "description": f"Payment due in {normalized_days} days"},
            )
            self.payment_term_by_days[normalized_days] = term
        return self.payment_term_by_days[normalized_days]

    def _prepare_default_payment_terms(self) -> None:
        for days in (14, 30, 60, 90):
            self._get_payment_term(days)

    def _ensure_placeholder_pdf(self) -> str:
        """
        Ensure invoices have a placeholder PDF reference.

        We intentionally do not create files during a dry-run.
        """
        if self.dry_run:
            return self.PLACEHOLDER_PDF_NAME

        media_root_value = getattr(settings, "MEDIA_ROOT", None) or "media"
        media_root = Path(media_root_value)
        if not media_root.is_absolute():
            media_root = Path.cwd() / media_root

        placeholder_path = media_root / self.PLACEHOLDER_PDF_NAME
        placeholder_dir = placeholder_path.parent
        placeholder_dir.mkdir(parents=True, exist_ok=True)
        if not placeholder_path.exists():
            placeholder_path.write_bytes(b"")
        return self.PLACEHOLDER_PDF_NAME

    def _resolve_project_from_slips(self, invoice_rowid: int) -> Optional[Project]:
        cursor = self.connection.execute(
            "SELECT invoicedProjectID, projectID FROM TimeSlip "
            "WHERE invoiceID = ? AND (invoicedProjectID IS NOT NULL OR projectID IS NOT NULL)",
            (invoice_rowid,),
        )
        for row in cursor.fetchall():
            raw_id = row["invoicedProjectID"] or row["projectID"]
            if raw_id in (None, "", 0):
                continue
            try:
                candidate_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            project = self.project_by_rowid.get(candidate_id)
            if not project:
                project = Project.objects.filter(external_id=str(candidate_id)).first()
            if project:
                if candidate_id not in self.project_by_rowid:
                    self.project_by_rowid[candidate_id] = project
                return project
        return None

    def _build_company_name(self, row: sqlite3.Row) -> str:
        company_name = self._clean_str(row["company"])
        if company_name:
            return company_name

        parts = [
            self._clean_str(row["prefix"]),
            self._clean_str(row["firstName"]),
            self._clean_str(row["middleName"]),
            self._clean_str(row["lastName"]),
            self._clean_str(row["suffix"]),
        ]
        fallback_name = " ".join(part for part in parts if part).strip()
        return fallback_name or f"Client {row['_rowid']}"

    def _find_matching_company_by_tax_id(self, tax_number: str) -> Optional[Company]:
        normalized_tax_id = _normalize_company_tax_id(tax_number)
        if not normalized_tax_id:
            return None

        for company in Company.objects.exclude(customer_information_file_number=""):
            if _normalize_company_tax_id(company.customer_information_file_number) == normalized_tax_id:
                return company
        return None

    def _find_matching_company_by_name_and_email(self, company_name: str, contact_email: str) -> Optional[Company]:
        normalized_name = _normalize_company_name(company_name)
        normalized_email = _normalize_company_contact_email(contact_email)
        if not normalized_name or not normalized_email:
            return None

        candidate_companies = Company.objects.exclude(name="").exclude(contact_email="")
        for company in candidate_companies:
            if _normalize_company_name(company.name) != normalized_name:
                continue
            if _normalize_company_contact_email(company.contact_email) != normalized_email:
                continue
            return company
        return None

    def _resolve_company_for_customer_import(
        self,
        *,
        customer: Optional[Customer],
        company_name: str,
        tax_number: str = "",
        contact_email: str = "",
    ) -> tuple[Company, Address]:
        if customer and customer.company:
            company = customer.company
            return company, company.address or Address()

        company = self._find_matching_company_by_tax_id(tax_number)
        if not company:
            company = self._find_matching_company_by_name_and_email(company_name, contact_email)
        if company:
            return company, company.address or Address()

        return Company(name=company_name), Address()

    def _upsert_customer_for_import(
        self,
        *,
        rowid: int,
        external_id: str,
        customer: Optional[Customer],
        company: Company,
        currency: Optional[Currency],
        payment_term: PaymentTerm,
        company_name: str,
        is_active: bool,
    ) -> Customer:
        contact_email = company.contact_email.strip() if company.contact_email else ""
        contact_name = company.contact_name.strip() if company.contact_name else company_name

        if customer:
            if not self.update_existing:
                # Keep mapping for downstream relations but don't modify existing records.
                self.customer_by_rowid[rowid] = customer
                return customer
            customer.issuer = self.issuer
            customer.company = company
            customer.currency = currency
            customer.payment_term = payment_term
            if contact_email:
                customer.billing_email = contact_email
            if contact_name:
                customer.billing_contact_name = contact_name
            customer.is_active = is_active
            customer.save()
        else:
            customer = Customer.objects.create(
                issuer=self.issuer,
                company=company,
                external_id=external_id,
                currency=currency,
                payment_term=payment_term,
                billing_email=contact_email,
                billing_contact_name=contact_name,
                is_active=is_active,
            )

        self.customer_by_rowid[rowid] = customer
        return customer

    # ------------------------------------------------------------------
    # Reference imports
    # ------------------------------------------------------------------

    def _import_currencies(self) -> None:
        cursor = self.connection.execute(
            "SELECT _rowid, name, currencyCode, currencySymbol, exchangeRateToBase, "
            "exchangeRateDate, isBaseCurrency FROM Currency WHERE currencyCode <> ''"
        )
        base_currency: Optional[Currency] = Currency.objects.filter(is_base=True).first()
        seen_base = base_currency is not None

        for row in cursor.fetchall():
            code = self._clean_str(row["currencyCode"]).upper()
            if not code:
                continue

            currency, created = Currency.objects.get_or_create(
                code=code,
                defaults={
                    "name": self._clean_str(row["name"]) or code,
                    "symbol": self._clean_str(row["currencySymbol"]),
                    "exchange_rate_to_base": self._decimal(row["exchangeRateToBase"]) or Decimal("1"),
                    "is_base": bool(row["isBaseCurrency"]),
                },
            )

            if not created and self.update_existing:
                currency.name = self._clean_str(row["name"]) or currency.name
                currency.symbol = self._clean_str(row["currencySymbol"]) or currency.symbol
                rate = self._decimal(row["exchangeRateToBase"])
                if rate > 0:
                    currency.exchange_rate_to_base = rate
                if bool(row["isBaseCurrency"]):
                    currency.is_base = True

            if created or self.update_existing:
                last_updated = self._epoch_to_datetime(row["exchangeRateDate"])
                if last_updated:
                    currency.last_updated = last_updated

            # Determine base currency if Billings marks it or rate equals 1.
            if created or self.update_existing:
                is_base = bool(row["isBaseCurrency"])
                if not is_base and not seen_base:
                    rate = float(row["exchangeRateToBase"] or 0)
                    is_base = abs(rate - 1) < 1e-6
                if is_base and not currency.is_base:
                    currency.is_base = True

            currency.save()
            self.currency_by_rowid[int(row["_rowid"])] = currency
            if currency.is_base:
                seen_base = True

        if not seen_base and self.currency_by_rowid:
            # Mark first currency as base to satisfy schema expectations.
            first_currency = next(iter(self.currency_by_rowid.values()))
            first_currency.is_base = True
            first_currency.save()

    # ------------------------------------------------------------------
    # Customer import
    # ------------------------------------------------------------------

    def _import_customers(self) -> None:
        cursor = self.connection.execute("SELECT * FROM Client")
        placeholder_pdf = self._ensure_placeholder_pdf()

        for row in cursor.fetchall():
            self.customer_total += 1
            external_id = str(row["_rowid"])
            customer = Customer.objects.filter(external_id=external_id).first()

            company_name = self._build_company_name(row)

            tax_number = self._clean_str(row["taxNumber"])
            full_address = self._clean_str(row["addressFormatted"])
            category_id = row["clientCategoryID"]
            is_active = self._determine_customer_is_active(category_id)
            status_key = "active" if is_active else "inactive"
            self.customer_status_counts[status_key] += 1

            # If customer already exists and we aren't updating, skip early
            if customer and not self.update_existing:
                self.customer_by_rowid[int(row["_rowid"])] = customer
                continue

            company, address = self._resolve_company_for_customer_import(
                customer=customer,
                company_name=company_name,
                tax_number=tax_number,
                contact_email=self._clean_str(row["email"]),
            )

            # Update address
            address.street = self._clean_str(row["addressStreet"])
            address.city = self._clean_str(row["addressCity"])
            address.state = self._clean_str(row["addressState"])
            address.postal_code = self._clean_str(row["addressZIP"])
            address.country = self._clean_str(row["addressCountry"])
            address.full_address = full_address or "\n".join(
                filter(
                    None,
                    [
                        address.street,
                        " ".join(filter(None, [address.postal_code, address.city])).strip(),
                        " ".join(filter(None, [address.state, address.country])).strip(),
                    ],
                )
            )
            address.save()

            company.name = company_name
            company.address = address
            company.contact_name = self._clean_str(row["nickName"]) or company_name
            company.contact_email = self._clean_str(row["email"]) or company.contact_email
            company.contact_cc_email = company.contact_cc_email or ""
            company.contact_phone_number = company.contact_phone_number or ""
            company.contact_country = company.contact_country or ""
            company.customer_information_file_number = tax_number or company.customer_information_file_number or ""
            company.save()

            currency = self.currency_by_rowid.get(int(row["currentCurrencyID"])) if row["currentCurrencyID"] else None
            if not currency:
                currency = next(iter(self.currency_by_rowid.values()), None)

            payment_term = self._derive_payment_term_for_client(int(row["_rowid"]))
            self._upsert_customer_for_import(
                rowid=int(row["_rowid"]),
                external_id=external_id,
                customer=customer,
                company=company,
                currency=currency,
                payment_term=payment_term,
                company_name=company_name,
                is_active=is_active,
            )

        # Store placeholder PDF path for invoices to reuse later.
        self.placeholder_pdf = placeholder_pdf
        note = " (dry-run, changes rolled back)" if self.dry_run else ""
        self.stdout.write(
            f"Customers processed: {self.customer_total} "
            f"(active {self.customer_status_counts['active']}, inactive {self.customer_status_counts['inactive']}){note}"
        )

    def _derive_payment_term_for_client(self, client_rowid: int) -> PaymentTerm:
        cursor = self.connection.execute(
            "SELECT invoiceDate, dueDate FROM Invoice "
            "WHERE clientID = ? AND invoiceDate IS NOT NULL AND dueDate IS NOT NULL "
            "AND invoiceDate > 0 AND dueDate > 0 "
            "ORDER BY invoiceDate ASC LIMIT 1",
            (client_rowid,),
        )
        row = cursor.fetchone()
        if row:
            issued = self._epoch_to_date(row["invoiceDate"])
            due = self._epoch_to_date(row["dueDate"])
            if issued and due:
                days = (due - issued).days
                if 0 < days <= 180:
                    return self._get_payment_term(days)
        return self._get_payment_term(None)

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def _import_projects(self) -> None:
        cursor = self.connection.execute("SELECT * FROM Project")
        for row in cursor.fetchall():
            self.project_total += 1
            external_id = str(row["_rowid"])
            client_id = int(row["clientID"]) if row["clientID"] else None
            if not client_id or client_id not in self.customer_by_rowid:
                self.stdout.write(self.style.WARNING(f"Skipping project {external_id}: missing client {client_id}"))
                self.project_skipped_missing_customer += 1
                continue

            customer = self.customer_by_rowid[client_id]
            project_code = self._clean_str(row["projectCode"])
            if not project_code:
                project_code = f"BP-{external_id}"

            project = Project.objects.filter(external_id=external_id).first()
            status = Project.STATUS_ACTIVE if int(row["stateID"] or 0) == 200 else Project.STATUS_INACTIVE
            defaults = {
                "customer": customer,
                "title": self._clean_str(row["name"]) or project_code,
                "status": status,
                "project_code": project_code,
                "comment": self._clean_str(row["objective"]),
                "billing_reference": self._clean_str(row["poNumber"]),
                "payment_term": customer.payment_term,
            }

            if project:
                if not self.update_existing:
                    self.project_by_rowid[int(row["_rowid"])] = project
                    self.project_updated += 0
                    continue
                for field, value in defaults.items():
                    setattr(project, field, value)
                project.save()
                self.project_updated += 1
            else:
                project = Project.objects.create(external_id=external_id, **defaults)
                self.project_created += 1

            self.project_by_rowid[int(row["_rowid"])] = project
        projects_after = Project.objects.filter(customer__issuer=self.issuer).count()
        note = " (dry-run, changes rolled back)" if self.dry_run else ""
        self.stdout.write(
            "Projects processed: "
            f"{self.project_total} total "
            f"(created {self.project_created}, updated {self.project_updated}, "
            f"skipped {self.project_skipped_missing_customer}) - "
            f"issuer count {self.projects_before} -> {projects_after}{note}"
        )

    # ------------------------------------------------------------------
    # Invoices
    # ------------------------------------------------------------------

    def _import_invoices(self) -> None:
        cursor = self.connection.execute("SELECT * FROM Invoice")
        for row in cursor.fetchall():
            self.invoice_total += 1
            external_id = str(row["_rowid"])
            client_id = int(row["clientID"]) if row["clientID"] else None
            if not client_id or client_id not in self.customer_by_rowid:
                self.stdout.write(self.style.WARNING(f"Skipping invoice {external_id}: missing client {client_id}"))
                continue

            customer = self.customer_by_rowid[client_id]
            project = None
            if row["projectID"]:
                project_id = int(row["projectID"])
                project = self.project_by_rowid.get(project_id)
                if project:
                    self.invoice_with_project_direct += 1

            if project is None:
                inferred_project = self._resolve_project_from_slips(int(row["_rowid"]))
                if inferred_project:
                    project = inferred_project
                    self.invoice_with_project_inferred += 1

            if project is None:
                self.invoice_missing_project += 1

            invoice = Invoice.objects.filter(external_id=external_id).first()
            status = self._map_invoice_state(row["state"])

            issued_date = self._epoch_to_date(row["invoiceDate"])
            due_date = self._epoch_to_date(row["dueDate"])
            sent_date = self._epoch_to_date(row["sentDate"])

            # Prefer invoice-level currency/rate if present, falling back to customer's.
            currency = customer.currency
            invoice_currency = currency
            try:
                # Billings typically stores a currency reference per invoice.
                currency_id = row["currencyID"]  # may raise KeyError if column absent
            except Exception:
                currency_id = None
            if currency_id not in (None, "", 0):
                try:
                    invoice_currency = self.currency_by_rowid.get(int(currency_id)) or invoice_currency
                except (TypeError, ValueError):
                    pass
            # Some exports may include a currency code instead of an ID.
            if not invoice_currency:
                try:
                    code = self._clean_str(row["currencyCode"]).upper()
                    if code:
                        invoice_currency = Currency.objects.filter(code=code).first() or invoice_currency
                except Exception:
                    pass

            # Exchange rate: use per-invoice rate if provided, else currency's rate (1 for base).
            exchange_rate = Decimal("1")
            if invoice_currency and invoice_currency.is_base:
                exchange_rate = Decimal("1")
            else:
                rate = None
                for rate_field in ("exchangeRateToBase", "exchangeRate"):
                    try:
                        raw = row[rate_field]
                        if raw not in (None, "", 0):
                            candidate = self._decimal(raw)
                            if candidate > 0:
                                rate = candidate
                                break
                    except Exception:
                        continue
                if rate and rate > 0:
                    exchange_rate = rate
                else:
                    exchange_rate = (invoice_currency.exchange_rate_to_base if invoice_currency else Decimal("1"))
            discount_value = self._decimal(row["discount"])
            tax_value = self._decimal(row["tax1"])
            secondary_tax_rate = self._decimal(row["tax2"])
            uses_secondary_tax = bool(row["useTax2"])
            secondary_tax_name = self._clean_str(row["tax2Name"])

            defaults = {
                "issuer": self.issuer,
                "customer": customer,
                "project": project,
                "bank_account": get_default_bank_account(self.issuer),
                "reference_number": self._clean_str(row["invoiceNumber"]) or f"BP-{external_id}",
                "status": status,
                "discount_value": discount_value,
                "issued_date": issued_date,
                "due_date": due_date,
                "sent_date": sent_date,
                "comment": self._clean_str(row["comment"]),
                "currency": invoice_currency,
                "exchange_rate": exchange_rate,
                # Use cached invoice total (invoice currency) converted using determined rate.
                "base_currency_total": self._decimal(row["totalCached"]) * exchange_rate if row["totalCached"] else Decimal("0"),
                "sub_total": Decimal("0"),
                "tax_amount": Decimal("0"),
                "tax_base": Decimal("0"),
                "tax_value": tax_value,
                "secondary_tax_rate": secondary_tax_rate,
                "secondary_tax_name": secondary_tax_name,
                "uses_secondary_tax": uses_secondary_tax,
                "total_due": Decimal("0"),
                "template_identifier": str(row["invoiceHtmlID"]) if row["invoiceHtmlID"] else "",
            }

            if invoice:
                if not self.update_existing:
                    # Keep mapping for payments/applications reconciliation but avoid modifying existing invoice.
                    self.invoice_by_rowid[int(row["_rowid"])] = invoice
                    self.invoice_state_by_rowid[int(row["_rowid"])] = row["state"]
                    continue
                for field, value in defaults.items():
                    setattr(invoice, field, value)
                if not invoice.pdf_document:
                    invoice.pdf_document = self.placeholder_pdf
                invoice.save()
            else:
                invoice = Invoice(external_id=external_id, **defaults)
                invoice.pdf_document = self.placeholder_pdf
                invoice.save()

            self.invoice_by_rowid[int(row["_rowid"])] = invoice
            self.invoice_state_by_rowid[int(row["_rowid"])] = row["state"]
        note = " (dry-run, changes rolled back)" if self.dry_run else ""
        self.stdout.write(
            "Invoices processed: "
            f"{self.invoice_total} total "
            f"(project direct {self.invoice_with_project_direct}, inferred {self.invoice_with_project_inferred}, "
            f"missing {self.invoice_missing_project}){note}"
        )

    def _map_invoice_state(self, state: Optional[int]) -> str:
        state_value = int(state or 0)
        mapping = {
            102: Invoice.STATUS_INVOICED,
        }
        return mapping.get(state_value, Invoice.STATUS_DRAFT)

    # ------------------------------------------------------------------
    # Time slips -> Order lines
    # ------------------------------------------------------------------

    def _import_time_slips(self) -> None:
        cursor = self.connection.execute("SELECT * FROM TimeSlip WHERE invoiceID IS NOT NULL")
        for row in cursor.fetchall():
            invoice_id = int(row["invoiceID"])
            if invoice_id not in self.invoice_by_rowid:
                self.stdout.write(self.style.WARNING(f"Skipping slip {row['_rowid']}: missing invoice {invoice_id}"))
                continue

            invoice = self.invoice_by_rowid[invoice_id]
            external_id = str(row["_rowid"])
            if OrderLine.objects.filter(external_id=external_id).exists():
                continue

            line_type = self._map_line_type(row["typeID"])
            description = self._clean_str(row["name"])
            notes_parts: List[str] = []
            slip_comment = self._clean_str(row["comment"])
            if slip_comment:
                notes_parts.append(slip_comment)

            quantity = Decimal("0")
            duration_seconds = int(row["durationCached"] or 0)
            if line_type == OrderLine.LINE_TYPE_TIME:
                quantity = (Decimal(duration_seconds) / Decimal("3600")).quantize(
                    Decimal("0.001"), rounding=ROUND_HALF_UP
                )
            else:
                units_value = self._decimal(row["units"])
                quantity = units_value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

            unit_price = self._decimal(row["rate"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            raw_total_value = row["totalCached"] if row["totalCached"] not in (None, "") else row["total"]
            cached_total = self._decimal(raw_total_value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            manual_total = line_type in {OrderLine.LINE_TYPE_FLAT, OrderLine.LINE_TYPE_EXPENSE}
            computed_total = (quantity * unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if manual_total:
                line_total = cached_total
            elif cached_total and cached_total != computed_total:
                manual_total = True
                line_total = cached_total
            else:
                line_total = computed_total

            time_entries = self.time_entries_by_slip.get(int(row["_rowid"]))
            time_entry_ids: List[str] = []
            if time_entries:
                for entry in time_entries:
                    uuid = self._clean_str(entry["uuid"])
                    comment = self._clean_str(entry["comment"])
                    if comment:
                        notes_parts.append(comment)
                    if uuid:
                        time_entry_ids.append(uuid)

            notes_text = "\n".join(filter(None, notes_parts)).strip()
            created_dt = self._epoch_to_datetime(row["createDate"])
            updated_dt = self._epoch_to_datetime(row["modifyDate"]) or created_dt

            order_line = OrderLine.objects.create(
                invoice=invoice,
                external_id=external_id,
                line_type=line_type,
                description=description,
                quantity=quantity,
                duration_seconds=duration_seconds,
                unit_price=unit_price,
                line_total=line_total,
                manual_total=manual_total,
                notes=notes_text,
                time_entry_external_id=", ".join(time_entry_ids),
                created_at=created_dt or timezone.now(),
                updated_at=updated_dt or timezone.now(),
            )
            if created_dt or updated_dt:
                OrderLine.objects.filter(pk=order_line.pk).update(
                    created_at=created_dt or order_line.created_at,
                    updated_at=updated_dt or order_line.updated_at,
                )
                order_line.created_at = created_dt or order_line.created_at
                order_line.updated_at = updated_dt or order_line.updated_at

            self.invoice_lines[int(row["invoiceID"])].append(order_line)

    @staticmethod
    def _map_line_type(type_id: Optional[int]) -> str:
        mapping = {
            100: OrderLine.LINE_TYPE_TIME,
            200: OrderLine.LINE_TYPE_FLAT,
            300: OrderLine.LINE_TYPE_QUANTITY,
            400: OrderLine.LINE_TYPE_EXPENSE,
        }
        return mapping.get(int(type_id or 0), OrderLine.LINE_TYPE_QUANTITY)

    def _finalize_invoice_totals(self) -> None:
        for invoice_rowid, invoice in self.invoice_by_rowid.items():
            lines = self.invoice_lines.get(invoice_rowid) or list(invoice.orderline_set.all())
            invoice.calculate_totals(lines)

            # base currency total uses current exchange rate
            exchange_rate = invoice.exchange_rate or Decimal("1")
            invoice.base_currency_total = (invoice.total_due * exchange_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            invoice.save(
                update_fields=[
                    "sub_total",
                    "discount_amount",
                    "tax_base",
                    "tax_amount",
                    "total_due",
                    "base_currency_total",
                ]
            )

    def _finalize_payment_statuses(self) -> None:
        """Set payment.status based on actual applications rather than cached fields.

        Some Billings exports have `cachedAppliedAmount` as 0 while applications
        exist. After importing `PaymentInvoiceEntry` rows, reflect that reality.
        """
        for payment in self.payment_by_rowid.values():
            applications = self.payment_applications_map.get(payment.id, [])
            applied_total = sum((app.amount_applied for app in applications), Decimal("0")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            desired = Payment.STATUS_APPLIED if applied_total > Decimal("0") else Payment.STATUS_PENDING
            if payment.status != desired:
                payment.status = desired
                payment.save(update_fields=["status"])

    # ------------------------------------------------------------------
    # Payments
    # ------------------------------------------------------------------

    def _import_payments(self) -> None:
        cursor = self.connection.execute("SELECT * FROM Payment")
        for row in cursor.fetchall():
            external_id = str(row["_rowid"])
            client_id = int(row["clientID"]) if row["clientID"] else None
            if not client_id or client_id not in self.customer_by_rowid:
                self.stdout.write(self.style.WARNING(f"Skipping payment {external_id}: missing client {client_id}"))
                continue

            customer = self.customer_by_rowid[client_id]
            project = None
            if row["projectID"]:
                project_id = int(row["projectID"])
                project = self.project_by_rowid.get(project_id)

            payment = Payment.objects.filter(external_id=external_id).first()
            amount = self._decimal(row["total"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            base_amount = self._decimal(row["baseCurrencyTotal"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            exchange_rate = customer.currency.exchange_rate_to_base if customer.currency else Decimal("1")
            if amount and base_amount and amount != Decimal("0"):
                exchange_rate = (base_amount / amount).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
            base_currency_amount = (
                base_amount if base_amount else (amount * exchange_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            )
            memo = self._clean_str(row["comment"])
            method_label = ""
            if row["methodID"]:
                try:
                    method_label = self.payment_method_labels.get(int(row["methodID"]), "")
                except (TypeError, ValueError):
                    method_label = ""
            if method_label:
                memo = f"{memo}\nMethod: {method_label}" if memo else f"Method: {method_label}"

            defaults = {
                "issuer": self.issuer,
                "customer": customer,
                "project": project,
                "currency": customer.currency,
                "amount": amount,
                "exchange_rate": exchange_rate,
                "base_currency_amount": base_currency_amount,
                "received_at": self._epoch_to_date(row["createDate"]) or self.now_date,
                "status": Payment.STATUS_APPLIED if self._decimal(row["cachedAppliedAmount"]) > 0 else Payment.STATUS_PENDING,
                "memo": memo,
            }

            if payment:
                if not self.update_existing:
                    self.payment_by_rowid[int(row["_rowid"])] = payment
                    continue
                for field, value in defaults.items():
                    setattr(payment, field, value)
                payment.save()
            else:
                payment = Payment.objects.create(external_id=external_id, **defaults)

            self.payment_by_rowid[int(row["_rowid"])] = payment

    def _import_payment_applications(self) -> None:
        cursor = self.connection.execute("SELECT * FROM PaymentInvoiceEntry")
        for row in cursor.fetchall():
            external_id = str(row["_rowid"])
            payment_id = int(row["paymentID"]) if row["paymentID"] else None
            invoice_id = int(row["invoiceID"]) if row["invoiceID"] else None

            payment = self.payment_by_rowid.get(payment_id)
            invoice = self.invoice_by_rowid.get(invoice_id)
            if not payment or not invoice:
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipping payment allocation {external_id}: payment {payment_id} or invoice {invoice_id} missing"
                    )
                )
                continue

            application = PaymentApplication.objects.filter(external_id=external_id).first()
            amount_applied = self._decimal(row["amountApplied"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            applied_at = self._epoch_to_datetime(row["modifyDate"]) or self._epoch_to_datetime(row["createDate"])

            if application:
                if not self.update_existing:
                    # Use stored application as-is for reconciliation and totals.
                    self.payment_applications_map[payment.id].append(application)
                    self.applied_amounts_by_invoice[invoice.id] += application.amount_applied
                    continue
                application.payment = payment
                application.invoice = invoice
                application.amount_applied = amount_applied
                if applied_at:
                    application.applied_at = applied_at
                application.save()
            else:
                application = PaymentApplication.objects.create(
                    external_id=external_id,
                    payment=payment,
                    invoice=invoice,
                    amount_applied=amount_applied,
                    applied_at=applied_at or timezone.now(),
                )
                if applied_at:
                    PaymentApplication.objects.filter(pk=application.pk).update(applied_at=applied_at)
                    application.applied_at = applied_at

            self.payment_applications_map[payment.id].append(application)
            self.applied_amounts_by_invoice[invoice.id] += amount_applied

    def _finalize_invoice_statuses(self) -> None:
        today = self.now_date
        for invoice in self.invoice_by_rowid.values():
            applied = self.applied_amounts_by_invoice.get(invoice.id, Decimal("0"))
            remaining = (invoice.total_due - applied).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if remaining <= Decimal("0.01"):
                desired_status = Invoice.STATUS_PAID
            elif invoice.due_date and invoice.due_date < today and remaining > Decimal("0.01"):
                desired_status = Invoice.STATUS_OVERDUE
            else:
                desired_status = Invoice.STATUS_INVOICED

            if invoice.status != desired_status:
                invoice.status = desired_status
                invoice.save(update_fields=["status"])

    # ------------------------------------------------------------------
    # Statements
    # ------------------------------------------------------------------

    def _import_statements(self) -> None:
        cursor = self.connection.execute("SELECT * FROM Statement")
        for row in cursor.fetchall():
            external_id = str(row["_rowid"])
            client_id = int(row["clientID"]) if row["clientID"] else None
            if not client_id or client_id not in self.customer_by_rowid:
                self.stdout.write(self.style.WARNING(f"Skipping statement {external_id}: missing client {client_id}"))
                continue

            customer = self.customer_by_rowid[client_id]
            statement = Statement.objects.filter(external_id=external_id).first()
            defaults = {
                "issuer": self.issuer,
                "customer": customer,
                "statement_number": self._clean_str(row["statementNumber"]),
                "from_date": self._epoch_to_date(row["fromDate"]),
                "to_date": self._epoch_to_date(row["toDate"]),
                "sent_date": self._epoch_to_date(row["sentDate"]),
                "total_balance": self._decimal(row["totalBalance"]),
                "current_due": self._decimal(row["currentDue"]),
                "overdue_30": self._decimal(row["overdue30Days"]),
                "overdue_60": self._decimal(row["overdue60Days"]),
                "overdue_90": self._decimal(row["overdue90Days"]),
                "overdue_over_90": self._decimal(row["overdueOver90Days"]),
                "comment": self._clean_str(row["comment"]),
            }

            if statement:
                if not self.update_existing:
                    continue
                for field, value in defaults.items():
                    setattr(statement, field, value)
                statement.save()
            else:
                Statement.objects.create(external_id=external_id, **defaults)
