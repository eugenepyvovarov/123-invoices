from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ApiToken


class ApiTokenAuthenticationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='api-user',
            email='api@example.com',
        )
        self.url = reverse('api:me')

    def test_valid_token_authenticates_account(self):
        api_token, plaintext = ApiToken.issue(owner=self.user, name='Test token')

        response = self.client.get(self.url, HTTP_AUTHORIZATION=f'Bearer {plaintext}')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['account']['id'], self.user.pk)
        api_token.refresh_from_db()
        self.assertIsNotNone(api_token.last_used_at)

    def test_missing_token_returns_json_401_not_login_redirect(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response['WWW-Authenticate'], 'Bearer')
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIn('error', response.json())

    def test_invalid_token_returns_json_401(self):
        invalid_token = f'{ApiToken.TOKEN_PREFIX}_bad_not-a-token'
        response = self.client.get(self.url, HTTP_AUTHORIZATION=f'Bearer {invalid_token}')

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response['WWW-Authenticate'], 'Bearer')
        self.assertIn('Invalid API token', response.json()['error']['message'])

    def test_revoked_token_returns_json_401(self):
        api_token, plaintext = ApiToken.issue(owner=self.user, name='Revoked token')
        api_token.revoke()

        response = self.client.get(self.url, HTTP_AUTHORIZATION=f'Bearer {plaintext}')

        self.assertEqual(response.status_code, 401)
        self.assertIn('revoked', response.json()['error']['message'])

    def test_expired_token_returns_json_401(self):
        _, plaintext = ApiToken.issue(
            owner=self.user,
            name='Expired token',
            expires_at=timezone.now() - timezone.timedelta(minutes=1),
        )

        response = self.client.get(self.url, HTTP_AUTHORIZATION=f'Bearer {plaintext}')

        self.assertEqual(response.status_code, 401)
        self.assertIn('expired', response.json()['error']['message'])
