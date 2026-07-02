from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import ApiToken
from invoices.models import Company, Customer, Issuer, IssuerBankAccount, Project


class ApiResourceEndpointTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='api-user',
            email='api@example.com',
            password='test-password',
        )
        self.other_user = User.objects.create_user(
            username='other-api-user',
            email='other@example.com',
            password='test-password',
        )
        self.superuser = User.objects.create_superuser(
            username='api-admin',
            email='admin@example.com',
            password='test-password',
        )
        self.issuer = self._issuer('Alpha Company', self.user)
        self.other_issuer = self._issuer('Beta Company', self.other_user)
        self.bank_account = IssuerBankAccount.objects.create(
            issuer=self.issuer,
            label='Operating account',
            payment_method='Bank transfer',
            account_details='IBAN TEST',
            is_default=True,
        )
        self.other_bank_account = IssuerBankAccount.objects.create(
            issuer=self.other_issuer,
            label='Hidden account',
            is_default=True,
        )
        self.customer = Customer.objects.create(
            issuer=self.issuer,
            company=Company.objects.create(name='Acme Customer', contact_email='billing@acme.test'),
            external_id='cust-acme',
            billing_email='billing@acme.test',
        )
        self.other_customer = Customer.objects.create(
            issuer=self.other_issuer,
            company=Company.objects.create(name='Hidden Customer'),
            external_id='cust-hidden',
        )
        self.project = Project.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            title='Acme Migration',
            project_code='ACME-1',
            external_id='proj-acme',
        )
        self.other_project = Project.objects.create(
            issuer=self.other_issuer,
            customer=self.other_customer,
            title='Hidden Project',
            project_code='HIDDEN-1',
            external_id='proj-hidden',
        )
        _, self.token = ApiToken.issue(owner=self.user, name='Resource token')
        _, self.other_token = ApiToken.issue(owner=self.other_user, name='Other token')
        _, self.superuser_token = ApiToken.issue(owner=self.superuser, name='Admin token')

    def _issuer(self, company_name, user):
        issuer = Issuer.objects.create(company=Company.objects.create(name=company_name))
        issuer.users.add(user)
        return issuer

    def auth(self, token=None):
        return {'HTTP_AUTHORIZATION': f'Bearer {token or self.token}'}

    def result_ids(self, response):
        payload = response.json()
        results = payload['results'] if 'results' in payload else payload
        return {item['id'] for item in results}

    def test_me_includes_accessible_issuer_metadata(self):
        response = self.client.get(reverse('api:me'), **self.auth())

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['account']['id'], self.user.pk)
        self.assertEqual([issuer['id'] for issuer in payload['issuers']], [self.issuer.pk])
        self.assertEqual(payload['issuers'][0]['company']['name'], 'Alpha Company')
        self.assertEqual(payload['issuers'][0]['bank_accounts'][0]['id'], self.bank_account.pk)

    def test_issuer_and_bank_account_lists_are_account_scoped(self):
        issuer_response = self.client.get(reverse('api:issuer-list'), **self.auth())
        bank_response = self.client.get(reverse('api:bankaccount-list'), **self.auth())

        self.assertEqual(issuer_response.status_code, 200)
        self.assertEqual(bank_response.status_code, 200)
        self.assertEqual(self.result_ids(issuer_response), {self.issuer.pk})
        self.assertEqual(self.result_ids(bank_response), {self.bank_account.pk})

    def test_resource_detail_rejects_cross_account_objects(self):
        urls = [
            reverse('api:issuer-detail', args=[self.other_issuer.pk]),
            reverse('api:bankaccount-detail', args=[self.other_bank_account.pk]),
            reverse('api:customer-detail', args=[self.other_customer.pk]),
            reverse('api:project-detail', args=[self.other_project.pk]),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url, **self.auth())
                self.assertEqual(response.status_code, 404)

    def test_customers_support_filtering_searching_pagination_metadata(self):
        response = self.client.get(
            reverse('api:customer-list'),
            {'issuer': self.issuer.pk, 'search': 'acme', 'page_size': 1},
            **self.auth(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['count'], 1)
        self.assertIn('next', payload)
        self.assertIn('previous', payload)
        self.assertEqual(payload['results'][0]['id'], self.customer.pk)
        self.assertEqual(payload['results'][0]['external_id'], 'cust-acme')
        self.assertTrue(payload['results'][0]['url'].endswith(reverse('api:customer-detail', args=[self.customer.pk])))

    def test_projects_support_filtering_and_searching(self):
        response = self.client.get(
            reverse('api:project-list'),
            {'issuer': self.issuer.pk, 'customer': self.customer.pk, 'search': 'migration'},
            **self.auth(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['count'], 1)
        self.assertEqual(payload['results'][0]['id'], self.project.pk)
        self.assertEqual(payload['results'][0]['issuer_id'], self.issuer.pk)

    def test_customer_create_requires_accessible_issuer(self):
        response = self.client.post(
            reverse('api:customer-list'),
            {
                'issuer': self.other_issuer.pk,
                'company_name': 'Blocked Customer',
                'external_id': 'blocked-customer',
            },
            content_type='application/json',
            **self.auth(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('issuer', response.json()['error']['details'])
        self.assertFalse(Customer.objects.filter(external_id='blocked-customer').exists())

    def test_customer_and_project_create_with_accessible_resources(self):
        customer_response = self.client.post(
            reverse('api:customer-list'),
            {
                'issuer': self.issuer.pk,
                'company_name': 'New Customer',
                'external_id': 'new-customer',
                'billing_email': 'billing@new.test',
            },
            content_type='application/json',
            **self.auth(),
        )
        self.assertEqual(customer_response.status_code, 201)
        customer_id = customer_response.json()['id']

        project_response = self.client.post(
            reverse('api:project-list'),
            {
                'customer': customer_id,
                'title': 'New Project',
                'project_code': 'NEW-1',
                'external_id': 'new-project',
            },
            content_type='application/json',
            **self.auth(),
        )

        self.assertEqual(project_response.status_code, 201)
        self.assertEqual(project_response.json()['issuer_id'], self.issuer.pk)

    def test_project_create_rejects_cross_account_customer(self):
        response = self.client.post(
            reverse('api:project-list'),
            {
                'customer': self.other_customer.pk,
                'title': 'Blocked Project',
                'project_code': 'BLOCKED-1',
            },
            content_type='application/json',
            **self.auth(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('customer', response.json()['error']['details'])

    def test_superuser_can_read_all_issuers(self):
        response = self.client.get(reverse('api:issuer-list'), **self.auth(self.superuser_token))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.result_ids(response), {self.issuer.pk, self.other_issuer.pk})
