"""`parkingradio auth`: connecting the tool to a site (see docs/design/auth.md)."""

import contextlib

import click
import httpx

from parkingradio import credentials, mcp, oauth, site


@click.group()
def auth() -> None:
    """Connect the tool to the site, as an admin."""


@auth.command()
@site.pass_site
def login(address: str) -> None:
    """Connect the tool to the site, from your browser."""
    # So that a connection isn't made that the tool can't keep.
    credentials.load(address)
    with site.client() as client:
        oauth.check_issuer(client, address)
        code, redirect_uri, verifier = oauth.authorize(address)
        try:
            tokens = oauth.exchange_code(client, address, code, redirect_uri, verifier)
        except oauth.OAuthError as error:
            raise click.ClickException(f"{address} refused to connect Parking Radio CLI: {error}") from error
        with credentials.locked():
            previous = credentials.load(address)
            try:
                credentials.save(address, tokens)
            except click.ClickException:
                # Not to leave a connection that the tool doesn't have.
                with contextlib.suppress(httpx.HTTPError):
                    oauth.revoke(client, address, tokens.refresh_token)
                raise
        click.echo(f"Connected to {address}.")
        if previous is not None:
            try:
                oauth.revoke(client, address, previous.refresh_token)
            except httpx.HTTPError as error:
                click.echo(f"Warning: the previous connection to {address} {_not_revoked(address, error)}", err=True)


@auth.command()
@site.pass_site
def status(address: str) -> None:
    """Show whether the tool is connected to the site, and if it works."""
    tokens = credentials.load(address)
    if tokens is None:
        click.echo(f"Not connected to {address}: run `parkingradio auth login`.")
        click.get_current_context().exit(1)
    with site.client() as client:
        server = mcp.initialize(client, address).get("serverInfo")
    name = server.get("name") if isinstance(server, dict) else None
    click.echo(
        f"Connected to {address}: the connection works.\n"
        f"MCP server: {name if isinstance(name, str) else '(no name)'}\n"
        f"Scopes: {tokens.scope}"
    )


@auth.command()
@site.pass_site
def logout(address: str) -> None:
    """Disconnect the tool from the site."""
    with credentials.locked():
        tokens = credentials.load(address)
        if tokens is None:
            click.echo(f"Not connected to {address}.")
            return
        failed = None
        with site.client() as client:
            try:
                oauth.revoke(client, address, tokens.refresh_token)
            except httpx.HTTPError as error:
                failed = error
        credentials.delete(address)
    if failed is not None:
        raise click.ClickException(f"Logged out of {address} here, but the connection {_not_revoked(address, failed)}")
    click.echo(f"Logged out of {address}.")


def _not_revoked(address: str, error: httpx.HTTPError) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        why = f"{address} answered with {error.response.status_code}"
    else:
        why = f"can't reach {address}: {error}"
    return (
        f"may still exist, since it couldn't be revoked ({why}): you can disconnect it from "
        '"Vos applications connectées", on the site\'s Admins page'
    )
