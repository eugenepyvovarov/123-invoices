from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.models import ApiToken
from tests.support import AuthenticatedCompanyTestCase


class UserSettingsViewTests(AuthenticatedCompanyTestCase):
    def setUp(self):
        self.issuer_a = self.create_issuer()
        self.issuer_b = self.create_issuer()
        self.user = self.create_user_with_issuers(
            issuers=[self.issuer_a, self.issuer_b],
            username='settings-user',
            email='settings@example.com',
        )
        self.settings_url = reverse('accounts:user_settings')

    def test_get_lists_accessible_companies_and_default_company(self):
        self.user.profile.default_company = self.issuer_b.company
        self.user.profile.save(update_fields=['default_company', 'updated_at'])
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.get(self.settings_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.issuer_a.company.name)
        self.assertContains(response, self.issuer_b.company.name)
        self.assertEqual(list(response.context['user_issuers']), [self.issuer_a, self.issuer_b])
        self.assertEqual(response.context['default_company_id'], self.issuer_b.company_id)

    def test_get_masks_saved_expense_ai_api_key(self):
        self.user.profile.expense_ai_provider_base_url = 'https://provider.example'
        self.user.profile.expense_ai_model_name = 'mapping-model'
        self.user.profile.expense_ai_api_key = 'sk-secret-value'
        self.user.profile.save()
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.get(self.settings_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Expense import AI provider')
        self.assertContains(response, 'unmatched expense statement header mapping inference')
        self.assertContains(response, 'unmatched expense statement headers')
        self.assertContains(response, '••••••••')
        self.assertNotContains(response, 'sk-secret-value')

    def test_save_expense_ai_provider_settings(self):
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.post(self.settings_url, {
            'action': 'update_expense_ai_provider',
            'expense_ai_provider_base_url': 'https://provider.example',
            'expense_ai_model_name': 'mapping-model',
            'expense_ai_api_key': 'sk-new-key',
        })

        self.assertRedirects(response, self.settings_url)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.expense_ai_provider_base_url, 'https://provider.example')
        self.assertEqual(self.user.profile.expense_ai_model_name, 'mapping-model')
        self.assertEqual(self.user.profile.expense_ai_api_key, 'sk-new-key')

    def test_blank_expense_ai_api_key_update_preserves_existing_key(self):
        self.user.profile.expense_ai_provider_base_url = 'https://old.example'
        self.user.profile.expense_ai_model_name = 'old-model'
        self.user.profile.expense_ai_api_key = 'sk-existing-key'
        self.user.profile.save()
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.post(self.settings_url, {
            'action': 'update_expense_ai_provider',
            'expense_ai_provider_base_url': 'https://new.example',
            'expense_ai_model_name': 'new-model',
            'expense_ai_api_key': '',
        })

        self.assertRedirects(response, self.settings_url)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.expense_ai_provider_base_url, 'https://new.example')
        self.assertEqual(self.user.profile.expense_ai_model_name, 'new-model')
        self.assertEqual(self.user.profile.expense_ai_api_key, 'sk-existing-key')

    def test_clear_expense_ai_api_key_removes_saved_key(self):
        self.user.profile.expense_ai_provider_base_url = 'https://provider.example'
        self.user.profile.expense_ai_model_name = 'mapping-model'
        self.user.profile.expense_ai_api_key = 'sk-existing-key'
        self.user.profile.save()
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.post(self.settings_url, {
            'action': 'update_expense_ai_provider',
            'expense_ai_provider_base_url': 'https://provider.example',
            'expense_ai_model_name': 'mapping-model',
            'clear_expense_ai_api_key': 'on',
        })

        self.assertRedirects(response, self.settings_url)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.expense_ai_api_key, '')

    def test_expense_ai_provider_requires_complete_settings(self):
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.post(self.settings_url, {
            'action': 'update_expense_ai_provider',
            'expense_ai_provider_base_url': 'https://provider.example',
            'expense_ai_model_name': '',
            'expense_ai_api_key': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Model name is required to enable AI mapping inference.')
        self.assertContains(response, 'API key is required to enable AI mapping inference.')
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.expense_ai_provider_base_url, '')

    def test_get_lists_only_owned_api_tokens(self):
        owned_token, _ = ApiToken.issue(owner=self.user, name='Owned token')
        other_user = self.create_user_with_issuers(username='other-api-user', email='other-api@example.com')
        other_token, _ = ApiToken.issue(owner=other_user, name='Other token')
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.get(self.settings_url)

        self.assertEqual(response.status_code, 200)
        self.assertIn('api_token_form', response.context)
        self.assertEqual(list(response.context['api_tokens']), [owned_token])
        self.assertNotIn(other_token, list(response.context['api_tokens']))
        self.assertContains(response, 'Invoices API tokens')
        self.assertContains(response, 'Owned token')
        self.assertContains(response, owned_token.prefix)
        self.assertContains(response, 'Active')
        self.assertNotContains(response, 'Other token')

    @override_settings(
        DEBUG=False,
        MCP_OAUTH_RESOURCE_URL='https://mcp.example.test/mcp',
        MCP_OAUTH_ISSUER_URL='https://invoices.example.test/',
        MCP_OAUTH_CIMD_ENABLED=False,
        OAUTH2_PROVIDER={
            'SCOPES': {
                'invoices:mcp:read': 'Read invoice data through MCP tools',
                'invoices:mcp:draft:write': 'Create and update draft invoices through MCP tools',
            },
        },
    )
    def test_get_includes_configured_mcp_connection_context(self):
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.get(self.settings_url)

        self.assertEqual(response.status_code, 200)
        mcp_connection = response.context['mcp_connection']
        self.assertEqual(mcp_connection['resource_url'], 'https://mcp.example.test/mcp/')
        self.assertEqual(mcp_connection['endpoint_url'], 'https://mcp.example.test/mcp/')
        self.assertEqual(mcp_connection['issuer_url'], 'https://invoices.example.test')
        self.assertEqual(
            mcp_connection['authorization_server_metadata_url'],
            'https://invoices.example.test/.well-known/oauth-authorization-server',
        )
        self.assertEqual(
            mcp_connection['protected_resource_metadata_url'],
            'https://invoices.example.test/.well-known/oauth-protected-resource',
        )
        self.assertEqual(mcp_connection['authorization_url'], 'https://invoices.example.test/o/authorize/')
        self.assertEqual(mcp_connection['token_url'], 'https://invoices.example.test/o/token/')
        self.assertFalse(mcp_connection['cimd_enabled'])
        self.assertEqual(mcp_connection['status']['key'], 'configured')
        self.assertEqual(
            mcp_connection['scopes'],
            [
                {'name': 'invoices:mcp:read', 'description': 'Read invoice data through MCP tools'},
                {'name': 'invoices:mcp:draft:write', 'description': 'Create and update draft invoices through MCP tools'},
            ],
        )

    @override_settings(
        DEBUG=False,
        MCP_OAUTH_RESOURCE_URL='https://mcp.example.test/mcp',
        MCP_OAUTH_ISSUER_URL='https://invoices.example.test/',
        MCP_OAUTH_CIMD_ENABLED=True,
        OAUTH2_PROVIDER={
            'SCOPES': {
                'invoices:mcp:read': 'Read invoice data through MCP tools',
            },
        },
    )
    def test_get_renders_api_mcp_integration_tabs_and_controls(self):
        api_token, _ = ApiToken.issue(owner=self.user, name='Reviewer token')
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.get(self.settings_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-testid="integrations-settings"')
        self.assertContains(response, 'href="#integrations-api-panel"')
        self.assertContains(response, 'aria-controls="integrations-api-panel"')
        self.assertContains(response, '>API</a>', html=False)
        self.assertContains(response, 'href="#integrations-mcp-panel"')
        self.assertContains(response, 'aria-controls="integrations-mcp-panel"')
        self.assertContains(response, '>MCP</a>', html=False)
        self.assertContains(response, 'id="integrations-api-panel"')
        self.assertContains(response, 'data-testid="invoices-api-token-settings"')
        self.assertContains(response, 'name="action" value="create_api_token"')
        self.assertContains(response, 'name="action" value="revoke_api_token"')
        self.assertContains(response, api_token.prefix)
        self.assertContains(response, 'id="integrations-mcp-panel"')
        self.assertContains(response, 'data-testid="mcp-connection-settings"')
        self.assertContains(response, 'data-testid="mcp-status-badge"')
        self.assertContains(response, 'Configured')
        self.assertContains(response, 'value="https://mcp.example.test/mcp/"')
        self.assertContains(response, 'data-copy-public-value-button')
        self.assertContains(response, 'OAuth 2.1 + PKCE')
        self.assertContains(response, 'Hermes, Codex')
        self.assertContains(response, 'CIMD')
        self.assertContains(response, 'invoices:mcp:read')
        self.assertContains(response, 'Expense import AI provider')
        self.assertContains(response, 'data-testid="expense-ai-provider-settings"')

    @override_settings(
        DEBUG=False,
        MCP_OAUTH_RESOURCE_URL='http://localhost:8765/mcp/',
        MCP_OAUTH_ISSUER_URL='http://localhost:8000',
    )
    def test_get_marks_local_mcp_urls_not_publicly_configured_outside_debug(self):
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.get(self.settings_url)

        self.assertEqual(response.status_code, 200)
        mcp_connection = response.context['mcp_connection']
        self.assertEqual(mcp_connection['status']['key'], 'not_configured')
        self.assertEqual(mcp_connection['status']['label'], 'Not publicly configured')

    @override_settings(
        DEBUG=True,
        MCP_OAUTH_RESOURCE_URL='http://localhost:8765/mcp/',
        MCP_OAUTH_ISSUER_URL='http://localhost:8000',
    )
    def test_get_marks_local_mcp_urls_as_local_development_in_debug(self):
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.get(self.settings_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['mcp_connection']['status']['key'], 'local_development')

    @override_settings(
        DEBUG=False,
        MCP_OAUTH_RESOURCE_URL='https://mcp.example.test/mcp/',
        MCP_OAUTH_ISSUER_URL='https://invoices.example.test',
        MCP_OAUTH_INTROSPECTION_TOKEN='introspection-secret-token',
        INVOICES_MCP_API_TOKEN='upstream-secret-token',
        OAUTH_ACCESS_TOKEN='oauth-access-secret',
        OAUTH_REFRESH_TOKEN='oauth-refresh-secret',
        CLIENT_SECRET='client-secret-value',
    )
    def test_get_does_not_render_secret_like_mcp_settings(self):
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.get(self.settings_url)

        self.assertEqual(response.status_code, 200)
        rendered = response.content.decode()
        context_repr = repr(response.context['mcp_connection'])
        for secret in [
            'introspection-secret-token',
            'upstream-secret-token',
            'oauth-access-secret',
            'oauth-refresh-secret',
            'client-secret-value',
        ]:
            self.assertNotIn(secret, rendered)
            self.assertNotIn(secret, context_repr)

    def test_get_renders_api_token_status_badges_and_expense_ai_label(self):
        active_token, _ = ApiToken.issue(owner=self.user, name='Active token')
        expired_token, _ = ApiToken.issue(
            owner=self.user,
            name='Expired token',
            expires_at=timezone.now() - timedelta(days=1),
        )
        revoked_token, _ = ApiToken.issue(owner=self.user, name='Revoked token')
        revoked_token.revoke()
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.get(self.settings_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invoices API tokens')
        self.assertContains(response, 'Expense import AI provider')
        self.assertContains(response, 'This provider API key is not an Invoices REST API token.')
        self.assertContains(response, active_token.prefix)
        self.assertContains(response, expired_token.prefix)
        self.assertContains(response, revoked_token.prefix)
        self.assertContains(response, 'Active')
        self.assertContains(response, 'Expired')
        self.assertContains(response, 'Revoked')

    def test_create_api_token_uses_form_and_reveals_plaintext_once(self):
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.post(self.settings_url, {
            'action': 'create_api_token',
            'name': 'Reporting integration',
            'expires_at': '2026-12-31 17:00',
        })

        self.assertEqual(response.status_code, 200)
        api_token = ApiToken.objects.get(owner=self.user, name='Reporting integration')
        plaintext = response.context['new_api_token_plaintext']
        self.assertEqual(response.context['new_api_token'], api_token)
        self.assertTrue(plaintext.startswith(f'{ApiToken.TOKEN_PREFIX}_{api_token.prefix}_'))
        self.assertNotEqual(api_token.secret_hash, plaintext)
        self.assertEqual(api_token.secret_hash, ApiToken.make_secret_hash(plaintext))
        self.assertEqual(api_token.expires_at.date().isoformat(), '2026-12-31')
        self.assertIn(api_token, list(response.context['api_tokens']))
        self.assertContains(response, 'Copy your new token now')
        self.assertContains(response, plaintext)
        self.assertContains(response, api_token.prefix)

        follow_up = self.client.get(self.settings_url)
        self.assertIsNone(follow_up.context['new_api_token_plaintext'])
        self.assertNotContains(follow_up, plaintext)

    def test_create_api_token_requires_name(self):
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.post(self.settings_url, {
            'action': 'create_api_token',
            'name': '   ',
            'expires_at': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ApiToken.objects.filter(owner=self.user).exists())
        self.assertFormError(response.context['api_token_form'], 'name', 'This field is required.')

    def test_revoke_api_token_scopes_lookup_to_owner(self):
        owned_token, _ = ApiToken.issue(owner=self.user, name='Owned token')
        other_user = self.create_user_with_issuers(username='other-revoke-user', email='other-revoke@example.com')
        other_token, _ = ApiToken.issue(owner=other_user, name='Other token')
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.post(self.settings_url, {
            'action': 'revoke_api_token',
            'token_id': other_token.pk,
        })

        self.assertRedirects(response, self.settings_url)
        owned_token.refresh_from_db()
        other_token.refresh_from_db()
        self.assertIsNone(owned_token.revoked_at)
        self.assertIsNone(other_token.revoked_at)

        response = self.client.post(self.settings_url, {
            'action': 'revoke_api_token',
            'token_id': owned_token.pk,
        })

        self.assertRedirects(response, self.settings_url)
        owned_token.refresh_from_db()
        self.assertIsNotNone(owned_token.revoked_at)

    def test_ui_created_revoked_token_cannot_authenticate_to_api(self):
        self.login_with_active_company(self.user, issuer=self.issuer_a)
        create_response = self.client.post(self.settings_url, {
            'action': 'create_api_token',
            'name': 'Temporary API client',
            'expires_at': '',
        })
        plaintext = create_response.context['new_api_token_plaintext']
        api_token = create_response.context['new_api_token']

        self.client.logout()
        api_response = self.client.get(reverse('api:me'), HTTP_AUTHORIZATION=f'Bearer {plaintext}')
        self.assertEqual(api_response.status_code, 200)

        api_token.revoke()
        revoked_response = self.client.get(reverse('api:me'), HTTP_AUTHORIZATION=f'Bearer {plaintext}')
        self.assertEqual(revoked_response.status_code, 401)
        self.assertIn('revoked', revoked_response.json()['error']['message'])

    def test_toggle_default_company_sets_profile_and_active_company_session(self):
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.post(
            self.settings_url,
            {
                'action': 'toggle_default_company',
                'company_id': self.issuer_b.company_id,
                'is_default': '1',
            },
        )

        self.assertRedirects(response, self.settings_url)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.default_company_id, self.issuer_b.company_id)
        self.assertEqual(self.client.session['active_company_id'], self.issuer_b.company_id)

    def test_toggle_default_company_success_message_renders_once_after_redirect(self):
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.post(
            self.settings_url,
            {
                'action': 'toggle_default_company',
                'company_id': self.issuer_b.company_id,
                'is_default': '1',
            },
            follow=True,
        )

        self.assertRedirects(response, self.settings_url)
        self.assertTemplateUsed(response, 'invoices/partials/messages.html')
        self.assertContains(response, 'data-testid="django-messages"', count=1)
        self.assertContains(response, f'Default company set to {self.issuer_b.company.name}.', count=1)

    def test_toggle_default_company_rejects_unassigned_company(self):
        outsider_issuer = self.create_issuer()
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.post(
            self.settings_url,
            {
                'action': 'toggle_default_company',
                'company_id': outsider_issuer.company_id,
                'is_default': '1',
            },
        )

        self.assertRedirects(response, self.settings_url)
        self.user.profile.refresh_from_db()
        self.assertIsNone(self.user.profile.default_company_id)
        self.assertEqual(self.client.session['active_company_id'], self.issuer_a.company_id)

    def test_toggle_default_company_clears_current_default_company(self):
        self.user.profile.default_company = self.issuer_b.company
        self.user.profile.save(update_fields=['default_company', 'updated_at'])
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.post(
            self.settings_url,
            {
                'action': 'toggle_default_company',
                'company_id': self.issuer_b.company_id,
                'is_default': '0',
            },
        )

        self.assertRedirects(response, self.settings_url)
        self.user.profile.refresh_from_db()
        self.assertIsNone(self.user.profile.default_company_id)
        self.assertEqual(self.client.session['active_company_id'], self.issuer_a.company_id)

    def test_toggle_default_company_does_not_clear_unassigned_company(self):
        outsider_issuer = self.create_issuer()
        self.user.profile.default_company = self.issuer_b.company
        self.user.profile.save(update_fields=['default_company', 'updated_at'])
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.post(
            self.settings_url,
            {
                'action': 'toggle_default_company',
                'company_id': outsider_issuer.company_id,
                'is_default': '0',
            },
        )

        self.assertRedirects(response, self.settings_url)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.default_company_id, self.issuer_b.company_id)
        self.assertEqual(self.client.session['active_company_id'], self.issuer_a.company_id)

    def test_start_totp_creates_pending_device(self):
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.post(self.settings_url, {'action': 'start_totp'})

        self.assertRedirects(response, self.settings_url)
        pending_device = TOTPDevice.objects.get(user=self.user, name='authenticator')
        self.assertFalse(pending_device.confirmed)

    @patch('accounts.views.otp_utils.generate_recovery_codes', return_value=['CODE123456'])
    @patch('django_otp.plugins.otp_totp.models.TOTPDevice.verify_token', return_value=True)
    def test_confirm_totp_enables_pending_device_and_stashes_recovery_codes(
        self,
        mock_verify_token,
        mock_generate_recovery_codes,
    ):
        pending_device = TOTPDevice.objects.create(user=self.user, name='authenticator', confirmed=False)
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.post(
            self.settings_url,
            {'action': 'confirm_totp', 'token': '123456'},
        )

        self.assertRedirects(response, self.settings_url, fetch_redirect_response=False)
        pending_device.refresh_from_db()
        self.assertTrue(pending_device.confirmed)
        mock_verify_token.assert_called_once_with('123456')
        mock_generate_recovery_codes.assert_called_once_with(self.user)
        self.assertEqual(self.client.session['otp_recovery_codes'], ['CODE123456'])

    def test_cancel_totp_clears_pending_device_and_keeps_otp_tab_active(self):
        TOTPDevice.objects.create(user=self.user, name='authenticator', confirmed=False)
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.post(self.settings_url, {'action': 'cancel_totp'})

        self.assertRedirects(response, self.settings_url, fetch_redirect_response=False)
        self.assertFalse(TOTPDevice.objects.filter(user=self.user, confirmed=False).exists())
        self.assertEqual(self.client.session['security_tab'], 'otp')

    @patch('accounts.views.otp_utils.generate_recovery_codes', return_value=['NEWCODE7890'])
    def test_regenerate_recovery_codes_stashes_codes_for_confirmed_device(self, mock_generate_recovery_codes):
        TOTPDevice.objects.create(user=self.user, name='authenticator', confirmed=True)
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.post(self.settings_url, {'action': 'regenerate_recovery'})

        self.assertRedirects(response, self.settings_url, fetch_redirect_response=False)
        mock_generate_recovery_codes.assert_called_once_with(self.user)
        self.assertEqual(self.client.session['otp_recovery_codes'], ['NEWCODE7890'])
        self.assertEqual(self.client.session['security_tab'], 'otp')

    def test_disable_totp_removes_confirmed_device_and_recovery_codes_device(self):
        TOTPDevice.objects.create(user=self.user, name='authenticator', confirmed=True)
        StaticDevice.objects.create(user=self.user, name='recovery')
        self.login_with_active_company(self.user, issuer=self.issuer_a)

        response = self.client.post(self.settings_url, {'action': 'disable_totp'})

        self.assertRedirects(response, self.settings_url)
        self.assertFalse(TOTPDevice.objects.filter(user=self.user, name='authenticator').exists())
        self.assertFalse(StaticDevice.objects.filter(user=self.user, name='recovery').exists())
