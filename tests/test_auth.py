import dataclasses
import time

import keyring
import keyring.backends.fail
import keyring.errors
import pytest
from click.testing import CliRunner
from conftest import SITE, run

from parkingradio import credentials, oauth, site
from parkingradio.cli import main


def assert_no_secrets(result, fake_site):
    secrets = [*fake_site.codes]
    for connection in fake_site.connections:
        secrets += [connection.access_token, connection.refresh_token, *connection.used_refresh_tokens]
    for secret in secrets:
        assert secret not in result.output
        assert secret not in result.stderr


# auth login


def test_login(fake_site):
    result = run("auth", "login")
    assert result.exit_code == 0, result.output
    assert result.stdout == f"Connected to {SITE}.\n"
    (url,) = fake_site.authorization_urls
    assert url in result.stderr
    (connection,) = fake_site.live
    tokens = credentials.load(SITE)
    assert tokens.access_token == connection.access_token
    assert tokens.refresh_token == connection.refresh_token
    assert tokens.scope == "admin"
    assert 3500 < tokens.expires_at - time.time() <= 3600
    assert_no_secrets(result, fake_site)


def test_login_refused(fake_site):
    fake_site.browse = lambda params: [{"error": "access_denied", "state": params["state"], "iss": SITE}]
    result = run("auth", "login")
    assert result.exit_code == 1
    assert "wasn't allowed" in result.stderr
    assert credentials.load(SITE) is None


def test_login_error(fake_site):
    fake_site.browse = lambda params: [
        {"error": "invalid_scope", "error_description": "Not an admin", "state": params["state"], "iss": SITE}
    ]
    result = run("auth", "login")
    assert result.exit_code == 1
    assert "Not an admin (invalid_scope)" in result.stderr
    assert credentials.load(SITE) is None


def test_login_page(fake_site):
    result = run("auth", "login")
    assert result.exit_code == 0, result.output
    ((_, response),) = fake_site.callbacks
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "go back to the terminal" in response.text


def test_login_ignores_other_requests(fake_site):
    def browse(params):
        answer = fake_site.allow(params)
        # With a code that isn't one, so that taking one of them as the answer fails.
        other = {**answer, "code": "not-a-code"}
        return [
            {"path": "/favicon.ico", **other},
            {**other, "state": "not-the-state"},
            {key: value for key, value in other.items() if key != "state"},
            answer,
        ]

    fake_site.browse = browse
    result = run("auth", "login")
    assert result.exit_code == 0, result.output
    assert [response.status_code for _, response in fake_site.callbacks] == [404, 400, 400, 200]
    assert len(fake_site.live) == 1


@pytest.mark.parametrize("iss", ["http://localhost:3000", None])
def test_login_checks_iss(fake_site, iss):
    def browse(params):
        answer = fake_site.allow(params)
        del answer["iss"]
        return [answer if iss is None else {**answer, "iss": iss}]

    fake_site.browse = browse
    result = run("auth", "login")
    assert result.exit_code == 1
    assert "doesn't come from" in result.stderr
    assert credentials.load(SITE) is None
    assert fake_site.live == []


def test_login_times_out(fake_site, monkeypatch):
    monkeypatch.setattr(oauth, "TIMEOUT", 0)
    fake_site.browse = lambda params: []
    result = run("auth", "login")
    assert result.exit_code == 1
    assert "The browser didn't come back" in result.stderr
    assert "If the site's page showed an error" in result.stderr
    assert credentials.load(SITE) is None


def test_login_checks_the_issuer_first(fake_site):
    fake_site.issuer = "http://localhost:3000"
    result = run("auth", "login")
    assert result.exit_code == 1
    assert "use --site http://localhost:3000" in result.stderr
    assert fake_site.authorization_urls == []


def test_login_site_unreachable(fake_site):
    fake_site.unreachable.add("/.well-known/oauth-authorization-server")
    result = run("auth", "login")
    assert result.exit_code == 1
    assert f"Can't reach {SITE}" in result.stderr
    assert fake_site.authorization_urls == []


def test_login_without_credential_store(fake_site):
    keyring.set_keyring(keyring.backends.fail.Keyring())
    result = run("auth", "login")
    assert result.exit_code == 1
    assert "Can't use the system's credential store" in result.stderr
    assert fake_site.authorization_urls == []


def test_login_again_revokes_the_previous_connection(fake_site):
    assert run("auth", "login").exit_code == 0
    first = fake_site.live[0]
    result = run("auth", "login")
    assert result.exit_code == 0, result.output
    assert first.ended
    (second,) = fake_site.live
    assert credentials.load(SITE).refresh_token == second.refresh_token


def test_login_again_when_revoking_fails(fake_site):
    assert run("auth", "login").exit_code == 0
    fake_site.unreachable.add("/api/oauth/revoke")
    result = run("auth", "login")
    assert result.exit_code == 0, result.output
    assert "Warning: the previous connection" in result.stderr
    assert "Vos applications connectées" in result.stderr
    assert len(fake_site.live) == 2
    assert credentials.load(SITE).refresh_token == fake_site.live[1].refresh_token


# auth status, and using the connection


def test_status_not_connected(fake_site):
    result = run("auth", "status")
    assert result.exit_code == 1
    assert result.stdout == f"Not connected to {SITE}: run `parkingradio auth login`.\n"


def test_status(fake_site):
    run("auth", "login")
    result = run("auth", "status")
    assert result.exit_code == 0, result.output
    assert f"Connected to {SITE}" in result.stdout
    assert "MCP server: Parking Radio (development)" in result.stdout
    assert "Scopes: admin" in result.stdout
    assert fake_site.refreshes == 0
    assert_no_secrets(result, fake_site)


