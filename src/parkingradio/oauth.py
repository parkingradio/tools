"""OAuth with the site, as its app "Parking Radio CLI" (see docs/design/auth.md)."""

import base64
import hashlib
import secrets
import socketserver
import time
import webbrowser
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlencode, urlsplit

import click
import httpx

from parkingradio.credentials import Tokens
from parkingradio.site import json_object, mcp_address

# The tool's OAuth client, the same whatever the site.
CLIENT_ID = "https://parking.radio/oauth/parkingradio-cli.json"

# How long `auth login` waits for the browser, in seconds.
TIMEOUT = 5 * 60

# How the browser is opened. The tests replace it, so that they never open a real one.
open_browser = webbrowser.open


class OAuthError(Exception):
    """An OAuth error that the site answered with."""

    def __init__(self, error: str, description: str | None):
        super().__init__(f"{description} ({error})" if description else error)
        self.error = error


def check_issuer(client: httpx.Client, site: str) -> None:
    """Fails unless the site's authorization server metadata says that its address is `site`."""
    response = client.get(f"{site}/.well-known/oauth-authorization-server")
    issuer = (json_object(response) or {}).get("issuer") if response.status_code == 200 else None
    if not isinstance(issuer, str):
        raise click.ClickException(f"{site} doesn't look like a Parking Radio site: it has no OAuth metadata")
    if issuer != site:
        raise click.ClickException(f"The site at {site} has {issuer} as its address: use --site {issuer}")


def authorize(site: str) -> tuple[str, str, str]:
    """Has the admin allow the tool in their browser. Returns the code, the redirect URI and the PKCE verifier."""
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(32)
    with _CallbackServer(state) as server:
        redirect_uri = f"http://127.0.0.1:{server.server_address[1]}/callback"
        query = {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": "admin",
            "state": state,
            "resource": mcp_address(site),
        }
        url = f"{site}/autoriser?{urlencode(query)}"
        click.echo(
            f"To connect to {site}, allow Parking Radio CLI on this page, which should open in your browser:\n\n"
            f"  {url}\n\nIf it doesn't, open it in the browser where you're logged in to the site.",
            err=True,
        )
        open_browser(url)
        deadline = time.monotonic() + TIMEOUT
        while server.answer is None:
            server.timeout = deadline - time.monotonic()
            if server.timeout <= 0:
                raise click.ClickException(
                    f"The browser didn't come back after {TIMEOUT // 60} minutes. If the site's page showed an error, "
                    "that's why Parking Radio CLI can't connect."
                )
            server.handle_request()
    answer = server.answer
    if answer.get("iss") != site:
        raise click.ClickException(f"The answer doesn't come from {site}: its issuer is {answer.get('iss')!r}")
    if answer.get("error") == "access_denied":
        raise click.ClickException(f"Parking Radio CLI wasn't allowed to connect to {site}")
    if "error" in answer:
        raise click.ClickException(f"{site} refused to connect Parking Radio CLI: {_error(answer)}")
    if "code" not in answer:
        raise click.ClickException(f"{site}'s answer has neither a code nor an error")
    return answer["code"], redirect_uri, verifier


def _error(answer: dict[str, str]) -> OAuthError:
    return OAuthError(answer["error"], answer.get("error_description"))


class _CallbackServer(socketserver.TCPServer):
    """Listens for the browser, on the loopback interface, until it comes back with `state`."""

    def __init__(self, state: str):
        super().__init__(("127.0.0.1", 0), _CallbackHandler)
        self.state = state
        self.answer: dict[str, str] | None = None


class _CallbackHandler(BaseHTTPRequestHandler):
    server: _CallbackServer
    # So that a connection the browser opens ahead of time, without a request, doesn't keep the server waiting.
    timeout = 5

    def do_GET(self):
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        if url.path != "/callback":
            return self._reply(404, "Not found.")
        if query.get("state") != [self.server.state]:
            return self._reply(400, "This isn't the answer Parking Radio CLI is waiting for.")
        self.server.answer = {name: values[0] for name, values in query.items()}
        if "error" in self.server.answer:
            return self._reply(200, f"Parking Radio CLI can't connect: {_error(self.server.answer)}")
        self._reply(200, "Parking Radio CLI got the site's answer: go back to the terminal. You can close this tab.")

    def _reply(self, status: int, text: str) -> None:
        body = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Requests are never logged: their query has the code.
        pass


def exchange_code(client: httpx.Client, site: str, code: str, redirect_uri: str, verifier: str) -> Tokens:
    form = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri, "code_verifier": verifier}
    return _token_request(client, site, form)


def refresh(client: httpx.Client, site: str, refresh_token: str) -> Tokens:
    return _token_request(client, site, {"grant_type": "refresh_token", "refresh_token": refresh_token})


def _token_request(client: httpx.Client, site: str, form: dict[str, str]) -> Tokens:
    """Raises OAuthError when the site answers with one."""
    # Waits longer for the answer than for other requests: when a refresh's answer doesn't come, the site may already
    # have replaced the tokens, and then the connection has ended (see the site's docs/design/server/oauth.md).
    response = client.post(
        f"{site}/api/oauth/token",
        data={**form, "client_id": CLIENT_ID, "resource": mcp_address(site)},
        timeout=httpx.Timeout(10, read=60),
    )
    body = json_object(response)
    if body is None:
        raise OAuthError("invalid_response", f"the site answered with {response.status_code}, without JSON")
    if response.status_code != 200:
        raise OAuthError(str(body.get("error", response.status_code)), body.get("error_description"))
    access_token, refresh_token = body.get("access_token"), body.get("refresh_token")
    expires_in, scope = body.get("expires_in"), body.get("scope", "")
    if (
        str(body.get("token_type")).lower() != "bearer"
        or not isinstance(access_token, str)
        or not isinstance(refresh_token, str)
        or not isinstance(expires_in, int | float)
        or not isinstance(scope, str)
    ):
        raise OAuthError("invalid_response", "the site's tokens aren't what the tool expects")
    return Tokens(access_token, time.time() + expires_in, refresh_token, scope)


def revoke(client: httpx.Client, site: str, token: str) -> None:
    """Raises httpx.HTTPError when the site can't be reached, or doesn't revoke the token."""
    client.post(f"{site}/api/oauth/revoke", data={"token": token, "client_id": CLIENT_ID}).raise_for_status()
