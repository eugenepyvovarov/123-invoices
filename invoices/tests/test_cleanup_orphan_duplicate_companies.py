import io

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from accounts.models import Profile
from invoices.management.commands.cleanup_orphan_duplicate_companies import Command
from invoices.models import Company, Customer, Issuer


class CleanupOrphanDuplicateCompaniesGroupingTests(TestCase):
    def setUp(self):
        self.command = Command()

    def test_groups_companies_by_normalized_tax_id(self):
        Company.objects.create(name="Acme One", customer_information_file_number=" ES B-123 456 ")
        Company.objects.create(name="Acme Two", customer_information_file_number="esb-123456")
        Company.objects.create(name="Unique", customer_information_file_number="VAT-999")

        duplicate_groups = self.command._get_candidate_duplicate_groups()

        self.assertEqual(len(duplicate_groups), 1)
        self.assertEqual(duplicate_groups[0].match_type, "tax_id")
        self.assertEqual(duplicate_groups[0].match_value, "ESB-123456")
        self.assertEqual(len(duplicate_groups[0].companies), 2)

    def test_groups_by_name_and_email_when_tax_id_is_blank(self):
        first = Company.objects.create(name="  ACME   Studio ", contact_email=" Billing@Example.com ")
        second = Company.objects.create(name="acme studio", contact_email="billing@example.com")
        Company.objects.create(name="ACME Studio", contact_email="other@example.com")

        duplicate_groups = self.command._get_candidate_duplicate_groups()

        self.assertEqual(len(duplicate_groups), 1)
        self.assertEqual(duplicate_groups[0].match_type, "name_email")
        self.assertEqual(duplicate_groups[0].match_value, "acme studio|billing@example.com")
        self.assertEqual([company.id for company in duplicate_groups[0].companies], [first.id, second.id])

    def test_prefers_tax_id_grouping_over_name_and_email_fallback(self):
        first = Company.objects.create(
            name="Acme Studio",
            contact_email="billing@example.com",
            customer_information_file_number="VAT-123",
        )
        second = Company.objects.create(
            name="Acme Studio",
            contact_email="billing@example.com",
            customer_information_file_number=" vat-123 ",
        )

        duplicate_groups = self.command._get_candidate_duplicate_groups()

        self.assertEqual(len(duplicate_groups), 1)
        self.assertEqual(duplicate_groups[0].match_type, "tax_id")
        self.assertEqual([company.id for company in duplicate_groups[0].companies], [first.id, second.id])

    def test_ignores_companies_without_usable_dedupe_keys(self):
        Company.objects.create(name="Acme Studio", contact_email="")
        Company.objects.create(name="Acme Studio", contact_email="")

        duplicate_groups = self.command._get_candidate_duplicate_groups()

        self.assertEqual(duplicate_groups, [])

    def test_only_includes_orphan_companies_as_deletion_candidates(self):
        customer_company = Company.objects.create(name="Acme One", customer_information_file_number="VAT-123")
        orphan_company = Company.objects.create(name="Acme Two", customer_information_file_number=" vat-123 ")
        issuer_company = Company.objects.create(name="Acme Three", customer_information_file_number=" vat-123 ")

        Customer.objects.create(company=customer_company)
        Issuer.objects.create(company=issuer_company)

        duplicate_groups = self.command._get_candidate_duplicate_groups()

        self.assertEqual(len(duplicate_groups), 1)
        self.assertEqual(duplicate_groups[0].match_type, "tax_id")
        self.assertEqual([company.id for company in duplicate_groups[0].companies], [orphan_company.id])
        self.assertEqual([company.id for company in duplicate_groups[0].retained_companies], [customer_company.id, issuer_company.id])
        self.assertEqual([company.id for company in duplicate_groups[0].deletion_candidates], [orphan_company.id])

    def test_dry_run_reporting_includes_group_counts_and_deletion_totals(self):
        linked_company = Company.objects.create(name="Acme One", customer_information_file_number="VAT-123")
        linked_duplicate = Company.objects.create(name="Acme Two", customer_information_file_number=" vat-123 ")
        Customer.objects.create(company=linked_company)

        orphan_first = Company.objects.create(name="Beta Studio", contact_email="billing@example.com")
        orphan_second = Company.objects.create(name=" beta studio ", contact_email=" BILLING@example.com ")

        buffer = io.StringIO()

        call_command("cleanup_orphan_duplicate_companies", stdout=buffer)

        output = buffer.getvalue()
        self.assertIn(
            "Dry-run summary: found 2 candidate duplicate groups, 4 matched companies, 3 orphan companies, and 2 companies that would be deleted.",
            output,
        )
        self.assertIn(
            f"[tax_id] VAT-123: matched=2 orphan=1 delete=1 keep={linked_company.id} all_ids={linked_company.id}, {linked_duplicate.id} delete_ids={linked_duplicate.id}",
            output,
        )
        self.assertIn(
            f"[name_email] beta studio|billing@example.com: matched=2 orphan=2 delete=1 keep={orphan_first.id} all_ids={orphan_first.id}, {orphan_second.id} delete_ids={orphan_second.id}",
            output,
        )
        self.assertIn(
            "Dry-run only. Re-run with --apply --confirm-backup after completing a full database backup to delete orphan duplicates.",
            output,
        )

    def test_apply_requires_backup_confirmation(self):
        retained = Company.objects.create(name="Acme One", customer_information_file_number="VAT-123")
        duplicate = Company.objects.create(name="Acme Two", customer_information_file_number=" vat-123 ")

        buffer = io.StringIO()

        call_command("cleanup_orphan_duplicate_companies", "--apply", stdout=buffer)

        output = buffer.getvalue()
        self.assertIn(
            "Deletion aborted: --confirm-backup is required when using --apply. Complete a full database backup first.",
            output,
        )
        self.assertTrue(Company.objects.filter(id=retained.id).exists())
        self.assertTrue(Company.objects.filter(id=duplicate.id).exists())

    def test_apply_deletes_orphan_duplicates_after_explicit_confirmation(self):
        linked_company = Company.objects.create(name="Acme One", customer_information_file_number="VAT-123")
        linked_duplicate = Company.objects.create(name="Acme Two", customer_information_file_number=" vat-123 ")
        Customer.objects.create(company=linked_company)

        orphan_first = Company.objects.create(name="Beta Studio", contact_email="billing@example.com")
        orphan_second = Company.objects.create(name=" beta studio ", contact_email=" BILLING@example.com ")

        buffer = io.StringIO()

        call_command(
            "cleanup_orphan_duplicate_companies",
            "--apply",
            "--confirm-backup",
            stdout=buffer,
        )

        output = buffer.getvalue()
        self.assertIn(
            f"Deleted 2 orphan duplicate companies: {linked_duplicate.id}, {orphan_second.id}",
            output,
        )
        self.assertTrue(Company.objects.filter(id=linked_company.id).exists())
        self.assertFalse(Company.objects.filter(id=linked_duplicate.id).exists())
        self.assertTrue(Company.objects.filter(id=orphan_first.id).exists())
        self.assertFalse(Company.objects.filter(id=orphan_second.id).exists())

    def test_apply_does_not_delete_non_orphan_duplicate_companies(self):
        customer_company = Company.objects.create(name="Acme One", customer_information_file_number="VAT-123")
        issuer_company = Company.objects.create(name="Acme Two", customer_information_file_number=" vat-123 ")
        Customer.objects.create(company=customer_company)
        Issuer.objects.create(company=issuer_company)

        buffer = io.StringIO()

        call_command(
            "cleanup_orphan_duplicate_companies",
            "--apply",
            "--confirm-backup",
            stdout=buffer,
        )

        output = buffer.getvalue()
        self.assertIn(
            "Dry-run summary: found 0 candidate duplicate groups, 0 matched companies, 0 orphan companies, and 0 companies that would be deleted.",
            output,
        )
        self.assertIn("Deleted 0 orphan duplicate companies: none", output)
        self.assertTrue(Company.objects.filter(id=customer_company.id).exists())
        self.assertTrue(Company.objects.filter(id=issuer_company.id).exists())

    def test_apply_does_not_delete_duplicate_company_used_as_profile_default(self):
        retained = Company.objects.create(name="Acme One", customer_information_file_number="VAT-123")
        profile_company = Company.objects.create(name="Acme Two", customer_information_file_number=" vat-123 ")
        user = get_user_model().objects.create_user(username="profile-user")
        profile = Profile.objects.get(user=user)
        profile.default_company = profile_company
        profile.save(update_fields=["default_company"])

        buffer = io.StringIO()

        call_command(
            "cleanup_orphan_duplicate_companies",
            "--apply",
            "--confirm-backup",
            stdout=buffer,
        )

        output = buffer.getvalue()
        self.assertIn(
            "Dry-run summary: found 1 candidate duplicate groups, 2 matched companies, 1 orphan companies, and 1 companies that would be deleted.",
            output,
        )
        self.assertIn(
            f"Deleted 1 orphan duplicate companies: {retained.id}",
            output,
        )
        self.assertFalse(Company.objects.filter(id=retained.id).exists())
        self.assertTrue(Company.objects.filter(id=profile_company.id).exists())
