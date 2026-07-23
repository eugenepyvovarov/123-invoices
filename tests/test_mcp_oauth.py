from datetime import timedelta
from contextlib import contextmanager
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
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
    MCP_OAUTH_CIMD_CACHE_SECONDS=60,
    MCP_OAUTH_CIMD_TIMEOUT_SECONDS=1,
    MCP_OAUTH_CIMD_MAX_BYTES=512,
)
class MCPOAuthCIMDTests(TestCase):
    client_id = 'https://client.example.test/oauth/client-metadata.json'
    redirect_uri = 'https://client.example.test/callback'

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_authorize_fetches_valid_cimd_metadata_and_registers_public_client(self):
        with self._mock_fetch(
            {
                'client_id': self.client_id,
                'client_name': '  Example\nMCP Client  ',
                'redirect_uris': [self.redirect_uri],
            }
        ) as mocks:
            response = self._authorize(self.client_id, self.redirect_uri)

        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])
        mocks.assert_called_once()
        app = get_application_model().objects.get(client_id=self.client_id)
        self.assertEqual(app.name, 'Example MCP Client')
        self.assertEqual(app.client_type, get_application_model().CLIENT_PUBLIC)
        self.assertEqual(app.redirect_uris, self.redirect_uri)

    def test_invalid_cimd_metadata_is_rejected(self):
        with self._mock_fetch({'client_id': 'https://other.example.test/client.json', 'redirect_uris': [self.redirect_uri]}):
            response = self._authorize(self.client_id, self.redirect_uri)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'invalid_client_metadata')
        self.assertFalse(get_application_model().objects.filter(client_id=self.client_id).exists())

    def test_redirect_uri_must_match_metadata(self):
        with self._mock_fetch({'client_id': self.client_id, 'redirect_uris': [self.redirect_uri]}):
            response = self._authorize(self.client_id, 'https://client.example.test/other-callback')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'invalid_request')

    def test_caches_valid_metadata(self):
        with self._mock_fetch({'client_id': self.client_id, 'redirect_uris': [self.redirect_uri]}) as mocks:
            first = self._authorize(self.client_id, self.redirect_uri)
            get_application_model().objects.filter(client_id=self.client_id).delete()
            second = self._authorize(self.client_id, self.redirect_uri)

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        mocks.assert_called_once()

    def test_rejects_unsafe_metadata_and_redirect_hosts(self):
        cases = [
            ('http://client.example.test/metadata.json', self.redirect_uri),
            ('file:///tmp/client.json', self.redirect_uri),
            ('https://localhost/client.json', self.redirect_uri),
            (self.client_id, 'https://127.0.0.1/callback'),
        ]
        for client_id, redirect_uri in cases:
            with self.subTest(client_id=client_id, redirect_uri=redirect_uri):
                if client_id == self.client_id:
                    context = self._mock_fetch({'client_id': client_id, 'redirect_uris': [redirect_uri]})
                else:
                    context = self._mock_fetch({'client_id': client_id, 'redirect_uris': [redirect_uri]})
                with context:
                    response = self._authorize(client_id, redirect_uri)
                self.assertEqual(response.status_code, 400)

    def test_rejects_oversized_metadata_document(self):
        with self._mock_fetch(
            {'client_id': self.client_id, 'redirect_uris': [self.redirect_uri], 'padding': 'x' * 600}
        ):
            response = self._authorize(self.client_id, self.redirect_uri)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'invalid_client_metadata')

    def test_preregistered_client_takes_priority_over_cimd(self):
        user = get_user_model().objects.create_user(username='owner')
        get_application_model().objects.create(
            name='Pre-registered Hermes',
            user=user,
            client_id=self.client_id,
            client_type=get_application_model().CLIENT_PUBLIC,
            authorization_grant_type=get_application_model().GRANT_AUTHORIZATION_CODE,
            redirect_uris=self.redirect_uri,
        )
        with patch('mcp_oauth.cimd.urlopen') as urlopen_mock:
            response = self._authorize(self.client_id, self.redirect_uri)

        self.assertEqual(response.status_code, 302)
        urlopen_mock.assert_not_called()
        self.assertEqual(get_application_model().objects.get(client_id=self.client_id).name, 'Pre-registered Hermes')

    def _authorize(self, client_id, redirect_uri):
        return self.client.get(
            reverse('oauth2_provider:authorize'),
            {
                'response_type': 'code',
                'client_id': client_id,
                'redirect_uri': redirect_uri,
                'scope': 'invoices:mcp:read',
                'code_challenge': 'x' * 43,
                'code_challenge_method': 'S256',
                'resource': MCP_RESOURCE,
            },
        )

    def _mock_fetch(self, payload, *, content_type='application/json'):
        response = _CIMDResponse(payload, content_type=content_type)
        return _mock_cimd_fetch(response)


@contextmanager
def _mock_cimd_fetch(response):
    with patch('mcp_oauth.cimd.urlopen', Mock(return_value=response)) as urlopen_mock:
        with patch('mcp_oauth.cimd._resolve_host_addresses', Mock(return_value=['93.184.216.34'])):
            yield urlopen_mock


class _CIMDResponse:
    def __init__(self, payload, *, content_type='application/json'):
        import json

        self._body = json.dumps(payload).encode()
        self.headers = {'Content-Type': content_type}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size=-1):
        if size == -1:
            return self._body
        return self._body[:size]


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
