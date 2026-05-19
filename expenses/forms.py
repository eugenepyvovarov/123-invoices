import os
from decimal import Decimal

from django import forms

from invoices.models import Customer, Expense, Project


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
