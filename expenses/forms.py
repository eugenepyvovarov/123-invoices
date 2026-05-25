import json
import os
from decimal import Decimal

from django import forms

from invoices.models import (
    Customer,
    Expense,
    IncomingEmailSource,
    IncomingInvoiceArtifact,
    IncomingInvoiceCandidate,
    Issuer,
    IssuerEmailRoutingRule,
    Project,
)


ALLOWED_ATTACHMENT_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv', '.png', '.jpg', '.jpeg'
}
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10 MB


class ExpenseForm(forms.ModelForm):
    paid_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    remove_attachment = forms.BooleanField(required=False)

    class Meta:
        model = Expense
        fields = [
            'paid_date',
            'amount',
            'customer',
            'project',
            'attachment',
            'description',
            'exclude_from_reports',
        ]
        widgets = {
            'customer': forms.Select(),
            'project': forms.Select(),
            'attachment': forms.ClearableFileInput(),
            'description': forms.Textarea(attrs={'placeholder': 'Optional notes', 'rows': 3}),
        }

    def __init__(self, *args, issuer=None, **kwargs):
        self.issuer = issuer
        super().__init__(*args, **kwargs)
        customer_queryset = Customer.objects.none()
        project_queryset = Project.objects.none()
        if issuer:
            customer_queryset = Customer.objects.filter(
                issuer=issuer,
                is_active=True,
                company__isnull=False,
            ).select_related('company').order_by('company__name')
            project_queryset = Project.objects.filter(
                customer__issuer=issuer,
                status=Project.STATUS_ACTIVE,
                customer__is_active=True,
            ).select_related('customer__company').order_by('title')

        self.fields['customer'].queryset = customer_queryset
        self.fields['project'].queryset = project_queryset
        self.fields['customer'].required = False
        self.fields['project'].required = False

        self.fields['amount'].widget.attrs.setdefault('step', '0.01')
        self.fields['amount'].widget.attrs.setdefault('inputmode', 'decimal')
        attachment_widget = self.fields['attachment'].widget
        existing_classes = [token for token in attachment_widget.attrs.get('class', '').split() if token]
        existing_classes.append('field-control')
        attachment_widget.attrs['class'] = ' '.join(dict.fromkeys(existing_classes))
        attachment_widget.attrs['accept'] = ','.join(sorted(ALLOWED_ATTACHMENT_EXTENSIONS))

        self.fields['remove_attachment'].widget = forms.CheckboxInput()
        self.fields['remove_attachment'].widget.attrs.setdefault('class', 'field-control--checkbox')
        self.fields['remove_attachment'].label = 'Remove existing attachment'
        self.fields['remove_attachment'].initial = False
        if self.instance and self.instance.attachment:
            self.fields['remove_attachment'].widget.attrs.pop('disabled', None)
        else:
            self.fields['remove_attachment'].widget.attrs['disabled'] = True

        self.fields['exclude_from_reports'].widget = forms.CheckboxInput(attrs={'class': 'field-control--checkbox'})
        self.fields['exclude_from_reports'].label = 'Exclude from reports'

        self._apply_pico_styles()

    def _apply_pico_styles(self):
        styled_widgets = (
            forms.DateInput,
            forms.NumberInput,
            forms.Select,
            forms.TextInput,
            forms.Textarea,
        )
        for name, field in self.fields.items():
            widget = field.widget
            if name in {'remove_attachment', 'exclude_from_reports'}:
                continue
            if isinstance(widget, styled_widgets):
                existing = widget.attrs.get('class', '')
                tokens = [token for token in existing.split() if token not in {'form-control', 'form-select'}]
                tokens.append('field-control')
                widget.attrs['class'] = ' '.join(dict.fromkeys(tokens))

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is None:
            return amount
        if amount < Decimal('0'):
            raise forms.ValidationError('Amount must be zero or greater.')
        return amount

    def clean_attachment(self):
        file = self.cleaned_data.get('attachment')
        if not file:
            return file
        ext = os.path.splitext(file.name or '')[1].lower()
        if ext and ext not in ALLOWED_ATTACHMENT_EXTENSIONS:
            raise forms.ValidationError('Unsupported file type.')
        size = getattr(file, 'size', 0)
        if size and size > MAX_ATTACHMENT_SIZE:
            raise forms.ValidationError('File exceeds the 10 MB size limit.')
        return file

    def clean(self):
        cleaned = super().clean()
        project = cleaned.get('project')
        customer = cleaned.get('customer')
        remove_attachment = cleaned.get('remove_attachment')

        if project:
            project_customer = project.customer if project.customer_id else None
            if customer and project_customer and customer.pk != project_customer.pk:
                self.add_error('project', 'Selected project is not associated with the chosen customer.')
            elif not customer and project_customer:
                cleaned['customer'] = project_customer

        if self.files.get(self.add_prefix('attachment')):
            cleaned['remove_attachment'] = False

        if remove_attachment and not (self.instance and self.instance.attachment):
            cleaned['remove_attachment'] = False

        return cleaned

    def save(self, commit=True, issuer=None):  # type: ignore[override]
        expense = super().save(commit=False)
        if issuer is not None:
            expense.issuer = issuer
        remove_attachment = self.cleaned_data.get('remove_attachment')
        if remove_attachment and expense.attachment:
            expense.attachment.delete(save=False)
            expense.attachment = None
        if commit:
            expense.save()
            self.save_m2m()
        return expense


