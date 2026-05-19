import shutil
import tempfile
from datetime import date
from decimal import Decimal

from django.test import override_settings

from invoices.models import Company, Customer, Expense, Issuer, Project
from tests.support import AuthenticatedCompanyTestCase


@override_settings(DEFAULT_FILE_STORAGE='django.core.files.storage.FileSystemStorage')
class ExpenseViewsTestCase(AuthenticatedCompanyTestCase):
    def setUp(self):
        self.temp_media = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.temp_media, ignore_errors=True))
        self.override = override_settings(MEDIA_ROOT=self.temp_media)
        self.override.enable()
        self.addCleanup(self.override.disable)

        issuer_company = Company.objects.create(name='Issuer Co', customer_information_file_number='VATISS')
        self.issuer = Issuer.objects.create(company=issuer_company)
        customer_company = Company.objects.create(name='Client Co', customer_information_file_number='VATC')
        self.customer = Customer.objects.create(
            issuer=self.issuer,
            company=customer_company,
            is_active=True,
        )
        self.project = Project.objects.create(
            customer=self.customer,
            title='Website revamp',
            project_code='WR001',
            status=Project.STATUS_ACTIVE,
        )

        self.user = self.create_user_with_issuers(
            [self.issuer],
            username='expense-views-user',
            email='expenses@example.com',
        )
        self.login_with_active_company(self.user, issuer=self.issuer)

        self.expense = Expense.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project,
            paid_date=date.today(),
            amount=Decimal('300.00'),
            description='Initial expense',
        )
