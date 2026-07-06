import os
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify

INVOICE_NUMBER_PADDING = 4


def normalize_import_header(value):
    return " ".join((value or "").lstrip("\ufeff").strip().casefold().split())


def normalized_import_header_signature(headers):
    normalized = [normalize_import_header(header) for header in headers or []]
    return "|".join(sorted(header for header in normalized if header))


class Address(models.Model):
    street = models.CharField(max_length=100, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    state = models.CharField(null=True, blank=True, max_length=100)
    postal_code = models.CharField(max_length=100, null=True, blank=True)
    country = models.CharField(null=True, blank=True, max_length=100)
    full_address = models.TextField(null=True, blank=True)
    alias = models.CharField(null=True, blank=True,
                             max_length=100, default='Default')

    def __str__(self):
        if self.full_address:
            return self.full_address
        parts = [
            self.street,
            " ".join(filter(None, [self.postal_code, self.city])).strip(),
            " ".join(filter(None, [self.state, self.country])).strip()
        ]
        return ", ".join([part for part in parts if part])

    class Meta:
        ordering = ['alias']


class Currency(models.Model):
    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=32, blank=True)
    symbol = models.CharField(max_length=8, blank=True)
    exchange_rate_to_base = models.DecimalField(max_digits=18, decimal_places=8, default=Decimal('1'))
    is_base = models.BooleanField(default=False)
    last_updated = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return self.code


class PaymentTerm(models.Model):
    name = models.CharField(max_length=32, unique=True)
    days = models.PositiveIntegerField(default=30)
    description = models.CharField(max_length=128, blank=True)

    class Meta:
        ordering = ['days', 'name']

    def __str__(self):
        return self.name


class Company(models.Model):
    address = models.ForeignKey(
        Address, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=100)
    bank_account_number = models.CharField(
        null=True, blank=True, max_length=500)
    payment_method = models.CharField(
        null=True, blank=True, max_length=100)
    payment_terms = models.TextField(null=True, blank=True)
    payment_term = models.ForeignKey(
        PaymentTerm, null=True, blank=True, on_delete=models.SET_NULL, related_name='issuing_companies'
    )
    customer_information_file_number = models.CharField(max_length=100, blank=True)
    logo = models.ImageField(null=True, blank=True, upload_to='company/images')
    contact_name = models.CharField(max_length=100, blank=True, default="")
    contact_email = models.CharField(max_length=100, blank=True, default="")
    contact_cc_email = models.CharField(max_length=100, blank=True, default="")
    contact_phone_number = models.CharField(max_length=100, blank=True, default="")
    contact_country = models.CharField(max_length=100, blank=True, default="")

    def __str__(self):
        if self.name is None:
            return self.id
        return self.name

    class Meta:
        ordering = ['name']


class Issuer(models.Model):
    company = models.OneToOneField(
        Company, on_delete=models.CASCADE, null=True, blank=True, related_name='issuer_profile')
    invoice_format = models.CharField(max_length=64, default='{{YYYY}}.{{ID}}')
    next_invoice_number = models.PositiveIntegerField(default=1)
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='issuers',
        blank=True,
        help_text='Users permitted to access this issuer.',
    )

    def __str__(self):
        if self.company is None:
            return str(self.id)
        return str(self.company)

    def render_invoice_reference(self, numbering_date, sequence_number):
        pattern = self.invoice_format or '{{YYYY}}.{{ID}}'
        tokens = {
            '{{YYYY}}': numbering_date.strftime('%Y'),
            '{{YY}}': numbering_date.strftime('%y'),
            '{{MM}}': numbering_date.strftime('%m'),
            '{{DD}}': numbering_date.strftime('%d'),
            '{{ID}}': str(sequence_number).zfill(INVOICE_NUMBER_PADDING),
        }
        for token, value in tokens.items():
            pattern = pattern.replace(token, value)
        return pattern


