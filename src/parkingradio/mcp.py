"""Requests to the site's MCP server, with the connection's tokens (see Using the connection in docs/design/auth.md)."""

import time
from importlib.metadata import version
from typing import Any

import click
import httpx

from parkingradio import credentials, oauth
from parkingradio.credentials import Tokens
from parkingradio.site import json_object, mcp_address

# How long before the access token expires the tool refreshes it, in seconds.
REFRESH_MARGIN = 60


def connection_ended(site: str) -> click.ClickException:
    return click.ClickException(f"The connection to {site} ended: run `parkingradio auth login` to connect again")


def not_connected(site: str) -> click.ClickException:
    return click.ClickException(f"Not connected to {site}: run `parkingradio auth login`")


def initialize(client: httpx.Client, site: str) -> dict[str, Any]:
    params = {
        "protocolVersion": "2025-11-25",
        "capabilities": {},
        "clientInfo": {"name": "parkingradio", "version": version("parkingradio")},
    }
    return call(client, site, "initialize", params)


def call(client: httpx.Client, site: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
    """Sends a JSON-RPC request to the site's MCP server, and returns its result."""
    tokens = credentials.load(site)
    if tokens is None:
        raise not_connected(site)
    if tokens.expires_at - time.time() < REFRESH_MARGIN:
        tokens = _refresh(client, site, tokens.access_token)
    response = _post(client, site, tokens.access_token, method, params)
    if response.status_code == 401:
        tokens = _refresh(client, site, tokens.access_token)
        response = _post(client, site, tokens.access_token, method, params)
        if response.status_code == 401:
            raise connection_ended(site)
    body = json_object(response)
    if body is None:
        raise click.ClickException(f"{site}/mcp answered with {response.status_code}, without JSON")
    if "error" in body:
        error = body["error"]
        message = error.get("message") if isinstance(error, dict) else error
        raise click.ClickException(f"{site}/mcp answered with an error: {message}")
    if response.status_code != 200 or not isinstance(body.get("result"), dict):
        raise click.ClickException(f"{site}/mcp answered with {response.status_code}, without a result")
    return body["result"]


def _post(client: httpx.Client, site: str, access_token: str, method: str, params: dict[str, Any]) -> httpx.Response:
    return client.post(
        mcp_address(site),
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        headers={"Accept": "application/json, text/event-stream", "Authorization": f"Bearer {access_token}"},
    )


def _refresh(client: httpx.Client, site: str, access_token: str) -> Tokens:
    """New tokens, unless those kept no longer have `access_token`, because another `parkingradio` already changed them:
    those are then used as they are."""
    with credentials.locked():
        tokens = credentials.load(site)
        if tokens is None:
            raise not_connected(site)
        if tokens.access_token != access_token:
            return tokens
        try:
            tokens = oauth.refresh(client, site, tokens.refresh_token)
        except oauth.OAuthError as error:
            if error.error == "invalid_grant":
                raise connection_ended(site) from error
            raise click.ClickException(f"{site} refused to refresh the connection's tokens: {error}") from error
        credentials.save(site, tokens)
        return tokens
