# Parking Radio tools

Tools that automate operating [Parking Radio](https://parking.radio), an independent non-profit radio in Québec City.
They're commands of `parkingradio`, a command-line tool that will act on the site on behalf of an admin. The site itself
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

CI runs these checks: see `.github/workflows/test.yml`.