class IssuerSifSettings(models.Model):
    class TaxCountry(models.TextChoices):
        UNSPECIFIED = '', 'Unspecified'
        SPAIN = 'ES', 'Spain'
        OTHER = 'OTHER', 'Other country'

    class SifMode(models.TextChoices):
        VERI_FACTU = 'VERI_FACTU', 'VERI*FACTU'
        NO_VERI_FACTU = 'NO_VERI_FACTU', 'No VERI*FACTU'

    class AeatEnvironment(models.TextChoices):
        TEST = 'TEST', 'AEAT test'
        PRODUCTION = 'PRODUCTION', 'AEAT production'

    class TaxpayerRole(models.TextChoices):
        CORPORATE = 'CORPORATE', 'SL / corporate taxpayer'
        AUTONOMO = 'AUTONOMO', 'Autónomo / individual taxpayer'
        OTHER = 'OTHER', 'Other covered taxpayer'

    class DeadlineCategory(models.TextChoices):
        CORPORATE = 'CORPORATE', 'Corporate Tax deadline'
        AUTONOMO_OTHER = 'AUTONOMO_OTHER', 'Autónomo / other taxpayer deadline'

    class OperationalStatus(models.TextChoices):
        NOT_READY = 'NOT_READY', 'Not ready'
        READY = 'READY', 'Ready'
        SUSPENDED = 'SUSPENDED', 'Suspended'

    CORPORATE_DEADLINE = date(2027, 1, 1)
    AUTONOMO_OTHER_DEADLINE = date(2027, 7, 1)

    issuer = models.OneToOneField(
        Issuer,
        on_delete=models.CASCADE,
        related_name='sif_settings',
    )
    tax_country = models.CharField(
        max_length=16,
        choices=TaxCountry.choices,
        default=TaxCountry.UNSPECIFIED,
        blank=True,
        help_text='Explicit issuer/establishment tax country. Spain (ES) makes SIF applicable.',
    )
    enabled = models.BooleanField(default=False)
    mode = models.CharField(
        max_length=16,
        choices=SifMode.choices,
        default=SifMode.VERI_FACTU,
    )
    aeat_environment = models.CharField(
        max_length=16,
        choices=AeatEnvironment.choices,
        default=AeatEnvironment.TEST,
    )
    taxpayer_role = models.CharField(
        max_length=16,
        choices=TaxpayerRole.choices,
        default=TaxpayerRole.OTHER,
    )
    deadline_category = models.CharField(
        max_length=16,
        choices=DeadlineCategory.choices,
        default=DeadlineCategory.AUTONOMO_OTHER,
    )
    software_name = models.CharField(max_length=128, blank=True, default='')
    software_version = models.CharField(max_length=64, blank=True, default='')
    software_code = models.CharField(max_length=64, blank=True, default='')
    certificate_reference = models.CharField(
        max_length=128,
        blank=True,
        default='',
        help_text='Non-secret certificate label or external reference only.',
    )
    operational_status = models.CharField(
        max_length=16,
        choices=OperationalStatus.choices,
        default=OperationalStatus.NOT_READY,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Issuer SIF settings'
        verbose_name_plural = 'Issuer SIF settings'
        ordering = ['issuer']

    def __str__(self):
        return f'SIF settings for {self.issuer}'

    @property
    def is_spanish_issuer(self):
        return self.tax_country == self.TaxCountry.SPAIN

    @property
    def informational_deadline(self):
        if self.deadline_category == self.DeadlineCategory.CORPORATE:
            return self.CORPORATE_DEADLINE
        return self.AUTONOMO_OTHER_DEADLINE

    def clean(self):
        super().clean()
        if not self.enabled:
            return

        errors = {}
        if not self.is_spanish_issuer:
            errors['enabled'] = 'SIF can only be enabled for Spanish issuers.'

        from invoices.services.sif import is_valid_spanish_tax_id

        tax_id = ''
        if self.issuer_id and self.issuer and self.issuer.company:
            tax_id = self.issuer.company.customer_information_file_number
        if not is_valid_spanish_tax_id(tax_id):
            errors['enabled'] = 'SIF requires a valid Spanish NIF, NIE, or CIF for the issuer.'

        if errors:
            raise ValidationError(errors)


class IssuerBankAccount(models.Model):
    issuer = models.ForeignKey(
        Issuer, on_delete=models.CASCADE, related_name='bank_accounts')
    label = models.CharField(max_length=100)
    payment_method = models.CharField(null=True, blank=True, max_length=100)
    account_details = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.label

    def clean(self):
        super().clean()
        if self.is_default and not self.is_active:
            raise ValidationError({
                'is_default': 'The default bank account must be active.',
            })

        if (
            self.is_default
            and self.issuer_id
            and not getattr(self, '_skip_default_uniqueness_validation', False)
        ):
            default_accounts = IssuerBankAccount.objects.filter(
                issuer_id=self.issuer_id,
                is_default=True,
            )
            if self.pk:
                default_accounts = default_accounts.exclude(pk=self.pk)
            if default_accounts.exists():
                raise ValidationError({
                    'is_default': 'Only one default bank account is allowed per company.',
                })

    class Meta:
        ordering = ['issuer', 'sort_order', 'label', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['issuer'],
                condition=models.Q(is_default=True),
                name='unique_default_bank_account_per_issuer',
            ),
        ]


class Customer(models.Model):
    issuer = models.ForeignKey(
        Issuer, null=True, blank=True, on_delete=models.CASCADE, related_name='customers')
    company = models.ForeignKey(
        Company, null=True, blank=True, on_delete=models.CASCADE)
    external_id = models.CharField(max_length=64, null=True, blank=True, unique=True)
    currency = models.ForeignKey(
        Currency, null=True, blank=True, on_delete=models.SET_NULL, related_name='customers')
    payment_term = models.ForeignKey(
        PaymentTerm, null=True, blank=True, on_delete=models.SET_NULL, related_name='customers')
    payment_notes = models.TextField(blank=True, default='')
    billing_email = models.EmailField(null=True, blank=True)
    billing_contact_name = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        if self.company is None:
            return str(self.id)
        return str(self.company)


