import asyncio
from unittest import IsolatedAsyncioTestCase, TestCase, mock

import httpx

from invoices_mcp.api_client import InvoicesAPIClient
from invoices_mcp.auth import BearerAuthASGIMiddleware, extract_bearer_token, is_authorized, token_matches
from invoices_mcp.config import MCPConfig, load_config
from invoices_mcp.errors import MCPConfigurationError, UpstreamAPIError
from invoices_mcp.redaction import redact_mapping
from invoices_mcp.server import create_app


def build_config(**overrides):
    values = {
        "api_base_url": "https://api.example.test/api/",
        "api_token": "upstream-secret",
        "client_tokens": ("client-secret",),
    }
    values.update(overrides)
    return MCPConfig(**values)


class MCPConfigTests(TestCase):
    def test_load_config_reads_and_normalizes_environment(self):
        config = load_config(
            {
                "INVOICES_MCP_API_BASE_URL": "https://api.example.test/api",
                "INVOICES_MCP_API_TOKEN": "upstream-token",
                "INVOICES_MCP_CLIENT_TOKENS": "first-token, second-token ",
                "INVOICES_MCP_HOST": "0.0.0.0",
                "INVOICES_MCP_PORT": "9001",
                "INVOICES_MCP_ENDPOINT_PATH": "mcp",
                "INVOICES_MCP_TIMEOUT_SECONDS": "2.5",
                "INVOICES_MCP_PUBLIC_URL": "https://invoices.example.test/mcp/",
                "INVOICES_MCP_MAX_ARTIFACT_BYTES": "1234",
            }
        )

        self.assertEqual(config.normalized_api_base_url, "https://api.example.test/api/")
        self.assertEqual(config.client_tokens, ("first-token", "second-token"))
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
                    "INVOICES_MCP_CLIENT_TOKENS": "client-token",
                    "INVOICES_MCP_PORT": "70000",
                }
            )


class MCPAuthTests(IsolatedAsyncioTestCase):
    def test_extract_bearer_token_accepts_only_bearer_scheme(self):
        self.assertEqual(extract_bearer_token("Bearer abc123"), "abc123")
        self.assertEqual(extract_bearer_token("bearer abc123"), "abc123")
        self.assertIsNone(extract_bearer_token("Basic abc123"))
        self.assertIsNone(extract_bearer_token(None))

    def test_token_matching_uses_constant_time_compare_for_each_configured_token(self):
        with mock.patch("invoices_mcp.auth.hmac.compare_digest", wraps=__import__("hmac").compare_digest) as compare:
            self.assertTrue(token_matches("second", ("first", "second")))

        self.assertEqual(compare.call_count, 2)
        compare.assert_any_call("second", "first")
        compare.assert_any_call("second", "second")

    def test_auth_fails_when_no_client_tokens_are_configured(self):
        with self.assertRaises(MCPConfigurationError):
            is_authorized("Bearer anything", ())

    async def test_auth_middleware_rejects_missing_or_invalid_bearer_token(self):
        async def app(scope, receive, send):
            response = httpx.Response(200, json={"ok": True})
            await send({"type": "http.response.start", "status": response.status_code, "headers": []})
            await send({"type": "http.response.body", "body": response.content})

        transport = httpx.ASGITransport(app=BearerAuthASGIMiddleware(app, ("valid-token",)))
        async with httpx.AsyncClient(transport=transport, base_url="http://mcp.test") as client:
            missing = await client.post("/mcp/")
            invalid = await client.post("/mcp/", headers={"Authorization": "Bearer invalid"})
            valid = await client.post("/mcp/", headers={"Authorization": "Bearer valid-token"})

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(invalid.status_code, 401)
        self.assertEqual(valid.status_code, 200)


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

    async def test_download_enforces_artifact_size_limit(self):
        def handler(request):
            return httpx.Response(200, content=b"abcdef")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = InvoicesAPIClient(build_config(max_artifact_bytes=5), client=http_client)
            with self.assertRaises(UpstreamAPIError) as context:
                await client.download("invoices/1/pdf/")

        self.assertEqual(context.exception.code, "artifact_too_large")


class MCPServerAndRedactionTests(TestCase):
    def test_create_app_mounts_configured_streamable_http_endpoint_with_auth(self):
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
                rejected = await client.post("/custom-mcp/")
                accepted = await client.post("/custom-mcp/", headers={"Authorization": "Bearer client-secret"})
            return rejected.status_code, accepted.status_code, accepted.content

        self.assertEqual(asyncio.run(probe()), (401, 202, b"mcp"))

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
