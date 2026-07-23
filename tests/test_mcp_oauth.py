from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from oauth2_provider.models import get_access_token_model, get_application_model

from mcp_oauth.models import AccessTokenResource


MCP_RESOURCE = 'https://mcp.example.test/mcp/'
MCP_ISSUER = 'https://invoices.example.test'


@override_settings(
    MCP_OAUTH_ISSUER_URL=MCP_ISSUER,
    MCP_OAUTH_RESOURCE_URL=MCP_RESOURCE,
)
class MCPOAuthMetadataTests(TestCase):
    def test_authorization_server_metadata_advertises_pkce_scopes_and_cimd(self):
        response = self.client.get('/.well-known/oauth-authorization-server')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['issuer'], MCP_ISSUER)
        self.assertEqual(payload['authorization_endpoint'], f'{MCP_ISSUER}/o/authorize/')
        self.assertEqual(payload['token_endpoint'], f'{MCP_ISSUER}/o/token/')
        self.assertEqual(payload['code_challenge_methods_supported'], ['S256'])
        self.assertTrue(payload['client_id_metadata_document_supported'])
        self.assertTrue(payload['resource_indicators_supported'])
        self.assertIn('invoices:mcp:read', payload['scopes_supported'])

    def test_protected_resource_metadata_points_to_in_app_authorization_server(self):
        response = self.client.get('/.well-known/oauth-protected-resource')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['resource'], MCP_RESOURCE)
        self.assertEqual(payload['authorization_servers'], [MCP_ISSUER])
        self.assertIn('invoices:mcp:draft:write', payload['scopes_supported'])