class Project(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_INACTIVE = 'inactive'
    STATUS_CHOICES = (
        (STATUS_ACTIVE, 'Active'),
        (STATUS_INACTIVE, 'Inactive'),
    )

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='projects')
    issuer = models.ForeignKey(
        Issuer, null=True, blank=True, on_delete=models.CASCADE, related_name='projects')
    external_id = models.CharField(max_length=64, null=True, blank=True, unique=True)
    title = models.CharField(max_length=200)
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    project_code = models.CharField(max_length=50)
    comment = models.TextField(blank=True, null=True)
    billing_reference = models.CharField(max_length=100, blank=True)
    payment_term = models.ForeignKey(
        PaymentTerm, null=True, blank=True, on_delete=models.SET_NULL, related_name='projects')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.project_code} - {self.title}"

    def clean(self):
        super().clean()
        issuer_id = self._resolved_issuer_id()
        if not issuer_id or not self.project_code:
            return

        duplicate_projects = Project.objects.filter(
            issuer_id=issuer_id,
            project_code=self.project_code,
        )
        if self.pk:
            duplicate_projects = duplicate_projects.exclude(pk=self.pk)
        if duplicate_projects.exists():
            raise ValidationError({
                'project_code': 'Project code already exists for this company.',
            })

    def save(self, *args, **kwargs):
        self.issuer_id = self._resolved_issuer_id()
        super().save(*args, **kwargs)

    def _resolved_issuer_id(self):
        customer = getattr(self, 'customer', None)
        if customer is not None:
            return customer.issuer_id
        return self.issuer_id

    class Meta:
        ordering = ['title']
        constraints = [
            models.UniqueConstraint(
                fields=['issuer', 'project_code'],
                name='unique_project_code_per_issuer',
            ),
        ]


