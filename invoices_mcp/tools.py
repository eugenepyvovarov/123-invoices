import base64
from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from typing import Any

from .api_client import InvoicesAPIClient
from .auth import has_required_scope, required_scope_for_tool
from .config import MCPConfig, load_config
from .errors import MCPServiceError, UpstreamAPIError
from .schemas import TOOL_SCHEMAS, bounded_page, bounded_page_size, positive_id


APIClientFactory = Callable[[], InvoicesAPIClient]
FINAL_STATES = {"final", "finalized", "sent", "invoiced", "overdue", "paid", "void", "voided", "cancelled", "canceled"}


def register_tools(mcp_server, config: MCPConfig | None = None, api_client_factory: APIClientFactory | None = None):
    tools = InvoiceMCPTools(config=config, api_client_factory=api_client_factory)

    for name, schema in TOOL_SCHEMAS.items():
        method = getattr(tools, name)
        description = schema["description"]
        input_schema = deepcopy(schema["input_schema"])
        registered_tool = _register_tool(mcp_server, method, name=name, description=description)
        if registered_tool is not None and hasattr(registered_tool, "parameters"):
            registered_tool.parameters = input_schema
        _set_tool_input_schema(method, input_schema)
    return mcp_server


class InvoiceMCPTools:
    def __init__(self, config: MCPConfig | None = None, api_client_factory: APIClientFactory | None = None):
        self.config = config
        self.api_client_factory = api_client_factory

    async def search_invoices(
        self,
        query: str | None = None,
        status: str | None = None,
        customer_id: int | None = None,
        issuer_id: int | None = None,
        project_id: int | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        if error := self._scope_error("search_invoices"):
            return error
        try:
            params = _clean_params(
                {
                    "search": query,
                    "status": status,
                    "customer": customer_id,
                    "issuer": issuer_id,
                    "project": project_id,
                    "page": bounded_page(page),
                    "page_size": bounded_page_size(page_size),
                }
            )
        except ValueError as exc:
            return _error_payload(MCPServiceError("invalid_tool_input", str(exc), status_code=400))
        return await self._call(lambda client: client.request_json("GET", "invoices/", params=params))

    async def get_invoice(self, invoice_id: int) -> dict[str, Any]:
        if error := self._scope_error("get_invoice"):
            return error
        try:
            positive_id(invoice_id, "invoice_id")
        except ValueError as exc:
            return _error_payload(MCPServiceError("invalid_tool_input", str(exc), status_code=400))
        return await self._call(lambda client: client.request_json("GET", f"invoices/{invoice_id}/"))

    async def list_issuers(self, page: int = 1, page_size: int = 25) -> dict[str, Any]:
        if error := self._scope_error("list_issuers"):
            return error
        return await self._list_reference("issuers/", page=page, page_size=page_size)

    async def list_bank_accounts(self, issuer_id: int | None = None, page: int = 1, page_size: int = 25) -> dict[str, Any]:
        if error := self._scope_error("list_bank_accounts"):
            return error
        try:
            params = {"issuer": issuer_id, "page": bounded_page(page), "page_size": bounded_page_size(page_size)}
        except ValueError as exc:
            return _error_payload(MCPServiceError("invalid_tool_input", str(exc), status_code=400))
        return await self._call(lambda client: client.request_json("GET", "bank-accounts/", params=_clean_params(params)))

    async def list_customers(self, query: str | None = None, page: int = 1, page_size: int = 25) -> dict[str, Any]:
        if error := self._scope_error("list_customers"):
            return error
        return await self._list_reference("customers/", query=query, page=page, page_size=page_size)

    async def list_projects(
        self,
        customer_id: int | None = None,
        query: str | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        if error := self._scope_error("list_projects"):
            return error
        try:
            params = {"customer": customer_id, "search": query, "page": bounded_page(page), "page_size": bounded_page_size(page_size)}
        except ValueError as exc:
            return _error_payload(MCPServiceError("invalid_tool_input", str(exc), status_code=400))
        return await self._call(lambda client: client.request_json("GET", "projects/", params=_clean_params(params)))

    async def list_products(
        self,
        query: str | None = None,
        customer_id: int | None = None,
        issuer_id: int | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        if error := self._scope_error("list_products"):
            return error
        try:
            params = _clean_params(
                {
                    "search": query,
                    "customer": customer_id,
                    "issuer": issuer_id,
                    "page": bounded_page(page),
                    "page_size": bounded_page_size(page_size),
                }
            )
        except ValueError as exc:
            return _error_payload(MCPServiceError("invalid_tool_input", str(exc), status_code=400))
        result = await self._call(lambda client: client.request_json("GET", "invoice-line-suggestions/", params=params))
        if result.get("ok"):
            result["catalog_note"] = "Reusable recent invoice order-line suggestions; not a canonical product catalog."
        return result

    async def create_draft_invoice(self, invoice: Mapping[str, Any]) -> dict[str, Any]:
        if error := self._scope_error("create_draft_invoice"):
            return error
        payload = {**dict(invoice), "status": "draft"}
        return await self._call(lambda client: client.request_json("POST", "invoices/", json=payload))

    async def update_draft_invoice(self, invoice_id: int, invoice: Mapping[str, Any]) -> dict[str, Any]:
        if error := self._scope_error("update_draft_invoice"):
            return error
        try:
            positive_id(invoice_id, "invoice_id")
        except ValueError as exc:
            return _error_payload(MCPServiceError("invalid_tool_input", str(exc), status_code=400))

        async def operation(client: InvoicesAPIClient):
            current = await client.request_json("GET", f"invoices/{invoice_id}/")
            if _is_finalized(current):
                raise MCPServiceError(
                    code="invoice_not_draft",
                    message="Finalized invoices cannot be updated through the draft update tool.",
                    status_code=409,
                    next_action="Create a new draft or inspect the invoice status before retrying.",
                )
            return await client.request_json("PATCH", f"invoices/{invoice_id}/", json=dict(invoice))

        return await self._call(operation)

    async def finalize_invoice(self, invoice_id: int, confirm: bool = False) -> dict[str, Any]:
        if error := self._scope_error("finalize_invoice"):
            return error
        try:
            positive_id(invoice_id, "invoice_id")
        except ValueError as exc:
            return _error_payload(MCPServiceError("invalid_tool_input", str(exc), status_code=400))
        if confirm is not True:
            return _error_payload(
                MCPServiceError(
                    code="confirmation_required",
                    message="Set confirm=true to finalize an invoice. Finalization may be irreversible.",
                    status_code=400,
                    next_action="Inspect the invoice first, then retry with confirm=true if finalization is intended.",
                )
            )
        return await self._call(lambda client: client.request_json("POST", f"invoices/{invoice_id}/finalize/", json={"confirm": True}))

    async def generate_invoice_pdf(self, invoice_id: int) -> dict[str, Any]:
        if error := self._scope_error("generate_invoice_pdf"):
            return error
        try:
            positive_id(invoice_id, "invoice_id")
        except ValueError as exc:
            return _error_payload(MCPServiceError("invalid_tool_input", str(exc), status_code=400))
        return await self._call(lambda client: client.request_json("POST", f"invoices/{invoice_id}/generate-pdf/"))

    async def get_invoice_artifact(self, invoice_id: int, mode: str = "metadata", max_bytes: int | None = None) -> dict[str, Any]:
        if error := self._scope_error("get_invoice_artifact"):
            return error
        try:
            positive_id(invoice_id, "invoice_id")
        except ValueError as exc:
            return _error_payload(MCPServiceError("invalid_tool_input", str(exc), status_code=400))
        if mode not in {"metadata", "content"}:
            return _error_payload(MCPServiceError("invalid_artifact_mode", "mode must be metadata or content.", status_code=400))
        if max_bytes is not None and max_bytes < 1:
            return _error_payload(MCPServiceError("invalid_artifact_limit", "max_bytes must be a positive integer.", status_code=400))
        if mode == "metadata":
            result = await self._call(lambda client: client.request_json("GET", f"invoices/{invoice_id}/pdf/", params={"mode": "metadata"}))
            if result.get("ok"):
                result["data"] = _safe_artifact_metadata(invoice_id, result.get("data"))
            return result

        async def operation(client: InvoicesAPIClient):
            content, headers = await client.download(f"invoices/{invoice_id}/pdf/", max_bytes=max_bytes)
            return {
                "invoice_id": invoice_id,
                "content_type": headers.get("content-type", "application/pdf"),
                "content_length": len(content),
                "content_base64": base64.b64encode(content).decode("ascii"),
            }

        return await self._call(operation)

    async def inspect_invoice_status_history(self, invoice_id: int) -> dict[str, Any]:
        if error := self._scope_error("inspect_invoice_status_history"):
            return error
        try:
            positive_id(invoice_id, "invoice_id")
        except ValueError as exc:
            return _error_payload(MCPServiceError("invalid_tool_input", str(exc), status_code=400))

        async def operation(client: InvoicesAPIClient):
            invoice = await client.request_json("GET", f"invoices/{invoice_id}/")
            return _status_summary(invoice)

        return await self._call(operation)

    async def _list_reference(self, path: str, *, query: str | None = None, page: int = 1, page_size: int = 25) -> dict[str, Any]:
        try:
            params = _clean_params({"search": query, "page": bounded_page(page), "page_size": bounded_page_size(page_size)})
        except ValueError as exc:
            return _error_payload(MCPServiceError("invalid_tool_input", str(exc), status_code=400))
        return await self._call(lambda client: client.request_json("GET", path, params=params))

    async def _call(self, operation: Callable[[InvoicesAPIClient], Awaitable[Any]]) -> dict[str, Any]:
        client = self._make_client()
        try:
            return {"ok": True, "data": await operation(client)}
        except (MCPServiceError, UpstreamAPIError) as exc:
            return _error_payload(exc)
        except ValueError as exc:
            return _error_payload(MCPServiceError("invalid_tool_input", str(exc), status_code=400))
        finally:
            await client.close()

    def _make_client(self) -> InvoicesAPIClient:
        if self.api_client_factory is not None:
            return self.api_client_factory()
        return InvoicesAPIClient(self.config or load_config())

    def _scope_error(self, tool_name: str) -> dict[str, Any] | None:
        if self.config is None:
            return None
        if has_required_scope(tool_name, self.config):
            return None
        required_scope = required_scope_for_tool(tool_name, self.config)
        return _error_payload(
            MCPServiceError(
                code="insufficient_scope",
                message=f"The MCP access token is missing the required scope: {required_scope}.",
                status_code=403,
                next_action="Re-authorize the MCP client with the required invoice scope.",
            )
        )


def _clean_params(params: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value not in (None, "")}


def _error_payload(error: MCPServiceError) -> dict[str, Any]:
    return {"ok": False, "error": error.to_payload()}


def _register_tool(mcp_server, method, *, name: str, description: str):
    tool_manager = getattr(mcp_server, "_tool_manager", None)
    add_tool = getattr(tool_manager, "add_tool", None)
    if callable(add_tool):
        return add_tool(method, name=name, description=description)

    try:
        return mcp_server.tool(name=name, description=description)(method)
    except TypeError:
        return mcp_server.tool(description=description)(method)


def _set_tool_input_schema(method, input_schema: Mapping[str, Any]) -> None:
    target = getattr(method, "__func__", method)
    try:
        setattr(target, "__mcp_input_schema__", deepcopy(dict(input_schema)))
    except (AttributeError, TypeError):
        pass


def _safe_artifact_metadata(invoice_id: int, payload: Any) -> dict[str, Any]:
    data = payload if isinstance(payload, Mapping) else {}
    pdf = data.get("pdf") if isinstance(data.get("pdf"), Mapping) else {}
    return {
        "invoice_id": data.get("invoice_id") or invoice_id,
        "pdf": {
            "available": bool(pdf.get("available")),
            "filename": pdf.get("filename"),
            "content_type": pdf.get("content_type"),
            "size": pdf.get("size"),
        },
        "retrieval": {
            "tool": "get_invoice_artifact",
            "mode": "content",
            "requires_api_credentials": False,
        },
    }


def _is_finalized(invoice: Mapping[str, Any] | None) -> bool:
    if not isinstance(invoice, Mapping):
        return False
    status = str(invoice.get("status") or invoice.get("state") or "").lower()
    return bool(invoice.get("finalized_at") or invoice.get("is_finalized") or status in FINAL_STATES)


def _status_summary(invoice: Mapping[str, Any]) -> dict[str, Any]:
    pdf = invoice.get("pdf") or invoice.get("pdf_document") or invoice.get("artifact") or {}
    if not isinstance(pdf, Mapping):
        pdf = {"available": bool(pdf)}
    if not pdf and (invoice.get("has_pdf") or invoice.get("pdf_url")):
        pdf = {"available": bool(invoice.get("has_pdf")), "url": invoice.get("pdf_url")}
    payments = invoice.get("payments") or invoice.get("payment_applications") or []
    return {
        "invoice_id": invoice.get("id"),
        "status": invoice.get("status") or invoice.get("state"),
        "is_finalized": _is_finalized(invoice),
        "timestamps": {
            "created_at": invoice.get("created_at"),
            "updated_at": invoice.get("updated_at"),
            "issued_date": invoice.get("issued_date"),
            "due_date": invoice.get("due_date"),
            "finalized_at": invoice.get("finalized_at"),
            "paid_at": invoice.get("paid_at"),
        },
        "pdf": {
            "available": bool(pdf.get("available") or pdf.get("url") or pdf.get("filename") or pdf.get("name")),
            "generated_at": pdf.get("generated_at") or invoice.get("pdf_generated_at"),
            "content_type": pdf.get("content_type"),
            "size": pdf.get("size") or pdf.get("content_length"),
        },
        "totals": invoice.get("totals") or {"subtotal": invoice.get("subtotal"), "tax": invoice.get("tax"), "total": invoice.get("total"), "balance_due": invoice.get("balance_due")},
        "payment_activity": payments,
    }
