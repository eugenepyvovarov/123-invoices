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
import json
import urllib.error
import urllib.request
import uuid


def assert_bearer_rejected(url: str, timeout: float, *, token: str | None = None, label: str = "request") -> str:
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
        return challenge


def challenge_parameter(challenge: str, name: str) -> str | None:
    for part in challenge.split(","):
        key, separator, value = part.strip().partition("=")
        if not separator:
            continue
        if key.removeprefix("Bearer ").strip() == name:
            return value.strip().strip('"')
    return None


def fetch_json(url: str, timeout: float, *, label: str) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"{label} returned HTTP {response.status}, expected 200.")
        try:
            payload = json.loads(response.read().decode("utf-8"))
        except ValueError as exc:
            raise RuntimeError(f"{label} did not return valid JSON.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} returned non-object JSON.")
    return payload


def assert_metadata(challenge: str, timeout: float, *, prm_url: str | None = None, as_metadata_url: str | None = None) -> None:
    prm_url = prm_url or challenge_parameter(challenge, "resource_metadata")
    if not prm_url:
        raise RuntimeError("MCP OAuth challenge did not include a resource metadata URL.")

    prm = fetch_json(prm_url, timeout, label="Protected Resource Metadata")
    if not prm.get("resource"):
        raise RuntimeError("Protected Resource Metadata did not include a resource value.")
    if not prm.get("authorization_servers"):
        raise RuntimeError("Protected Resource Metadata did not include authorization_servers.")
    if not prm.get("scopes_supported"):
        raise RuntimeError("Protected Resource Metadata did not include scopes_supported.")

    if as_metadata_url:
        metadata = fetch_json(as_metadata_url, timeout, label="Authorization Server Metadata")
        if not metadata.get("authorization_endpoint") or not metadata.get("token_endpoint"):
            raise RuntimeError("Authorization Server Metadata did not include authorization/token endpoints.")
        if "S256" not in metadata.get("code_challenge_methods_supported", []):
            raise RuntimeError("Authorization Server Metadata did not advertise S256 PKCE support.")
        if metadata.get("client_id_metadata_document_supported") is not True:
            raise RuntimeError("Authorization Server Metadata did not advertise CIMD support.")


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
    parser.add_argument("--token", help="Inbound MCP OAuth access token to verify with tool discovery.")
    parser.add_argument("--wrong-audience-token", help="Bearer token expected to fail because it is bound to a different resource/audience.")
    parser.add_argument("--resource-metadata-url", help="Override Protected Resource Metadata URL when challenge URL is not reachable from the probe network.")
    parser.add_argument("--authorization-server-metadata-url", help="Optional AS metadata URL to verify from the probe network.")
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

    challenge = ""
    if not args.skip_unauthenticated:
        challenge = assert_bearer_rejected(args.url, args.timeout, label="Unauthenticated")
        assert_metadata(
            challenge,
            args.timeout,
            prm_url=args.resource_metadata_url,
            as_metadata_url=args.authorization_server_metadata_url,
        )
    if not args.skip_invalid_token:
        assert_bearer_rejected(args.url, args.timeout, token=f"invalid-{uuid.uuid4().hex}", label="Invalid-token")
    if args.wrong_audience_token:
        assert_bearer_rejected(args.url, args.timeout, token=args.wrong_audience_token, label="Wrong-audience-token")

    if args.token:
        tool_count = asyncio.run(assert_authenticated_tool_list(args.url, args.token))
        if tool_count < 1:
            raise RuntimeError("Authenticated MCP probe discovered no tools.")

        print(f"Authenticated MCP probe discovered {tool_count} tools at {args.url}.")
    else:
        print(f"OAuth challenge and metadata probe passed at {args.url}; authenticated tool discovery skipped.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"MCP probe failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