class Invoice(models.Model):
    DEFAULT_SEQUENCE = 'INV'
    DEFAULT_LEAD_ZEROS = INVOICE_NUMBER_PADDING

    STATUS_DRAFT = 'draft'
    STATUS_INVOICED = 'invoiced'
    STATUS_OVERDUE = 'overdue'
    STATUS_PAID = 'paid'

    STATUS_CHOICES = (
        (STATUS_DRAFT, 'Draft'),
        (STATUS_INVOICED, 'Invoiced'),
        (STATUS_OVERDUE, 'Overdue'),
        (STATUS_PAID, 'Paid'),
    )

    issuer = models.ForeignKey(
        Issuer, null=True, blank=True, on_delete=models.CASCADE)
    customer = models.ForeignKey(
        Customer, null=True, blank=True, on_delete=models.CASCADE)
    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.PROTECT, related_name='invoices')
    bank_account = models.ForeignKey(
        IssuerBankAccount, null=True, blank=True, on_delete=models.PROTECT, related_name='invoices')

    external_id = models.CharField(max_length=64, null=True, blank=True, unique=True)
    reference_number = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    created_at = models.DateTimeField(auto_now_add=True)
    discount_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    discount_value = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True, default=0)
    issued_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    sent_date = models.DateField(null=True, blank=True)
    number = models.IntegerField(null=True, blank=True)
    pdf_document = models.FileField(upload_to='invoices_pdf/')
    sequence = models.CharField(null=True, blank=True, max_length=100)
    template_identifier = models.CharField(max_length=64, blank=True)
    comment = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    currency = models.ForeignKey(
        Currency, null=True, blank=True, on_delete=models.SET_NULL, related_name='invoices')
    exchange_rate = models.DecimalField(
        max_digits=18, decimal_places=8, null=True, blank=True, default=Decimal('1'))
    base_currency_total = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    sub_total = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    tax_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    tax_base = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    tax_value = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True, default=0)
    secondary_tax_rate = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True, default=0)
    secondary_tax_name = models.CharField(max_length=64, blank=True)
    uses_secondary_tax = models.BooleanField(default=False)
    total_due = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    unique_code_number = models.CharField(
        null=True, blank=True, max_length=100, unique=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Cached amount fields
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    amount_due = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    amount_overdue = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    last_payment_date = models.DateField(null=True, blank=True)
    payment_term = models.ForeignKey(
        PaymentTerm, null=True, blank=True, on_delete=models.SET_NULL, related_name='invoices'
    )

    def get_snapshot_customer(self):
        if self.customer_id:
            return self.customer
        if self.project_id:
            return self.project.customer
        return None

    def apply_missing_currency_snapshot(self):
        had_currency = bool(self.currency_id or self.currency)
        resolved_currency = self.currency
        snapshot_filled = False

        if not resolved_currency:
            customer = self.get_snapshot_customer()
            customer_currency = getattr(customer, 'currency', None)
            if customer_currency:
                self.currency = customer_currency
                resolved_currency = customer_currency
                snapshot_filled = True

        if (
            not had_currency
            and resolved_currency
            and (not self.exchange_rate or self.exchange_rate == Decimal('1'))
        ):
            self.exchange_rate = resolved_currency.exchange_rate_to_base
            snapshot_filled = True

        if (
            snapshot_filled
            and self.exchange_rate
            and self.total_due not in (None, '')
            and (not self.base_currency_total or self.base_currency_total == Decimal('0'))
        ):
            self.base_currency_total = (
                _normalize_decimal(self.total_due) * _normalize_decimal(self.exchange_rate)
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def save(self, *args, **kwargs):
        if not self.issuer:
            raise ValueError('Invoice issuer is required')

        needs_number = self.number is None
        needs_reference = not self.reference_number
        numbering_date = self.issued_date or timezone.now().date()

        if needs_number or needs_reference:
            issuer = self.issuer
            with transaction.atomic():
                issuer_locked = Issuer.objects.select_for_update().get(pk=issuer.pk)
                if needs_number:
                    next_number = issuer_locked.next_invoice_number or 1
                    issuer_locked.next_invoice_number = next_number + 1
                    issuer_locked.save(update_fields=['next_invoice_number'])
                    self.number = next_number
                else:
                    next_number = self.number

                if needs_reference:
                    self.reference_number = issuer_locked.render_invoice_reference(numbering_date, next_number)

                issuer.next_invoice_number = issuer_locked.next_invoice_number

        self.discount_value = _normalize_decimal(self.discount_value)
        self.tax_value = _normalize_decimal(self.tax_value)
        self.secondary_tax_rate = _normalize_decimal(self.secondary_tax_rate)
        self.sub_total = _normalize_decimal(self.sub_total)
        self.discount_amount = _normalize_decimal(self.discount_amount)
        self.tax_base = _normalize_decimal(self.tax_base)
        self.tax_amount = _normalize_decimal(self.tax_amount)
        self.total_due = _normalize_decimal(self.total_due)
        self.base_currency_total = _normalize_decimal(self.base_currency_total)
        self.apply_missing_currency_snapshot()

        if not self.exchange_rate:
            self.exchange_rate = Decimal('1')

        if self.payment_term and self.issued_date and not self.due_date:
            self.due_date = self.issued_date + timedelta(days=self.payment_term.days)

        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.bank_account_id and self.issuer_id and self.bank_account.issuer_id != self.issuer_id:
            raise ValidationError({
                'bank_account': 'Bank account must belong to the invoice issuer.',
            })

    @property
    def sequence_number(self):
        if self.reference_number:
            return self.reference_number
        if self.sequence and self.number:
            formatted_number = str(self.number).zfill(self.DEFAULT_LEAD_ZEROS)
            return f"{self.sequence}-{formatted_number}"
        else:
            return f"Database id: {self.id}"

    def calculate_totals(self, orders):
        self.sub_total = self.discount_amount = self.tax_base = self.tax_amount = self.total_due = Decimal('0')
        for current_order in orders:
            self.sub_total += _normalize_decimal(current_order.line_total)

        discount_rate = _normalize_decimal(self.discount_value)
        tax_rate = _normalize_decimal(self.tax_value)

        self.discount_amount = (self.sub_total * discount_rate) / Decimal('100')
        self.tax_base = self.sub_total - self.discount_amount
        self.tax_amount = (self.tax_base * tax_rate) / Decimal('100')
        self.total_due = self.tax_base + self.tax_amount

    def __str__(self):
        return self.sequence_number

    @property
    def amount_invoiced(self):
        # alias to preserve naming consistency without DB rename (see BACKLOG.md)
        return self.total_due or Decimal('0')


class OrderLine(models.Model):
    LINE_TYPE_TIME = 'time'
    LINE_TYPE_FLAT = 'flat'
    LINE_TYPE_QUANTITY = 'quantity'
    LINE_TYPE_EXPENSE = 'expense'

    LINE_TYPE_CHOICES = (
        (LINE_TYPE_TIME, 'Time'),
        (LINE_TYPE_FLAT, 'Flat Fee'),
        (LINE_TYPE_QUANTITY, 'Quantity'),
        (LINE_TYPE_EXPENSE, 'Expense'),
    )

    invoice = models.ForeignKey(to=Invoice, on_delete=models.CASCADE)
    external_id = models.CharField(max_length=64, null=True, blank=True, unique=True)
    line_type = models.CharField(max_length=16, choices=LINE_TYPE_CHOICES, default=LINE_TYPE_QUANTITY)
    description = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(
        max_digits=12, decimal_places=3, null=True, blank=True, default=0)
    duration_seconds = models.PositiveIntegerField(default=0)
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    line_total = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    manual_total = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    time_entry_external_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['id']

    def save(self, *args, **kwargs):
        normalized_quantity = _normalize_decimal(self.quantity)
        normalized_unit_price = _normalize_decimal(self.unit_price)
        normalized_total = _normalize_decimal(self.line_total)

        self.quantity = normalized_quantity
        self.unit_price = normalized_unit_price

        if not self.manual_total:
            normalized_total = normalized_quantity * normalized_unit_price

        self.line_total = normalized_total
        now = timezone.now()
        if not self.created_at:
            self.created_at = now
        self.updated_at = now

        super().save(*args, **kwargs)


class Payment(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPLIED = 'applied'

    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPLIED, 'Applied'),
    )

    issuer = models.ForeignKey(Issuer, on_delete=models.CASCADE, related_name='payments')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='payments')
    project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.SET_NULL, related_name='payments')
    external_id = models.CharField(max_length=64, null=True, blank=True, unique=True)
    currency = models.ForeignKey(Currency, null=True, blank=True, on_delete=models.SET_NULL, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True, default=Decimal('1'))
    base_currency_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    received_at = models.DateField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_APPLIED)
    memo = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-received_at', '-id']

    def __str__(self):
        return f"Payment {self.id} - {self.amount}"

    def save(self, *args, **kwargs):
        self.amount = _normalize_decimal(self.amount)
        self.base_currency_amount = _normalize_decimal(
            self.base_currency_amount if self.base_currency_amount not in (None, '') else self.amount
        )
        if not self.exchange_rate:
            self.exchange_rate = Decimal('1')
        super().save(*args, **kwargs)


class PaymentApplication(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='applications')
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payment_applications')
    amount_applied = models.DecimalField(max_digits=12, decimal_places=2)
    external_id = models.CharField(max_length=64, null=True, blank=True, unique=True)
    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('payment', 'invoice')

    def __str__(self):
        return f"{self.payment_id} -> {self.invoice_id}: {self.amount_applied}"

    def save(self, *args, **kwargs):
        self.amount_applied = _normalize_decimal(self.amount_applied)
        super().save(*args, **kwargs)


