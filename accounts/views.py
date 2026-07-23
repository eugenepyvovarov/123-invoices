from django.contrib import messages
from django.contrib.auth import get_user_model, login as auth_login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django_otp import login as otp_login, user_has_device

from accounts.forms import (
    ApiTokenCreateForm,
    EmailAuthenticationForm,
    ExpenseAIProviderSettingsForm,
    OTPTokenForm,
    RecoveryCodeForm,
    UserProfileForm,
)
from accounts.models import ApiToken, Profile
from accounts.utils import otp as otp_utils
from invoices.models import Issuer


OTP_PENDING_USER_ID = 'otp_pending_user_id'
OTP_PENDING_BACKEND = 'otp_pending_backend'
OTP_PENDING_NEXT = 'otp_pending_next'
OTP_SESSION_RECOVERY_CODES = 'otp_recovery_codes'


class EmailLoginView(LoginView):
    """Email-first login view."""

    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        user = form.get_user()
        if user_has_device(user, confirmed=True):
            self.request.session[OTP_PENDING_USER_ID] = user.pk
            self.request.session[OTP_PENDING_BACKEND] = user.backend
            self.request.session[OTP_PENDING_NEXT] = self.get_success_url()
            return redirect('accounts:otp_verify')
        return super().form_valid(form)


class EmailLogoutView(LogoutView):
    """Log users out and send them back to the login screen."""

    next_page = reverse_lazy("accounts:login")


class OTPVerifyView(View):
    template_name = "accounts/otp_verify.html"

    def dispatch(self, request, *args, **kwargs):
        if self._pending_user is None:
            return redirect('accounts:login')
        return super().dispatch(request, *args, **kwargs)

    @property
    def _pending_user(self):
        user_id = self.request.session.get(OTP_PENDING_USER_ID)
        if not user_id:
            return None
        return get_user_model().objects.filter(pk=user_id).first()

    def get(self, request):
        context = self._context_data()
        return render(request, self.template_name, context)

    def post(self, request):
        action = request.POST.get('action')
        context = self._context_data()
        user = self._pending_user
        if user is None:
            return redirect('accounts:login')

        if action == 'verify_totp':
            form = OTPTokenForm(request.POST)
            context['totp_form'] = form
            if form.is_valid():
                device = otp_utils.get_confirmed_device(user)
                if device and device.verify_token(form.cleaned_data['token']):
                    return self._finalize_login(user, device)
                messages.error(request, "Invalid authenticator code. Please try again.")
        elif action == 'verify_recovery':
            form = RecoveryCodeForm(request.POST)
            context['recovery_form'] = form
            if form.is_valid():
                device = otp_utils.recovery_device(user)
                if device and device.verify_token(form.cleaned_data['code']):
                    return self._finalize_login(user, device)
                messages.error(request, "That recovery code is not valid or has already been used.")
        else:
            return redirect('accounts:login')

        return render(request, self.template_name, context)

    def _context_data(self):
        return {
            'totp_form': OTPTokenForm(),
            'recovery_form': RecoveryCodeForm(),
            'next': self.request.session.get(OTP_PENDING_NEXT) or reverse('dashboard'),
        }

    def _finalize_login(self, user, device):
        backend = self.request.session.get(OTP_PENDING_BACKEND, 'django.contrib.auth.backends.ModelBackend')
        auth_login(self.request, user, backend=backend)
        otp_login(self.request, device)
        next_url = self.request.session.pop(OTP_PENDING_NEXT, None) or reverse('dashboard')
        self.request.session.pop(OTP_PENDING_USER_ID, None)
        self.request.session.pop(OTP_PENDING_BACKEND, None)
        return redirect(next_url)


