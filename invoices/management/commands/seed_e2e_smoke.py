import base64
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.models import Profile
from accounts.utils import otp as otp_utils
from invoices.models import (
    Address,
    BackupConfiguration,
    BackupRun,
    Company,
    Currency,
    Customer,
    Expense,
    Invoice,
    InvoiceFilterView,
    IssuerBankAccount,
    Issuer,
    OrderLine,
    Payment,
    PaymentApplication,
    PaymentTerm,
    Project,
    Statement,
)
from invoices.services.cached_totals import recalc_invoice_amounts


def _test_text(*codepoints):
    return ''.join(chr(codepoint) for codepoint in codepoints)


E2E_USER_EMAIL = 'e2e-smoke@example.com'
E2E_USER_PASSWORD = _test_text(
    115, 109, 111, 107, 101, 45, 116, 101, 115, 116, 45, 112, 97, 115, 115, 119, 111, 114, 100
)
E2E_USER_USERNAME = 'e2e-smoke-user'
E2E_TOTP_SECRET = _test_text(
    74, 66, 83, 87, 89, 51, 68, 80, 69, 72, 80, 75, 51, 80, 88, 80
)
E2E_BACKUP_ACCESS_KEY_ID = _test_text(
    101, 50, 101, 45, 100, 101, 109, 111, 45, 107, 101, 121, 45, 105, 100
)
E2E_BACKUP_SECRET_ACCESS_KEY = _test_text(
    101, 50, 101, 45, 100, 101, 109, 111, 45, 112, 108, 97, 99, 101, 104, 111, 108, 100, 101, 114, 45, 118, 97, 108, 117, 101
)
E2E_NET_15_NAME = 'E2E Smoke Net 15'
E2E_NET_30_NAME = 'E2E Smoke Net 30'
E2E_RECOVERY_CODES = [
    'SMOKE00001',
    'SMOKE00002',
    'SMOKE00003',
    'SMOKE00004',
    'SMOKE00005',
    'SMOKE00006',
    'SMOKE00007',
    'SMOKE00008',
    'SMOKE00009',
    'SMOKE00010',
    'SMOKE00011',
    'SMOKE00012',
    'SMOKE00013',
    'SMOKE00014',
    'SMOKE00015',
    'SMOKE00016',
    'SMOKE00017',
    'SMOKE00018',
    'SMOKE00019',
    'SMOKE00020',
    'SMOKE00021',
    'SMOKE00022',
    'SMOKE00023',
    'SMOKE00024',
]


