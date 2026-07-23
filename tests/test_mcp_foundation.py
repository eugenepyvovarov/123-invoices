import asyncio
import time
from unittest import IsolatedAsyncioTestCase, TestCase

import httpx

from invoices_mcp.api_client import InvoicesAPIClient
from invoices_mcp.auth import InvoicesTokenVerifier, build_auth_settings
from invoices_mcp.config import MCPConfig, load_config
from invoices_mcp.errors import MCPConfigurationError, UpstreamAPIError
from invoices_mcp.redaction import redact_mapping
from invoices_mcp.server import create_app


def build_config(**overrides):
    values = {
        "api_base_url": "https://api.example.test/api/",
        "api_token": "upstream-secret",
        "oauth_issuer_url": "https://auth.example.test/",
        "oauth_resource_url": "https://mcp.example.test/mcp/",
        "oauth_introspection_url": "https://auth.example.test/oauth/introspect/",
    }
    values.update(overrides)
    return MCPConfig(**values)


class MCPConfigTests(TestCase):
    def test_load_config_reads_and_normalizes_environment(self):
        config = load_config(
            {
                "INVOICES_MCP_API_BASE_URL": "https://api.example.test/api",
                "INVOICES_MCP_API_TOKEN": "upstream-token",
                "INVOICES_MCP_OAUTH_ISSUER_URL": "https://auth.example.test/",
                "INVOICES_MCP_OAUTH_RESOURCE_URL": "https://mcp.example.test/mcp/",
                "INVOICES_MCP_OAUTH_INTROSPECTION_URL": "https://auth.example.test/oauth/introspect/",
                "INVOICES_MCP_AUTH_TEST_TOKENS": "first-token, second-token ",
                "INVOICES_MCP_HOST": "0.0.0.0",
                "INVOICES_MCP_PORT": "9001",
                "INVOICES_MCP_ENDPOINT_PATH": "mcp",
                "INVOICES_MCP_TIMEOUT_SECONDS": "2.5",
                "INVOICES_MCP_PUBLIC_URL": "https://invoices.example.test/mcp/",
                "INVOICES_MCP_MAX_ARTIFACT_BYTES": "1234",
            }
        )

        self.assertEqual(config.normalized_api_base_url, "https://api.example.test/api/")
        self.assertEqual(config.auth_test_tokens, ("first-token", "second-token"))
        self.assertEqual(config.oauth_issuer_url, "https://auth.example.test/")
        self.assertEqual(config.oauth_resource_url, "https://mcp.example.test/mcp/")
        self.assertEqual(config.host, "0.0.0.0")
        self.assertEqual(config.port, 9001)
        self.assertEqual(config.endpoint_path, "/mcp/")
        self.assertEqual(config.timeout_seconds, 2.5)
        self.assertEqual(config.public_url, "https://invoices.example.test/mcp/")
        self.assertEqual(config.max_artifact_bytes, 1234)

    def test_load_config_fails_safely_when_required_tokens_are_missing(self):
        with self.assertRaises(MCPConfigurationError) as context:
            load_config({"INVOICES_MCP_API_BASE_URL": "https://api.example.test/api/"})

        self.assertEqual(context.exception.code, "mcp_configuration_error")
        self.assertNotIn("upstream-secret", context.exception.message)

    def test_load_config_rejects_invalid_port(self):
        with self.assertRaises(MCPConfigurationError):
            load_config(
                {
                    "INVOICES_MCP_API_BASE_URL": "https://api.example.test/api/",
                    "INVOICES_MCP_API_TOKEN": "upstream-token",
                    "INVOICES_MCP_OAUTH_ISSUER_URL": "https://auth.example.test/",
                    "INVOICES_MCP_OAUTH_RESOURCE_URL": "https://mcp.example.test/mcp/",
                    "INVOICES_MCP_PORT": "70000",
                }
            )


