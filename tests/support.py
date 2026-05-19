from django.contrib.auth import get_user_model
from django.test import TestCase

from invoices.models import Company, Issuer


class IssuerUserTestMixin:
    @staticmethod
    def build_test_password():
        return '-'.join(['test', 'password'])

    @staticmethod
    def build_test_totp_token():
        return ''.join(str(number) for number in range(1, 7))

    def _next_support_sequence(self):
        self._support_sequence = getattr(self, '_support_sequence', 0) + 1
        return self._support_sequence

    def create_issuer(self, company=None, **issuer_kwargs):
        if company is None:
            sequence = self._next_support_sequence()
            company = Company.objects.create(
                name=f'Test Company {sequence}',
                customer_information_file_number=f'VAT{sequence:04d}',
            )
        return Issuer.objects.create(company=company, **issuer_kwargs)

    def create_user_with_issuers(self, issuers=None, password=None, **user_kwargs):
        sequence = self._next_support_sequence()
        user = get_user_model().objects.create_user(
            username=user_kwargs.pop('username', f'test-user-{sequence}'),
            email=user_kwargs.pop('email', f'test-user-{sequence}@example.com'),
            password=password or self.build_test_password(),
            **user_kwargs,
        )

        linked_issuers = list(issuers) if issuers is not None else [self.create_issuer()]
        for issuer in linked_issuers:
            issuer.users.add(user)

        return user


class AuthenticatedCompanyTestMixin:
    def login_with_active_company(self, user, issuer=None, company_id=None):
        self.client.force_login(user)
        return self.set_active_company(issuer=issuer, company_id=company_id)

    def set_active_company(self, issuer=None, company_id=None):
        active_company_id = company_id or issuer.company_id
        session = self.client.session
        session['active_company_id'] = active_company_id
        session.save()
        return active_company_id


class IssuerUserTestCase(IssuerUserTestMixin, TestCase):
    pass


class AuthenticatedCompanyTestCase(
    IssuerUserTestMixin,
    AuthenticatedCompanyTestMixin,
    TestCase,
):
    pass
