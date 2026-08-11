from pathlib import Path

from django.test import TestCase

from invoices.models import Company, Issuer, IssuerSifSettings
from invoices.services.fiscal import (
    get_applicable_adapters,
    get_implementation_inventory,
    get_regime,
)
from invoices.services.sif import get_sif_settings


REPO_ROOT = Path(__file__).resolve().parents[2]


class FiscalRegistryTests(TestCase):
    def _issuer(self, name, tax_id='12345678Z'):
        company = Company.objects.create(
            name=name,
            customer_information_file_number=tax_id,
        )
        return Issuer.objects.create(company=company)

    def test_catalog_marks_ready_pre_live_regimes(self):
        ready = {spec.code for spec in get_implementation_inventory() if spec.implementation_ready}
        blocked = {spec.code for spec in get_implementation_inventory() if not spec.implementation_ready}

        self.assertIn('ES_SIF', ready)
        self.assertIn('FR_PDP', ready)
        self.assertIn('DE_EN16931', ready)
        self.assertIn('PL_KSEF', ready)
        self.assertIn('PEPPOL_BIS', ready)
        self.assertIn('ES_B2B', blocked)
        self.assertIn('SK_EFAKTURA', blocked)

    def test_ready_regimes_have_local_spec_paths(self):
        for spec in get_implementation_inventory():
            if not spec.implementation_ready:
                continue
            self.assertTrue(spec.local_spec_paths, spec.code)
            for relative in spec.local_spec_paths:
                self.assertTrue(
                    (REPO_ROOT / relative).exists(),
                    f'Missing local spec for {spec.code}: {relative}',
                )

    def test_es_sif_adapter_only_when_effectively_active(self):
        issuer = self._issuer('Ready SL')
        settings = get_sif_settings(issuer)
        settings.tax_country = IssuerSifSettings.TaxCountry.SPAIN
        settings.enabled = True
        settings.operational_status = IssuerSifSettings.OperationalStatus.READY
        settings.save()

        codes = {adapter.spec.code for adapter in get_applicable_adapters(issuer)}
        self.assertEqual(codes, {'ES_SIF'})

    def test_non_spanish_issuer_gets_no_adapters(self):
        issuer = self._issuer('Belgian BV', tax_id='BE0123456789')
        get_sif_settings(issuer)
        self.assertEqual(get_applicable_adapters(issuer), ())

    def test_get_regime_lookup(self):
        self.assertEqual(get_regime('PL_KSEF').status, 'live')
        with self.assertRaises(KeyError):
            get_regime('NOPE')
