from __future__ import annotations

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 25
MAX_ARTIFACT_BYTES_FIELD = "max_bytes"

LINE_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "line_type": {"type": "string", "enum": ["time", "flat", "quantity", "expense"]},
        "description": {"type": "string", "maxLength": 255},
        "quantity": {"type": ["number", "string"]},
        "unit_price": {"type": ["number", "string"]},
        "line_total": {"type": ["number", "string"]},
        "manual_total": {"type": "boolean"},
        "notes": {"type": "string"},
    },
    "additionalProperties": False,
}

DRAFT_INVOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "issuer": {"type": "integer", "minimum": 1},
        "customer": {"type": "integer", "minimum": 1},
        "project": {"type": "integer", "minimum": 1},
        "bank_account": {"type": ["integer", "null"], "minimum": 1},
        "issued_date": {"type": "string", "format": "date"},
        "due_date": {"type": ["string", "null"], "format": "date"},
        "reference_number": {"type": "string", "maxLength": 64},
        "notes": {"type": "string"},
        "comment": {"type": "string"},
        "tax_value": {"type": ["number", "string"]},
        "discount_value": {"type": ["number", "string"]},
        "secondary_tax_rate": {"type": ["number", "string"]},
        "secondary_tax_name": {"type": "string", "maxLength": 64},
        "uses_secondary_tax": {"type": "boolean"},
        "lines": {"type": "array", "items": LINE_ITEM_SCHEMA},
    },
    "additionalProperties": False,
}


def bounded_page(value: int | None, *, default: int = 1) -> int:
    if value is None:
        return default
    if value < 1:
        raise ValueError("page must be at least 1")
    return value


def bounded_page_size(value: int | None, *, default: int = DEFAULT_PAGE_SIZE) -> int:
    if value is None:
        return default
    if value < 1 or value > MAX_PAGE_SIZE:
        raise ValueError(f"page_size must be between 1 and {MAX_PAGE_SIZE}")
    return value


def positive_id(value: int, field: str = "id") -> int:
    if value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


TOOL_SCHEMAS: dict[str, dict] = {
    "search_invoices": {
        "description": "Search invoices through the authenticated invoices API with bounded pagination.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "status": {"type": "string"},
                "customer_id": {"type": "integer", "minimum": 1},
                "issuer_id": {"type": "integer", "minimum": 1},
                "project_id": {"type": "integer", "minimum": 1},
                "page": {"type": "integer", "minimum": 1, "default": 1},
                "page_size": {"type": "integer", "minimum": 1, "maximum": MAX_PAGE_SIZE, "default": DEFAULT_PAGE_SIZE},
            },
            "additionalProperties": False,
        },
    },
    "get_invoice": {
        "description": "Retrieve one invoice by ID through the authenticated invoices API.",
        "input_schema": {"type": "object", "properties": {"invoice_id": {"type": "integer", "minimum": 1}}, "required": ["invoice_id"], "additionalProperties": False},
    },
    "list_issuers": {"description": "List invoice issuers.", "input_schema": {"type": "object", "properties": {"page": {"type": "integer", "minimum": 1}, "page_size": {"type": "integer", "minimum": 1, "maximum": MAX_PAGE_SIZE}}, "additionalProperties": False}},
    "list_bank_accounts": {"description": "List issuer bank accounts.", "input_schema": {"type": "object", "properties": {"issuer_id": {"type": "integer", "minimum": 1}, "page": {"type": "integer", "minimum": 1}, "page_size": {"type": "integer", "minimum": 1, "maximum": MAX_PAGE_SIZE}}, "additionalProperties": False}},
    "list_customers": {"description": "List invoice customers.", "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "page": {"type": "integer", "minimum": 1}, "page_size": {"type": "integer", "minimum": 1, "maximum": MAX_PAGE_SIZE}}, "additionalProperties": False}},
    "list_projects": {"description": "List customer projects.", "input_schema": {"type": "object", "properties": {"customer_id": {"type": "integer", "minimum": 1}, "query": {"type": "string"}, "page": {"type": "integer", "minimum": 1}, "page_size": {"type": "integer", "minimum": 1, "maximum": MAX_PAGE_SIZE}}, "additionalProperties": False}},
    "list_products": {"description": "List reusable recent invoice order-line suggestions; this is not a canonical product catalog.", "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "customer_id": {"type": "integer", "minimum": 1}, "issuer_id": {"type": "integer", "minimum": 1}, "page": {"type": "integer", "minimum": 1}, "page_size": {"type": "integer", "minimum": 1, "maximum": MAX_PAGE_SIZE}}, "additionalProperties": False}},
    "create_draft_invoice": {"description": "Create a draft invoice through the invoices API.", "input_schema": {"type": "object", "properties": {"invoice": {**DRAFT_INVOICE_SCHEMA, "required": ["issuer"]}}, "required": ["invoice"], "additionalProperties": False}},
    "update_draft_invoice": {"description": "Update a draft invoice through the invoices API after checking finalized-invoice safety.", "input_schema": {"type": "object", "properties": {"invoice_id": {"type": "integer", "minimum": 1}, "invoice": DRAFT_INVOICE_SCHEMA}, "required": ["invoice_id", "invoice"], "additionalProperties": False}},
    "finalize_invoice": {"description": "Finalize an invoice only when explicitly confirmed.", "input_schema": {"type": "object", "properties": {"invoice_id": {"type": "integer", "minimum": 1}, "confirm": {"type": "boolean", "const": True}}, "required": ["invoice_id", "confirm"], "additionalProperties": False}},
    "generate_invoice_pdf": {"description": "Ask the invoices API to generate or refresh invoice PDF metadata.", "input_schema": {"type": "object", "properties": {"invoice_id": {"type": "integer", "minimum": 1}}, "required": ["invoice_id"], "additionalProperties": False}},
    "get_invoice_artifact": {"description": "Download an invoice artifact through API-approved PDF download flow, subject to MCP size limits.", "input_schema": {"type": "object", "properties": {"invoice_id": {"type": "integer", "minimum": 1}, "mode": {"type": "string", "enum": ["metadata", "content"], "default": "metadata"}, MAX_ARTIFACT_BYTES_FIELD: {"type": "integer", "minimum": 1}}, "required": ["invoice_id"], "additionalProperties": False}},
    "inspect_invoice_status_history": {"description": "Return a derived invoice status summary from current API fields, PDF state, totals, and payment activity.", "input_schema": {"type": "object", "properties": {"invoice_id": {"type": "integer", "minimum": 1}}, "required": ["invoice_id"], "additionalProperties": False}},
}
