"""The site the tool acts on (see Site in docs/design/README.md), and how it's reached."""

import functools
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import click
import httpx

# What requests to sites go through: None for the network. The tests replace it, so that they never reach a real site.
transport: httpx.BaseTransport | None = None


def parse(value: str) -> str:
    """The site's address, from what `--site` or `PARKINGRADIO_SITE` gives, or a usage error."""
    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    try:
        valid_port = parts.port is None or parts.port > 0
    except ValueError:
        valid_port = False
    host = parts.hostname
    if (
        scheme not in ("https", "http")
        or not host
        or not valid_port
        or "@" in parts.netloc
        or parts.path not in ("", "/")
        or "?" in value
        or "#" in value
    ):
        raise click.BadParameter(f"{value!r} isn't a site's address, e.g. https://parking.radio")
    if scheme == "http" and host != "localhost":
        raise click.BadParameter(f"{value!r}: only http://localhost can be used without https")
    return f"{scheme}://{parts.netloc.lower()}"


def pass_site(command: Callable[..., Any]) -> Callable[..., Any]:
    """Passes the site's address to `command`, which is a usage error without one."""

    @functools.wraps(command)
    def with_site(*args, **kwargs):
        address = click.get_current_context().obj
        if address is None:
            raise click.UsageError(
                "No site to act on: give its address with --site, before the command, or with PARKINGRADIO_SITE, e.g. "
                "https://parking.radio"
            )
        return command(address, *args, **kwargs)

    return with_site


def mcp_address(site: str) -> str:
    """The site's MCP server, which the connection's tokens are for."""
    return f"{site}/mcp"


def client() -> httpx.Client:
    """What requests to sites are sent with. When one can't reach the site, `parkingradio` fails, and says so (see
    cli.py)."""
    return httpx.Client(transport=transport, timeout=10)


def json_object(response: httpx.Response) -> dict[str, Any] | None:
    """The response's body, when it's a JSON object."""
    try:
        body = response.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None
