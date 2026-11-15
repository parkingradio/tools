# Parking Radio tools

Tools that automate operating [Parking Radio](https://parking.radio), an independent non-profit radio in Québec City.
They're commands of `parkingradio`, a command-line tool that acts on the site on behalf of an admin. The site itself
is in [parkingradio/website](https://github.com/parkingradio/website).

## Design

See [docs/design](docs/design/README.md) for what the tool does: its conventions, and each of its commands.

## Installing

With [uv](https://docs.astral.sh/uv/):

```sh
uv tool install git+https://github.com/parkingradio/tools
parkingradio --help
```

`uv tool upgrade parkingradio` installs the latest version.

## Connecting to the site

The tool acts on the site whose address `PARKINGRADIO_SITE` gives, e.g. `https://parking.radio` for production, or
`--site`, before the command, e.g. `parkingradio --site http://localhost:5173 auth login` for a development server. It
has no default, so that it never acts on production by accident. Each site has its own connection.

It acts on the site as an admin, who connects it once, from their browser, on the computer it runs on:

```sh
parkingradio auth login
```

This opens the site's page where you allow "Parking Radio CLI" to act as you, once logged in as an admin. If the browser
doesn't open, open the link that the command shows. The tool then keeps the connection's tokens in your system's
credential store (the Windows Credential Manager, the macOS Keychain, or the Secret Service on Linux).

```sh
parkingradio auth status    # whether the tool is connected, and whether the connection works
parkingradio auth logout    # disconnects the tool, and deletes its tokens
```

The connection ends when it's disconnected from the site's Admins page, under "Vos applications connectées", or after 90
days without being used: run `parkingradio auth login` again.

## Development

The tool is a Python package, `parkingradio`, in `src/parkingradio`, managed with uv, which installs the Python it needs
when it isn't there. Its dependencies are locked in `uv.lock`.

```sh
uv sync                     # creates .venv, with the tool and the development dependencies
uv run parkingradio --help  # runs the tool from the checkout
uv run pytest               # runs the tests
uv run ruff check           # lints
uv run ruff format          # formats
```

CI runs these checks: see `.github/workflows/test.yml`. The tests never reach a site, open a browser, or use the
system's credential store: they use fakes of them (see `tests/conftest.py`). To try the tool on a development server of
the site (see the site's README), use `--site` or `PARKINGRADIO_SITE`, as in [Connecting to the
site](#connecting-to-the-site).