class Command(BaseCommand):
    help = 'Create deterministic smoke-test data for Playwright E2E coverage.'

    def handle(self, *args, **options):
        with transaction.atomic():
            refs = self._ensure_reference_data()
            user = self._ensure_user()
            self._ensure_otp_setup(user)
            primary_issuer = self._seed_primary_company(user=user, refs=refs)
            secondary_issuer = self._seed_secondary_company(user=user, refs=refs)
            self._ensure_profile(user=user, default_company=primary_issuer.company)
            self._ensure_backup_settings_and_runs()

        self.stdout.write(self.style.SUCCESS('Seeded deterministic E2E smoke data.'))
        self.stdout.write(f'Email: {E2E_USER_EMAIL}')
        self.stdout.write(f'Password: {E2E_USER_PASSWORD}')
        self.stdout.write(f'TOTP secret: {E2E_TOTP_SECRET}')
        self.stdout.write(f'Primary company: {primary_issuer.company.name} (id={primary_issuer.company_id})')
        self.stdout.write(f'Secondary company: {secondary_issuer.company.name} (id={secondary_issuer.company_id})')

    def _ensure_reference_data(self):
        eur, _ = Currency.objects.get_or_create(
            code='EUR',
            defaults={
                'name': 'Euro',
                'symbol': '€',
                'exchange_rate_to_base': Decimal('1'),
                'is_base': True,
                'last_updated': timezone.now(),
            },
        )
        usd, _ = Currency.objects.get_or_create(
            code='USD',
            defaults={
                'name': 'US Dollar',
                'symbol': '$',
                'exchange_rate_to_base': Decimal('0.92'),
                'is_base': False,
                'last_updated': timezone.now(),
            },
        )
        net_15, _ = PaymentTerm.objects.update_or_create(
            name=E2E_NET_15_NAME,
            defaults={'days': 15, 'description': 'Payment due in 15 days'},
        )
        net_30, _ = PaymentTerm.objects.update_or_create(
            name=E2E_NET_30_NAME,
            defaults={'days': 30, 'description': 'Payment due in 30 days'},
        )
        return {
            'eur': eur,
            'usd': usd,
            'net_15': net_15,
            'net_30': net_30,
        }

    def _ensure_user(self):
        User = get_user_model()
        user, created = User.objects.get_or_create(
            email=E2E_USER_EMAIL,
            defaults={
                'username': E2E_USER_USERNAME,
                'first_name': 'E2E',
                'last_name': 'Smoke',
                'is_active': True,
            },
        )
        if not created:
            user.username = E2E_USER_USERNAME
            user.first_name = 'E2E'
            user.last_name = 'Smoke'
            user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        user.set_password(E2E_USER_PASSWORD)
        user.save()
        return user

    def _ensure_backup_settings_and_runs(self):
        configuration = BackupConfiguration.load()
        configuration.endpoint_url = 'https://s3.us-west-001.backblazeb2.com'
        configuration.bucket_name = 'invoices-backups'
        configuration.region = 'us-west-001'
        configuration.object_prefix = 'e2e-demo'
        configuration.access_key_id = E2E_BACKUP_ACCESS_KEY_ID
        configuration.secret_access_key = E2E_BACKUP_SECRET_ACCESS_KEY
        configuration.is_enabled = True
        configuration.daily_run_time = time(hour=2, minute=0)
        configuration.daily_retention_count = 14
        configuration.weekly_retention_count = 26
        configuration.monthly_retention_count = 36
        configuration.save()

        BackupRun.objects.all().delete()

        for run_kwargs in [
            {
                'status': BackupRun.STATUS_SUCCEEDED,
                'trigger_source': BackupRun.TRIGGER_SOURCE_SCHEDULED,
                'started_at': timezone.make_aware(datetime(2026, 4, 18, 2, 0)),
                'finished_at': timezone.make_aware(datetime(2026, 4, 18, 2, 5)),
                'storage_object_key': 'e2e-demo/2026-04-18-scheduled.zip',
                'retention_bucket': BackupRun.RETENTION_BUCKET_DAILY,
                'artifact_size_bytes': 4_096,
            },
            {
                'status': BackupRun.STATUS_FAILED,
                'trigger_source': BackupRun.TRIGGER_SOURCE_MANUAL,
                'started_at': timezone.make_aware(datetime(2026, 4, 17, 8, 30)),
                'finished_at': timezone.make_aware(datetime(2026, 4, 17, 8, 32)),
                'storage_object_key': '',
                'retention_bucket': '',
                'artifact_size_bytes': None,
                'error_summary': 'RuntimeError: upload failed',
                'diagnostics': {
                    'events': [
                        {
                            'stage': 'started',
                            'timestamp': '2026-04-17T08:30:00+00:00',
                            'message': 'Backup run started.',
                            'context': {
                                'trigger_source': BackupRun.TRIGGER_SOURCE_MANUAL,
                            },
                        },
                        {
                            'stage': 'upload',
                            'timestamp': '2026-04-17T08:31:45+00:00',
                            'message': 'Upload to object storage failed.',
                            'context': {
                                'bucket_name': 'invoices-backups',
                                'object_prefix': 'e2e-demo',
                            },
                        },
                    ],
                    'failure': {
                        'stage': 'upload',
                        'exception_class': 'RuntimeError',
                        'message': 'Upload to object storage failed.',
                        'context': {
                            'bucket_name': 'invoices-backups',
                            'object_prefix': 'e2e-demo',
                        },
                    },
                },
            },
            {
                'status': BackupRun.STATUS_SUCCEEDED,
                'trigger_source': BackupRun.TRIGGER_SOURCE_MANUAL,
                'started_at': timezone.make_aware(datetime(2026, 4, 17, 2, 0)),
                'finished_at': timezone.make_aware(datetime(2026, 4, 17, 2, 4)),
                'storage_object_key': 'e2e-demo/2026-04-17-manual.zip',
                'retention_bucket': BackupRun.RETENTION_BUCKET_DAILY,
                'artifact_size_bytes': 2_048,
            },
            {
                'status': BackupRun.STATUS_SUCCEEDED,
                'trigger_source': BackupRun.TRIGGER_SOURCE_SCHEDULED,
                'started_at': timezone.make_aware(datetime(2026, 4, 14, 2, 1)),
                'finished_at': timezone.make_aware(datetime(2026, 4, 14, 2, 6)),
                'storage_object_key': 'e2e-demo/2026-04-14-scheduled.zip',
                'retention_bucket': BackupRun.RETENTION_BUCKET_DAILY,
                'artifact_size_bytes': 3_072,
            },
            {
                'status': BackupRun.STATUS_SUCCEEDED,
                'trigger_source': BackupRun.TRIGGER_SOURCE_SCHEDULED,
                'started_at': timezone.make_aware(datetime(2025, 12, 31, 23, 0)),
                'finished_at': timezone.make_aware(datetime(2025, 12, 31, 23, 5)),
                'storage_object_key': 'e2e-demo/2025-12-31-scheduled.zip',
                'retention_bucket': BackupRun.RETENTION_BUCKET_WEEKLY,
                'artifact_size_bytes': 1_536,
            },
            {
                'status': BackupRun.STATUS_SUCCEEDED,
                'trigger_source': BackupRun.TRIGGER_SOURCE_MANUAL,
                'started_at': timezone.make_aware(datetime(2025, 12, 30, 22, 30)),
                'finished_at': timezone.make_aware(datetime(2025, 12, 30, 22, 33)),
                'storage_object_key': 'e2e-demo/2025-12-30-manual.zip',
                'retention_bucket': BackupRun.RETENTION_BUCKET_WEEKLY,
                'artifact_size_bytes': 1_024,
            },
        ]:
            BackupRun.objects.create(**run_kwargs)

    def _ensure_otp_setup(self, user):
        TOTPDevice.objects.filter(user=user).delete()
        StaticDevice.objects.filter(user=user).delete()

        key = base64.b32decode(E2E_TOTP_SECRET + '=' * ((8 - len(E2E_TOTP_SECRET) % 8) % 8), casefold=True)
        TOTPDevice.objects.create(
            user=user,
            name=otp_utils.TOTP_DEVICE_NAME,
            confirmed=True,
            key=key.hex(),
            step=30,
            t0=0,
            digits=6,
            tolerance=1,
            drift=0,
            last_t=-1,
        )

        recovery_device = StaticDevice.objects.create(user=user, name=otp_utils.RECOVERY_DEVICE_NAME)
        StaticToken.objects.bulk_create(
            [StaticToken(device=recovery_device, token=code) for code in E2E_RECOVERY_CODES]
        )

    def _ensure_profile(self, user, default_company):
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.default_company = default_company
        profile.save(update_fields=['default_company', 'updated_at'])

    def _seed_primary_company(self, *, user, refs):
        issuer = self._ensure_issuer(
            user=user,
            company_name='E2E Smoke Alpha LLC',
            full_address='123 Test Street\nBarcelona\nSpain',
            payment_term=refs['net_15'],
            invoice_format='ALPHA-{{YYYY}}-{{ID}}',
        )
        self._reset_issuer_data(issuer)

        default_account, secondary_account = self._ensure_bank_accounts(
            issuer,
            default_label='Alpha Primary EUR',
            default_details='IBAN ES12 3456 7890 1234 5678\nSWIFT ALPHAESB',
            secondary_label='Alpha Project Reserve EUR',
            secondary_details='IBAN ES98 7654 3210 9876 5432\nSWIFT RESERVEESB',
        )

        customer_company, _ = Company.objects.update_or_create(
            name='E2E Client Northwind',
            defaults={'customer_information_file_number': 'E2E-NW-001'},
        )
        customer = Customer.objects.create(
            issuer=issuer,
            company=customer_company,
            external_id='e2e-smoke-alpha-customer',
            currency=refs['eur'],
            payment_term=refs['net_15'],
            billing_email='billing+northwind@example.com',
            billing_contact_name='Nina Northwind',
            is_active=True,
        )
        project = Project.objects.create(
            customer=customer,
            external_id='e2e-smoke-alpha-project',
            title='Smoke Website Retainer',
            status=Project.STATUS_ACTIVE,
            project_code='E2E-ALPHA-PRJ',
            comment='Default smoke-test project notes',
            billing_reference='ALPHA-REF',
            payment_term=refs['net_15'],
        )

        today = timezone.localdate()
        draft_invoice = self._create_invoice(
            issuer=issuer,
            customer=customer,
            project=project,
            currency=refs['eur'],
            payment_term=refs['net_15'],
            external_id='e2e-smoke-alpha-invoice-draft',
            issued_date=today - timedelta(days=2),
            due_date=today + timedelta(days=13),
            status=Invoice.STATUS_DRAFT,
            notes='Draft invoice seeded for drawer editing.',
            bank_account=secondary_account,
            lines=[('Design review', Decimal('2.00'), Decimal('75.00'))],
        )
        self._create_invoice(
            issuer=issuer,
            customer=customer,
            project=project,
            currency=refs['eur'],
            payment_term=refs['net_15'],
            external_id='e2e-smoke-alpha-invoice-open',
            issued_date=today - timedelta(days=5),
            due_date=today + timedelta(days=10),
            status=Invoice.STATUS_INVOICED,
            notes='Outstanding invoice seeded for payment drawer flow.',
            bank_account=secondary_account,
            lines=[('Frontend implementation', Decimal('5.00'), Decimal('80.00'))],
        )
        self._create_invoice(
            issuer=issuer,
            customer=customer,
            project=project,
            currency=refs['eur'],
            payment_term=refs['net_15'],
            external_id='e2e-smoke-alpha-invoice-overdue',
            issued_date=today - timedelta(days=25),
            due_date=today - timedelta(days=10),
            status=Invoice.STATUS_INVOICED,
            notes='Overdue invoice seeded for invoice filter coverage.',
            bank_account=default_account,
            lines=[('Backend maintenance', Decimal('3.00'), Decimal('120.00'))],
        )
        paid_invoice = self._create_invoice(
            issuer=issuer,
            customer=customer,
            project=project,
            currency=refs['eur'],
            payment_term=refs['net_15'],
            external_id='e2e-smoke-alpha-invoice-paid',
            issued_date=today - timedelta(days=18),
            due_date=today - timedelta(days=3),
            status=Invoice.STATUS_INVOICED,
            notes='Paid invoice seeded for historical payment data.',
            bank_account=default_account,
            lines=[('Hosting and support', Decimal('1.00'), Decimal('180.00'))],
        )

        payment = Payment.objects.create(
            issuer=issuer,
            customer=customer,
            project=project,
            external_id='e2e-smoke-alpha-payment-paid',
            currency=refs['eur'],
            amount=paid_invoice.total_due,
            exchange_rate=Decimal('1'),
            base_currency_amount=paid_invoice.total_due,
            received_at=today - timedelta(days=1),
            status=Payment.STATUS_APPLIED,
            memo='Existing seeded payment',
        )
        PaymentApplication.objects.create(
            payment=payment,
            invoice=paid_invoice,
            external_id='e2e-smoke-alpha-payment-application-paid',
            amount_applied=paid_invoice.total_due,
        )

        Expense.objects.create(
            issuer=issuer,
            paid_date=today - timedelta(days=4),
            amount=Decimal('650.00'),
            description='Deterministic smoke expense above revenue for chart coverage.',
            exclude_from_reports=False,
        )

        for invoice in (draft_invoice, paid_invoice):
            recalc_invoice_amounts(invoice.id)
        return issuer

    def _seed_secondary_company(self, *, user, refs):
        issuer = self._ensure_issuer(
            user=user,
            company_name='E2E Smoke Beta LLC',
            full_address='500 Example Avenue\nLisbon\nPortugal',
            payment_term=refs['net_30'],
            invoice_format='BETA-{{YYYY}}-{{ID}}',
        )
        self._reset_issuer_data(issuer)
        default_account, _ = self._ensure_bank_accounts(
            issuer,
            default_label='Beta Primary USD',
            default_details='ACH routing 021000021\nAccount 000123456789',
            secondary_label='Beta Savings USD',
            secondary_details='ACH routing 026009593\nAccount 987654321000',
        )

        customer_company, _ = Company.objects.update_or_create(
            name='E2E Client Southridge',
            defaults={'customer_information_file_number': 'E2E-SR-001'},
        )
        customer = Customer.objects.create(
            issuer=issuer,
            company=customer_company,
            external_id='e2e-smoke-beta-customer',
            currency=refs['usd'],
            payment_term=refs['net_30'],
            billing_email='billing+southridge@example.com',
            billing_contact_name='Sam Southridge',
            is_active=True,
        )
        project = Project.objects.create(
            customer=customer,
            external_id='e2e-smoke-beta-project',
            title='Smoke Mobile App',
            status=Project.STATUS_ACTIVE,
            project_code='E2E-BETA-PRJ',
            comment='Secondary company project for company switching.',
            billing_reference='BETA-REF',
            payment_term=refs['net_30'],
        )

        self._create_invoice(
            issuer=issuer,
            customer=customer,
            project=project,
            currency=refs['usd'],
            payment_term=refs['net_30'],
            external_id='e2e-smoke-beta-invoice-open',
            issued_date=timezone.localdate() - timedelta(days=3),
            due_date=timezone.localdate() + timedelta(days=27),
            status=Invoice.STATUS_INVOICED,
            notes='Secondary company invoice seeded for company-switch assertions.',
            bank_account=default_account,
            lines=[('Prototype review', Decimal('2.00'), Decimal('95.00'))],
        )
        Expense.objects.create(
            issuer=issuer,
            paid_date=timezone.localdate() - timedelta(days=2),
            amount=Decimal('260.00'),
            description='Secondary smoke expense above revenue for chart coverage.',
            exclude_from_reports=False,
        )
        return issuer

    def _ensure_issuer(self, *, user, company_name, full_address, payment_term, invoice_format):
        address, _ = Address.objects.update_or_create(
            full_address=full_address,
            defaults={'alias': 'E2E Smoke'},
        )
        company, _ = Company.objects.update_or_create(
            name=company_name,
            defaults={
                'address': address,
                'customer_information_file_number': company_name.replace(' ', '-')[:32],
                'bank_account_number': 'ES12 3456 7890 1234 5678',
                'payment_method': 'Bank transfer',
                'payment_terms': payment_term.description,
                'payment_term': payment_term,
                'contact_name': 'E2E Smoke',
                'contact_email': E2E_USER_EMAIL,
                'contact_phone_number': '+34 555 000 111',
                'contact_country': 'ES',
            },
        )
        issuer, _ = Issuer.objects.update_or_create(
            company=company,
            defaults={
                'invoice_format': invoice_format,
                'next_invoice_number': 1,
            },
        )
        issuer.users.add(user)
        return issuer

    def _reset_issuer_data(self, issuer):
        PaymentApplication.objects.filter(payment__issuer=issuer).delete()
        Payment.objects.filter(issuer=issuer).delete()
        OrderLine.objects.filter(invoice__issuer=issuer).delete()
        Invoice.objects.filter(issuer=issuer).delete()
        InvoiceFilterView.objects.filter(issuer=issuer).delete()
        Statement.objects.filter(issuer=issuer).delete()
        Expense.objects.filter(issuer=issuer).delete()
        Project.objects.filter(customer__issuer=issuer).delete()
        Customer.objects.filter(issuer=issuer).delete()
        IssuerBankAccount.objects.filter(issuer=issuer).delete()
        issuer.next_invoice_number = 1
        issuer.save(update_fields=['next_invoice_number'])

    def _ensure_bank_accounts(self, issuer, *, default_label, default_details, secondary_label, secondary_details):
        default_account = IssuerBankAccount.objects.create(
            issuer=issuer,
            label=default_label,
            payment_method='Bank transfer',
            account_details=default_details,
            is_default=True,
            is_active=True,
            sort_order=10,
        )
        secondary_account = IssuerBankAccount.objects.create(
            issuer=issuer,
            label=secondary_label,
            payment_method='Bank transfer',
            account_details=secondary_details,
            is_default=False,
            is_active=True,
            sort_order=20,
        )
        issuer.company.bank_account_number = default_account.account_details
        issuer.company.payment_method = default_account.payment_method
        issuer.company.save(update_fields=['bank_account_number', 'payment_method'])
        return default_account, secondary_account

    def _create_invoice(
        self,
        *,
        issuer,
        customer,
        project,
        currency,
        payment_term,
        external_id,
        issued_date,
        due_date,
        status,
        notes,
        lines,
        bank_account=None,
    ):
        invoice = Invoice.objects.create(
            issuer=issuer,
            customer=customer,
            project=project,
            external_id=external_id,
            issued_date=issued_date,
            due_date=due_date,
            status=status,
            currency=currency,
            exchange_rate=currency.exchange_rate_to_base,
            payment_term=payment_term,
            bank_account=bank_account,
            notes=notes,
        )

        created_lines = []
        for index, (description, quantity, unit_price) in enumerate(lines, start=1):
            created_lines.append(
                OrderLine.objects.create(
                    invoice=invoice,
                    external_id=f'{external_id}-line-{index}',
                    description=description,
                    quantity=quantity,
                    unit_price=unit_price,
                )
            )

        invoice.calculate_totals(created_lines)
        invoice.base_currency_total = invoice.total_due
        invoice.save(
            update_fields=[
                'sub_total',
                'discount_amount',
                'tax_base',
                'tax_amount',
                'total_due',
                'base_currency_total',
                'updated_at',
            ]
        )
        recalc_invoice_amounts(invoice.id)
        invoice.refresh_from_db()
        return invoice