@override_settings(
    MCP_OAUTH_ISSUER_URL=MCP_ISSUER,
    MCP_OAUTH_RESOURCE_URL=MCP_RESOURCE,
)
class MCPOAuthProtocolTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='oauth-user',
            email='oauth-user@example.test',
            password='password',
        )
        self.application = self._create_application(
            client_id='mcp-client',
            client_type=get_application_model().CLIENT_PUBLIC,
        )

    def test_oauth_toolkit_is_configured_for_pkce_and_short_lived_tokens(self):
        from django.conf import settings

        provider_settings = settings.OAUTH2_PROVIDER
        self.assertIs(provider_settings['PKCE_REQUIRED'], True)
        self.assertEqual(provider_settings['ACCESS_TOKEN_EXPIRE_SECONDS'], 3600)
        self.assertEqual(provider_settings['OAUTH2_VALIDATOR_CLASS'], 'mcp_oauth.validators.MCPOAuth2Validator')

    def test_authorize_rejects_missing_or_wrong_resource_before_redirect(self):
        response = self.client.get(
            reverse('oauth2_provider:authorize'),
            {
                'response_type': 'code',
                'client_id': self.application.client_id,
                'redirect_uri': 'https://client.example.test/callback',
                'scope': 'invoices:mcp:read',
                'code_challenge': 'x' * 43,
                'code_challenge_method': 'S256',
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'invalid_target')

        response = self.client.get(
            reverse('oauth2_provider:authorize'),
            {
                'response_type': 'code',
                'client_id': self.application.client_id,
                'redirect_uri': 'https://client.example.test/callback',
                'scope': 'invoices:mcp:read',
                'code_challenge': 'x' * 43,
                'code_challenge_method': 'S256',
                'resource': 'https://other.example.test/mcp/',
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'invalid_target')

    def test_authorize_allows_exact_resource_and_leaves_redirect_uri_validation_to_dot(self):
        response = self.client.get(
            reverse('oauth2_provider:authorize'),
            {
                'response_type': 'code',
                'client_id': self.application.client_id,
                'redirect_uri': 'https://client.example.test/callback',
                'scope': 'invoices:mcp:read',
                'code_challenge': 'x' * 43,
                'code_challenge_method': 'S256',
                'resource': MCP_RESOURCE,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])

    def test_token_rejects_invalid_resource_before_invalid_client_details_leak(self):
        response = self.client.post(
            reverse('oauth2_provider:token'),
            {
                'grant_type': 'authorization_code',
                'code': 'invalid-code',
                'client_id': self.application.client_id,
                'redirect_uri': 'https://client.example.test/callback',
                'code_verifier': 'x' * 43,
                'resource': 'https://other.example.test/mcp/',
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'invalid_target')

    def test_confidential_clients_can_be_preregistered(self):
        confidential = self._create_application(
            client_id='hermes-confidential',
            client_type=get_application_model().CLIENT_CONFIDENTIAL,
        )

        self.assertEqual(confidential.client_type, get_application_model().CLIENT_CONFIDENTIAL)
        self.assertEqual(confidential.authorization_grant_type, get_application_model().GRANT_AUTHORIZATION_CODE)

    def _create_application(self, *, client_id, client_type):
        Application = get_application_model()
        kwargs = {
            'name': client_id,
            'user': self.user,
            'client_id': client_id,
            'client_type': client_type,
            'authorization_grant_type': Application.GRANT_AUTHORIZATION_CODE,
            'redirect_uris': 'https://client.example.test/callback',
        }
        if client_type == Application.CLIENT_CONFIDENTIAL:
            kwargs['client_secret'] = 'secret'
        return Application.objects.create(**kwargs)


@override_settings(
    MCP_OAUTH_ISSUER_URL=MCP_ISSUER,
    MCP_OAUTH_RESOURCE_URL=MCP_RESOURCE,
)
class MCPOAuthIntrospectionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='token-user',
            email='token-user@example.test',
        )
        Application = get_application_model()
        self.application = Application.objects.create(
            name='mcp-client',
            user=self.user,
            client_id='mcp-client',
            client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris='https://client.example.test/callback',
        )

    def test_introspection_shapes_active_token_for_mcp_token_verifier(self):
        access_token = self._create_access_token(
            token='active-token',
            expires=timezone.now() + timedelta(minutes=10),
            scope='invoices:mcp:read invoices:mcp:artifact:read',
        )
        AccessTokenResource.objects.create(access_token=access_token, resource=MCP_RESOURCE)

        response = self.client.post('/oauth/introspect/', {'token': 'active-token', 'resource': MCP_RESOURCE})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['active'])
        self.assertEqual(payload['client_id'], 'mcp-client')
        self.assertEqual(payload['iss'], MCP_ISSUER)
        self.assertEqual(payload['aud'], MCP_RESOURCE)
        self.assertEqual(payload['resource'], MCP_RESOURCE)
        self.assertEqual(payload['scope'], 'invoices:mcp:read invoices:mcp:artifact:read')

    def test_introspection_rejects_expired_unknown_and_wrong_resource_tokens(self):
        self._create_access_token(
            token='expired-token',
            expires=timezone.now() - timedelta(seconds=1),
            scope='invoices:mcp:read',
        )
        wrong_resource_token = self._create_access_token(
            token='wrong-resource-token',
            expires=timezone.now() + timedelta(minutes=10),
            scope='invoices:mcp:read',
        )
        AccessTokenResource.objects.create(
            access_token=wrong_resource_token,
            resource='https://other.example.test/mcp/',
        )

        cases = ['missing-token', 'expired-token', 'wrong-resource-token']
        for token in cases:
            with self.subTest(token=token):
                response = self.client.post('/oauth/introspect/', {'token': token, 'resource': MCP_RESOURCE})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {'active': False})

    @override_settings(MCP_OAUTH_INTROSPECTION_TOKEN='probe-secret')
    def test_introspection_can_require_service_authentication(self):
        response = self.client.post('/oauth/introspect/', {'token': 'anything', 'resource': MCP_RESOURCE})
        self.assertEqual(response.status_code, 401)

        response = self.client.post(
            '/oauth/introspect/',
            {'token': 'anything', 'resource': MCP_RESOURCE},
            HTTP_AUTHORIZATION='Bearer probe-secret',
        )
        self.assertEqual(response.status_code, 200)

    def _create_access_token(self, *, token, expires, scope):
        return get_access_token_model().objects.create(
            user=self.user,
            application=self.application,
            token=token,
            expires=expires,
            scope=scope,
        )
