"""The connections' tokens, kept in the system's credential store, one entry per site (see Credentials in
docs/design/README.md)."""

import json
import os
import sys
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

import click
import filelock
import keyring
import keyring.errors

SERVICE = "parkingradio"


@dataclass
class Tokens:
    access_token: str
    # When the access token expires, in seconds since the epoch.
    expires_at: float
    refresh_token: str
    scope: str


def directory() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    if os.path.isabs(xdg):
        base = Path(xdg)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path.home() / ".config"
    return base / "parkingradio"


@contextmanager
def locked():
    """Holds the lock under which a site's tokens are read, then changed."""
    path = directory()
    path.mkdir(parents=True, exist_ok=True)
    with filelock.FileLock(path / "credentials.lock"):
        yield


@contextmanager
def _store():
    try:
        yield
    except keyring.errors.KeyringError as error:
        raise click.ClickException(f"Can't use the system's credential store: {error}") from error


def load(site: str) -> Tokens | None:
    """The site's tokens, or None when there are none, or when they can't be read, e.g. after a change of the tool:
    either way, the tool has to be connected again."""
    with _store():
        value = keyring.get_password(SERVICE, site)
    try:
        return None if value is None else Tokens(**json.loads(value))
    except (ValueError, TypeError):
        return None


def save(site: str, tokens: Tokens) -> None:
    with _store():
        keyring.set_password(SERVICE, site, json.dumps(asdict(tokens)))


def delete(site: str) -> None:
    with _store():
        keyring.delete_password(SERVICE, site)