def expire():
    with credentials.locked():
        credentials.save(SITE, dataclasses.replace(credentials.load(SITE), expires_at=time.time() + 30))


def test_status_refreshes_an_expiring_token(fake_site):
    run("auth", "login")
    expire()
    result = run("auth", "status")
    assert result.exit_code == 0, result.output
    assert fake_site.refreshes == 1
    (connection,) = fake_site.live
    assert credentials.load(SITE).access_token == connection.access_token
    assert credentials.load(SITE).refresh_token == connection.refresh_token
    assert_no_secrets(result, fake_site)


def test_refused_token_refreshes(fake_site):
    run("auth", "login")
    fake_site.end_access_token()
    result = run("auth", "status")
    assert result.exit_code == 0, result.output
    assert fake_site.refreshes == 1
    assert credentials.load(SITE).access_token == fake_site.live[0].access_token


def test_refused_token_with_newer_tokens_kept(fake_site):
    run("auth", "login")

    # Another `parkingradio` refreshes the tokens while this one sends its request, with the previous access token.
    def refresh_elsewhere():
        fake_site.before_mcp = lambda: None
        with credentials.locked(), site.client() as client:
            tokens = credentials.load(SITE)
            credentials.save(SITE, oauth.refresh(client, SITE, tokens.refresh_token))

    fake_site.before_mcp = refresh_elsewhere
    result = run("auth", "status")
    assert result.exit_code == 0, result.output
    # Only the other one's: this one used the tokens it kept.
    assert fake_site.refreshes == 1
    assert len(fake_site.live) == 1


def test_connection_ended(fake_site):
    run("auth", "login")
    fake_site.live[0].ended = True
    kept = credentials.load(SITE)
    for _ in range(2):
        result = run("auth", "status")
        assert result.exit_code == 1
        assert "ended: run `parkingradio auth login`" in result.stderr
        assert credentials.load(SITE) == kept


def test_refresh_when_site_unreachable(fake_site):
    run("auth", "login")
    expire()
    kept = credentials.load(SITE)
    fake_site.unreachable.add("/api/oauth/token")
    result = run("auth", "status")
    assert result.exit_code == 1
    assert f"Can't reach {SITE}" in result.stderr
    assert credentials.load(SITE) == kept


# auth logout


def test_logout(fake_site):
    run("auth", "login")
    result = run("auth", "logout")
    assert result.exit_code == 0, result.output
    assert result.stdout == f"Logged out of {SITE}.\n"
    assert fake_site.live == []
    assert credentials.load(SITE) is None


def test_logout_when_revoking_fails(fake_site):
    run("auth", "login")
    fake_site.unreachable.add("/api/oauth/revoke")
    result = run("auth", "logout")
    assert result.exit_code == 1
    assert "may still exist" in result.stderr
    assert credentials.load(SITE) is None
    assert len(fake_site.live) == 1


def test_logout_not_connected(fake_site):
    result = run("auth", "logout")
    assert result.exit_code == 0
    assert result.stdout == f"Not connected to {SITE}.\n"


def test_refused_after_a_refresh(fake_site):
    run("auth", "login")
    fake_site.refuse_access_tokens = True
    result = run("auth", "status")
    assert result.exit_code == 1
    assert fake_site.refreshes == 1
    assert f"The connection to {SITE} ended: run `parkingradio auth login`" in result.stderr


@pytest.mark.parametrize(
    "tamper",
    [
        lambda tokens: {**tokens, "token_type": "mac"},
        lambda tokens: {key: value for key, value in tokens.items() if key != "refresh_token"},
    ],
)
def test_tokens_are_checked(fake_site, tamper):
    fake_site.tamper = tamper
    result = run("auth", "login")
    assert result.exit_code == 1
    assert "the site's tokens aren't what the tool expects" in result.stderr
    assert credentials.load(SITE) is None


def test_login_when_the_tokens_cant_be_kept(fake_site):
    def refuse(service, username, password):
        raise keyring.errors.PasswordSetError("Locked")

    keyring.get_keyring().set_password = refuse
    result = run("auth", "login")
    assert result.exit_code == 1
    assert "Can't use the system's credential store: Locked" in result.stderr
    # The connection that the tool couldn't keep is revoked.
    assert len(fake_site.connections) == 1
    assert fake_site.live == []


def test_unreadable_tokens(fake_site):
    with credentials.locked():
        keyring.set_password(credentials.SERVICE, SITE, "not what the tool keeps")
    result = run("auth", "status")
    assert result.exit_code == 1
    assert result.stdout == f"Not connected to {SITE}: run `parkingradio auth login`.\n"
    assert run("auth", "login").exit_code == 0
    assert run("auth", "status").exit_code == 0


def test_site_from_the_environment(fake_site, monkeypatch):
    monkeypatch.setenv("PARKINGRADIO_SITE", SITE)
    result = CliRunner().invoke(main, ["auth", "status"])
    assert result.stdout == f"Not connected to {SITE}: run `parkingradio auth login`.\n"
    result = CliRunner().invoke(main, ["--site", "https://test.example", "auth", "status"])
    assert result.stdout == "Not connected to https://test.example: run `parkingradio auth login`.\n"


@pytest.mark.parametrize("command", ["login", "status", "logout"])
def test_no_site(command):
    result = CliRunner().invoke(main, ["auth", command])
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "--site" in result.stderr
    assert "PARKINGRADIO_SITE" in result.stderr


@pytest.mark.parametrize("args", [["--help"], ["--version"], ["auth", "--help"], ["auth", "login", "--help"]])
def test_no_site_needed(args):
    result = CliRunner().invoke(main, args)
    assert result.exit_code == 0
    assert result.stderr == ""
