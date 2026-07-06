import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django import forms
from django.core.exceptions import NON_FIELD_ERRORS
from django.db.models import Q
from django.forms import BaseInlineFormSet, inlineformset_factory, ModelForm
from django.forms.widgets import NumberInput

from invoices.models import (
    Address,
    BackupConfiguration,
    Company,
    Currency,
    Customer,
    Invoice,
    Issuer,
    IssuerBankAccount,
    IssuerSifSettings,
    OrderLine,
    PaymentTerm,
    Project,
)
from invoices.services.bank_accounts import resolve_invoice_bank_account
from invoices.services.sif import is_valid_spanish_tax_id


class StyledModelForm(ModelForm):
    def _apply_pico_styles(self):
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, (forms.HiddenInput,)):
                continue
            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault('rows', 3)
            base_class = widget.attrs.get('class', '')
            class_tokens = [token for token in base_class.split() if token]
            if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                class_tokens.append('field-control--checkbox')
            else:
                class_tokens.append('field-control')
            widget.attrs['class'] = ' '.join(sorted(set(class_tokens)))


class BackupConfigurationForm(StyledModelForm):
    prefix = 'backup_settings'
    connection_test_fields = (
        'endpoint_url',
        'bucket_name',
        'region',
        'access_key_id',
        'secret_access_key',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['daily_run_time'].widget = forms.TimeInput(
            format='%H:%M',
            attrs={'type': 'time'},
        )
        self.fields['secret_access_key'].widget = forms.PasswordInput(render_value=True)
        for field_name in ('daily_retention_count', 'weekly_retention_count', 'monthly_retention_count'):
            self.fields[field_name].widget.attrs.setdefault('min', 0)
        self._apply_pico_styles()

    class Meta:
        model = BackupConfiguration
        fields = [
            'endpoint_url',
            'bucket_name',
            'region',
            'object_prefix',
            'access_key_id',
            'secret_access_key',
            'is_enabled',
            'daily_run_time',
            'daily_retention_count',
            'weekly_retention_count',
            'monthly_retention_count',
        ]

    def is_valid_for_connection_test(self):
        self.full_clean()

        allowed_error_keys = {*self.connection_test_fields, NON_FIELD_ERRORS}
        for field_name in list(self.errors):
            if field_name not in allowed_error_keys:
                del self.errors[field_name]

        return not bool(self.errors)


class InvoiceForm(StyledModelForm):
    project = forms.ModelChoiceField(queryset=Project.objects.none())
    bank_account = forms.ModelChoiceField(
        queryset=IssuerBankAccount.objects.none(),
        required=False,
        empty_label='Select bank account',
        label='Bank account',
    )
    issued_date = forms.DateField(widget=NumberInput(attrs={'type': 'date'}))
    due_date = forms.DateField(required=False, widget=NumberInput(attrs={'type': 'date'}))
    payment_term = forms.ModelChoiceField(
        queryset=PaymentTerm.objects.none(),
        required=False,
        empty_label='Select payment period',
        label='Payment period',
    )
    reference_number = forms.CharField(
        required=False,
        max_length=64,
        widget=forms.TextInput(attrs={'placeholder': 'YYYY.XXXX'}),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Optional notes shown on the invoice'}),
        label='Notes',
    )

    def __init__(self, *args, issuer=None, customer=None, **kwargs):
        super().__init__(*args, **kwargs)
        instance = self.instance if isinstance(self.instance, Invoice) else None
        project_qs = Project.objects.select_related('customer__company').filter(
            status=Project.STATUS_ACTIVE,
            customer__is_active=True,
        ).order_by('title')
        if issuer:
            project_qs = project_qs.filter(customer__issuer=issuer)
        if customer:
            project_qs = project_qs.filter(customer=customer)
        self.fields['project'].queryset = project_qs
        self.fields['project'].label_from_instance = lambda obj: f"{obj.project_code} — {obj.title}"
        self.fields['project'].required = True
        payment_terms = PaymentTerm.objects.order_by('days', 'name')
        self.fields['payment_term'].queryset = payment_terms
        self.fields['payment_term'].widget.attrs.setdefault('class', 'field-control')
        self.fields['due_date'].widget.attrs.setdefault('class', 'field-control')

        bank_account_qs = IssuerBankAccount.objects.none()
        if issuer:
            bank_account_qs = IssuerBankAccount.objects.filter(issuer=issuer, is_active=True)
            if instance and instance.bank_account_id:
                bank_account_qs = IssuerBankAccount.objects.filter(issuer=issuer).filter(
                    Q(is_active=True) | Q(pk=instance.bank_account_id)
                )
        self.fields['bank_account'].queryset = bank_account_qs.order_by('sort_order', 'label', 'id')
        self.fields['bank_account'].label_from_instance = lambda obj: f"{obj.label}{' (default)' if obj.is_default else ''}"
        self.fields['bank_account'].widget.attrs.setdefault('class', 'field-control')

        project = instance.project if instance and instance.project_id else None
        if instance and not getattr(instance, 'customer_id', None) and customer:
            instance.customer = customer

        if not self.is_bound and not project and customer:
            try:
                project_count = project_qs.count()
            except Exception:
                project_count = 0
            if project_count == 1:
                only_project = project_qs.first()
                if only_project:
                    project = only_project
                    self.fields['project'].initial = only_project.pk

        if not self.is_bound and instance and not getattr(instance, 'notes', None):
            project_notes = getattr(project, 'comment', None)
            if project_notes:
                self.initial.setdefault('notes', project_notes)

        payment_term_initial = None
        if instance and instance.payment_term_id:
            payment_term_initial = instance.payment_term_id
        elif project and project.payment_term_id:
            payment_term_initial = project.payment_term_id
        elif project and project.customer and project.customer.payment_term_id:
            payment_term_initial = project.customer.payment_term_id
        elif instance and instance.customer and instance.customer.payment_term_id:
            payment_term_initial = instance.customer.payment_term_id

        if not self.is_bound and payment_term_initial:
            self.fields['payment_term'].initial = payment_term_initial

        bank_account_initial = None
        if instance and instance.bank_account_id:
            bank_account_initial = instance.bank_account_id
        elif issuer:
            resolved_account = resolve_invoice_bank_account(
                issuer,
                customer=(project.customer if project else (customer or getattr(instance, 'customer', None))),
                project=project,
                exclude_invoice=instance if instance and instance.pk else None,
            )
            bank_account_initial = resolved_account.pk if resolved_account else None
        if not self.is_bound and bank_account_initial:
            self.fields['bank_account'].initial = bank_account_initial

        if not self.is_bound and instance and instance.due_date:
            self.fields['due_date'].initial = instance.due_date

        self._apply_pico_styles()

    def clean(self):
        cleaned = super().clean()
        project = cleaned.get('project')
        if project is None and self.instance and getattr(self.instance, 'project', None):
            project = self.instance.project

        payment_term = cleaned.get('payment_term')
        if not payment_term:
            if project and project.payment_term_id:
                payment_term = project.payment_term
            elif project and project.customer and project.customer.payment_term_id:
                payment_term = project.customer.payment_term
            elif self.instance and getattr(self.instance, 'customer', None) and self.instance.customer.payment_term_id:
                payment_term = self.instance.customer.payment_term
            if payment_term:
                cleaned['payment_term'] = payment_term

        issued_date = cleaned.get('issued_date')
        due_date = cleaned.get('due_date')
        bank_account = cleaned.get('bank_account')

        if issued_date and payment_term and not due_date:
            cleaned['due_date'] = issued_date + timedelta(days=payment_term.days)
        elif issued_date and due_date and due_date < issued_date:
            self.add_error('due_date', 'Due date cannot be earlier than the invoice date.')

        if bank_account:
            issuer_id = getattr(bank_account, 'issuer_id', None)
            invoice_issuer_id = getattr(self.instance, 'issuer_id', None)
            if invoice_issuer_id and issuer_id != invoice_issuer_id:
                self.add_error('bank_account', 'Bank account must belong to the invoice issuer.')
            if not bank_account.is_active and bank_account.pk != getattr(self.instance, 'bank_account_id', None):
                self.add_error('bank_account', 'Select an active bank account.')

        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        project = self.cleaned_data.get('project')
        if project:
            instance.customer = project.customer
        payment_term = self.cleaned_data.get('payment_term')
        if payment_term:
            instance.payment_term = payment_term
        else:
            instance.payment_term = None
        instance.due_date = self.cleaned_data.get('due_date')
        if not self.is_bound or 'bank_account' in self.data:
            instance.bank_account = self.cleaned_data.get('bank_account')
        elif not instance.pk and getattr(instance, 'issuer', None):
            instance.bank_account = resolve_invoice_bank_account(
                instance.issuer,
                customer=instance.customer,
                project=project,
            )
        instance.apply_missing_currency_snapshot()
        if commit:
            instance.save()
        return instance

    class Meta:
        model = Invoice
        fields = ['reference_number', 'issued_date', 'due_date', 'payment_term', 'status', 'project', 'bank_account', 'notes']


class OrderLineForm(StyledModelForm):
    LINE_TYPE_CHOICES = (
        (OrderLine.LINE_TYPE_QUANTITY, 'Time / Quantity'),
        (OrderLine.LINE_TYPE_FLAT, 'Flat fee'),
    )

    line_type = forms.ChoiceField(choices=LINE_TYPE_CHOICES)
    description = forms.CharField(max_length=255, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['line_type'].widget.attrs.setdefault('class', 'field-control order-line-type')
        self._apply_pico_styles()
        self.fields['quantity'].widget.attrs.setdefault('step', '0.01')
        self.fields['quantity'].widget.attrs.setdefault('inputmode', 'decimal')
        quantity_initial = self.initial.get('quantity', Decimal('0'))
        try:
            quantity_decimal = Decimal(str(quantity_initial))
        except (InvalidOperation, TypeError):
            quantity_decimal = Decimal('0')
        self.initial['quantity'] = f"{quantity_decimal:.2f}"
        instance = getattr(self, 'instance', None)
        initial_type = OrderLine.LINE_TYPE_QUANTITY
        if instance and instance.pk:
            if instance.line_type == OrderLine.LINE_TYPE_FLAT:
                initial_type = OrderLine.LINE_TYPE_FLAT
            else:
                initial_type = OrderLine.LINE_TYPE_QUANTITY
        if not self.is_bound:
            self.fields['line_type'].initial = initial_type

    def clean(self):
        cleaned = super().clean()
        line_type = cleaned.get('line_type') or OrderLine.LINE_TYPE_QUANTITY
        quantity = cleaned.get('quantity')
        unit_price = cleaned.get('unit_price')
        if line_type != OrderLine.LINE_TYPE_FLAT:
            qty_val = quantity or Decimal('0')
            price_val = unit_price or Decimal('0')
            if price_val and qty_val <= 0:
                self.add_error('quantity', 'Quantity must be greater than zero for time / quantity lines.')
        return cleaned

    class Meta:
        model = OrderLine
        fields = ['line_type', 'description', 'quantity', 'unit_price']

    def save(self, commit=True):
        instance = super().save(commit=False)
        line_type = self.cleaned_data.get('line_type') or OrderLine.LINE_TYPE_QUANTITY
        instance.line_type = line_type
        if line_type == OrderLine.LINE_TYPE_FLAT:
            if not instance.quantity or instance.quantity <= 0:
                instance.quantity = Decimal('1')
            instance.manual_total = True
            unit_price = self.cleaned_data.get('unit_price') or Decimal('0')
            instance.line_total = unit_price
        else:
            instance.manual_total = False
        if commit:
            instance.save()
        return instance


class BaseInlineOrderFormSet(BaseInlineFormSet):
    deletion_widget = forms.HiddenInput
    MIN_ROWS = 5

    def get_extra(self):
        # On GET, only add blanks to reach MIN_ROWS. If existing >= MIN_ROWS, no extra rows.
        # On POST, defer to default behavior so posted TOTAL_FORMS drives processing.
        if self.is_bound:
            return super().get_extra()
        existing = 0
        try:
            parent = getattr(self, 'instance', None)
            if parent is not None and getattr(parent, 'pk', None):
                # Inline formset existing forms correspond to related objects
                existing = parent.orderline_set.count()
            else:
                existing = 0
        except Exception:
            existing = 0
        return max(self.MIN_ROWS - existing, 0)

    def total_form_count(self):
        # Ensure the management TOTAL_FORMS reflects our dynamic extra on GET.
        if self.is_bound:
            return super().total_form_count()
        try:
            initial = super().initial_form_count()
        except Exception:
            initial = 0
        desired_extra = max(self.MIN_ROWS - initial, 0)
        total = initial + desired_extra
        try:
            max_num = self.max_num
            if max_num is not None:
                total = min(total, max_num)
        except Exception:
            pass
        return total

    def clean(self):
        super().clean()
        # Auto-discard empty slips (order lines) so they are not saved
        for form in self.forms:
            if not hasattr(form, 'cleaned_data'):
                continue
            data = form.cleaned_data
            if not data or data.get('DELETE'):
                continue
            line_type = data.get('line_type') or OrderLine.LINE_TYPE_QUANTITY
            description = (data.get('description') or '').strip()
            quantity = data.get('quantity')
            unit_price = data.get('unit_price')

            # Normalize numeric values
            try:
                qty_val = Decimal(str(quantity)) if quantity not in (None, '') else Decimal('0')
            except Exception:
                qty_val = Decimal('0')
            try:
                price_val = Decimal(str(unit_price)) if unit_price not in (None, '') else Decimal('0')
            except Exception:
                price_val = Decimal('0')

            is_empty_quantity_line = (
                line_type != OrderLine.LINE_TYPE_FLAT and qty_val <= 0 and price_val == 0
            )
            is_empty_flat_line = (
                line_type == OrderLine.LINE_TYPE_FLAT and price_val == 0
            )

            if (not description) and (is_empty_quantity_line or is_empty_flat_line):
                # Mark for deletion to avoid saving an empty slip
                data['DELETE'] = True


OrderLineFormSet = inlineformset_factory(
    Invoice,
    OrderLine,
    form=OrderLineForm,
    formset=BaseInlineOrderFormSet,
    fields=('line_type', 'description', 'quantity', 'unit_price'),
    extra=5,
    can_delete=True,
)


class AddressForm(StyledModelForm):
    prefix = 'address'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['full_address'].label = 'Address'
        self.fields['full_address'].widget = forms.Textarea(
            attrs={'rows': 3, 'placeholder': 'Street address\nCity, Postal code\nCountry'})
        self._apply_pico_styles()

    class Meta:
        model = Address
        fields = ['full_address']


class CompanyForm(StyledModelForm):
    prefix = 'company'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer_information_file_number'].label = 'VAT'
        self.fields['contact_email'].widget = forms.EmailInput()
        self.fields['contact_cc_email'].widget = forms.EmailInput()
        self._apply_pico_styles()

    class Meta:
        model = Company
        fields = [
            'name',
            'customer_information_file_number',
            'contact_name',
            'contact_email',
            'contact_cc_email',
            'contact_phone_number',
            'contact_country',
        ]


class CustomerBillingForm(StyledModelForm):
    prefix = 'customer'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['currency'].required = False
        self.fields['currency'].empty_label = 'Select currency'
        self.fields['currency'].queryset = Currency.objects.order_by('code')
        self.fields['payment_term'].required = False
        self.fields['payment_term'].empty_label = 'Select payment period'
        self.fields['payment_term'].queryset = PaymentTerm.objects.order_by('days', 'name')
        self.fields['payment_term'].label = 'Payment period'
        self.fields['payment_notes'].required = False
        self.fields['payment_notes'].widget = forms.Textarea(
            attrs={'rows': 3, 'placeholder': 'Add optional customer-specific payment notes'}
        )
        self.fields['payment_notes'].label = 'Payment notes'
        self._apply_pico_styles()

    class Meta:
        model = Customer
        fields = ['currency', 'payment_term', 'payment_notes']


class IssuerCompanyForm(StyledModelForm):
    prefix = 'issuer_company'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer_information_file_number'].label = 'VAT'
        self.fields['payment_terms'].widget = forms.Textarea(
            attrs={'rows': 3, 'placeholder': 'Add optional payment notes shown on invoices'}
        )
        self.fields['payment_terms'].label = 'Payment notes'
        self.fields['payment_term'].label = 'Payment period'
        self.fields['payment_term'].required = False
        self.fields['payment_term'].queryset = PaymentTerm.objects.order_by('days', 'name')
        self.fields['payment_term'].empty_label = 'Select payment period'
        self.fields['contact_email'].widget = forms.EmailInput()
        self._apply_pico_styles()

    class Meta:
        model = Company
        fields = [
            'name',
            'customer_information_file_number',
            'contact_name',
            'contact_email',
            'contact_phone_number',
            'payment_term',
            'payment_terms',
        ]


class IssuerBankAccountForm(StyledModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['label'].widget.attrs.setdefault('placeholder', 'Primary EUR account')
        self.fields['payment_method'].widget.attrs.setdefault('placeholder', 'Bank transfer')
        self.fields['account_details'].widget = forms.Textarea(
            attrs={'rows': 3, 'placeholder': 'Add IBAN, SWIFT, or payment instructions'}
        )
        self.fields['sort_order'].widget.attrs.setdefault('min', 0)
        if not self.instance.pk:
            self.fields['is_active'].initial = False
            self.fields['sort_order'].initial = None
        self._apply_pico_styles()

    class Meta:
        model = IssuerBankAccount
        fields = [
            'label',
            'payment_method',
            'account_details',
            'is_active',
            'sort_order',
            'is_default',
        ]

    def _post_clean(self):
        self.instance._skip_default_uniqueness_validation = True
        try:
            super()._post_clean()
        finally:
            if hasattr(self.instance, '_skip_default_uniqueness_validation'):
                del self.instance._skip_default_uniqueness_validation


class BaseIssuerBankAccountFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        active_forms = []
        default_forms = []
        for form in self.forms:
            if not hasattr(form, 'cleaned_data') or not form.cleaned_data:
                continue
            if self.can_delete and form.cleaned_data.get('DELETE'):
                continue
            label = (form.cleaned_data.get('label') or '').strip()
            details = (form.cleaned_data.get('account_details') or '').strip()
            payment_method = (form.cleaned_data.get('payment_method') or '').strip()
            has_account_data = bool(label or details or payment_method or form.instance.pk)
            if not has_account_data:
                continue
            is_active = form.cleaned_data.get('is_active')
            is_default = form.cleaned_data.get('is_default')
            if is_default and not is_active:
                form.add_error('is_default', 'The default bank account must be active.')
            if is_active:
                active_forms.append(form)
                if is_default:
                    default_forms.append(form)

        if active_forms and len(default_forms) != 1:
            raise forms.ValidationError('Select exactly one active default bank account.')


IssuerBankAccountFormSet = inlineformset_factory(
    Issuer,
    IssuerBankAccount,
    form=IssuerBankAccountForm,
    formset=BaseIssuerBankAccountFormSet,
    extra=1,
    can_delete=False,
)


class IssuerSettingsForm(StyledModelForm):
    prefix = 'issuer_settings'
    TOKEN_PATTERN = re.compile(r'{{([A-Z]+)}}')
    ALLOWED_TOKENS = {'YYYY', 'YY', 'MM', 'DD', 'ID'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        invoice_field = self.fields['invoice_format']
        invoice_field.label = 'Invoice format'
        invoice_field.widget.attrs.setdefault('placeholder', '{{YYYY}}.{{ID}}')
        invoice_field.help_text = 'Available tokens: {{YYYY}}, {{YY}}, {{MM}}, {{DD}}, {{ID}}.'

        sequence_field = self.fields['next_invoice_number']
        sequence_field.label = 'Next invoice ID'
        sequence_field.widget = NumberInput(attrs={'min': 1})

        self._apply_pico_styles()

    class Meta:
        model = Issuer
        fields = ['invoice_format', 'next_invoice_number']

    def clean_invoice_format(self):
        raw_format = self.cleaned_data.get('invoice_format', '')
        normalized = (raw_format or '').strip()
        if not normalized:
            raise forms.ValidationError('Invoice format cannot be empty.')

        tokens = self.TOKEN_PATTERN.findall(normalized)
        invalid_tokens = [token for token in tokens if token not in self.ALLOWED_TOKENS]
        if invalid_tokens:
            raise forms.ValidationError(
                f"Unsupported token(s): {', '.join(sorted(set(invalid_tokens)))}."
            )
        if 'ID' not in tokens:
            raise forms.ValidationError('Invoice format must include the {{ID}} token.')

        stripped = self.TOKEN_PATTERN.sub('', normalized)
        if '{' in stripped or '}' in stripped:
            raise forms.ValidationError('Invoice format contains unmatched braces.')

        if re.search(r'[^A-Za-z0-9\s#\.\-/_]', stripped):
            raise forms.ValidationError('Invoice format contains unsupported characters.')

        return normalized

    def clean_next_invoice_number(self):
        value = self.cleaned_data.get('next_invoice_number')
        if value is None or value < 1:
            raise forms.ValidationError('Next invoice ID must be at least 1.')
        return value


class IssuerSifSettingsForm(StyledModelForm):
    prefix = 'sif_settings'

    def __init__(self, *args, issuer_company_tax_id=None, **kwargs):
        self.issuer_company_tax_id = issuer_company_tax_id
        super().__init__(*args, **kwargs)
        if issuer_company_tax_id is not None:
            self.instance._validation_tax_id = issuer_company_tax_id

        self.fields['tax_country'].label = 'Issuer tax country'
        self.fields['tax_country'].required = False
        self.fields['tax_country'].help_text = 'Choose Spain (ES) only for Spanish establishments covered by SIF.'
        self.fields['enabled'].label = 'Enable Spanish SIF compliance for this issuer'
        self.fields['mode'].label = 'SIF mode'
        self.fields['mode'].help_text = 'VERI*FACTU is optional. NO VERI*FACTU is also a SIF mode with local-control obligations.'
        self.fields['aeat_environment'].label = 'AEAT environment'
        self.fields['deadline_category'].label = 'Readiness deadline'
        self.fields['software_code'].label = 'Software code'
        self.fields['certificate_reference'].label = 'Certificate reference'
        self.fields['certificate_reference'].help_text = 'Store a non-secret label or external reference only; do not paste certificate files or passwords.'
        self.fields['operational_status'].label = 'Operational readiness'
        for field_name, field in self.fields.items():
            if field_name != 'enabled':
                field.required = False
        self._apply_pico_styles()

    class Meta:
        model = IssuerSifSettings
        fields = [
            'tax_country',
            'enabled',
            'mode',
            'aeat_environment',
            'taxpayer_role',
            'deadline_category',
            'software_name',
            'software_version',
            'software_code',
            'certificate_reference',
            'operational_status',
        ]

    def clean(self):
        cleaned_data = super().clean()
        for field_name, field in self.fields.items():
            value = cleaned_data.get(field_name)
            if value in (None, '') and field_name != 'enabled':
                cleaned_data[field_name] = getattr(
                    self.instance,
                    field_name,
                    self._meta.model._meta.get_field(field_name).get_default(),
                )

        enabled = cleaned_data.get('enabled')
        tax_country = cleaned_data.get('tax_country')
        if enabled and tax_country != IssuerSifSettings.TaxCountry.SPAIN:
            self.add_error('enabled', 'SIF can only be enabled for Spanish issuers.')
        if enabled and not is_valid_spanish_tax_id(self.issuer_company_tax_id):
            self.add_error('enabled', 'SIF requires a valid Spanish NIF, NIE, or CIF for the issuer.')
        return cleaned_data


class ProjectForm(StyledModelForm):
    prefix = 'project'

    @staticmethod
    def _customer_choice_label(customer):
        label = customer.company.name if customer.company else f"Customer {customer.pk}"
        if not customer.is_active:
            return f"{label} (inactive)"
        return label

    def __init__(self, *args, issuer=None, **kwargs):
        self.issuer = issuer
        super().__init__(*args, **kwargs)
        instance_customer = None
        if self.instance and self.instance.pk and getattr(self.instance, 'customer_id', None):
            instance_customer = self.instance.customer

        customer_qs = Customer.objects.select_related('company')
        if issuer:
            customer_qs = customer_qs.filter(issuer=issuer)

        customer_filter = Q(is_active=True)
        if (
            instance_customer
            and not instance_customer.is_active
            and (not issuer or instance_customer.issuer_id == issuer.pk)
        ):
            customer_filter |= Q(pk=instance_customer.pk)

        customer_qs = customer_qs.filter(customer_filter)

        customer_qs = customer_qs.order_by('company__name')
        self.fields['customer'].queryset = customer_qs
        self.fields['customer'].label_from_instance = self._customer_choice_label
        payment_terms = PaymentTerm.objects.order_by('days', 'name')
        self.fields['payment_term'].queryset = payment_terms
        self.fields['payment_term'].required = False
        self.fields['payment_term'].empty_label = 'Select payment period'
        self.fields['payment_term'].label = 'Payment period'
        self.fields['comment'].widget = forms.Textarea(attrs={'rows': 3})
        self._apply_pico_styles()

        if not self.is_bound:
            if self.instance and self.instance.pk and self.instance.payment_term_id:
                self.fields['payment_term'].initial = self.instance.payment_term_id
            else:
                customer_id = getattr(self.instance, 'customer_id', None)
                if customer_id:
                    customer_payment = self.instance.customer.payment_term_id
                    if customer_payment:
                        self.fields['payment_term'].initial = customer_payment

    def clean(self):
        cleaned_data = super().clean()
        project_code = cleaned_data.get('project_code')
        customer = cleaned_data.get('customer')
        issuer_id = customer.issuer_id if customer else getattr(self.issuer, 'pk', None)
        if project_code and issuer_id:
            duplicate_projects = Project.objects.filter(
                issuer_id=issuer_id,
                project_code=project_code,
            )
            if self.instance and self.instance.pk:
                duplicate_projects = duplicate_projects.exclude(pk=self.instance.pk)
            if duplicate_projects.exists():
                self.add_error('project_code', 'Project code already exists for this company.')
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        payment_term = self.cleaned_data.get('payment_term')
        if payment_term:
            instance.payment_term = payment_term
        elif getattr(instance, 'customer_id', None):
            customer_payment = instance.customer.payment_term
            instance.payment_term = customer_payment
        else:
            instance.payment_term = None
        instance.issuer_id = instance.customer.issuer_id if getattr(instance, 'customer_id', None) else None
        if commit:
            instance.save()
        return instance

    class Meta:
        model = Project
        fields = ['title', 'project_code', 'status', 'customer', 'payment_term', 'comment']


class CustomerStatusForm(forms.Form):
    prefix = 'customer_status'
    STATUS_CHOICES = (('true', 'Active'), ('false', 'Inactive'))
    is_active = forms.TypedChoiceField(
        required=True,
        initial='true',
        choices=STATUS_CHOICES,
        coerce=lambda value: value == 'true',
        label='Active client',
    )

    def __init__(self, *args, **kwargs):
        initial = kwargs.get('initial')
        if initial is not None:
            initial_mapping = dict(initial)
            if 'is_active' in initial_mapping:
                initial_mapping['is_active'] = 'true' if initial_mapping['is_active'] else 'false'
                kwargs['initial'] = initial_mapping
        super().__init__(*args, **kwargs)
        self.fields['is_active'].widget.attrs.setdefault('class', 'field-control')
