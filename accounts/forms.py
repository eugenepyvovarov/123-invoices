from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm

from accounts.models import Profile


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "data-testid": "login-email-input",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password"].widget.attrs["data-testid"] = "login-password-input"

    def clean_username(self):
        username = self.cleaned_data.get("username", "")
        return username.strip().lower()


class OTPTokenForm(forms.Form):
    token = forms.CharField(
        label="Authenticator code",
        max_length=6,
        min_length=6,
        widget=forms.TextInput(
            attrs={
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
                "class": "form-control text-center",
                "data-testid": "otp-token-input",
            }
        ),
    )

    def clean_token(self):
        token = self.cleaned_data["token"].strip()
        if not token.isdigit():
            raise forms.ValidationError("Codes must be 6 digits.")
        return token


class RecoveryCodeForm(forms.Form):
    code = forms.CharField(
        label="Recovery code",
        max_length=32,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "one-time-code",
                "class": "form-control text-center text-uppercase",
                "data-testid": "otp-recovery-code-input",
            }
        ),
    )

    def clean_code(self):
        code = self.cleaned_data["code"].strip().replace(" ", "")
        if not code:
            raise forms.ValidationError("Enter the recovery code exactly as provided.")
        return code


class UserProfileForm(forms.ModelForm):
    email = forms.EmailField(label="Email")

    class Meta:
        model = get_user_model()
        fields = ["email", "first_name", "last_name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            "first_name": "First name",
            "last_name": "Last name",
            "email": "you@example.com",
        }
        for name, field in self.fields.items():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{css} form-control".strip()
            field.widget.attrs.setdefault("placeholder", placeholders.get(name, ""))

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        User = get_user_model()
        qs = User.objects.filter(email=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Another user already uses this email.")
        return email


class ExpenseAIProviderSettingsForm(forms.ModelForm):
    expense_ai_api_key = forms.CharField(
        label='API key',
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text='Leave blank to keep the saved key. The saved value is never displayed.',
    )
    clear_expense_ai_api_key = forms.BooleanField(
        label='Clear saved API key',
        required=False,
    )

    class Meta:
        model = Profile
        fields = ['expense_ai_provider_base_url', 'expense_ai_model_name']
        labels = {
            'expense_ai_provider_base_url': 'Provider base URL',
            'expense_ai_model_name': 'Model name',
        }
        help_texts = {
            'expense_ai_provider_base_url': 'OpenAI-compatible base URL, for example https://api.openai.com.',
            'expense_ai_model_name': 'Model used to infer mappings for unmatched expense statement headers.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['expense_ai_provider_base_url'].required = False
        self.fields['expense_ai_model_name'].required = False
        placeholders = {
            'expense_ai_provider_base_url': 'https://api.openai.com',
            'expense_ai_model_name': 'gpt-4o-mini',
            'expense_ai_api_key': 'Enter a new API key',
        }
        for name, field in self.fields.items():
            css = field.widget.attrs.get('class', '')
            if name == 'clear_expense_ai_api_key':
                field.widget.attrs['class'] = f"{css} field-control--checkbox".strip()
                continue
            field.widget.attrs['class'] = f"{css} form-control".strip()
            field.widget.attrs.setdefault('placeholder', placeholders.get(name, ''))

    def clean(self):
        cleaned = super().clean()
        base_url = (cleaned.get('expense_ai_provider_base_url') or '').strip()
        model_name = (cleaned.get('expense_ai_model_name') or '').strip()
        api_key = (cleaned.get('expense_ai_api_key') or '').strip()
        clear_key = cleaned.get('clear_expense_ai_api_key')
        existing_key = bool(self.instance and self.instance.expense_ai_api_key)

        has_any_setting = bool(base_url or model_name or api_key or (existing_key and not clear_key))
        if has_any_setting:
            if not base_url:
                self.add_error('expense_ai_provider_base_url', 'Provider base URL is required to enable AI mapping inference.')
            if not model_name:
                self.add_error('expense_ai_model_name', 'Model name is required to enable AI mapping inference.')
            if not api_key and not existing_key:
                self.add_error('expense_ai_api_key', 'API key is required to enable AI mapping inference.')
        cleaned['expense_ai_provider_base_url'] = base_url
        cleaned['expense_ai_model_name'] = model_name
        cleaned['expense_ai_api_key'] = api_key
        return cleaned

    def save(self, commit=True):  # type: ignore[override]
        profile = super().save(commit=False)
        if self.cleaned_data.get('clear_expense_ai_api_key'):
            profile.expense_ai_api_key = ''
        elif self.cleaned_data.get('expense_ai_api_key'):
            profile.expense_ai_api_key = self.cleaned_data['expense_ai_api_key']
        if commit:
            profile.save()
        return profile
