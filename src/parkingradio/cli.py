import click
import httpx

from parkingradio import site
from parkingradio.auth import auth


class _Main(click.Group):
    def invoke(self, context: click.Context):
        # Whatever request can't reach the site, unless a command handles it itself, e.g. revoking a token.
        try:
            return super().invoke(context)
        except httpx.TransportError as error:
            raise click.ClickException(f"Can't reach {context.obj}: {error}") from error
        except httpx.HTTPError as error:
            raise click.ClickException(f"A request to {context.obj} failed: {error}") from error


@click.group(name="parkingradio", cls=_Main)
@click.version_option(package_name="parkingradio")
@click.option(
    "--site",
    "address",
    metavar="ADDRESS",
    envvar="PARKINGRADIO_SITE",
    callback=lambda _context, _parameter, value: None if value is None else site.parse(value),
    help="The site to act on, e.g. https://parking.radio, or http://localhost:5173 for a development server. Also "
    "PARKINGRADIO_SITE.",
)
@click.pass_context
def main(context: click.Context, address: str | None) -> None:
    """Tools that automate operating Parking Radio."""
    context.obj = address


main.add_command(auth)
