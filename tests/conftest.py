import base64
import hashlib
import json
import secrets
import threading
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlsplit

import filelock
import httpx
import keyring.backend
import keyring.core
import keyring.errors
import pytest
from click.testing import CliRunner

from parkingradio import credentials, oauth, site
from parkingradio.cli import main

SITE = "http://localhost:5173"


def assert_locked():
    """Fails unless the tool holds the lock under which it changes a site's tokens."""
    try:
        with filelock.FileLock(credentials.directory() / "credentials.lock", timeout=0):
            pytest.fail("The tool doesn't hold the lock")
    except filelock.Timeout:
        pass


class MemoryKeyring(keyring.backend.KeyringBackend):
    """A credential store that changes entries only under the tool's lock."""

    priority = 0

    def __init__(self):
        super().__init__()
        self.entries: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self.entries.get((service, username))

    def set_password(self, service, username, password):
        assert_locked()
        self.entries[(service, username)] = password

    def delete_password(self, service, username):
        assert_locked()
        if self.entries.pop((service, username), None) is None:
            raise keyring.errors.PasswordDeleteError(username)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """No test reaches a real site, opens a browser, or uses the system's credential store or configuration."""

    def unreachable(request):
        pytest.fail(f"A test sent a request to {request.url} without a fake site")

    def no_browser(url):
        pytest.fail(f"A test opened {url} without a fake browser")

    monkeypatch.setattr(site, "transport", httpx.MockTransport(unreachable))
    monkeypatch.setattr(oauth, "open_browser", no_browser)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("PARKINGRADIO_SITE", raising=False)
    # Without looking for the system's credential store, which keyring would otherwise do the first time it's used.
    monkeypatch.setattr(keyring.core, "_keyring_backend", MemoryKeyring())


def run(*args):
    return CliRunner().invoke(main, ["--site", SITE, *args])


@dataclass
class Connection:
    access_token: str
    refresh_token: str
    used_refresh_tokens: set[str] = field(default_factory=set)
    ended: bool = False


def _new_token():
    return secrets.token_hex(32)


def _oauth_error(error, description="", status=400):
    return httpx.Response(status, json={"error": error, "error_description": description})


def _rpc_error(status, code, id=None):
    return httpx.Response(status, json={"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": str(code)}})


