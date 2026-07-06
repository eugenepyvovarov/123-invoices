from __future__ import annotations

import argparse

import uvicorn
from starlette.applications import Starlette
from starlette.responses import RedirectResponse
from starlette.routing import Mount, Route

from .auth import BearerAuthASGIMiddleware
from .config import MCPConfig, load_config
from .errors import MCPConfigurationError
from .tools import register_tools


SERVICE_NAME = "invoices"


def create_mcp_server(config: MCPConfig | None = None):
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - covered by dependency installation in CI
        raise MCPConfigurationError("The MCP SDK is not installed.") from exc

    if config is None:
        return register_tools(FastMCP(SERVICE_NAME), config)
    server = FastMCP(
        SERVICE_NAME,
        host=config.host,
        port=config.port,
        streamable_http_path=config.endpoint_path,
    )
    return register_tools(server, config)


def create_mcp_asgi_app(config: MCPConfig | None = None, mcp_server=None):
    server = mcp_server or create_mcp_server(config)
    if not hasattr(server, "streamable_http_app"):
        raise MCPConfigurationError("The installed MCP SDK does not support Streamable HTTP.")
    return server.streamable_http_app()


async def redirect_to_mcp(request):
    return RedirectResponse(url="/mcp/")


def create_app(config: MCPConfig | None = None, mcp_server=None) -> Starlette:
    config = config or load_config()
    mcp_app = BearerAuthASGIMiddleware(create_mcp_asgi_app(config, mcp_server), config.client_tokens)
    return Starlette(
        routes=[
            Route("/", redirect_to_mcp, methods=["GET"]),
            Mount("/", app=mcp_app, name="mcp"),
        ]
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the invoices Streamable HTTP MCP service.")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args(argv)

    config = load_config()
    uvicorn.run(
        create_app(config),
        host=args.host or config.host,
        port=args.port or config.port,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