class Statement(models.Model):
    issuer = models.ForeignKey(Issuer, on_delete=models.CASCADE, related_name='statements')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='statements')
    external_id = models.CharField(max_length=64, null=True, blank=True, unique=True)
    statement_number = models.CharField(max_length=64, blank=True)
    from_date = models.DateField(null=True, blank=True)
    to_date = models.DateField(null=True, blank=True)
    sent_date = models.DateField(null=True, blank=True)
    total_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    current_due = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    overdue_30 = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    overdue_60 = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    overdue_90 = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    overdue_over_90 = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-from_date', '-id']

    def __str__(self):
        return f"Statement {self.statement_number or self.id}"


def expense_attachment_upload_path(instance, filename):
    """Store attachments under expenses/<YYYY>/<MM>/expense-<id>-<slug>.<ext>."""

    original_name = filename or 'attachment'
    base, ext = os.path.splitext(original_name)
    ext = ext.lower()
    slug = slugify(base) or 'attachment'
    paid_date = getattr(instance, 'paid_date', None) or date.today()
    year = paid_date.strftime('%Y')
    month = paid_date.strftime('%m')
    identifier = getattr(instance, 'pk', None) or uuid4().hex
    prefix = f"expense-{identifier}"
    return f"expenses/{year}/{month}/{prefix}-{slug}{ext}"


def incoming_invoice_artifact_upload_path(instance, filename):
    """Store incoming invoice artifacts under media/incoming-invoices/..."""

    original_name = filename or 'artifact'
    base, ext = os.path.splitext(original_name)
    slug = slugify(base) or 'artifact'
    ext = ext.lower()
    candidate = getattr(instance, 'candidate', None)
    received_at = getattr(candidate, 'received_at', None) or timezone.now()
    source_id = getattr(candidate, 'source_id', None) or 'unassigned-source'
    candidate_id = getattr(candidate, 'pk', None) or uuid4().hex
    return (
        f"incoming-invoices/{received_at:%Y}/{received_at:%m}/"
        f"source-{source_id}/candidate-{candidate_id}/{slug}{ext}"
    )


class Expense(models.Model):
    issuer = models.ForeignKey(Issuer, on_delete=models.CASCADE)
    customer = models.ForeignKey(
        Customer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='expenses',
    )
    project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.SET_NULL)
    invoice = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.SET_NULL)
    paid_date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    external_id = models.CharField(max_length=64, blank=True, null=True, unique=True)
    attachment = models.FileField(upload_to=expense_attachment_upload_path, null=True, blank=True)
    description = models.CharField(max_length=255, blank=True)
    raw_data = models.JSONField(default=dict, blank=True)
    exclude_from_reports = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Expense {self.amount} on {self.paid_date}"

    def clean(self):
        super().clean()
        if self.project and self.project.customer_id and self.customer_id:
            if self.project.customer_id != self.customer_id:
                raise ValidationError({
                    'project': 'Selected project is not associated with the chosen customer.',
                })

    def save(self, *args, **kwargs):
        if self.project and self.project.customer_id and not self.customer_id:
            self.customer = self.project.customer
        super().save(*args, **kwargs)


class IncomingEmailSource(models.Model):
    PROVIDER_IMAP = 'imap'
    PROVIDER_CHOICES = (
        (PROVIDER_IMAP, 'IMAP'),
    )

    issuer = models.ForeignKey(
        Issuer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='incoming_email_sources',
        help_text='Optional issuer for a company-specific mailbox source.',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='incoming_email_sources',
    )
    provider = models.CharField(max_length=16, choices=PROVIDER_CHOICES, default=PROVIDER_IMAP)
    display_name = models.CharField(max_length=100)
    email_address = models.EmailField()
    is_enabled = models.BooleanField(default=True)
    folder = models.CharField(max_length=255, default='INBOX')
    polling_query = models.CharField(max_length=255, blank=True)
    credential_reference = models.CharField(max_length=255, blank=True)
    provider_state = models.JSONField(default=dict, blank=True)
    last_seen_message_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_name', 'id']
        indexes = [
            models.Index(fields=['provider', 'is_enabled'], name='incoming_source_provider_idx'),
            models.Index(fields=['issuer', 'is_enabled'], name='incoming_source_issuer_idx'),
        ]

    def __str__(self):
        return f"{self.display_name} <{self.email_address}>"

    def clean(self):
        super().clean()
        if self.provider != self.PROVIDER_IMAP:
            raise ValidationError({'provider': 'Only IMAP incoming email sources are supported for this issue.'})


class IssuerEmailRoutingRule(models.Model):
    issuer = models.OneToOneField(
        Issuer,
        on_delete=models.CASCADE,
        related_name='incoming_email_routing_rule',
    )
    recipient_aliases = models.JSONField(default=list, blank=True)
    delivered_to_addresses = models.JSONField(default=list, blank=True)
    legal_names = models.JSONField(default=list, blank=True)
    tax_identifiers = models.JSONField(default=list, blank=True)
    keywords = models.JSONField(default=list, blank=True)
    confidence_threshold = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.80'))
    auto_assign_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['issuer']
        indexes = [
            models.Index(fields=['issuer', 'auto_assign_enabled'], name='issuer_routing_enabled_idx'),
        ]

    def __str__(self):
        return f"Incoming routing for {self.issuer}"


