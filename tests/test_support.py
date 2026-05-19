from tests.support import AuthenticatedCompanyTestCase, IssuerUserTestCase


class IssuerUserTestCaseTests(IssuerUserTestCase):
    def test_create_user_with_issuers_creates_and_links_default_issuer(self):
        user = self.create_user_with_issuers()

        issuers = list(user.issuers.select_related('company'))
        self.assertEqual(len(issuers), 1)
        self.assertEqual(issuers[0].company.name, 'Test Company 2')
        self.assertEqual(issuers[0].company.customer_information_file_number, 'VAT0002')

    def test_create_user_with_issuers_links_all_supplied_issuers(self):
        issuer_a = self.create_issuer()
        issuer_b = self.create_issuer()

        user = self.create_user_with_issuers(issuers=[issuer_a, issuer_b])

        self.assertCountEqual(user.issuers.all(), [issuer_a, issuer_b])


class AuthenticatedCompanyTestCaseTests(AuthenticatedCompanyTestCase):
    def setUp(self):
        self.issuer = self.create_issuer()
        self.user = self.create_user_with_issuers(issuers=[self.issuer])

    def test_login_with_active_company_logs_in_and_sets_session(self):
        active_company_id = self.login_with_active_company(self.user, issuer=self.issuer)

        session = self.client.session
        self.assertEqual(session['_auth_user_id'], str(self.user.pk))
        self.assertEqual(session['active_company_id'], active_company_id)
        self.assertEqual(active_company_id, self.issuer.company_id)

    def test_set_active_company_uses_explicit_company_id(self):
        other_issuer = self.create_issuer()

        active_company_id = self.set_active_company(company_id=other_issuer.company_id)

        self.assertEqual(active_company_id, other_issuer.company_id)
        self.assertEqual(self.client.session['active_company_id'], other_issuer.company_id)

    def test_login_with_active_company_uses_explicit_company_id_override(self):
        other_issuer = self.create_issuer()

        active_company_id = self.login_with_active_company(
            self.user,
            issuer=self.issuer,
            company_id=other_issuer.company_id,
        )

        self.assertEqual(active_company_id, other_issuer.company_id)
        self.assertEqual(self.client.session['active_company_id'], other_issuer.company_id)