@login_required
def user_settings(request):
    """Display account info, issuers, and password management."""

    try:
        profile = request.user.profile
    except Profile.DoesNotExist:
        profile = Profile.objects.create(user=request.user)

    if request.user.is_superuser:
        issuers = Issuer.objects.select_related('company').order_by('company__name')
        has_full_access = True
    else:
        issuers = request.user.issuers.select_related('company').order_by('company__name')
        has_full_access = False

    password_form = PasswordChangeForm(request.user)
    _style_password_form(password_form)
    profile_form = UserProfileForm(instance=request.user)
    expense_ai_form = ExpenseAIProviderSettingsForm(instance=profile)
    api_token_form = ApiTokenCreateForm()
    new_api_token = None
    new_api_token_plaintext = None
    otp_form = OTPTokenForm()
    _style_otp_form(otp_form)
    pending_device = otp_utils.get_pending_device(request.user)
    confirmed_device = otp_utils.get_confirmed_device(request.user)
    recovery_codes = request.session.pop(OTP_SESSION_RECOVERY_CODES, None)
    outstanding_tab = request.session.pop('security_tab', None)

    if request.method == 'POST':
        form_action = request.POST.get('action')
        if form_action == 'update_profile':
            profile_form = UserProfileForm(request.POST, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Account details updated.")
                return redirect('accounts:user_settings')
            messages.error(request, "Please fix the highlighted errors and try again.")
        elif form_action == 'toggle_default_company':
            company_id = request.POST.get('company_id')
            is_default = request.POST.get('is_default') == '1'
            try:
                company_id_int = int(company_id)
            except (TypeError, ValueError):
                messages.error(request, "Invalid company selection.")
                return redirect('accounts:user_settings')

            target_issuer = issuers.filter(company_id=company_id_int).first()
            if not target_issuer or not target_issuer.company_id:
                messages.error(request, "Company not found.")
                return redirect('accounts:user_settings')

            if is_default:
                profile.default_company = target_issuer.company
                profile.save(update_fields=['default_company', 'updated_at'])
                request.session['active_company_id'] = target_issuer.company_id
                messages.success(request, f"Default company set to {target_issuer.company.name}.")
            else:
                if profile.default_company_id == target_issuer.company_id:
                    profile.default_company = None
                    profile.save(update_fields=['default_company', 'updated_at'])
                    messages.success(request, "Default company cleared.")
                else:
                    messages.info(request, "Default company unchanged.")
            return redirect('accounts:user_settings')
        elif form_action == 'update_password':
            password_form = PasswordChangeForm(request.user, request.POST)
            _style_password_form(password_form)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Password updated successfully.")
                return redirect('accounts:user_settings')
            messages.error(request, "Please correct the errors highlighted below.")
        elif form_action == 'update_expense_ai_provider':
            expense_ai_form = ExpenseAIProviderSettingsForm(request.POST, instance=profile)
            if expense_ai_form.is_valid():
                expense_ai_form.save()
                messages.success(request, "Expense import AI provider settings updated.")
                return redirect('accounts:user_settings')
            messages.error(request, "Please fix the highlighted AI provider settings errors and try again.")
        elif form_action == 'create_api_token':
            api_token_form = ApiTokenCreateForm(request.POST)
            if api_token_form.is_valid():
                new_api_token, new_api_token_plaintext = ApiToken.issue(
                    owner=request.user,
                    name=api_token_form.cleaned_data['name'],
                    expires_at=api_token_form.cleaned_data['expires_at'],
                )
                api_token_form = ApiTokenCreateForm()
                messages.success(request, "Invoices API token created. Copy it now; it will not be shown again.")
            else:
                messages.error(request, "Please fix the highlighted API token errors and try again.")
        elif form_action == 'revoke_api_token':
            token_id = request.POST.get('token_id')
            api_token = request.user.api_tokens.filter(pk=token_id).first()
            if api_token:
                api_token.revoke()
                messages.success(request, "Invoices API token revoked.")
            else:
                messages.error(request, "API token not found.")
            return redirect('accounts:user_settings')
        elif form_action == 'start_totp':
            if confirmed_device:
                messages.info(request, "Two-factor authentication is already enabled.")
            else:
                pending_device = otp_utils.start_enrollment(request.user)
                messages.info(request, "Scan the QR code below and confirm using your authenticator app.")
            return redirect('accounts:user_settings')
        elif form_action == 'confirm_totp':
            pending_device = otp_utils.get_pending_device(request.user)
            if not pending_device:
                messages.error(request, "Start the setup process before confirming a code.")
                return redirect('accounts:user_settings')
            otp_form = OTPTokenForm(request.POST)
            _style_otp_form(otp_form)
            if otp_form.is_valid() and pending_device.verify_token(otp_form.cleaned_data['token']):
                pending_device.confirmed = True
                pending_device.save()
                codes = otp_utils.generate_recovery_codes(request.user)
                request.session[OTP_SESSION_RECOVERY_CODES] = codes
                messages.success(request, "Two-factor authentication is now enabled.")
                return redirect('accounts:user_settings')
            messages.error(request, "Invalid code. Make sure you are using the authenticator linked below.")
        elif form_action == 'cancel_totp':
            otp_utils.cancel_enrollment(request.user)
            messages.info(request, "Two-factor setup canceled.")
            request.session['security_tab'] = 'otp'
            return redirect('accounts:user_settings')
        elif form_action == 'disable_totp':
            if otp_utils.get_confirmed_device(request.user):
                otp_utils.disable_two_factor(request.user)
                messages.success(request, "Two-factor authentication has been disabled.")
            else:
                messages.info(request, "Two-factor authentication is not enabled.")
            return redirect('accounts:user_settings')
        elif form_action == 'regenerate_recovery':
            if otp_utils.get_confirmed_device(request.user):
                codes = otp_utils.generate_recovery_codes(request.user)
                request.session[OTP_SESSION_RECOVERY_CODES] = codes
                request.session['security_tab'] = 'otp'
                messages.success(request, "New recovery codes generated. Store them securely.")
            else:
                messages.error(request, "Enable two-factor authentication before generating recovery codes.")
            return redirect('accounts:user_settings')

    pending_device = pending_device or otp_utils.get_pending_device(request.user)
    confirmed_device = otp_utils.get_confirmed_device(request.user)
    otp_qr_image = otp_manual_key = None
    if pending_device:
        otp_qr_image = otp_utils.build_qr_image(pending_device.config_url)
        otp_manual_key = otp_utils.manual_key(pending_device)
    active_security_tab = outstanding_tab or ('otp' if (pending_device or recovery_codes) else 'password')

    context = {
        'password_form': password_form,
        'profile_form': profile_form,
        'expense_ai_form': expense_ai_form,
        'api_token_form': api_token_form,
        'api_tokens': request.user.api_tokens.order_by('-created_at', '-id'),
        'new_api_token': new_api_token,
        'new_api_token_plaintext': new_api_token_plaintext,
        'expense_ai_has_key': profile.has_expense_ai_api_key,
        'expense_ai_masked_key': profile.masked_expense_ai_api_key,
        'user_issuers': issuers,
        'has_full_access': has_full_access,
        'default_company_id': profile.default_company_id,
        'two_factor_enabled': bool(confirmed_device),
        'pending_totp': pending_device,
        'otp_qr_image': otp_qr_image,
        'otp_manual_key': otp_manual_key,
        'otp_setup_form': otp_form,
        'recovery_codes': recovery_codes,
        'active_security_tab': active_security_tab,
    }
    return render(request, 'accounts/user_settings.html', context)


def _style_password_form(form: PasswordChangeForm):
    for name, field in form.fields.items():
        css = field.widget.attrs.get('class', '')
        field.widget.attrs['class'] = f"{css} form-control".strip()
        if name == 'old_password':
            field.widget.attrs.setdefault('autocomplete', 'current-password')
        else:
            field.widget.attrs.setdefault('autocomplete', 'new-password')


def _style_otp_form(form: OTPTokenForm):
    field = form.fields['token']
    css = field.widget.attrs.get('class', '')
    field.widget.attrs['class'] = f"{css} form-control".strip()