class IncomingInvoiceCandidate(models.Model):
    STATUS_NEW = 'new'
    STATUS_NEEDS_REVIEW = 'needs_review'
    STATUS_READY = 'ready'
    STATUS_REVIEWED_UNPAID = 'reviewed_unpaid'
    STATUS_CONVERTED = 'converted'
    STATUS_REJECTED = 'rejected'
    STATUS_NOT_INVOICE = 'not_invoice'
    STATUS_DUPLICATE = 'duplicate'
    STATUS_NEEDS_FETCH = 'needs_fetch'
    STATUS_ERROR = 'error'
    STATUS_CHOICES = (
        (STATUS_NEW, 'New'),
        (STATUS_NEEDS_REVIEW, 'Needs review'),
        (STATUS_READY, 'Ready'),
        (STATUS_REVIEWED_UNPAID, 'Reviewed/unpaid'),
        (STATUS_CONVERTED, 'Converted'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_NOT_INVOICE, 'Not an invoice'),
        (STATUS_DUPLICATE, 'Duplicate'),
        (STATUS_NEEDS_FETCH, 'Needs manual fetch'),
        (STATUS_ERROR, 'Error'),
    )

    source = models.ForeignKey(IncomingEmailSource, on_delete=models.CASCADE, related_name='candidates')
    suggested_issuer = models.ForeignKey(
        Issuer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='suggested_incoming_invoice_candidates',
    )
    confirmed_issuer = models.ForeignKey(
        Issuer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='confirmed_incoming_invoice_candidates',
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_NEW)
    provider_message_id = models.CharField(max_length=255)
    provider_thread_id = models.CharField(max_length=255, blank=True)
    from_name = models.CharField(max_length=255, blank=True)
    from_email = models.EmailField(blank=True)
    to_addresses = models.JSONField(default=list, blank=True)
    cc_addresses = models.JSONField(default=list, blank=True)
    delivered_to_addresses = models.JSONField(default=list, blank=True)
    subject = models.CharField(max_length=500, blank=True)
    received_at = models.DateTimeField()
    body_text = models.TextField(blank=True)
    body_html = models.TextField(blank=True)
    extracted_metadata = models.JSONField(default=dict, blank=True)
    detection_metadata = models.JSONField(default=dict, blank=True)
    duplicate_metadata = models.JSONField(default=dict, blank=True)
    fingerprint = models.CharField(max_length=128, blank=True)
    raw_provider_metadata = models.JSONField(default=dict, blank=True)
    selected_artifact = models.ForeignKey(
        'IncomingInvoiceArtifact',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='selected_for_candidates',
    )
    generated_body_pdf_artifact = models.ForeignKey(
        'IncomingInvoiceArtifact',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='body_pdf_for_candidates',
    )
    reviewed_metadata = models.JSONField(default=dict, blank=True)
    conversion_limitation_message = models.TextField(blank=True)
    converted_expense = models.OneToOneField(
        'Expense',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='incoming_invoice_candidate',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-received_at', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['source', 'provider_message_id'],
                name='uniq_inc_cand_source_msg',
            ),
        ]
        indexes = [
            models.Index(fields=['status', 'received_at'], name='inc_cand_status_date_idx'),
            models.Index(fields=['suggested_issuer', 'status'], name='inc_cand_suggested_idx'),
            models.Index(fields=['confirmed_issuer', 'status'], name='inc_cand_confirmed_idx'),
            models.Index(fields=['source', 'received_at'], name='inc_cand_source_date_idx'),
            models.Index(fields=['fingerprint'], name='inc_cand_fingerprint_idx'),
        ]

    def __str__(self):
        return self.display_subject

    @property
    def display_subject(self):
        return self.subject or f"Incoming message {self.provider_message_id}"

    @property
    def issuer_for_review(self):
        return self.confirmed_issuer or self.suggested_issuer

    @property
    def is_terminal(self):
        return self.status in {
            self.STATUS_REVIEWED_UNPAID,
            self.STATUS_CONVERTED,
            self.STATUS_REJECTED,
            self.STATUS_NOT_INVOICE,
            self.STATUS_DUPLICATE,
            self.STATUS_NEEDS_FETCH,
        }

    def mark_reviewed_unpaid(self, issuer, artifact, metadata=None, message=''):
        self.confirmed_issuer = issuer
        self.selected_artifact = artifact
        self.reviewed_metadata = metadata or {}
        self.conversion_limitation_message = message or (
            'Reviewed as unpaid; no accounting record exists yet because expenses require a paid date.'
        )
        self.status = self.STATUS_REVIEWED_UNPAID


