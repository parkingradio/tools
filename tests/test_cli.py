import shutil
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

from click.testing import CliRunner

from parkingradio.cli import main


def test_help():
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert result.stdout.startswith("Usage: parkingradio")
    assert result.stderr == ""


def test_no_command_shows_usage():
    result = CliRunner().invoke(main, [])
    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr.startswith("Usage: parkingradio")
    assert main.help in result.stderr


def test_usage_error():
    result = CliRunner().invoke(main, ["--bogus"])
    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr.startswith("Usage: parkingradio")
    assert "--bogus" in result.stderr


def test_version():
    # Through the `parkingradio` script that installing the package creates, next to the interpreter.
    script = shutil.which("parkingradio", path=Path(sys.executable).parent)
    assert script is not None
    result = subprocess.run([script, "--version"], capture_output=True, text=True, check=True)
    assert version("parkingradio") in result.stdout
