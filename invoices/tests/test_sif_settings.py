from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from invoices.models import Company, Issuer, IssuerSifSettings
from invoices.services.sif import (
    get_sif_readiness,
    get_sif_settings,
    is_sif_effectively_active,
    is_valid_spanish_tax_id,
    normalize_spanish_tax_id,
)


class IssuerSifSettingsModelTests(TestCase):
    def _issuer(self, name='Issuer', tax_id=''):
        company = Company.objects.create(name=name, customer_information_file_number=tax_id)
        return Issuer.objects.create(company=company)

    def test_defaults_are_disabled_and_non_active(self):
        settings = IssuerSifSettings.objects.create(issuer=self._issuer())

        self.assertFalse(settings.enabled)
        self.assertEqual(settings.tax_country, IssuerSifSettings.TaxCountry.UNSPECIFIED)
        self.assertEqual(settings.mode, IssuerSifSettings.SifMode.VERI_FACTU)
        self.assertEqual(settings.aeat_environment, IssuerSifSettings.AeatEnvironment.TEST)
        self.assertEqual(settings.operational_status, IssuerSifSettings.OperationalStatus.NOT_READY)
        self.assertFalse(is_sif_effectively_active(settings.issuer))

    def test_persists_both_sif_modes(self):
        issuer_one = self._issuer('VeriFactu SL', '12345678Z')
        issuer_two = self._issuer('Local SIF SL', '12345678Z')

        veri_factu = IssuerSifSettings.objects.create(
            issuer=issuer_one,
            tax_country=IssuerSifSettings.TaxCountry.SPAIN,
            mode=IssuerSifSettings.SifMode.VERI_FACTU,
        )
        no_veri_factu = IssuerSifSettings.objects.create(
            issuer=issuer_two,
            tax_country=IssuerSifSettings.TaxCountry.SPAIN,
            mode=IssuerSifSettings.SifMode.NO_VERI_FACTU,
        )

        self.assertEqual(veri_factu.mode, 'VERI_FACTU')
        self.assertEqual(no_veri_factu.mode, 'NO_VERI_FACTU')

    def test_deadline_helper_returns_corporate_and_autonomo_deadlines(self):
        settings = IssuerSifSettings.objects.create(issuer=self._issuer())

        settings.deadline_category = IssuerSifSettings.DeadlineCategory.CORPORATE
        self.assertEqual(settings.informational_deadline, date(2027, 1, 1))

        settings.deadline_category = IssuerSifSettings.DeadlineCategory.AUTONOMO_OTHER
        self.assertEqual(settings.informational_deadline, date(2027, 7, 1))

    def test_model_validation_blocks_enabled_non_spanish_issuer(self):
        settings = IssuerSifSettings(
            issuer=self._issuer(tax_id='12345678Z'),
            tax_country=IssuerSifSettings.TaxCountry.OTHER,
            enabled=True,
        )

        with self.assertRaises(ValidationError) as context:
            settings.full_clean()

        self.assertIn('enabled', context.exception.message_dict)

    def test_model_validation_blocks_enabled_spanish_issuer_with_invalid_tax_id(self):
        settings = IssuerSifSettings(
            issuer=self._issuer(tax_id='NOT-A-NIF'),
            tax_country=IssuerSifSettings.TaxCountry.SPAIN,
            enabled=True,
        )

        with self.assertRaises(ValidationError) as context:
            settings.full_clean()

        self.assertIn('enabled', context.exception.message_dict)


class SifServiceTests(TestCase):
    def _issuer(self, name, tax_id='12345678Z'):
        company = Company.objects.create(name=name, customer_information_file_number=tax_id)
        return Issuer.objects.create(company=company)

    def test_get_sif_settings_is_issuer_scoped(self):
        issuer_one = self._issuer('One SL')
        issuer_two = self._issuer('Two SL')

        settings_one = get_sif_settings(issuer_one)
        settings_two = get_sif_settings(issuer_two)
        settings_one.tax_country = IssuerSifSettings.TaxCountry.SPAIN
        settings_one.enabled = True
        settings_one.operational_status = IssuerSifSettings.OperationalStatus.READY
        settings_one.save()

        settings_two.refresh_from_db()
        self.assertNotEqual(settings_one.pk, settings_two.pk)
        self.assertFalse(settings_two.enabled)
        self.assertEqual(settings_two.tax_country, IssuerSifSettings.TaxCountry.UNSPECIFIED)

    def test_spanish_tax_id_normalization_and_validation(self):
        self.assertEqual(normalize_spanish_tax_id(' es-12345678 z '), 'ES12345678Z')
        self.assertTrue(is_valid_spanish_tax_id('12345678-Z'))
        self.assertTrue(is_valid_spanish_tax_id('X2482300-W'))
        self.assertTrue(is_valid_spanish_tax_id('A58818501'))
        self.assertFalse(is_valid_spanish_tax_id('12345678A'))
        self.assertFalse(is_valid_spanish_tax_id(''))

    def test_effective_activation_requires_spanish_enabled_valid_tax_id_and_ready_status(self):
        issuer = self._issuer('Ready SL')
        settings = get_sif_settings(issuer)
        settings.tax_country = IssuerSifSettings.TaxCountry.SPAIN
        settings.enabled = True
        settings.operational_status = IssuerSifSettings.OperationalStatus.READY
        settings.save()

        readiness = get_sif_readiness(issuer)
        self.assertTrue(readiness.effective_activation)
        self.assertTrue(is_sif_effectively_active(issuer))
        self.assertEqual(readiness.missing_prerequisites, ())

    def test_readiness_reports_missing_prerequisites_without_cross_issuer_bleed(self):
        spanish = self._issuer('Spanish SL', tax_id='12345678A')
        non_spanish = self._issuer('Belgian BV', tax_id='BE0123456789')
        spanish_settings = get_sif_settings(spanish)
        spanish_settings.tax_country = IssuerSifSettings.TaxCountry.SPAIN
        spanish_settings.enabled = True
        spanish_settings.save()
        non_spanish_settings = get_sif_settings(non_spanish)
        non_spanish_settings.tax_country = IssuerSifSettings.TaxCountry.OTHER
        non_spanish_settings.enabled = False
        non_spanish_settings.save()

        spanish_readiness = get_sif_readiness(spanish)
        non_spanish_readiness = get_sif_readiness(non_spanish)

        self.assertFalse(spanish_readiness.effective_activation)
        self.assertIn('valid_spanish_tax_id', spanish_readiness.missing_prerequisites)
        self.assertFalse(non_spanish_readiness.effective_activation)
        self.assertEqual(non_spanish_readiness.missing_prerequisites, ())
        self.assertFalse(non_spanish_readiness.is_spanish_issuer)
