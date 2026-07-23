from unittest import IsolatedAsyncioTestCase, TestCase, mock

from invoices_mcp.config import MCPConfig
from invoices_mcp.errors import UpstreamAPIError
from invoices_mcp.schemas import TOOL_SCHEMAS
from invoices_mcp.tools import InvoiceMCPTools, register_tools


class FakeAPIClient:
    def __init__(self, responses=None, downloads=None, error=None):
        self.responses = list(responses or [])
        self.downloads = list(downloads or [])
        self.error = error
        self.requests = []
        self.closed = False

    async def request_json(self, method, path, *, params=None, json=None):
        self.requests.append((method, path, params, json))
        if self.error:
            raise self.error
        return self.responses.pop(0)

    async def download(self, path, *, params=None, max_bytes=None):
        self.requests.append(("DOWNLOAD", path, params, {"max_bytes": max_bytes}))
        if self.error:
            raise self.error
        content, headers = self.downloads.pop(0)
        if max_bytes is not None and len(content) > max_bytes:
            raise UpstreamAPIError(
                code="artifact_too_large",
                message="The requested artifact exceeds the configured MCP artifact size limit.",
                status_code=413,
            )
        return content, headers

    async def close(self):
        self.closed = True


class MCPToolSchemaTests(TestCase):
    def test_all_expected_tools_have_discoverable_json_schemas(self):
        expected = {
            "search_invoices",
            "get_invoice",
            "list_issuers",
            "list_bank_accounts",
            "list_customers",
            "list_projects",
            "list_products",
            "create_draft_invoice",
            "update_draft_invoice",
            "finalize_invoice",
            "generate_invoice_pdf",
            "get_invoice_artifact",
            "inspect_invoice_status_history",
        }

        self.assertEqual(set(TOOL_SCHEMAS), expected)
        self.assertEqual(TOOL_SCHEMAS["search_invoices"]["input_schema"]["properties"]["page_size"]["maximum"], 100)
        self.assertIn("not a canonical product catalog", TOOL_SCHEMAS["list_products"]["description"])
        draft_schema = TOOL_SCHEMAS["create_draft_invoice"]["input_schema"]["properties"]["invoice"]
        self.assertEqual(draft_schema["additionalProperties"], False)
        self.assertEqual(
            draft_schema["properties"]["lines"]["items"]["additionalProperties"],
            False,
        )

    def test_register_tools_adds_each_schema_tool(self):
        class FakeTool:
            def __init__(self, name, description):
                self.name = name
                self.description = description
                self.parameters = None

        class FakeToolManager:
            def __init__(self):
                self.tools = []

            def add_tool(self, fn, *, name=None, description=None):
                tool = FakeTool(name or fn.__name__, description)
                self.tools.append(tool)
                return tool

        class FakeMCP:
            def __init__(self):
                self._tool_manager = FakeToolManager()
                self.names = []

            def tool(self, *, name=None, description=None):
                def decorator(func):
                    self.names.append((name or func.__name__, description))
                    return func

                return decorator

        fake = register_tools(FakeMCP(), api_client_factory=lambda: FakeAPIClient())

        self.assertEqual({tool.name for tool in fake._tool_manager.tools}, set(TOOL_SCHEMAS))
        self.assertEqual(
            fake._tool_manager.tools[0].parameters,
            TOOL_SCHEMAS[fake._tool_manager.tools[0].name]["input_schema"],
        )


