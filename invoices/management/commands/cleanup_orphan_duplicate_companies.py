from dataclasses import dataclass
from typing import Optional

from django.core.management.base import BaseCommand

from invoices.company_deduplication import (
    _normalize_company_contact_email,
    _normalize_company_name,
    _normalize_company_tax_id,
)
from invoices.models import Company, Issuer


@dataclass(frozen=True)
class CompanyDuplicateGroup:
    match_type: str
    match_value: str
    matched_companies: tuple[Company, ...]
    companies: tuple[Company, ...]
    retained_companies: tuple[Company, ...]
    deletion_candidates: tuple[Company, ...]


class Command(BaseCommand):
    help = "Inspect candidate duplicate Company rows for orphan cleanup."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Delete orphan duplicate companies instead of running in dry-run mode.",
        )
        parser.add_argument(
            "--confirm-backup",
            action="store_true",
            help="Acknowledge that a full database backup has been completed before deletion.",
        )

    def handle(self, *args, **options):
        duplicate_groups = self._get_candidate_duplicate_groups()
        self.stdout.write(
            f"Dry-run summary: found {len(duplicate_groups)} candidate duplicate groups, "
            f"{sum(len(group.matched_companies) for group in duplicate_groups)} matched companies, "
            f"{sum(len(group.companies) for group in duplicate_groups)} orphan companies, and "
            f"{sum(len(group.deletion_candidates) for group in duplicate_groups)} companies that would be deleted."
        )

        for group in duplicate_groups:
            company_ids = ", ".join(str(company.id) for company in group.matched_companies)
            retained_ids = ", ".join(str(company.id) for company in group.retained_companies)
            deletion_ids = ", ".join(str(company.id) for company in group.deletion_candidates) or "none"
            self.stdout.write(
                f"[{group.match_type}] {group.match_value}: "
                f"matched={len(group.matched_companies)} orphan={len(group.companies)} "
                f"delete={len(group.deletion_candidates)} keep={retained_ids} "
                f"all_ids={company_ids} delete_ids={deletion_ids}"
            )

        if not options["apply"]:
            self.stdout.write(
                "Dry-run only. Re-run with --apply --confirm-backup after completing a full database backup to delete orphan duplicates."
            )
            return

        if not options["confirm_backup"]:
            self.stdout.write(
                self.style.ERROR(
                    "Deletion aborted: --confirm-backup is required when using --apply. Complete a full database backup first."
                )
            )
            return

        deleted_company_ids: list[int] = []
        for group in duplicate_groups:
            for company in group.deletion_candidates:
                deleted_company_ids.append(company.id)
                company.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {len(deleted_company_ids)} orphan duplicate companies: "
                f"{', '.join(str(company_id) for company_id in deleted_company_ids) or 'none'}"
            )
        )

    def _get_candidate_duplicate_groups(self) -> list[CompanyDuplicateGroup]:
        grouped_companies: dict[tuple[str, str], list[Company]] = {}

        for company in Company.objects.all().order_by("id"):
            dedupe_key = self._get_company_dedupe_key(company)
            if not dedupe_key:
                continue
            grouped_companies.setdefault(dedupe_key, []).append(company)

        duplicate_groups: list[CompanyDuplicateGroup] = []
        for (match_type, match_value), companies in grouped_companies.items():
            if len(companies) < 2:
                continue

            orphan_companies = [company for company in companies if self._is_orphan_company(company)]
            if not orphan_companies:
                continue

            retained_companies = [company for company in companies if company not in orphan_companies]
            deletion_candidates = orphan_companies
            if not retained_companies:
                retained_companies = orphan_companies[:1]
                deletion_candidates = orphan_companies[1:]

            duplicate_groups.append(
                CompanyDuplicateGroup(
                    match_type=match_type,
                    match_value=match_value,
                    matched_companies=tuple(companies),
                    companies=tuple(orphan_companies),
                    retained_companies=tuple(retained_companies),
                    deletion_candidates=tuple(deletion_candidates),
                )
            )

        return duplicate_groups

    def _get_company_dedupe_key(self, company: Company) -> Optional[tuple[str, str]]:
        normalized_tax_id = _normalize_company_tax_id(company.customer_information_file_number)
        if normalized_tax_id:
            return ("tax_id", normalized_tax_id)

        normalized_name = _normalize_company_name(company.name)
        normalized_email = _normalize_company_contact_email(company.contact_email)
        if normalized_name and normalized_email:
            return ("name_email", f"{normalized_name}|{normalized_email}")

        return None

    def _is_orphan_company(self, company: Company) -> bool:
        return (
            not company.customer_set.exists()
            and not Issuer.objects.filter(company=company).exists()
            and not company.default_for_profiles.exists()
        )