class JsonListField(forms.CharField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('required', False)
        kwargs.setdefault('widget', forms.Textarea(attrs={'rows': 2}))
        super().__init__(*args, **kwargs)

    def prepare_value(self, value):
        if isinstance(value, list):
            return ', '.join(str(item) for item in value)
        return value or ''

    def to_python(self, value):
        if not value:
            return []
        if isinstance(value, list):
            return value
        value = value.strip()
        if not value:
            return []
        if value.startswith('['):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as exc:
                raise forms.ValidationError('Enter a comma-separated list or valid JSON list.') from exc
            if not isinstance(parsed, list):
                raise forms.ValidationError('Enter a list of values.')
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [item.strip() for item in value.split(',') if item.strip()]


class IncomingEmailSourceForm(forms.ModelForm):
    class Meta:
        model = IncomingEmailSource
        fields = ['display_name', 'email_address', 'issuer', 'is_enabled', 'folder', 'polling_query', 'credential_reference']
        widgets = {
            'display_name': forms.TextInput(),
            'email_address': forms.EmailInput(),
            'folder': forms.TextInput(),
            'polling_query': forms.TextInput(),
            'credential_reference': forms.TextInput(),
            'is_enabled': forms.CheckboxInput(attrs={'class': 'field-control--checkbox'}),
        }

    def __init__(self, *args, user=None, issuers=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields['issuer'].queryset = issuers or Issuer.objects.none()
        self.fields['issuer'].required = False
        self._apply_pico_styles()

    def _apply_pico_styles(self):
        for name, field in self.fields.items():
            if name == 'is_enabled':
                continue
            field.widget.attrs.setdefault('class', 'field-control')

    def save(self, commit=True):  # type: ignore[override]
        source = super().save(commit=False)
        source.provider = IncomingEmailSource.PROVIDER_IMAP
        if self.user is not None and not source.user_id:
            source.user = self.user
        if commit:
            source.save()
        return source


class IssuerEmailRoutingRuleForm(forms.ModelForm):
    recipient_aliases = JsonListField(label='Recipient aliases')
    delivered_to_addresses = JsonListField(label='Delivered-to addresses')
    legal_names = JsonListField(label='Legal company names')
    tax_identifiers = JsonListField(label='VAT/tax identifiers')
    keywords = JsonListField(label='Keywords')

    class Meta:
        model = IssuerEmailRoutingRule
        fields = [
            'recipient_aliases',
            'delivered_to_addresses',
            'legal_names',
            'tax_identifiers',
            'keywords',
            'confidence_threshold',
            'auto_assign_enabled',
        ]
        widgets = {
            'confidence_threshold': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '1'}),
            'auto_assign_enabled': forms.CheckboxInput(attrs={'class': 'field-control--checkbox'}),
        }

    def __init__(self, *args, issuer=None, **kwargs):
        self.issuer = issuer
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name == 'auto_assign_enabled':
                continue
            field.widget.attrs.setdefault('class', 'field-control')

    def save(self, commit=True):  # type: ignore[override]
        rule = super().save(commit=False)
        if self.issuer is not None:
            rule.issuer = self.issuer
        if commit:
            rule.save()
        return rule