class MCPToolCallTests(IsolatedAsyncioTestCase):
    def make_tools(self, client):
        return InvoiceMCPTools(api_client_factory=lambda: client)

    def make_configured_tools(self, client):
        config = MCPConfig(
            api_base_url="https://api.example.test/api/",
            api_token="upstream-secret",
            oauth_issuer_url="https://auth.example.test/",
            oauth_resource_url="https://mcp.example.test/mcp/",
        )
        return InvoiceMCPTools(config=config, api_client_factory=lambda: client)

    async def test_search_invoices_maps_filters_and_bounded_pagination(self):
        client = FakeAPIClient(responses=[{"results": [{"id": 1}]}])
        result = await self.make_tools(client).search_invoices(query="acme", status="draft", customer_id=2, page=2, page_size=50)

        self.assertTrue(result["ok"])
        self.assertEqual(client.requests[0], ("GET", "invoices/", {"search": "acme", "status": "draft", "customer": 2, "page": 2, "page_size": 50}, None))

    async def test_reference_and_detail_tools_use_api_endpoints(self):
        client = FakeAPIClient(responses=[{"id": 7}, {"results": []}, {"results": []}, {"results": []}, {"results": []}])
        tools = self.make_tools(client)

        await tools.get_invoice(7)
        await tools.list_issuers()
        await tools.list_bank_accounts(issuer_id=3)
        await tools.list_customers(query="Acme")
        await tools.list_projects(customer_id=9)

        self.assertEqual([request[1] for request in client.requests], ["invoices/7/", "issuers/", "bank-accounts/", "customers/", "projects/"])

    async def test_list_products_returns_reusable_suggestion_note(self):
        client = FakeAPIClient(responses=[{"results": [{"description": "Consulting", "unit_price": "100.00"}]}])
        result = await self.make_tools(client).list_products(query="consult")

        self.assertTrue(result["ok"])
        self.assertEqual(client.requests[0][1], "invoice-line-suggestions/")
        self.assertIn("not a canonical product catalog", result["catalog_note"])

    async def test_create_and_update_draft_invoice_use_api_without_model_access(self):
        client = FakeAPIClient(responses=[{"id": 1, "status": "draft"}, {"id": 1, "status": "draft"}, {"id": 1, "status": "draft", "total": "10.00"}])
        tools = self.make_tools(client)

        created = await tools.create_draft_invoice({"customer": 2, "lines": [], "status": "paid"})
        updated = await tools.update_draft_invoice(1, {"lines": [{"description": "Work"}]})

        self.assertTrue(created["ok"])
        self.assertTrue(updated["ok"])
        self.assertEqual(client.requests[0], ("POST", "invoices/", None, {"customer": 2, "lines": [], "status": "draft"}))
        self.assertEqual(client.requests[2][0:2], ("PATCH", "invoices/1/"))

    async def test_update_draft_invoice_rejects_finalized_invoice_safely(self):
        client = FakeAPIClient(responses=[{"id": 1, "status": "finalized", "finalized_at": "2026-01-01T00:00:00Z"}])
        result = await self.make_tools(client).update_draft_invoice(1, {"lines": []})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "invoice_not_draft")
        self.assertEqual(len(client.requests), 1)

    async def test_finalize_invoice_requires_confirmation_then_calls_api_action(self):
        client = FakeAPIClient(responses=[{"id": 1, "status": "finalized"}])
        tools = self.make_tools(client)

        rejected = await tools.finalize_invoice(1)
        accepted = await tools.finalize_invoice(1, confirm=True)

        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["error"]["code"], "confirmation_required")
        self.assertTrue(accepted["ok"])
        self.assertEqual(client.requests[0], ("POST", "invoices/1/finalize/", None, {"confirm": True}))

    async def test_generate_and_download_artifacts_respect_limits(self):
        client = FakeAPIClient(responses=[{"pdf": {"available": True}}], downloads=[(b"%PDF", {"content-type": "application/pdf"})])
        tools = self.make_tools(client)

        metadata = await tools.generate_invoice_pdf(4)
        artifact = await tools.get_invoice_artifact(4, mode="content", max_bytes=10)

        self.assertTrue(metadata["ok"])
        self.assertEqual(client.requests[0][0:2], ("POST", "invoices/4/generate-pdf/"))
        self.assertEqual(artifact["data"]["content_base64"], "JVBERg==")
        self.assertEqual(client.requests[1], ("DOWNLOAD", "invoices/4/pdf/", None, {"max_bytes": 10}))

    async def test_artifact_metadata_omits_storage_paths_and_api_urls(self):
        client = FakeAPIClient(
            responses=[
                {
                    "invoice_id": 4,
                    "pdf": {
                        "available": True,
                        "filename": "invoice.pdf",
                        "name": "invoices_pdf/private/invoice.pdf",
                        "url": "https://api.example.test/media/invoices_pdf/private/invoice.pdf",
                        "content_type": "application/pdf",
                        "size": 123,
                    },
                }
            ]
        )

        result = await self.make_tools(client).get_invoice_artifact(4, mode="metadata")

        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["pdf"]["filename"], "invoice.pdf")
        self.assertNotIn("name", result["data"]["pdf"])
        self.assertNotIn("url", result["data"]["pdf"])
        self.assertFalse(result["data"]["retrieval"]["requires_api_credentials"])

    async def test_artifact_limit_error_is_mcp_safe(self):
        client = FakeAPIClient(downloads=[(b"too-large", {})])
        result = await self.make_tools(client).get_invoice_artifact(4, mode="content", max_bytes=3)

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "artifact_too_large")

    async def test_status_inspection_derives_summary_from_invoice_detail(self):
        invoice = {
            "id": 8,
            "status": "draft",
            "updated_at": "2026-01-02T00:00:00Z",
            "total": "120.00",
            "pdf": {"filename": "invoice.pdf", "size": 500},
            "payment_applications": [{"amount": "20.00"}],
        }
        client = FakeAPIClient(responses=[invoice])
        result = await self.make_tools(client).inspect_invoice_status_history(8)

        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["invoice_id"], 8)
        self.assertTrue(result["data"]["pdf"]["available"])
        self.assertEqual(result["data"]["payment_activity"], [{"amount": "20.00"}])

    async def test_upstream_auth_failure_is_normalized(self):
        client = FakeAPIClient(
            error=UpstreamAPIError(
                code="upstream_authentication_failed",
                message="The MCP service could not authenticate to the invoices API.",
                status_code=401,
            )
        )
        result = await self.make_tools(client).get_invoice(1)

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "upstream_authentication_failed")

    async def test_tool_scope_failure_returns_safe_error_without_calling_upstream(self):
        client = FakeAPIClient(responses=[{"id": 1}])

        with mock.patch("invoices_mcp.tools.has_required_scope", return_value=False):
            result = await self.make_configured_tools(client).create_draft_invoice({"customer": 2, "lines": []})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "insufficient_scope")
        self.assertIn("invoices:mcp:draft:write", result["error"]["message"])
        self.assertEqual(client.requests, [])
