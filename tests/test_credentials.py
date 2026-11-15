import sys
from pathlib import Path

import pytest

from parkingradio import credentials


def test_directory_from_xdg_config_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert credentials.directory() == tmp_path / "parkingradio"


@pytest.mark.parametrize("xdg", [None, "relative/path"])
def test_directory_by_default(monkeypatch, tmp_path, xdg):
    if xdg is None:
        monkeypatch.delenv("XDG_CONFIG_HOME")
    else:
        monkeypatch.setenv("XDG_CONFIG_HOME", xdg)
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    monkeypatch.setattr(sys, "platform", "win32")
    assert credentials.directory() == tmp_path / "AppData" / "parkingradio"
    monkeypatch.setattr(sys, "platform", "linux")
    assert credentials.directory() == Path.home() / ".config" / "parkingradio"


def test_lock_file():
    with credentials.locked():
        assert (credentials.directory() / "credentials.lock").exists()