class IncomingCandidateReviewForm(forms.Form):
    ACTION_CONFIRM = 'confirm'
    ACTION_NOT_INVOICE = 'not_invoice'
    ACTION_NEEDS_FETCH = 'needs_fetch'
    ACTION_REVIEWED_UNPAID = 'reviewed_unpaid'
    ACTION_DUPLICATE = 'duplicate'
    ACTION_LINK_EXISTING = 'link_existing'
    ACTION_CHOICES = (
        (ACTION_CONFIRM, 'Confirm company/artifact'),
        (ACTION_NOT_INVOICE, 'Not an invoice'),
        (ACTION_NEEDS_FETCH, 'Needs manual fetch'),
        (ACTION_REVIEWED_UNPAID, 'Reviewed/unpaid'),
        (ACTION_DUPLICATE, 'Duplicate'),
        (ACTION_LINK_EXISTING, 'Duplicate / link existing expense'),
    )

    action = forms.ChoiceField(choices=ACTION_CHOICES)
    confirmed_issuer = forms.ModelChoiceField(queryset=Issuer.objects.none(), required=False)
    selected_artifact = forms.ModelChoiceField(queryset=IncomingInvoiceArtifact.objects.none(), required=False)
    vendor = forms.CharField(required=False, max_length=255)
    description = forms.CharField(required=False, max_length=255)
    amount = forms.DecimalField(required=False, max_digits=12, decimal_places=2, min_value=Decimal('0'))
    currency = forms.CharField(required=False, max_length=8)
    paid_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    existing_expense = forms.ModelChoiceField(queryset=Expense.objects.none(), required=False)
    duplicate_override = forms.BooleanField(required=False)

    def __init__(self, *args, candidate=None, issuers=None, **kwargs):
        self.candidate = candidate
        super().__init__(*args, **kwargs)
        issuers = issuers or Issuer.objects.none()
        self.fields['confirmed_issuer'].queryset = issuers
        self.fields['selected_artifact'].queryset = candidate.artifacts.all() if candidate else IncomingInvoiceArtifact.objects.none()
        self.fields['existing_expense'].queryset = Expense.objects.filter(issuer__in=issuers).order_by('-paid_date', '-id')
        metadata = (candidate.extracted_metadata if candidate else {}) or {}
        if candidate:
            self.fields['confirmed_issuer'].initial = candidate.confirmed_issuer or candidate.suggested_issuer
            self.fields['selected_artifact'].initial = candidate.selected_artifact or candidate.generated_body_pdf_artifact or candidate.artifacts.first()
        self.fields['vendor'].initial = metadata.get('vendor') or metadata.get('supplier') or ''
        self.fields['description'].initial = metadata.get('description') or metadata.get('vendor') or candidate.subject if candidate else ''
        self.fields['amount'].initial = metadata.get('amount') or ''
        self.fields['currency'].initial = metadata.get('currency') or 'EUR'
        self._apply_pico_styles()

    def _apply_pico_styles(self):
        for name, field in self.fields.items():
            if name == 'duplicate_override':
                field.widget.attrs.setdefault('class', 'field-control--checkbox')
                continue
            field.widget.attrs.setdefault('class', 'field-control')

    def clean(self):
        cleaned = super().clean()
        action = cleaned.get('action')
        issuer = cleaned.get('confirmed_issuer')
        artifact = cleaned.get('selected_artifact')
        if action in {self.ACTION_CONFIRM, self.ACTION_REVIEWED_UNPAID}:
            if not issuer:
                self.add_error('confirmed_issuer', 'Confirm a company before saving review state.')
            if not artifact:
                self.add_error('selected_artifact', 'Choose the artifact that represents this invoice.')
        if action == self.ACTION_LINK_EXISTING and not cleaned.get('existing_expense'):
            self.add_error('existing_expense', 'Choose the existing expense to link.')
        return cleaned


class IncomingCandidateConversionForm(forms.Form):
    paid_state = forms.ChoiceField(choices=(('paid', 'Already paid'), ('unpaid', 'Not paid yet')))
    confirmed_issuer = forms.ModelChoiceField(queryset=Issuer.objects.none())
    selected_artifact = forms.ModelChoiceField(queryset=IncomingInvoiceArtifact.objects.none())
    vendor = forms.CharField(max_length=255)
    description = forms.CharField(max_length=255)
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0'))
    currency = forms.CharField(max_length=8, required=False)
    paid_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    duplicate_override = forms.BooleanField(required=False)

    def __init__(self, *args, candidate=None, issuers=None, **kwargs):
        self.candidate = candidate
        super().__init__(*args, **kwargs)
        issuers = issuers or Issuer.objects.none()
        self.fields['confirmed_issuer'].queryset = issuers
        self.fields['selected_artifact'].queryset = candidate.artifacts.all() if candidate else IncomingInvoiceArtifact.objects.none()
        metadata = (candidate.reviewed_metadata or candidate.extracted_metadata if candidate else {}) or {}
        self.fields['confirmed_issuer'].initial = candidate.confirmed_issuer or candidate.suggested_issuer if candidate else None
        self.fields['selected_artifact'].initial = candidate.selected_artifact or candidate.generated_body_pdf_artifact or candidate.artifacts.first() if candidate else None
        self.fields['vendor'].initial = metadata.get('vendor') or metadata.get('supplier') or ''
        self.fields['description'].initial = metadata.get('description') or metadata.get('vendor') or candidate.subject if candidate else ''
        self.fields['amount'].initial = metadata.get('amount') or ''
        self.fields['currency'].initial = metadata.get('currency') or 'EUR'
        for name, field in self.fields.items():
            if name == 'duplicate_override':
                field.widget.attrs.setdefault('class', 'field-control--checkbox')
            else:
                field.widget.attrs.setdefault('class', 'field-control')

    def clean(self):
        cleaned = super().clean()
        paid_state = cleaned.get('paid_state')
        if paid_state == 'paid' and not cleaned.get('paid_date'):
            self.add_error('paid_date', 'Paid date is required when creating an expense.')
        if self.candidate and self.candidate.status == IncomingInvoiceCandidate.STATUS_DUPLICATE and not cleaned.get('duplicate_override'):
            self.add_error('duplicate_override', 'Duplicate candidates require explicit override before conversion.')
        return cleaned