class FakeSite:
    """The site at SITE, as strict as the real one is with what the tool sends (see the website's
    docs/design/server/oauth.md and mcp.md), and the admin's browser, which allows the tool by default."""

    def __init__(self):
        self.issuer = SITE
        self.server_name = "Parking Radio (development)"
        # What the browser does with the authorization page's parameters: the query of the requests it sends back to
        # the tool, as a list.
        self.browse = lambda params: [self.allow(params)]
        self.codes: dict[str, dict] = {}
        self.connections: list[Connection] = []
        # Paths whose requests fail as if the site couldn't be reached.
        self.unreachable: set[str] = set()
        # Called before answering a request to /mcp.
        self.before_mcp = lambda: None
        # Whether /mcp refuses every access token.
        self.refuse_access_tokens = False
        # Changes the token endpoint's answers.
        self.tamper = lambda tokens: tokens
        self.authorization_urls: list[str] = []
        self._callbacks: list[tuple[dict, httpx.Response]] = []
        self._threads: list[threading.Thread] = []

    @property
    def refreshes(self):
        return sum(len(connection.used_refresh_tokens) for connection in self.connections)

    @property
    def live(self):
        return [connection for connection in self.connections if not connection.ended]

    # The browser.

    @property
    def callbacks(self):
        """The browser's requests to the tool, with the tool's answers. Waits for the browser first: it can finish after
        the tool."""
        self.wait_for_browser()
        return self._callbacks

    def wait_for_browser(self):
        for thread in self._threads:
            thread.join()

    def open_browser(self, url):
        self.authorization_urls.append(url)
        assert url.startswith(f"{self.issuer}/autoriser?")
        params = dict(parse_qsl(urlsplit(url).query))
        answers = self.browse(params)

        def go_back():
            with httpx.Client(trust_env=False) as client:
                for answer in answers:
                    path = answer.pop("path", "/callback")
                    response = client.get(params["redirect_uri"].replace("/callback", path), params=answer)
                    self._callbacks.append((answer, response))

        thread = threading.Thread(target=go_back)
        thread.start()
        self._threads.append(thread)
        return True

    def allow(self, params):
        assert params["response_type"] == "code"
        assert params["client_id"] == oauth.CLIENT_ID
        assert urlsplit(params["redirect_uri"]).hostname == "127.0.0.1"
        assert urlsplit(params["redirect_uri"]).path == "/callback"
        assert params["code_challenge_method"] == "S256"
        assert params["scope"] == "admin"
        assert params["resource"] == f"{self.issuer}/mcp"
        code = _new_token()
        self.codes[code] = {"params": params, "connection": None}
        return {"code": code, "state": params["state"], "iss": self.issuer}

    # The site.

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path in self.unreachable:
            raise httpx.ConnectError("Connection refused", request=request)
        routes = {
            ("GET", "/.well-known/oauth-authorization-server"): self.metadata,
            ("POST", "/api/oauth/token"): self.token,
            ("POST", "/api/oauth/revoke"): self.revoke,
            ("POST", "/mcp"): self.mcp,
        }
        route = routes.get((request.method, request.url.path))
        return route(request) if route else httpx.Response(404, json={"ok": False, "error": "Not found"})

    def metadata(self, request):
        return httpx.Response(200, json={"issuer": self.issuer, "authorization_endpoint": f"{self.issuer}/autoriser"})

    def _form(self, request):
        """The form of a request to the token or revocation endpoint, or the error it fails with."""
        if "authorization" in request.headers:
            return None, _oauth_error("invalid_request", "Apps don't authenticate")
        if request.headers.get("content-type") != "application/x-www-form-urlencoded":
            return None, _oauth_error("invalid_request", "Not a form")
        form = dict(parse_qsl(request.content.decode()))
        if "client_secret" in form:
            return None, _oauth_error("invalid_request", "Apps don't authenticate")
        return form, None

    def _tokens(self, connection):
        tokens = {
            "access_token": connection.access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": connection.refresh_token,
            "scope": "admin",
        }
        return httpx.Response(200, json=self.tamper(tokens))

    def token(self, request):
        form, error = self._form(request)
        if error:
            return error
        if form.get("client_id") != oauth.CLIENT_ID:
            return _oauth_error("invalid_client")
        if "resource" in form and form["resource"] != f"{self.issuer}/mcp":
            return _oauth_error("invalid_target")
        if form.get("grant_type") == "authorization_code":
            issued = self.codes.get(form.get("code"))
            if issued is None:
                return _oauth_error("invalid_grant", "Unknown code")
            if issued["connection"] is not None:
                issued["connection"].ended = True
                return _oauth_error("invalid_grant", "The code was already used")
            params = issued["params"]
            if form.get("redirect_uri") != params["redirect_uri"]:
                return _oauth_error("invalid_request", "Not the redirect_uri of the code")
            verifier = form.get("code_verifier", "")
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
            if challenge != params["code_challenge"]:
                return _oauth_error("invalid_grant", "The verifier doesn't match")
            connection = Connection(_new_token(), _new_token())
            issued["connection"] = connection
            self.connections.append(connection)
            return self._tokens(connection)
        if form.get("grant_type") == "refresh_token":
            assert_locked()
            token = form.get("refresh_token")
            for connection in self.connections:
                if token in connection.used_refresh_tokens:
                    connection.ended = True
                if token == connection.refresh_token and not connection.ended:
                    connection.used_refresh_tokens.add(token)
                    connection.access_token, connection.refresh_token = _new_token(), _new_token()
                    return self._tokens(connection)
            return _oauth_error("invalid_grant", "The refresh token isn't valid")
        return _oauth_error("unsupported_grant_type")

    def revoke(self, request):
        form, error = self._form(request)
        if error:
            return error
        if "token" not in form or "client_id" not in form:
            return _oauth_error("invalid_request", "token and client_id are required")
        for connection in self.connections:
            if form["client_id"] == oauth.CLIENT_ID and form["token"] in (
                connection.access_token,
                connection.refresh_token,
            ):
                connection.ended = True
        return httpx.Response(200, json={})

    def end_access_token(self):
        """Has the access token of the live connection stop working, as if it expired, while the connection lives."""
        (connection,) = self.live
        connection.access_token = _new_token()

    def mcp(self, request):
        self.before_mcp()
        authorization = request.headers.get("authorization")
        if self.refuse_access_tokens or authorization not in [f"Bearer {c.access_token}" for c in self.live]:
            return _rpc_error(401, -32000)
        accept = request.headers.get("accept", "")
        if "application/json" not in accept or "text/event-stream" not in accept:
            return _rpc_error(406, -32000)
        if request.headers.get("content-type") != "application/json":
            return _rpc_error(415, -32000)
        message = json.loads(request.content)
        params = message.get("params", {})
        required = {"protocolVersion", "capabilities", "clientInfo"}
        if message.get("method") != "initialize" or not required <= set(params):
            return _rpc_error(200, -32602, message.get("id"))
        result = {
            "protocolVersion": params["protocolVersion"],
            "capabilities": {"tools": {}},
            "serverInfo": {"name": self.server_name, "version": "1.0.0"},
        }
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": message["id"], "result": result})


@pytest.fixture
def fake_site(monkeypatch):
    fake = FakeSite()
    monkeypatch.setattr(site, "transport", httpx.MockTransport(fake.handle))
    monkeypatch.setattr(oauth, "open_browser", fake.open_browser)
    yield fake
    fake.wait_for_browser()
