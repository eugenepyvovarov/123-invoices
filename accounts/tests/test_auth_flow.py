from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.views import OTP_PENDING_BACKEND, OTP_PENDING_NEXT, OTP_PENDING_USER_ID
from tests.support import IssuerUserTestMixin


class EmailLoginViewTests(TestCase):
    def setUp(self):
        self.password = IssuerUserTestMixin.build_test_password()
        self.user = get_user_model().objects.create_user(
            username='auth-user',
            email='auth@example.com',
            password=self.password,
        )

    def test_get_renders_email_login_form(self):
        response = self.client.get(reverse('accounts:login'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sign in')
        self.assertContains(response, 'Email')

    def test_post_authenticates_with_email_address(self):
        response = self.client.post(
            reverse('accounts:login'),
            {
                'username': '  AUTH@EXAMPLE.COM  ',
                'password': self.password,
            },
        )

        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)
        session = self.client.session
        self.assertEqual(session['_auth_user_id'], str(self.user.pk))
        self.assertNotIn(OTP_PENDING_USER_ID, session)

    def test_post_with_confirmed_device_stages_otp_verification(self):
        TOTPDevice.objects.create(user=self.user, name='authenticator', confirmed=True)

        response = self.client.post(
            reverse('accounts:login'),
            {
                'username': self.user.email,
                'password': self.password,
                'next': reverse('dashboard'),
            },
        )

        self.assertRedirects(response, reverse('accounts:otp_verify'))
        session = self.client.session
        self.assertEqual(session[OTP_PENDING_USER_ID], self.user.pk)
        self.assertEqual(session[OTP_PENDING_NEXT], reverse('dashboard'))
        self.assertEqual(
            session[OTP_PENDING_BACKEND],
            'accounts.backends.EmailBackend',
        )
        self.assertNotIn('_auth_user_id', session)


class OTPVerifyViewTests(TestCase):
    def setUp(self):
        self.token = IssuerUserTestMixin.build_test_totp_token()
        self.user = get_user_model().objects.create_user(
            username='otp-user',
            email='otp@example.com',
            password=IssuerUserTestMixin.build_test_password(),
        )
        self.verify_url = reverse('accounts:otp_verify')

    def _stage_pending_otp(self, next_url=None):
        session = self.client.session
        session[OTP_PENDING_USER_ID] = self.user.pk
        session[OTP_PENDING_BACKEND] = 'accounts.backends.EmailBackend'
        session[OTP_PENDING_NEXT] = next_url or reverse('dashboard')
        session.save()

    def test_get_without_pending_session_redirects_to_login(self):
        response = self.client.get(self.verify_url)

        self.assertRedirects(response, reverse('accounts:login'))

    def test_post_without_pending_session_redirects_to_login(self):
        response = self.client.post(self.verify_url, {'action': 'verify_totp', 'token': self.token})

        self.assertRedirects(response, reverse('accounts:login'))

    @patch('accounts.views.otp_utils.get_confirmed_device')
    def test_post_with_valid_token_logs_user_in_and_clears_pending_session(self, mock_get_confirmed_device):
        self._stage_pending_otp(next_url=reverse('dashboard'))
        device = SimpleNamespace(
            persistent_id='otp-totpdevice/1',
            user_id=self.user.pk,
            verify_token=Mock(return_value=True),
        )
        mock_get_confirmed_device.return_value = device

        response = self.client.post(self.verify_url, {'action': 'verify_totp', 'token': self.token})

        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)
        device.verify_token.assert_called_once_with(self.token)
        session = self.client.session
        self.assertEqual(session['_auth_user_id'], str(self.user.pk))
        self.assertNotIn(OTP_PENDING_USER_ID, session)
        self.assertNotIn(OTP_PENDING_BACKEND, session)
        self.assertNotIn(OTP_PENDING_NEXT, session)

    @patch('accounts.views.otp_utils.get_confirmed_device')
    def test_post_with_invalid_token_shows_error_and_keeps_pending_session(self, mock_get_confirmed_device):
        self._stage_pending_otp()
        device = SimpleNamespace(
            persistent_id='otp-totpdevice/1',
            user_id=self.user.pk,
            verify_token=Mock(return_value=False),
        )
        mock_get_confirmed_device.return_value = device

        response = self.client.post(self.verify_url, {'action': 'verify_totp', 'token': self.token})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid authenticator code. Please try again.')
        device.verify_token.assert_called_once_with(self.token)
        session = self.client.session
        self.assertNotIn('_auth_user_id', session)
        self.assertEqual(session[OTP_PENDING_USER_ID], self.user.pk)
