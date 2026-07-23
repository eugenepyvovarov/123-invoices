#!/usr/bin/env python3
"""Probe the invoices Streamable HTTP MCP endpoint.

The probe verifies both auth boundaries expected during rollout/runtime smoke:
unauthenticated requests must be rejected, while an authenticated MCP client can
complete the protocol initialize flow and discover tools.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import urllib.error
import urllib.request
import uuid


def assert_bearer_rejected(url: str, timeout: float, *, token: str | None = None, label: str = "request") -> None:
    request = urllib.request.Request(url, data=b"{}", method="POST")
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raise RuntimeError(f"{label} MCP probe unexpectedly returned HTTP {response.status}.")
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            raise RuntimeError(f"{label} MCP probe returned HTTP {exc.code}, expected 401.") from exc
        challenge = exc.headers.get("WWW-Authenticate", "")
        if "Bearer" not in challenge or "resource_metadata=" not in challenge:
            raise RuntimeError(f"{label} MCP probe did not return an OAuth resource_metadata challenge.") from exc


async def assert_authenticated_tool_list(url: str, token: str) -> int:
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError as exc:  # pragma: no cover - exercised only in incomplete runtime images
        raise RuntimeError("The MCP SDK is required to run the MCP probe.") from exc

    headers = {"Authorization": f"Bearer {token}"}
    async with streamablehttp_client(url, headers=headers) as (read_stream, write_stream, _get_session_id):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools_result = await session.list_tools()

    return len(tools_result.tools)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify invoices MCP protocol reachability.")
    parser.add_argument("--url", required=True, help="Streamable HTTP MCP endpoint URL, e.g. http://127.0.0.1:8765/mcp/")
    parser.add_argument("--token", required=True, help="Inbound MCP client bearer token to verify.")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds for the unauthenticated probe.")
    parser.add_argument(
        "--skip-unauthenticated",
        action="store_true",
        help="Skip the unauthenticated 401 probe when an external gateway handles auth before the MCP service.",
    )
    parser.add_argument(
        "--skip-invalid-token",
        action="store_true",
        help="Skip the invalid bearer-token 401 probe when an external gateway handles auth before the MCP service.",
    )
    args = parser.parse_args(argv)

    if not args.skip_unauthenticated:
        assert_bearer_rejected(args.url, args.timeout, label="Unauthenticated")
    if not args.skip_invalid_token:
        assert_bearer_rejected(args.url, args.timeout, token=f"invalid-{uuid.uuid4().hex}", label="Invalid-token")

    tool_count = asyncio.run(assert_authenticated_tool_list(args.url, args.token))
    if tool_count < 1:
        raise RuntimeError("Authenticated MCP probe discovered no tools.")

    print(f"Authenticated MCP probe discovered {tool_count} tools at {args.url}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"MCP probe failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