class IncomingInvoiceArtifact(models.Model):
    KIND_ATTACHMENT = 'attachment'
    KIND_EMAIL_BODY_PDF = 'email_body_pdf'
    KIND_INLINE_IMAGE = 'inline_image'
    KIND_OTHER = 'other'
    KIND_CHOICES = (
        (KIND_ATTACHMENT, 'Attachment'),
        (KIND_EMAIL_BODY_PDF, 'Email body PDF'),
        (KIND_INLINE_IMAGE, 'Inline image'),
        (KIND_OTHER, 'Other'),
    )

    candidate = models.ForeignKey(IncomingInvoiceCandidate, on_delete=models.CASCADE, related_name='artifacts')
    kind = models.CharField(max_length=32, choices=KIND_CHOICES, default=KIND_ATTACHMENT)
    original_filename = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=255, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64)
    file = models.FileField(upload_to=incoming_invoice_artifact_upload_path)
    extracted_text = models.TextField(blank=True)
    parsed_metadata = models.JSONField(default=dict, blank=True)
    is_invoice_like = models.BooleanField(default=False)
    invoice_confidence = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['candidate', 'id']
        constraints = [
            models.UniqueConstraint(fields=['candidate', 'sha256'], name='uniq_inc_art_cand_hash'),
        ]
        indexes = [
            models.Index(fields=['sha256'], name='incoming_artifact_hash_idx'),
            models.Index(fields=['kind', 'is_invoice_like'], name='incoming_artifact_kind_idx'),
        ]

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        return self.original_filename or self.get_kind_display()


class ImportMappingQuerySet(models.QuerySet):
    def visible_to(self, user):
        return self.filter(models.Q(scope=ImportMapping.SCOPE_GLOBAL) | models.Q(scope=ImportMapping.SCOPE_USER, owner=user))

    def matching_headers(self, headers):
        candidate_headers = set(
            filter(None, (normalize_import_header(header) for header in headers or []))
        )
        matches = []
        for mapping in self:
            stored_headers = set(filter(None, mapping.normalized_header_signature.split('|')))
            if stored_headers and stored_headers.issubset(candidate_headers):
                matches.append(mapping.pk)
        return self.filter(pk__in=matches)

    def best_for_user_and_headers(self, user, headers):
        return (
            self.visible_to(user)
            .matching_headers(headers)
            .order_by(
                models.Case(
                    models.When(scope=ImportMapping.SCOPE_USER, owner=user, then=0),
                    models.When(scope=ImportMapping.SCOPE_GLOBAL, then=1),
                    default=2,
                    output_field=models.IntegerField(),
                ),
                'name',
                'id',
            )
            .first()
        )


class ImportMapping(models.Model):
    SCOPE_GLOBAL = 'global'
    SCOPE_USER = 'user'
    SCOPE_CHOICES = (
        (SCOPE_GLOBAL, 'Global'),
        (SCOPE_USER, 'User'),
    )

    scope = models.CharField(max_length=16, choices=SCOPE_CHOICES)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='expense_import_mappings',
    )
    name = models.CharField(max_length=100)
    normalized_header_signature = models.TextField()
    mapping_json = models.JSONField(default=dict)
    default_row_selection_rules = models.JSONField(default=dict, blank=True)
    read_only = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ImportMappingQuerySet.as_manager()

    class Meta:
        ordering = ['scope', 'name']
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(scope='global', owner__isnull=True)
                    | models.Q(scope='user', owner__isnull=False)
                ),
                name='import_mapping_scope_owner_valid',
            ),
            models.UniqueConstraint(
                fields=['name'],
                condition=models.Q(scope='global'),
                name='unique_global_import_mapping_name',
            ),
            models.UniqueConstraint(
                fields=['owner', 'name'],
                condition=models.Q(scope='user'),
                name='unique_user_import_mapping_name',
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.scope})"

    def clean(self):
        super().clean()
        errors = {}
        if self.scope == self.SCOPE_GLOBAL and self.owner_id:
            errors['owner'] = 'Global import mappings cannot have an owner.'
        if self.scope == self.SCOPE_USER and not self.owner_id:
            errors['owner'] = 'User import mappings require an owner.'
        if not self.normalized_header_signature:
            errors['normalized_header_signature'] = 'Header signature is required.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk, read_only=True).exists():
            existing = type(self).objects.get(pk=self.pk)
            protected_fields = [
                'scope',
                'owner_id',
                'name',
                'normalized_header_signature',
                'mapping_json',
                'default_row_selection_rules',
                'read_only',
            ]
            if any(getattr(existing, field) != getattr(self, field) for field in protected_fields):
                raise ValidationError('Read-only import mappings cannot be modified.')
        super().save(*args, **kwargs)

    @classmethod
    def signature_from_headers(cls, headers):
        return normalized_import_header_signature(headers)

    def matches_headers(self, headers):
        candidate_headers = set(filter(None, (normalize_import_header(header) for header in headers or [])))
        stored_headers = set(filter(None, self.normalized_header_signature.split('|')))
        return bool(stored_headers) and stored_headers.issubset(candidate_headers)


class ImportBatch(models.Model):
    STATUS_UPLOADED = 'uploaded'
    STATUS_MAPPED = 'mapped'
    STATUS_IMPORTED = 'imported'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = (
        (STATUS_UPLOADED, 'Uploaded'),
        (STATUS_MAPPED, 'Mapped'),
        (STATUS_IMPORTED, 'Imported'),
        (STATUS_FAILED, 'Failed'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='expense_import_batches')
    issuer = models.ForeignKey(Issuer, on_delete=models.CASCADE, related_name='expense_import_batches')
    mapping = models.ForeignKey(
        ImportMapping,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='import_batches',
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_UPLOADED)
    source_filename = models.CharField(max_length=255, blank=True)
    normalized_header_signature = models.TextField(blank=True)
    raw_headers = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f"Import batch {self.id or 'pending'} for {self.issuer}"


class ImportPreviewRow(models.Model):
    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name='preview_rows')
    row_index = models.PositiveIntegerField()
    raw_data = models.JSONField(default=dict)
    mapped_data = models.JSONField(default=dict, blank=True)
    default_selected = models.BooleanField(default=True)
    selected = models.BooleanField(default=True)
    validation_errors = models.JSONField(default=list, blank=True)
    fingerprint = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['row_index']
        constraints = [
            models.UniqueConstraint(fields=['batch', 'row_index'], name='unique_import_preview_row_index'),
        ]

    def __str__(self):
        return f"Preview row {self.row_index} for batch {self.batch_id}"