class MCPAuthTests(IsolatedAsyncioTestCase):
    def test_build_auth_settings_wires_resource_server_metadata(self):
        settings = build_auth_settings(build_config())

        self.assertEqual(str(settings.issuer_url), "https://auth.example.test/")
        self.assertEqual(str(settings.resource_server_url), "https://mcp.example.test/mcp/")
        self.assertEqual(settings.required_scopes, ["invoices:mcp:read"])

    async def test_token_verifier_accepts_active_resource_bound_introspection(self):
        def handler(request):
            self.assertEqual(request.url, "https://auth.example.test/oauth/introspect/")
            self.assertIn(b"resource=https%3A%2F%2Fmcp.example.test%2Fmcp%2F", request.content)
            return httpx.Response(
                200,
                json={
                    "active": True,
                    "client_id": "client-1",
                    "scope": "invoices:mcp:read invoices:mcp:draft:write",
                    "exp": int(time.time()) + 60,
                    "iss": "https://auth.example.test/",
                    "aud": "https://mcp.example.test/mcp/",
                    "sub": "user-1",
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            access_token = await InvoicesTokenVerifier(build_config(), client=http_client).verify_token("oauth-token")

        self.assertIsNotNone(access_token)
        self.assertEqual(access_token.client_id, "client-1")
        self.assertIn("invoices:mcp:read", access_token.scopes)

    async def test_token_verifier_rejects_invalid_expired_or_wrong_audience_tokens(self):
        config = build_config()
        cases = [
            {"active": False, "aud": config.oauth_resource_url},
            {"active": True, "exp": int(time.time()) - 1, "aud": config.oauth_resource_url},
            {"active": True, "exp": int(time.time()) + 60, "aud": "https://wrong.example.test/mcp/"},
        ]

        for payload in cases:
            with self.subTest(payload=payload):
                self.assertIsNone(InvoicesTokenVerifier.access_token_from_introspection("token", payload, config))


class MCPAPIClientTests(IsolatedAsyncioTestCase):
    async def test_request_json_forwards_bearer_token_and_parses_response(self):
        seen_requests = []

        def handler(request):
            seen_requests.append(request)
            return httpx.Response(200, json={"results": [1]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = InvoicesAPIClient(build_config(), client=http_client)
            payload = await client.request_json("GET", "invoices/", params={"q": "draft"})

        self.assertEqual(payload, {"results": [1]})
        self.assertEqual(seen_requests[0].url, "https://api.example.test/api/invoices/?q=draft")
        self.assertEqual(seen_requests[0].headers["Authorization"], "Bearer upstream-secret")

    async def test_request_json_maps_upstream_validation_errors(self):
        def handler(request):
            return httpx.Response(
                400,
                json={"message": "Invalid invoice", "field_errors": {"number": ["Required"]}},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = InvoicesAPIClient(build_config(), client=http_client)
            with self.assertRaises(UpstreamAPIError) as context:
                await client.request_json("POST", "invoices/", json={})

        self.assertEqual(context.exception.code, "upstream_validation_error")
        self.assertEqual(context.exception.field_errors, {"number": ["Required"]})

    async def test_request_json_maps_timeout(self):
        def handler(request):
            raise httpx.ReadTimeout("timed out", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = InvoicesAPIClient(build_config(), client=http_client)
            with self.assertRaises(UpstreamAPIError) as context:
                await client.request_json("GET", "invoices/")

        self.assertEqual(context.exception.code, "upstream_timeout")

    async def test_request_json_maps_not_found_conflict_and_server_errors(self):
        cases = [
            (404, {"detail": "Missing"}, "upstream_not_found", 404),
            (409, {"message": "Invoice already finalized"}, "upstream_conflict", 409),
            (500, {"detail": "Server error"}, "upstream_api_error", 502),
        ]

        for status_code, payload, expected_code, expected_status in cases:
            with self.subTest(status_code=status_code):
                def handler(request):
                    return httpx.Response(status_code, json=payload)

                async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
                    client = InvoicesAPIClient(build_config(), client=http_client)
                    with self.assertRaises(UpstreamAPIError) as context:
                        await client.request_json("GET", "invoices/1/")

                self.assertEqual(context.exception.code, expected_code)
                self.assertEqual(context.exception.status_code, expected_status)
                self.assertEqual(context.exception.upstream_status_code, status_code)

    async def test_request_json_maps_request_error_to_upstream_outage(self):
        def handler(request):
            raise httpx.ConnectError("connection refused", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = InvoicesAPIClient(build_config(), client=http_client)
            with self.assertRaises(UpstreamAPIError) as context:
                await client.request_json("GET", "invoices/")

        self.assertEqual(context.exception.code, "upstream_unavailable")
        self.assertEqual(context.exception.status_code, 502)

    async def test_download_enforces_artifact_size_limit(self):
        def handler(request):
            return httpx.Response(200, content=b"abcdef")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = InvoicesAPIClient(build_config(max_artifact_bytes=5), client=http_client)
            with self.assertRaises(UpstreamAPIError) as context:
                await client.download("invoices/1/pdf/")

        self.assertEqual(context.exception.code, "artifact_too_large")


class MCPServerAndRedactionTests(TestCase):
    def test_create_app_mounts_configured_streamable_http_endpoint(self):
        class FakeMCPServer:
            def streamable_http_app(self):
                async def app(scope, receive, send):
                    await send({"type": "http.response.start", "status": 202, "headers": []})
                    await send({"type": "http.response.body", "body": b"mcp"})

                return app

        app = create_app(build_config(endpoint_path="/custom-mcp/"), mcp_server=FakeMCPServer())

        async def probe():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://mcp.test") as client:
                accepted = await client.post("/custom-mcp/")
            return accepted.status_code, accepted.content

        self.assertEqual(asyncio.run(probe()), (202, b"mcp"))

    def test_redact_mapping_removes_tokens_and_authorization_headers(self):
        redacted = redact_mapping(
            {
                "Authorization": "Bearer secret",
                "nested": {"api_token": "upstream-secret", "safe": "value"},
                "artifact_body": b"pdf bytes",
            }
        )

        self.assertEqual(redacted["Authorization"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["api_token"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["safe"], "value")
        self.assertEqual(redacted["artifact_body"], "[REDACTED]")
