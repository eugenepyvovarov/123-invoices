from typing import Dict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from invoices.models import (
    Company,
    Issuer,
    Customer,
    Project,
    Invoice,
    OrderLine,
    Payment,
    PaymentApplication,
)


class Command(BaseCommand):
    help = (
        "Delete all projects, customers, invoices, and payments for a single company "
        "(issuer) without deleting the company record itself. Useful to reset data "
        "prior to re-import."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--company-id",
            type=int,
            required=True,
            help="Company ID (issuer company) to clear data for.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without performing any deletions.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Actually perform deletions. Without this flag, the command aborts after showing counts.",
        )

    def handle(self, *args, **options):
        company_id = options["company_id"]
        dry_run = options["dry_run"]
        force = options["force"]

        try:
            company = Company.objects.get(pk=company_id)
        except Company.DoesNotExist as exc:
            raise CommandError(f"Company {company_id} does not exist") from exc

        issuer: Issuer = getattr(company, "issuer_profile", None)
        if not issuer:
            self.stdout.write(self.style.WARNING(f"Company {company_id} has no issuer; nothing to delete."))
            return

        # Build scoped querysets
        payments_qs = Payment.objects.filter(issuer=issuer)
        payment_apps_qs = PaymentApplication.objects.filter(payment__in=payments_qs)
        invoices_qs = Invoice.objects.filter(issuer=issuer)
        order_lines_qs = OrderLine.objects.filter(invoice__in=invoices_qs)
        projects_qs = Project.objects.filter(customer__issuer=issuer)
        customers_qs = Customer.objects.filter(issuer=issuer)

        counts: Dict[str, int] = {
            "payment_applications": payment_apps_qs.count(),
            "payments": payments_qs.count(),
            "order_lines": order_lines_qs.count(),
            "invoices": invoices_qs.count(),
            "projects": projects_qs.count(),
            "customers": customers_qs.count(),
        }

        self.stdout.write(
            f"Planned deletions for company {company.id} ({company.name}):\n"
            f"  PaymentApplications: {counts['payment_applications']}\n"
            f"  Payments:            {counts['payments']}\n"
            f"  OrderLines:          {counts['order_lines']}\n"
            f"  Invoices:            {counts['invoices']}\n"
            f"  Projects:            {counts['projects']}\n"
            f"  Customers:           {counts['customers']}\n"
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run: no changes made."))
            return

        if not force:
            raise CommandError("Refusing to delete without --force. Re-run with --dry-run to preview.")

        with transaction.atomic():
            # Delete in a safe order (children first when bypassing cascades for clarity)
            # Cascades would cover most of this, but explicit order gives clearer intent and counts.
            deleted_apps = payment_apps_qs.delete()[0]
            deleted_payments = payments_qs.delete()[0]
            deleted_order_lines = order_lines_qs.delete()[0]
            deleted_invoices = invoices_qs.delete()[0]
            deleted_projects = projects_qs.delete()[0]
            deleted_customers = customers_qs.delete()[0]

        self.stdout.write(
            self.style.SUCCESS(
                "Deletion completed. Rows removed (including cascades reported by Django):\n"
                f"  PaymentApplications: {deleted_apps}\n"
                f"  Payments:            {deleted_payments}\n"
                f"  OrderLines:          {deleted_order_lines}\n"
                f"  Invoices:            {deleted_invoices}\n"
                f"  Projects:            {deleted_projects}\n"
                f"  Customers:           {deleted_customers}"
            )
        )