class InvoiceFilterView(models.Model):
    issuer = models.ForeignKey(Issuer, on_delete=models.CASCADE, related_name='invoice_filter_views')
    name = models.CharField(max_length=64)
    query = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ('issuer', 'name')

    def __str__(self):
        return f"{self.name} ({self.issuer})"

    def to_query_params(self):
        params = {}
        status = self.query.get('status')
        if status:
            params['status'] = status

        period = self.query.get('period')
        if period and period != 'all':
            params['period'] = period

        project = self.query.get('project')
        if project:
            params['project'] = str(project)

        customer = self.query.get('customer')
        if customer:
            params['customer'] = str(customer)

        search = self.query.get('q')
        if search:
            params['q'] = search

        return params

    def to_querystring(self):
        from urllib.parse import urlencode

        params = self.to_query_params()
        return urlencode(params)


class BackupConfiguration(models.Model):
    singleton_pk = 1

    endpoint_url = models.URLField(max_length=500, blank=True)
    bucket_name = models.CharField(max_length=255, blank=True)
    region = models.CharField(max_length=100, blank=True)
    object_prefix = models.CharField(max_length=255, blank=True)
    access_key_id = models.CharField(max_length=255, blank=True)
    secret_access_key = models.CharField(max_length=255, blank=True)
    is_enabled = models.BooleanField(default=False)
    daily_run_time = models.TimeField(default=datetime.strptime('02:00', '%H:%M').time)
    daily_retention_count = models.PositiveIntegerField(default=14)
    weekly_retention_count = models.PositiveIntegerField(default=26)
    monthly_retention_count = models.PositiveIntegerField(default=36)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Backup configuration'
        verbose_name_plural = 'Backup configuration'

    def __str__(self):
        return 'Backup configuration'

    def clean(self):
        super().clean()

        if not self.is_enabled:
            return

        required_fields = {
            'endpoint_url': self.endpoint_url,
            'bucket_name': self.bucket_name,
            'region': self.region,
            'access_key_id': self.access_key_id,
            'secret_access_key': self.secret_access_key,
        }
        errors = {
            field_name: 'This field is required when backups are enabled.'
            for field_name, value in required_fields.items()
            if not value
        }

        if errors:
            raise ValidationError(errors)

    @classmethod
    def load(cls):
        configuration, _ = cls.objects.get_or_create(pk=cls.singleton_pk)
        return configuration

    def save(self, *args, **kwargs):
        self.pk = self.singleton_pk

        existing_configuration = type(self).objects.filter(pk=self.singleton_pk).first()
        if existing_configuration and self._state.adding and not self.created_at:
            self.created_at = existing_configuration.created_at
        
        super().save(*args, **kwargs)


def default_backup_run_failure_metadata():
    return {
        'stage': '',
        'exception_class': '',
        'message': '',
        'context': {},
    }


def default_backup_run_diagnostics():
    return {
        'events': [],
        'failure': default_backup_run_failure_metadata(),
    }


class BackupRun(models.Model):
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_SUCCEEDED = 'succeeded'
    STATUS_FAILED = 'failed'

    TRIGGER_SOURCE_MANUAL = 'manual'
    TRIGGER_SOURCE_SCHEDULED = 'scheduled'

    RETENTION_BUCKET_DAILY = 'daily'
    RETENTION_BUCKET_WEEKLY = 'weekly'
    RETENTION_BUCKET_MONTHLY = 'monthly'

    STATUS_CHOICES = (
        (STATUS_IN_PROGRESS, 'In progress'),
        (STATUS_SUCCEEDED, 'Succeeded'),
        (STATUS_FAILED, 'Failed'),
    )

    TRIGGER_SOURCE_CHOICES = (
        (TRIGGER_SOURCE_MANUAL, 'Manual'),
        (TRIGGER_SOURCE_SCHEDULED, 'Scheduled'),
    )

    RETENTION_BUCKET_CHOICES = (
        (RETENTION_BUCKET_DAILY, 'Daily'),
        (RETENTION_BUCKET_WEEKLY, 'Weekly'),
        (RETENTION_BUCKET_MONTHLY, 'Monthly'),
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_IN_PROGRESS)
    trigger_source = models.CharField(
        max_length=20,
        choices=TRIGGER_SOURCE_CHOICES,
        default=TRIGGER_SOURCE_MANUAL,
    )
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    storage_object_key = models.CharField(max_length=1024, blank=True)
    retention_bucket = models.CharField(max_length=20, choices=RETENTION_BUCKET_CHOICES, blank=True)
    artifact_size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    error_summary = models.CharField(max_length=500, blank=True)
    diagnostics = models.JSONField(default=default_backup_run_diagnostics, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-started_at', '-id']

    def __str__(self):
        return f"Backup run {self.id or 'pending'} - {self.get_status_display()}"

def _normalize_decimal(value):
    if value in (None, ''):
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0')
